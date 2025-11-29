import random
from typing import List, Dict, Any, Set, Tuple
from services.legality_checker import (
    check_assignment_legality,
    check_driver_wish_bonus,
    SolverParameters,
    ConstraintsData,
)


def time_string_to_minutes(time_str: str) -> int:
    if not time_str:
        return 0
    if ":" in time_str:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    if len(str(time_str)) == 4:
        s = str(time_str)
        return int(s[:2]) * 60 + int(s[2:])
    return 0


def build_tasks_from_trips(
    trips: List[Dict[str, Any]], full_data: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Merges Trips, Pairs (Mandatory Sequences), and Joints (Mandatory Connections)
    into unified 'Tasks'. A Task may contain 1 trip or a chain of multiple trips.

    Pairs and Joints are treated identically - both create A -> B links.
    Chains like A -> B and B -> C get merged into A -> B -> C.

    Handles duplicate trip IDs (same trip on different days) by using
    start_minutes for disambiguation.

    Returns:
        - tasks: List of task objects
        - total_connections: Number of mandatory connections in the data
    """
    trip_by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
    trips_by_id: Dict[str, List[Dict[str, Any]]] = {}

    for t in trips:
        tid = t["id"]
        start_min = t.get("start_minutes", 0)
        trip_by_key[(tid, start_min)] = t
        if tid not in trips_by_id:
            trips_by_id[tid] = []
        trips_by_id[tid].append(t)

    constraints = full_data.get("constraints", {}) if full_data else {}

    adj_list: Dict[Tuple[str, int], Tuple[str, int]] = {}
    all_sequenced_keys: Set[Tuple[str, int]] = set()

    for seq in constraints.get("mandatorySequences", []):
        ids = seq.get("tripIds", []) if isinstance(seq, dict) else seq
        for i in range(len(ids) - 1):
            u_id, v_id = ids[i], ids[i + 1]
            if u_id in trips_by_id and v_id in trips_by_id:
                u_trip = trips_by_id[u_id][0]
                v_trip = trips_by_id[v_id][0]
                u_key = (u_id, u_trip.get("start_minutes", 0))
                v_key = (v_id, v_trip.get("start_minutes", 0))
                adj_list[u_key] = v_key
                all_sequenced_keys.add(u_key)
                all_sequenced_keys.add(v_key)

    total_connections = 0
    skipped_cross_day = 0

    for joint in constraints.get("mandatoryConnections", []):
        u_id = joint.get("incomingTripId")
        v_id = joint.get("outgoingTripId")
        joint_time = joint.get("time", 0)  

        if not u_id or not v_id:
            continue
        if u_id not in trips_by_id or v_id not in trips_by_id:
            continue

        joint_minutes = ((joint_time // 100) * 60) + (joint_time % 100)

        v_trip = None
        for t in trips_by_id[v_id]:
            if t.get("start_minutes", 0) == joint_minutes:
                v_trip = t
                break
        if not v_trip:
            v_trip = trips_by_id[v_id][0]

        u_trip = None
        for t in sorted(
            trips_by_id[u_id], key=lambda x: x.get("end_minutes", 0), reverse=True
        ):
            if t.get("end_minutes", 0) <= joint_minutes:
                u_trip = t
                break
        if not u_trip:
            u_trip = trips_by_id[u_id][0]

        u_key = (u_id, u_trip.get("start_minutes", 0))
        v_key = (v_id, v_trip.get("start_minutes", 0))

        gap = v_trip.get("start_minutes", 0) - u_trip.get("end_minutes", 0)
        if gap > 720:
            skipped_cross_day += 1
            continue

        adj_list[u_key] = v_key
        all_sequenced_keys.add(u_key)
        all_sequenced_keys.add(v_key)
        total_connections += 1

    destinations = set(adj_list.values())
    start_nodes = [key for key in all_sequenced_keys if key not in destinations]

    tasks: List[Dict[str, Any]] = []
    processed_keys: Set[Tuple[str, int]] = set()

    for start_key in start_nodes:
        chain: List[Dict[str, Any]] = []
        curr_key = start_key

        while curr_key:
            if curr_key in processed_keys:
                break
            if curr_key not in trip_by_key:
                break
            chain.append(trip_by_key[curr_key])
            processed_keys.add(curr_key)
            curr_key = adj_list.get(curr_key)

        if chain:
            total_duration = sum(
                t.get("time", {}).get("durationMinutes", 0) for t in chain
            )
            tasks.append(
                {
                    "id": f"CHAIN_{chain[0]['id']}",
                    "is_sequence": True,
                    "sub_trips": chain,
                    "start_minutes": chain[0].get("start_minutes", 0),
                    "end_minutes": chain[-1].get("end_minutes", 0),
                    "startStation": chain[0].get("startStation", ""),
                    "endStation": chain[-1].get("endStation", ""),
                    "classification": chain[0].get("classification", {}),
                    "total_duration": total_duration,
                }
            )

    for trip in trips:
        trip_key = (trip["id"], trip.get("start_minutes", 0))
        if trip_key not in processed_keys:
            tasks.append(
                {
                    "id": trip["id"],
                    "is_sequence": False,
                    "sub_trips": [trip],
                    "start_minutes": trip.get("start_minutes", 0),
                    "end_minutes": trip.get("end_minutes", 0),
                    "startStation": trip.get("startStation", ""),
                    "endStation": trip.get("endStation", ""),
                    "classification": trip.get("classification", {}),
                    "total_duration": trip.get("time", {}).get("durationMinutes", 0),
                }
            )

    return tasks, total_connections


def run_constructive_heuristic(
    trips: List[Dict[str, Any]],
    drivers: List[Dict[str, Any]],
    full_data: Dict[str, Any] = None,
) -> Dict[str, Any]:
    params = SolverParameters.from_data(full_data)
    constraints_data = ConstraintsData.from_data(full_data)

    meta = full_data.get("metaData", {}) if full_data else {}
    current_day_index = meta.get("dayOfPeriod", 1)

    tasks, total_connections = build_tasks_from_trips(trips, full_data)

    sorted_tasks = sorted(
        tasks, key=lambda t: (t["start_minutes"], -t["total_duration"])
    )

    resources_list = full_data.get("resources", []) if full_data else []
    resources_dict = {r["busId"]: r for r in resources_list}

    bus_states: Dict[str, Dict[str, Any]] = {}

    for driver in drivers:
        bus_id = driver.get("busId")
        if not bus_id:
            continue

        resource = resources_dict.get(bus_id, {})

        shift_start_str = resource.get("shiftStartTime", "0000")
        available_at = time_string_to_minutes(shift_start_str)

        bus_states[bus_id] = {
            "resourceRef": resource,
            "driverId": resource.get("driverId", ""),
            "busId": bus_id,
            "homeStation": driver.get("homeStation", resource.get("homeStation", "")),
            "currentStation": driver.get(
                "homeStation", resource.get("currentStation", "")
            ),
            "availableAt": available_at,
            "assignedTrips": [],
            "assignedTripObjects": [],
            "totalIdleTime": 0,
            "totalDrivingTime": 0,
            "busType": resource.get("busAttributes", {}).get("type", "01"),
        }

    assignments = []
    unassigned_trips = []

    for task in sorted_tasks:
        task_start = task["start_minutes"]
        task_start_station = task["startStation"]

        candidates = []

        for bus_id, state in bus_states.items():
            is_at_station = state["currentStation"] == task_start_station

            arrival_time = state["availableAt"]
            if not is_at_station:
                arrival_time += params.transit_minutes

            if arrival_time > task_start:
                continue

            temp_assigned_objects = state["assignedTripObjects"].copy()
            all_legal = True

            for sub_trip in task["sub_trips"]:
                is_legal, _ = check_assignment_legality(
                    sub_trip,
                    state["resourceRef"],
                    temp_assigned_objects,
                    params,
                    current_day_index,
                    constraints_data,
                )

                if not is_legal:
                    all_legal = False
                    break

                temp_assigned_objects.append(sub_trip)

            if all_legal:
                idle = task_start - arrival_time
                wish_bonus = check_driver_wish_bonus(
                    task["sub_trips"][0], state["resourceRef"], constraints_data
                )
                candidates.append(
                    {
                        "state": state,
                        "idle": idle,
                        "is_at_station": is_at_station,
                        "wish_bonus": wish_bonus,
                    }
                )

        if not candidates:
            for sub_trip in task["sub_trips"]:
                unassigned_trips.append(sub_trip["id"])
            continue

        candidates.sort(
            key=lambda x: (-x["wish_bonus"], not x["is_at_station"], x["idle"])
        )
        best_match = candidates[0]
        best_candidate = best_match["state"]

        initial_idle = best_match["idle"]

        for i, sub_trip in enumerate(task["sub_trips"]):
            sub_trip_id = sub_trip.get("id", "")
            sub_end = sub_trip.get("end_minutes", 0)
            sub_start = sub_trip.get("start_minutes", 0)
            adjusted_sub_end = sub_end + 1440 if sub_end < sub_start else sub_end
            sub_duration = sub_trip.get("time", {}).get("durationMinutes", 0)

            current_idle = initial_idle if i == 0 else 0

            best_candidate["assignedTrips"].append(sub_trip_id)
            best_candidate["assignedTripObjects"].append(sub_trip)
            best_candidate["totalIdleTime"] += current_idle
            best_candidate["totalDrivingTime"] += sub_duration
            best_candidate["currentStation"] = sub_trip["endStation"]
            best_candidate["availableAt"] = adjusted_sub_end

            assignments.append(
                {
                    "tripId": sub_trip_id,
                    "driverId": best_candidate["driverId"],
                    "busId": best_candidate["busId"],
                    "idleTime": current_idle,
                    "sequenceId": task["id"] if task["is_sequence"] else None,
                }
            )

    bus_results = []
    for state in bus_states.values():
        clean_state = {
            "driverId": state["driverId"],
            "busId": state["busId"],
            "homeStation": state["homeStation"],
            "currentStation": state["currentStation"],
            "assignedTrips": state["assignedTrips"],
            "totalIdleTime": state["totalIdleTime"],
            "totalDrivingTime": state["totalDrivingTime"],
        }
        bus_results.append(clean_state)

    used_buses = [b for b in bus_results if len(b["assignedTrips"]) > 0]
    unused_buses = [b for b in bus_results if len(b["assignedTrips"]) == 0]
    total_idle_time = sum(b["totalIdleTime"] for b in used_buses)
    total_driving_time = sum(b["totalDrivingTime"] for b in used_buses)

    chain_count = sum(1 for t in tasks if t["is_sequence"])

    return {
        "assignments": assignments,
        "busStates": used_buses,
        "unusedBuses": unused_buses,
        "unassignedTrips": unassigned_trips,
        "parameters": params.to_dict(),
        "metrics": {
            "totalTrips": len(trips),
            "assigned": len(trips) - len(unassigned_trips),
            "unassigned": len(unassigned_trips),
            "busesUsed": len(used_buses),
            "totalIdleTime": total_idle_time,
            "totalDrivingTime": total_driving_time,
            "chainsProcessed": chain_count,
            "connectionsInData": total_connections,
        },
    }
