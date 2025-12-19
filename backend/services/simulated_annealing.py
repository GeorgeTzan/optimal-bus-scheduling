import math
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from services.legality_checker import (
    SolverParameters,
    ConstraintsData,
    check_assignment_legality,
)


@dataclass(frozen=True)
class SAWeights:
    duty_balance: float = 1.0
    overtime_over_8h: float = 4.0
    idle_time: float = 1.0
    unused_bus: float = 250.0


@dataclass(frozen=True)
class SAConfig:
    max_iters: int = 4000
    start_temp: float = 100.0
    end_temp: float = 0.5
    cooling: float = 0.9
    moves_per_temp: int = 50
    seed: Optional[int] = 7
    log_every: int = 200


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


def _fairness_penalty(duties: List[int]) -> float:
    if not duties:
        return 0.0
    avg = sum(duties) / len(duties)
    return sum((d - avg) ** 2 for d in duties) / len(duties)


def compute_cost(
    driver_trips: Dict[str, List[Dict[str, Any]]],
    resources: Dict[str, Dict[str, Any]],
    params: SolverParameters,
    weights: SAWeights,
) -> Tuple[float, Dict[str, Any]]:
    duties: List[int] = []
    total_idle = 0
    total_overtime = 0
    used_buses = 0

    for _, trips in driver_trips.items():
        duty = _duty_minutes(trips)
        duties.append(duty)
        if trips:
            used_buses += 1
        total_idle += _idle_minutes(trips, params.transit_minutes)
        total_overtime += _overtime_over_8h_minutes(duty)

    total_buses = len(resources)
    unused = max(0, total_buses - used_buses)

    fairness = _fairness_penalty(duties)

    cost = (
        weights.duty_balance * fairness
        + weights.idle_time * total_idle
        + weights.overtime_over_8h * total_overtime
        + weights.unused_bus * unused
    )

    metrics = {
        "fairness": fairness,
        "totalIdle": total_idle,
        "totalOver8h": total_overtime,
        "unusedBuses": unused,
        "usedBuses": used_buses,
    }
    return float(cost), metrics


def _is_legal_sequence(
    trips: List[Dict[str, Any]],
    resource: Dict[str, Any],
    params: SolverParameters,
    constraints: ConstraintsData,
    day_index: int,
) -> bool:
    if not trips:
        return True

    sorted_trips = sorted(trips, key=lambda x: x.get("start_minutes", 0))

    assigned: List[Dict[str, Any]] = []
    for i, t in enumerate(sorted_trips):
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

    for bus_id in resources.keys():
        driver_trips.setdefault(bus_id, [])

    best = {k: list(v) for k, v in driver_trips.items()}
    best_cost, best_metrics = compute_cost(best, resources, params, weights)

    current = {k: list(v) for k, v in driver_trips.items()}
    current_cost = best_cost

    temp = config.start_temp
    it = 0
    start_ts = time.time()

    while it < config.max_iters and temp > config.end_temp:
        for _ in range(config.moves_per_temp):
            it += 1
            if random.random() < 0.5:
                pick_a = _pick_random_trip(current)
                pick_b = _pick_random_trip(current)
                if not pick_a or not pick_b:
                    continue
                a_bus, a_idx = pick_a
                b_bus, b_idx = pick_b
                if a_bus == b_bus:
                    continue

                a_trips = current[a_bus]
                b_trips = current[b_bus]

                ta = a_trips[a_idx]
                tb = b_trips[b_idx]

                new_a = list(a_trips)
                new_b = list(b_trips)
                new_a[a_idx] = tb
                new_b[b_idx] = ta

                res_a = resources.get(a_bus, {})
                res_b = resources.get(b_bus, {})

                if not _is_legal_sequence(
                    new_a, res_a, params, constraints_data, day_index
                ):
                    continue
                if not _is_legal_sequence(
                    new_b, res_b, params, constraints_data, day_index
                ):
                    continue

                current[a_bus] = sorted(new_a, key=lambda x: x.get("start_minutes", 0))
                current[b_bus] = sorted(new_b, key=lambda x: x.get("start_minutes", 0))
            else:
                pick_a = _pick_random_trip(current)
                if not pick_a:
                    continue
                a_bus, a_idx = pick_a
                b_bus = random.choice(list(current.keys()))
                if a_bus == b_bus:
                    continue

                a_trips = current[a_bus]
                b_trips = current[b_bus]

                ta = a_trips[a_idx]
                new_a = list(a_trips)
                del new_a[a_idx]
                new_b = list(b_trips) + [ta]

                res_a = resources.get(a_bus, {})
                res_b = resources.get(b_bus, {})

                if not _is_legal_sequence(
                    new_a, res_a, params, constraints_data, day_index
                ):
                    continue
                if not _is_legal_sequence(
                    new_b, res_b, params, constraints_data, day_index
                ):
                    continue

                current[a_bus] = sorted(new_a, key=lambda x: x.get("start_minutes", 0))
                current[b_bus] = sorted(new_b, key=lambda x: x.get("start_minutes", 0))

            new_cost, _ = compute_cost(current, resources, params, weights)
            delta = new_cost - current_cost

            accept = False
            if delta <= 0:
                accept = True
            else:
                prob = math.exp(-delta / max(1e-9, temp))
                if random.random() < prob:
                    accept = True

            if accept:
                current_cost = new_cost
                if new_cost < best_cost:
                    best_cost, best_metrics = compute_cost(
                        current, resources, params, weights
                    )
                    best = {k: list(v) for k, v in current.items()}
            else:
                if random.random() < 0.02:
                    current = {k: list(v) for k, v in best.items()}
                    current_cost = best_cost

            if verbose and config.log_every and it % config.log_every == 0:
                elapsed = time.time() - start_ts
                print(
                    f"[SA] it={it} temp={temp:.2f} cost={best_cost:.1f} "
                    f"idle={best_metrics['totalIdle']} over8h={best_metrics['totalOver8h']} "
                    f"unused={best_metrics['unusedBuses']} fairness={best_metrics['fairness']:.1f} "
                    f"t={elapsed:.1f}s"
                )

            if it >= config.max_iters:
                break

        temp *= config.cooling

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
                "homeStation": res.get("homeStation", ""),
                "currentStation": (
                    trips[-1].get("endStation", res.get("currentStation", ""))
                    if trips
                    else res.get("currentStation", "")
                ),
                "assignedTrips": assigned_ids,
                "totalIdleTime": idle,
                "totalDrivingTime": driving,
            }
        )

        for tid in assigned_ids:
            assignments.append({"tripId": tid, "driverId": driver_id, "busId": bus_id})

    used = [b for b in bus_states if b["assignedTrips"]]
    unused = [b for b in bus_states if not b["assignedTrips"]]

    return {
        "assignments": assignments,
        "busStates": used,
        "unusedBuses": unused,
        "unassignedTrips": [],
        "parameters": params.to_dict(),
        "sa": {
            "config": config.__dict__,
            "weights": weights.__dict__,
            "bestCost": best_cost,
            "bestMetrics": best_metrics,
        },
        "metrics": {
            "totalTrips": len(full_data.get("trips", [])),
            "assigned": len(full_data.get("trips", [])),
            "unassigned": 0,
            "busesUsed": len(used),
            "totalIdleTime": sum(b["totalIdleTime"] for b in used),
            "totalDrivingTime": sum(b["totalDrivingTime"] for b in used),
        },
    }
