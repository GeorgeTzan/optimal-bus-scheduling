import math
import random
import time
import json
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from services.legality_checker import (
    SolverParameters,
    ConstraintsData,
    check_assignment_legality,
    get_transfer_duration,
)


VERSION_TAG = "v1.8-Optimized-HotLoop"


@dataclass
class SAConfig:
    max_iters: int = 10000
    moves_per_temp: int = 1
    start_temp: float = 100.0
    end_temp: float = 0.1
    cooling: float = 0.9999
    log_every: int = 1000
    seed: Optional[int] = 42
    reheat_threshold: int = 5000
    reheat_temp_ratio: float = 0.5


@dataclass
class SAWeights:
    unassigned_trip: float = 100_000_000.0
    unused_bus: float = 50_000.0
    overtime_minutes: float = 100.0
    idle_minutes: float = 1.0
    transfer_penalty: float = 10.0
    fairness_term: float = 5.0
    return_to_base_penalty: float = 200.0


_STATION_MAP = {}


def _get_station_idx(station_code: str) -> int:
    if station_code in _STATION_MAP:
        return _STATION_MAP[station_code]
    try:
        idx = int(station_code) - 1
        _STATION_MAP[station_code] = idx
        return idx
    except (ValueError, TypeError):
        return -1


def _trip_key(trip: Dict[str, Any]) -> Tuple[str, int]:
    return (trip.get("id", ""), int(trip.get("start_minutes", 0)))


def _reconstruct_driver_trips(
    full_data: Dict[str, Any],
    greedy_result: Dict[str, Any],
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]]]:
    trips = full_data.get("trips", [])
    trip_by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
    trips_by_id: Dict[str, List[Dict[str, Any]]] = {}

    for t in trips:
        key = _trip_key(t)
        trip_by_key[key] = t
        tid = t.get("id", "")
        trips_by_id.setdefault(tid, []).append(t)

    def resolve_trip(trip_id: str) -> Optional[Dict[str, Any]]:
        candidates = trips_by_id.get(trip_id, [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        candidates_sorted = sorted(candidates, key=lambda x: x.get("start_minutes", 0))
        return candidates_sorted[0]

    resources = {r.get("busId", ""): r for r in full_data.get("resources", [])}
    driver_trips: Dict[str, List[Dict[str, Any]]] = {}

    for state in greedy_result.get("busStates", []):
        bus_id = state.get("busId", "")
        resource = resources.get(bus_id, {})
        _ = resource.get("driverId", state.get("driverId", ""))
        assigned_ids = state.get("assignedTrips", [])
        resolved: List[Dict[str, Any]] = []
        for tid in assigned_ids:
            t = resolve_trip(tid)
            if t is not None:
                resolved.append(t)
        resolved.sort(key=lambda x: x.get("start_minutes", 0))
        driver_trips[bus_id] = resolved

    return driver_trips, resources


def _duty_minutes(trips: List[Dict[str, Any]]) -> int:
    if not trips:
        return 0
    start = int(trips[0].get("start_minutes", 0))
    end = int(trips[-1].get("end_minutes", 0))
    if end < start:
        end += 1440
    return max(0, end - start)


def _idle_minutes(trips: List[Dict[str, Any]], transit_minutes: int) -> int:
    if len(trips) <= 1:
        return 0
    idle = 0
    for a, b in zip(trips, trips[1:]):
        a_end = int(a.get("end_minutes", 0))
        b_start = int(b.get("start_minutes", 0))
        if b_start < a_end:
            b_start += 1440
        gap = b_start - a_end
        idle += max(0, gap)
    return idle


def _overtime_over_8h_minutes(duty_minutes: int) -> int:
    return max(0, duty_minutes - 8 * 60)


def _transfer_minutes_and_mismatch(
    trips: List[Dict[str, Any]],
    resource: Dict[str, Any],
    params: SolverParameters,
    constraints: ConstraintsData,
) -> Tuple[int, int]:
    if not trips:
        return 0, 0

    transfer_time = 0
    home_station = resource.get("homeStation")
    first_trip = trips[0]
    if home_station and first_trip.get("startStation") != home_station:
        transfer_time += get_transfer_duration(
            home_station, first_trip.get("startStation"), constraints, params
        )

    for a, b in zip(trips, trips[1:]):
        a_end_st = a.get("endStation")
        b_start_st = b.get("startStation")
        if a_end_st != b_start_st:
            transfer_time += get_transfer_duration(
                a_end_st, b_start_st, constraints, params
            )

    mismatch = 0
    last_end_station = trips[-1].get("endStation")
    if home_station and last_end_station != home_station:
        mismatch = 1

    return transfer_time, mismatch


def _fairness_penalty(duties: List[int]) -> float:
    if not duties:
        return 0.0
    avg = sum(duties) / len(duties)
    return sum((d - avg) ** 2 for d in duties) / len(duties)


def _compute_driver_cost(
    trips: List[Dict[str, Any]],
    resource: Dict[str, Any],
    params: SolverParameters,
    constraints: ConstraintsData,
    weights: SAWeights,
    target_duty: float = 540.0,
) -> float:
    """Compute cost for a single driver. unused drivers get penalized!"""

    if not trips:
        return weights.unused_bus + (target_duty**2) * weights.fairness_term / 100.0

    cost = 0.0

    first_start = trips[0].get("start_minutes", 0)
    last_end = trips[-1].get("end_minutes", 0)

    if last_end < first_start:
        duty_minutes = (1440 - first_start) + last_end
    else:
        duty_minutes = last_end - first_start

    work_minutes = sum(t.get("duration_minutes", 0) for t in trips)
    idle_minutes = max(0, duty_minutes - work_minutes)

    if duty_minutes > 480:
        cost += (duty_minutes - 480) * weights.overtime_minutes

    cost += idle_minutes * weights.idle_minutes

    # Transfer/Virtual Drom penalty
    home = resource.get("homeStation", "")
    if home:
        if trips[0].get("startStation") != home:
            cost += weights.transfer_penalty * 30
        if trips[-1].get("endStation") != home:
            cost += weights.return_to_base_penalty

    for i in range(len(trips) - 1):
        if trips[i].get("endStation") != trips[i + 1].get("startStation"):
            cost += weights.transfer_penalty * 30

    deviation = duty_minutes - target_duty
    cost += (deviation**2) * weights.fairness_term / 100.0

    return cost


def compute_cost(
    driver_trips: Dict[str, List[Dict[str, Any]]],
    resources: Dict[str, Dict[str, Any]],
    params: SolverParameters,
    constraints: ConstraintsData,
    weights: SAWeights,
    unassigned_trips: List[Dict[str, Any]] = None,
    target_duty: float = 480.0,
) -> Tuple[float, Dict[str, Any]]:
    num_drivers = len(resources)
    total_cost = 0.0

    all_duties = []
    total_idle = 0
    total_overtime = 0
    total_transfer = 0
    total_mismatch = 0
    used_buses = 0

    for bus_id, trips in driver_trips.items():
        res = resources.get(bus_id, {})
        total_cost += _compute_driver_cost(
            trips, res, params, constraints, weights, target_duty
        )

        duty = _duty_minutes(trips)
        all_duties.append(duty)
        if trips:
            used_buses += 1
            trans_min, mismatch = _transfer_minutes_and_mismatch(
                trips, res, params, constraints
            )
            total_transfer += trans_min
            total_mismatch += mismatch
            total_idle += _idle_minutes(trips, params.transit_minutes)
            total_overtime += _overtime_over_8h_minutes(duty)

    num_unassigned = len(unassigned_trips) if unassigned_trips else 0
    total_cost += num_unassigned * weights.unassigned_trip

    unused_count = num_drivers - used_buses
    if unused_count > 0:
        total_cost += unused_count * weights.unused_bus

    metrics = {
        "fairness": _fairness_penalty(all_duties),
        "totalIdle": total_idle,
        "totalOver8h": total_overtime,
        "totalTransfer": total_transfer,
        "baseMismatch": total_mismatch,
        "unusedBuses": unused_count,
        "unassigned": num_unassigned,
    }

    return total_cost, metrics


def _is_legal_sequence(
    trips: List[Dict[str, Any]],
    resource: Dict[str, Any],
    params: SolverParameters,
    constraints: ConstraintsData,
    day_index: int,
) -> bool:
    """Optimized legality check: avoids re-sorting if possible."""
    if not trips:
        return True

    sorted_trips = trips
    if len(trips) > 1:
        if any(
            trips[i]["start_minutes"] > trips[i + 1]["start_minutes"]
            for i in range(len(trips) - 1)
        ):
            sorted_trips = sorted(trips, key=lambda x: x.get("start_minutes", 0))

    assigned = []
    for t in sorted_trips:
        ok, _ = check_assignment_legality(
            t,
            resource,
            assigned,
            params,
            day_index,
            constraints,
        )
        if not ok:
            return False
        assigned.append(t)
    return True


def _pick_random_trip(
    driver_trips: Dict[str, List[Dict[str, Any]]],
) -> Optional[Tuple[str, int]]:
    non_empty = [bus_id for bus_id, trips in driver_trips.items() if trips]
    if not non_empty:
        return None
    bus_id = random.choice(non_empty)
    idx = random.randrange(len(driver_trips[bus_id]))
    return bus_id, idx


def _perform_sa_move_inplace(
    current: Dict[str, List[Dict[str, Any]]],
    current_unassigned: List[Dict[str, Any]],
    current_cost: float,
    resources: Dict[str, Dict[str, Any]],
    params: SolverParameters,
    constraints_data: ConstraintsData,
    weights: SAWeights,
    temp: float,
    day_index: int,
    worst_drivers: List[str],
    chain_map: Dict[str, List[str]],
    target_duty: float = 480.0,
) -> Tuple[float, bool]:
    move_type = random.random()
    unassigned_move_prob = 0.25 if current_unassigned else 0.0

    if worst_drivers and random.random() < 0.4:
        bus_a = random.choice(worst_drivers)
        if not current[bus_a]:
            bus_a = random.choice(list(current.keys()))
    else:
        bus_a = random.choice(list(current.keys()))

    old_a_cost = _compute_driver_cost(
        current[bus_a],
        resources.get(bus_a, {}),
        params,
        constraints_data,
        weights,
        target_duty,
    )
    old_b_cost = 0.0
    old_unassigned_cost = len(current_unassigned) * weights.unassigned_trip

    backup_unassigned = None
    backup_a = None
    backup_b = None
    bus_b = None

    if move_type < unassigned_move_prob and current_unassigned:
        trip = random.choice(current_unassigned)
        new_trips = sorted(
            current[bus_a] + [trip], key=lambda x: x.get("start_minutes", 0)
        )
        if _is_legal_sequence(
            new_trips, resources.get(bus_a, {}), params, constraints_data, day_index
        ):
            backup_a = list(current[bus_a])
            backup_unassigned = list(current_unassigned)
            current[bus_a] = new_trips
            current_unassigned[:] = [
                t for t in current_unassigned if t["id"] != trip["id"]
            ]
        else:
            return current_cost, False

    elif move_type < 0.5:
        # Swap
        if current[bus_a]:
            idx_a = random.randrange(len(current[bus_a]))
        else:
            pick_a = _pick_random_trip(current)
            if not pick_a:
                return current_cost, False
            bus_a, idx_a = pick_a
            old_a_cost = _compute_driver_cost(
                current[bus_a],
                resources.get(bus_a, {}),
                params,
                constraints_data,
                weights,
                target_duty,
            )

        pick_b = _pick_random_trip(current)
        if not pick_b:
            return current_cost, False
        bus_b, idx_b = pick_b
        if bus_a == bus_b:
            return current_cost, False

        old_b_cost = _compute_driver_cost(
            current[bus_b],
            resources.get(bus_b, {}),
            params,
            constraints_data,
            weights,
            target_duty,
        )

        ta_id = current[bus_a][idx_a].get("id", "")
        tb_id = current[bus_b][idx_b].get("id", "")

        chain_a = chain_map.get(ta_id, [ta_id])
        chain_b = chain_map.get(tb_id, [tb_id])

        trips_a_chain = [t for t in current[bus_a] if t.get("id", "") in chain_a]
        trips_b_chain = [t for t in current[bus_b] if t.get("id", "") in chain_b]

        trips_a_new = sorted(
            [t for t in current[bus_a] if t.get("id", "") not in chain_a]
            + trips_b_chain,
            key=lambda x: x.get("start_minutes", 0),
        )
        trips_b_new = sorted(
            [t for t in current[bus_b] if t.get("id", "") not in chain_b]
            + trips_a_chain,
            key=lambda x: x.get("start_minutes", 0),
        )

        if _is_legal_sequence(
            trips_a_new, resources.get(bus_a, {}), params, constraints_data, day_index
        ) and _is_legal_sequence(
            trips_b_new, resources.get(bus_b, {}), params, constraints_data, day_index
        ):
            backup_a = list(current[bus_a])
            backup_b = list(current[bus_b])
            current[bus_a] = trips_a_new
            current[bus_b] = trips_b_new
        else:
            return current_cost, False

    else:
        # Transfer trip to another driver
        if current[bus_a]:
            idx_a = random.randrange(len(current[bus_a]))
        else:
            pick_a = _pick_random_trip(current)
            if not pick_a:
                return current_cost, False
            bus_a, idx_a = pick_a
            old_a_cost = _compute_driver_cost(
                current[bus_a],
                resources.get(bus_a, {}),
                params,
                constraints_data,
                weights,
                target_duty,
            )

        bus_b = random.choice(list(current.keys()))
        if bus_a == bus_b:
            return current_cost, False

        old_b_cost = _compute_driver_cost(
            current[bus_b],
            resources.get(bus_b, {}),
            params,
            constraints_data,
            weights,
            target_duty,
        )

        trip = current[bus_a][idx_a]
        trip_id = trip.get("id", "")

        chain_members = chain_map.get(trip_id, [trip_id])

        trips_to_move = [t for t in current[bus_a] if t.get("id", "") in chain_members]

        trips_a = [t for t in current[bus_a] if t.get("id", "") not in chain_members]

        trips_b = sorted(
            current[bus_b] + trips_to_move, key=lambda x: x.get("start_minutes", 0)
        )

        if _is_legal_sequence(
            trips_b, resources.get(bus_b, {}), params, constraints_data, day_index
        ):
            backup_a = list(current[bus_a])
            backup_b = list(current[bus_b])
            current[bus_a] = trips_a
            current[bus_b] = trips_b
        else:
            return current_cost, False

    new_a_cost = _compute_driver_cost(
        current[bus_a],
        resources.get(bus_a, {}),
        params,
        constraints_data,
        weights,
        target_duty,
    )
    new_b_cost = (
        _compute_driver_cost(
            current[bus_b],
            resources.get(bus_b, {}),
            params,
            constraints_data,
            weights,
            target_duty,
        )
        if bus_b
        else 0.0
    )
    new_unassigned_cost = len(current_unassigned) * weights.unassigned_trip

    delta = (new_a_cost + new_b_cost + new_unassigned_cost) - (
        old_a_cost + old_b_cost + old_unassigned_cost
    )
    new_total_cost = current_cost + delta

    if delta <= 0 or random.random() < math.exp(-delta / max(1e-9, temp)):
        return new_total_cost, True

    if backup_a is not None:
        current[bus_a] = backup_a
    if backup_b is not None:
        current[bus_b] = backup_b
    if backup_unassigned is not None:
        current_unassigned[:] = backup_unassigned
    return current_cost, False


def _build_chain_mapping(full_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Build a mapping from each trip ID to its chain members.
    Returns: {trip_id: [trip_id_1, trip_id_2, ...]} for all trips in a chain
    """
    chain_map: Dict[str, List[str]] = {}
    constraints = full_data.get("constraints", {}) if full_data else {}

    all_pairs = []

    for seq in constraints.get("mandatorySequences", []):
        ids = seq.get("tripIds", []) if isinstance(seq, dict) else seq
        for i in range(len(ids) - 1):
            all_pairs.append((ids[i], ids[i + 1]))

    for joint in constraints.get("mandatoryConnections", []):
        u_id = joint.get("incomingTripId")
        v_id = joint.get("outgoingTripId")
        if u_id and v_id:
            all_pairs.append((u_id, v_id))

    visited = set()
    for start_id, _ in all_pairs:
        if start_id in visited:
            continue

        chain = []
        current = start_id
        while current and current not in visited:
            chain.append(current)
            visited.add(current)
            next_id = None
            for u, v in all_pairs:
                if u == current:
                    next_id = v
                    break
            current = next_id

        if chain:
            for trip_id in chain:
                chain_map[trip_id] = chain

    return chain_map


def optimize_with_simulated_annealing(
    full_data: Dict[str, Any],
    greedy_result: Dict[str, Any],
    params: Optional[SolverParameters] = None,
    constraints_data: Optional[ConstraintsData] = None,
    config: Optional[SAConfig] = None,
    weights: Optional[SAWeights] = None,
    day_index: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    if params is None:
        params = SolverParameters.from_data(full_data)
    if constraints_data is None:
        constraints_data = ConstraintsData.from_data(full_data)
    if config is None:
        config = SAConfig()
    if weights is None:
        weights = SAWeights()

    meta = full_data.get("metaData", {}) if full_data else {}
    if day_index is None:
        day_index = int(meta.get("dayOfPeriod", 1))

    if config.seed is not None:
        random.seed(config.seed)

    driver_trips, resources = _reconstruct_driver_trips(full_data, greedy_result)

    unassigned_ids = set(greedy_result.get("unassignedTrips", []))
    all_trips = full_data.get("trips", [])
    current_unassigned = [t for t in all_trips if t.get("id") in unassigned_ids]

    for bus_id in resources.keys():
        driver_trips.setdefault(bus_id, [])

    best = {k: list(v) for k, v in driver_trips.items()}
    best_unassigned = list(current_unassigned)

    num_drivers = len(resources)
    total_work = sum(
        sum(t.get("duration_minutes", 0) for t in trips)
        for trips in driver_trips.values()
    )
    target_duty = (total_work / num_drivers) * 1.2 if num_drivers > 0 else 480.0
    target_duty = max(target_duty, 300.0)

    chain_map = _build_chain_mapping(full_data)

    best_cost, best_metrics = compute_cost(
        best, resources, params, constraints_data, weights, best_unassigned, target_duty
    )

    current = {k: list(v) for k, v in driver_trips.items()}
    current_cost = best_cost
    current_unassigned = list(best_unassigned)

    refiner = {k: list(v) for k, v in driver_trips.items()}
    refiner_cost = best_cost
    refiner_unassigned = list(best_unassigned)

    temp = config.start_temp
    refiner_temp = 2.0

    it = 0
    iters_since_best = 0
    start_ts = time.time()
    worst_drivers = []
    last_logged_unassigned = best_metrics["unassigned"]

    while it < config.max_iters:
        if it % 500 == 0:
            worst_drivers = _get_worst_drivers(
                current, resources, params, constraints_data, weights, target_duty
            )

        for _ in range(config.moves_per_temp):
            it += 1

            current_cost, accepted = _perform_sa_move_inplace(
                current,
                current_unassigned,
                current_cost,
                resources,
                params,
                constraints_data,
                weights,
                temp,
                day_index,
                worst_drivers,
                chain_map,
                target_duty,
            )

            if current_cost < best_cost:
                best_cost, best_metrics = compute_cost(
                    current,
                    resources,
                    params,
                    constraints_data,
                    weights,
                    current_unassigned,
                    target_duty,
                )
                best = {k: list(v) for k, v in current.items()}
                best_unassigned = list(current_unassigned)
                iters_since_best = 0
            else:
                iters_since_best += 1

            refiner_cost, _ = _perform_sa_move_inplace(
                refiner,
                refiner_unassigned,
                refiner_cost,
                resources,
                params,
                constraints_data,
                weights,
                refiner_temp,
                day_index,
                worst_drivers,
                chain_map,
                target_duty,
            )

            if refiner_cost < best_cost:
                best_cost, best_metrics = compute_cost(
                    refiner,
                    resources,
                    params,
                    constraints_data,
                    weights,
                    refiner_unassigned,
                    target_duty,
                )
                best = {k: list(v) for k, v in refiner.items()}
                best_unassigned = list(refiner_unassigned)
                iters_since_best = 0

            if it % 1000 == 0 and best_cost < current_cost:
                current = {k: list(v) for k, v in best.items()}
                current_unassigned = list(best_unassigned)
                current_cost = best_cost

            if not accepted and random.random() < 0.01:
                current = {k: list(v) for k, v in best.items()}
                current_unassigned = list(best_unassigned)
                current_cost = best_cost

            cur_unassigned = best_metrics["unassigned"]
            unassigned_changed = cur_unassigned != last_logged_unassigned

            should_log = False
            if unassigned_changed:
                should_log = True
                last_logged_unassigned = cur_unassigned
            elif cur_unassigned == 0 and it % config.log_every == 0:
                should_log = True

            if verbose and config.log_every and should_log:
                elapsed = time.time() - start_ts
                print(
                    f"[SA] it={it} temp={temp:.2f} cost={best_cost:.1f} "
                    f"tr={best_metrics['totalTransfer']} mismatch={best_metrics['baseMismatch']} "
                    f"idle={best_metrics['totalIdle']} over8h={best_metrics['totalOver8h']} "
                    f"unassigned={best_metrics['unassigned']} t={elapsed:.1f}s"
                )

            if it >= config.max_iters:
                break

        if iters_since_best >= config.reheat_threshold:
            reheat_to = max(temp * 2.5, config.start_temp * config.reheat_temp_ratio)
            if verbose:
                print(
                    f" [REHEAT] it={it} - Stagnation at {best_cost:.1f}. Temp {temp:.2f} -> {reheat_to:.2f}"
                )
            temp = reheat_to
            current = {k: list(v) for k, v in best.items()}
            current_unassigned = list(best_unassigned)
            current_cost = best_cost
            iters_since_best = 0

        cooling_factor = config.cooling
        if temp < 5.0:
            cooling_factor = 0.998
        temp *= cooling_factor
        if temp < config.end_temp:
            temp = config.end_temp

    assignments: List[Dict[str, Any]] = []
    bus_states: List[Dict[str, Any]] = []

    for bus_id, trips in best.items():
        res = resources.get(bus_id, {})
        driver_id = res.get("driverId", "")
        assigned_ids = [t.get("id", "") for t in trips]

        driving = sum(t.get("time", {}).get("durationMinutes", 0) for t in trips)
        idle = _idle_minutes(trips, params.transit_minutes)

        transfers = []
        home_station = res.get("homeStation")

        if home_station and trips:
            first_trip = trips[0]
            if first_trip.get("startStation") != home_station:
                dur = get_transfer_duration(
                    home_station,
                    first_trip.get("startStation"),
                    constraints_data,
                    params,
                )
                transfers.append(
                    {
                        "type": "VIRTUAL",
                        "fromStation": home_station,
                        "toStation": first_trip.get("startStation"),
                        "startMinutes": first_trip.get("start_minutes", 0) - dur,
                        "endMinutes": first_trip.get("start_minutes", 0),
                        "duration": dur,
                    }
                )

        for a, b in zip(trips, trips[1:]):
            a_end_st = a.get("endStation")
            b_start_st = b.get("startStation")
            if a_end_st != b_start_st:
                dur = get_transfer_duration(
                    a_end_st, b_start_st, constraints_data, params
                )
                transfers.append(
                    {
                        "type": "VIRTUAL",
                        "fromStation": a_end_st,
                        "toStation": b_start_st,
                        "startMinutes": b.get("start_minutes", 0) - dur,
                        "endMinutes": b.get("start_minutes", 0),
                        "duration": dur,
                    }
                )

        if home_station and trips:
            last_trip = trips[-1]
            if last_trip.get("endStation") != home_station:
                dur = get_transfer_duration(
                    last_trip.get("endStation"),
                    home_station,
                    constraints_data,
                    params,
                )
                transfers.append(
                    {
                        "type": "VIRTUAL",
                        "fromStation": last_trip.get("endStation"),
                        "toStation": home_station,
                        "startMinutes": last_trip.get("end_minutes", 0),
                        "endMinutes": last_trip.get("end_minutes", 0) + dur,
                        "duration": dur,
                    }
                )

        bus_states.append(
            {
                "driverId": driver_id,
                "busId": bus_id,
                "homeStation": home_station,
                "currentStation": (
                    trips[-1].get("endStation", res.get("currentStation", ""))
                    if trips
                    else res.get("currentStation", "")
                ),
                "assignedTrips": assigned_ids,
                "transfers": transfers,
                "totalIdleTime": idle,
                "totalDrivingTime": driving,
            }
        )

        for tid in assigned_ids:
            assignments.append({"tripId": tid, "driverId": driver_id, "busId": bus_id})

    used = [b for b in bus_states if b["assignedTrips"]]
    unused = [b for b in bus_states if not b["assignedTrips"]]

    unassigned_ids_final = [t["id"] for t in best_unassigned]

    #_save_run_log(config, weights, best_metrics, best_cost)

    worst_drivers = _get_worst_drivers(
        driver_trips, resources, params, constraints_data, weights, target_duty
    )

    return {
        "assignments": assignments,
        "busStates": used,
        "unusedBuses": unused,
        "unassignedTrips": unassigned_ids_final,
        "parameters": params.to_dict(),
        "sa": {
            "config": config.__dict__,
            "weights": weights.__dict__,
            "bestCost": best_cost,
            "bestMetrics": best_metrics,
        },
        "metrics": {
            "totalTrips": len(full_data.get("trips", [])),
            "assigned": len(full_data.get("trips", [])) - len(unassigned_ids_final),
            "unassigned": len(unassigned_ids_final),
            "busesUsed": len(used),
            "totalIdleTime": sum(b["totalIdleTime"] for b in used),
            "totalDrivingTime": sum(b["totalDrivingTime"] for b in used),
            "totalTransferTime": best_metrics.get("totalTransfer", 0),
            "baseMismatchCount": best_metrics.get("baseMismatch", 0),
        },
        "worstDrivers": worst_drivers,
    }


def _save_run_log(
    config: SAConfig,
    weights: SAWeights,
    metrics: Dict[str, Any],
    best_cost: float,
):
    log_file = os.path.join(os.path.dirname(__file__), "..", "run_log.json")
    entry = {
        "timestamp": datetime.now().isoformat(),
        "version": VERSION_TAG,
        "best_cost": round(best_cost, 2),
        "config": config.__dict__,
        "weights": weights.__dict__,
        "metrics": metrics,
    }

    history = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append(entry)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def _get_worst_drivers(
    driver_trips: Dict[str, List[Dict[str, Any]]],
    resources: Dict[str, Dict[str, Any]],
    params: SolverParameters,
    constraints: ConstraintsData,
    weights: SAWeights,
    target_duty: float = 480.0,
) -> List[str]:
    scores = []
    for bus_id, trips in driver_trips.items():
        res = resources.get(bus_id, {})
        cost_b = _compute_driver_cost(
            trips, res, params, constraints, weights, target_duty
        )
        scores.append((bus_id, cost_b))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in scores[:10]]
