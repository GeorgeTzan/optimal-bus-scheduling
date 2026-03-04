import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from services.legality_checker import (
    SolverParameters,
    ConstraintsData,
    check_assignment_legality,
)
from services.simulated_annealing import (
    SAWeights,
    _build_chain_mapping,
    _compute_driver_cost,
    _idle_minutes,
    _duty_minutes,
    _base_mismatch,
    _fairness_penalty,
    compute_cost,
    _is_legal_sequence,
    _pick_random_trip,
    _get_worst_drivers,
)


@dataclass
class LAHCConfig:
    max_iters: int = 200000
    L: int = 1000
    log_every: int = 5000
    restart_threshold: int = 20000
    max_seconds: int = 240


def _build_empty_state(
    full_data: Dict[str, Any],
) -> Tuple[
    Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]], List[Dict[str, Any]]
]:
    resources = {r.get("busId", ""): r for r in full_data.get("resources", [])}
    driver_trips: Dict[str, List[Dict[str, Any]]] = {bus_id: [] for bus_id in resources}
    all_trips = full_data.get("trips", [])
    return driver_trips, resources, list(all_trips)


def _build_state_from_solution(
    full_data: Dict[str, Any],
    previous_solution: Dict[str, Any],
) -> Tuple[
    Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]], List[Dict[str, Any]]
]:
    resources = {r.get("busId", ""): r for r in full_data.get("resources", [])}
    trips_by_id: Dict[str, Dict[str, Any]] = {}
    for t in full_data.get("trips", []):
        trips_by_id[t.get("id", "")] = t

    driver_trips: Dict[str, List[Dict[str, Any]]] = {bus_id: [] for bus_id in resources}

    for state in previous_solution.get("busStates", []):
        bus_id = state.get("busId", "")
        if bus_id not in driver_trips:
            continue
        assigned_ids = state.get("assignedTrips", [])
        resolved = [trips_by_id[tid] for tid in assigned_ids if tid in trips_by_id]
        resolved.sort(key=lambda x: x.get("start_minutes", 0))
        driver_trips[bus_id] = resolved

    assigned_set = {
        tid
        for state in previous_solution.get("busStates", [])
        for tid in state.get("assignedTrips", [])
    }
    all_unassigned = [
        t for t in full_data.get("trips", []) if t.get("id", "") not in assigned_set
    ]

    return driver_trips, resources, all_unassigned


def _perform_lahc_move(
    current: Dict[str, List[Dict[str, Any]]],
    current_unassigned: List[Dict[str, Any]],
    resources: Dict[str, Dict[str, Any]],
    params: SolverParameters,
    constraints_data: ConstraintsData,
    weights: SAWeights,
    day_index: int,
    worst_drivers: List[str],
    chain_map: Dict[str, List[str]],
    target_duty: float,
) -> Tuple[Optional[Dict[str, List]], Optional[List], float]:
    move_type = random.random()
    total_trips = sum(len(v) for v in current.values()) + len(current_unassigned)
    unassigned_ratio = len(current_unassigned) / max(total_trips, 1)
    unassigned_move_prob = (
        min(0.85, 0.25 + unassigned_ratio * 0.6) if current_unassigned else 0.0
    )

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

    bus_b = None
    new_a = None
    new_b = None
    new_unassigned = None

    if move_type < unassigned_move_prob and current_unassigned:
        trip = random.choice(current_unassigned)
        bus_ids = list(current.keys())
        random.shuffle(bus_ids)
        found = False
        for try_bus in bus_ids:
            candidate = sorted(
                current[try_bus] + [trip], key=lambda x: x.get("start_minutes", 0)
            )
            if _is_legal_sequence(
                candidate, resources.get(try_bus, {}), params, constraints_data, day_index
            ):
                bus_a = try_bus
                old_a_cost = _compute_driver_cost(
                    current[bus_a], resources.get(bus_a, {}), params, constraints_data, weights, target_duty
                )
                new_a = candidate
                new_unassigned = [t for t in current_unassigned if t["id"] != trip["id"]]
                found = True
                break
        if not found:
            return None, None, 0.0

    elif move_type < 0.5:
        if current[bus_a]:
            idx_a = random.randrange(len(current[bus_a]))
        else:
            pick = _pick_random_trip(current)
            if not pick:
                return None, None, 0.0
            bus_a, idx_a = pick
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
            return None, None, 0.0
        bus_b, idx_b = pick_b
        if bus_a == bus_b:
            return None, None, 0.0

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

        candidate_a = sorted(
            [t for t in current[bus_a] if t.get("id", "") not in chain_a]
            + [t for t in current[bus_b] if t.get("id", "") in chain_b],
            key=lambda x: x.get("start_minutes", 0),
        )
        candidate_b = sorted(
            [t for t in current[bus_b] if t.get("id", "") not in chain_b]
            + [t for t in current[bus_a] if t.get("id", "") in chain_a],
            key=lambda x: x.get("start_minutes", 0),
        )

        if not (
            _is_legal_sequence(
                candidate_a,
                resources.get(bus_a, {}),
                params,
                constraints_data,
                day_index,
            )
            and _is_legal_sequence(
                candidate_b,
                resources.get(bus_b, {}),
                params,
                constraints_data,
                day_index,
            )
        ):
            return None, None, 0.0

        new_a = candidate_a
        new_b = candidate_b

    else:
        if current[bus_a]:
            idx_a = random.randrange(len(current[bus_a]))
        else:
            pick = _pick_random_trip(current)
            if not pick:
                return None, None, 0.0
            bus_a, idx_a = pick
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
            return None, None, 0.0

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

        candidate_b = sorted(
            current[bus_b] + trips_to_move, key=lambda x: x.get("start_minutes", 0)
        )
        if not _is_legal_sequence(
            candidate_b, resources.get(bus_b, {}), params, constraints_data, day_index
        ):
            return None, None, 0.0

        new_a = [t for t in current[bus_a] if t.get("id", "") not in chain_members]
        new_b = candidate_b

    new_a_cost = _compute_driver_cost(
        new_a, resources.get(bus_a, {}), params, constraints_data, weights, target_duty
    )
    new_b_cost = (
        _compute_driver_cost(
            new_b,
            resources.get(bus_b, {}),
            params,
            constraints_data,
            weights,
            target_duty,
        )
        if bus_b and new_b is not None
        else 0.0
    )
    final_unassigned = (
        new_unassigned if new_unassigned is not None else current_unassigned
    )
    new_unassigned_cost = len(final_unassigned) * weights.unassigned_trip

    delta = (new_a_cost + new_b_cost + new_unassigned_cost) - (
        old_a_cost + old_b_cost + old_unassigned_cost
    )

    result_state = {"bus_a": bus_a, "new_a": new_a, "bus_b": bus_b, "new_b": new_b}
    return result_state, new_unassigned if new_unassigned is not None else None, delta


def optimize_with_lahc(
    full_data: Dict[str, Any],
    params: Optional[SolverParameters] = None,
    constraints_data: Optional[ConstraintsData] = None,
    config: Optional[LAHCConfig] = None,
    weights: Optional[SAWeights] = None,
    day_index: Optional[int] = None,
    previous_solution: Optional[Dict[str, Any]] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    if params is None:
        params = SolverParameters.from_data(full_data)
    if constraints_data is None:
        constraints_data = ConstraintsData.from_data(full_data)
    if config is None:
        config = LAHCConfig()
    if weights is None:
        weights = SAWeights()

    meta = full_data.get("metaData", {}) if full_data else {}
    if day_index is None:
        day_index = int(meta.get("dayOfPeriod", 1))

    if previous_solution is not None:
        driver_trips, resources, current_unassigned = _build_state_from_solution(
            full_data, previous_solution
        )
    else:
        driver_trips, resources, current_unassigned = _build_empty_state(full_data)

    num_drivers = len(resources)
    total_work = sum(
        t.get("time", {}).get("durationMinutes", 0) for t in full_data.get("trips", [])
    )
    target_duty = (total_work / num_drivers) * 1.2 if num_drivers > 0 else 480.0
    target_duty = max(target_duty, 300.0)

    chain_map = _build_chain_mapping(full_data)

    current = {k: list(v) for k, v in driver_trips.items()}
    current_cost, _ = compute_cost(
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
    best_cost, best_metrics = compute_cost(
        best, resources, params, constraints_data, weights, best_unassigned, target_duty
    )

    history = [current_cost] * config.L
    v = 0

    worst_drivers: List[str] = []
    iters_since_best = 0
    start_ts = time.time()
    last_logged_unassigned = best_metrics["unassigned"]
    all_assigned_at: Optional[int] = None

    it = 0
    while True:
        it += 1

        if all_assigned_at is None:
            if best_metrics["unassigned"] == 0:
                all_assigned_at = it
                iters_since_best = 0
                history = [current_cost] * config.L
                v = 0
            elif time.time() - start_ts > config.max_seconds:
                break
        else:
            if it - all_assigned_at >= config.max_iters and time.time() - start_ts > config.max_seconds:
                break
        if it % 500 == 0:
            worst_drivers = _get_worst_drivers(
                current, resources, params, constraints_data, weights, target_duty
            )

        result_state, new_unassigned, delta = _perform_lahc_move(
            current,
            current_unassigned,
            resources,
            params,
            constraints_data,
            weights,
            day_index,
            worst_drivers,
            chain_map,
            target_duty,
        )

        if result_state is None:
            history[v] = current_cost
            v = (v + 1) % config.L
            continue

        candidate_cost = current_cost + delta

        reduces_unassigned = new_unassigned is not None and len(new_unassigned) < len(current_unassigned)

        if reduces_unassigned or candidate_cost <= history[v]:
            current[result_state["bus_a"]] = result_state["new_a"]
            if result_state["bus_b"] and result_state["new_b"] is not None:
                current[result_state["bus_b"]] = result_state["new_b"]
            if new_unassigned is not None:
                current_unassigned[:] = new_unassigned
            current_cost = candidate_cost

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
                best = {k: list(v_) for k, v_ in current.items()}
                best_unassigned = list(current_unassigned)
                iters_since_best = 0
            else:
                iters_since_best += 1
        else:
            iters_since_best += 1

        history[v] = current_cost
        v = (v + 1) % config.L

        if iters_since_best >= config.restart_threshold:
            current = {k: list(v_) for k, v_ in best.items()}
            current_unassigned = list(best_unassigned)
            current_cost = best_cost
            history = [current_cost] * config.L
            v = 0
            iters_since_best = 0
            if verbose:
                elapsed = time.time() - start_ts
                print(
                    f"[LAHC] restart at it={it} cost={best_cost:.1f} t={elapsed:.1f}s"
                )

        cur_unassigned = best_metrics["unassigned"]
        unassigned_changed = cur_unassigned != last_logged_unassigned
        should_log = unassigned_changed or (
            cur_unassigned == 0 and it % config.log_every == 0
        )

        if verbose and should_log:
            last_logged_unassigned = cur_unassigned
            elapsed = time.time() - start_ts
            print(
                f"[LAHC] it={it} cost={best_cost:.1f} "
                f"mismatch={best_metrics['baseMismatch']} "
                f"idle={best_metrics['totalIdle']} "
                f"unassigned={best_metrics['unassigned']} t={elapsed:.1f}s"
            )
    assignments: List[Dict[str, Any]] = []
    bus_states: List[Dict[str, Any]] = []

    for bus_id, trips in best.items():
        res = resources.get(bus_id, {})
        driver_id = res.get("driverId", "")
        assigned_ids = [t.get("id", "") for t in trips]
        driving = sum(t.get("time", {}).get("durationMinutes", 0) for t in trips)
        idle = _idle_minutes(trips, params.transit_minutes)

        bus_states.append(
            {
                "driverId": driver_id,
                "busId": bus_id,
                "homeStation": res.get("homeStation"),
                "currentStation": (
                    trips[-1].get("endStation", res.get("currentStation", ""))
                    if trips
                    else res.get("currentStation", "")
                ),
                "assignedTrips": assigned_ids,
                "transfers": [],
                "totalIdleTime": idle,
                "totalDrivingTime": driving,
            }
        )

        for tid in assigned_ids:
            assignments.append({"tripId": tid, "driverId": driver_id, "busId": bus_id})

    used = [b for b in bus_states if b["assignedTrips"]]
    unused = [b for b in bus_states if not b["assignedTrips"]]
    unassigned_ids_final = list({t["id"] for t in best_unassigned})

    return {
        "assignments": assignments,
        "busStates": used,
        "unusedBuses": unused,
        "unassignedTrips": unassigned_ids_final,
        "parameters": params.to_dict(),
        "lahc": {
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
    }
