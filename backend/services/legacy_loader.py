import os
from typing import List, Dict, Any
from dat_parser import parse_trips, parse_drivers, get_full_data
from services.legality_checker import (
    get_transfer_duration,
    ConstraintsData,
    SolverParameters,
)


def load_legacy_solution(shifts_dat_path: str) -> Dict[str, Any]:
    """
    Parses shifts.dat from legacy software and returns a Solution compatible format.
    """
    if not os.path.exists(shifts_dat_path):
        raise FileNotFoundError(f"Legacy shifts file not found at {shifts_dat_path}")

    trips = parse_trips()
    drivers = parse_drivers()
    full_data = get_full_data()
    constraints = ConstraintsData.from_data(full_data)
    params = SolverParameters.from_data(full_data)

    trip_map = {t["id"]: t for t in trips}

    with open(shifts_dat_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    if not lines:
        return {}

    try:
        num_shifts = int(lines[0])
    except (ValueError, IndexError):
        return {
            "error": "Invalid format in shifts.dat - first line must be number of shifts",
            "metrics": None,
        }

    assignments = []
    bus_states = []
    assigned_ids = set()

    current_line = 1
    for _ in range(num_shifts):
        if current_line + 1 >= len(lines):
            break

        trip_line = lines[current_line]
        driver_line = lines[current_line + 1]
        current_line += 2

        trip_parts = trip_line.split()
        if len(trip_parts) < 2:
            continue

        num_trips_in_shift = int(trip_parts[0])

        trip_codes = trip_parts[2 : 2 + num_trips_in_shift]

        driver_parts = driver_line.split()
        driver_bus_idx = int(driver_parts[5]) - 1 if len(driver_parts) > 5 else -1

        assigned_trips = []
        for code in trip_codes:
            trip_obj = trip_map.get(code)
            if trip_obj:
                assigned_trips.append(trip_obj)
            else:
                print(f"Warning: Trip code {code} not found in data.json")

        legacy_driver_code = driver_parts[0]
        legacy_bus_code = driver_parts[1][-3:]

        resource = None
        if 0 <= driver_bus_idx < len(drivers):
            temp_res = drivers[driver_bus_idx]
            if (
                temp_res.get("driverId") == legacy_driver_code
                or temp_res.get("busId") == legacy_bus_code
            ):
                resource = temp_res

        if not resource:
            resource = next((d for d in drivers if d["busId"] == legacy_bus_code), None)

        if not resource:
            resource = {
                "driverId": legacy_driver_code,
                "busId": legacy_bus_code,
                "homeStation": driver_parts[2],
                "currentStation": driver_parts[2],
                "busAttributes": {"type": "01"},
            }

        total_driving = 0
        total_idle = 0
        total_transfer = 0

        if assigned_trips:
            total_driving = sum(t["time"]["durationMinutes"] for t in assigned_trips)

            for i in range(len(assigned_trips) - 1):
                t1 = assigned_trips[i]
                t2 = assigned_trips[i + 1]

                transfer = get_transfer_duration(
                    t1["endStation"], t2["startStation"], constraints, params
                )
                total_transfer += transfer

                gap = t2["start_minutes"] - t1["end_minutes"]

                if gap < -600:
                    gap += 1440

                idle = gap - transfer
                total_idle += max(0, idle)

            last_trip = assigned_trips[-1]
            base_mismatch = (
                1 if last_trip["endStation"] != resource.get("homeStation", "") else 0
            )

            bus_states.append(
                {
                    "busId": resource["busId"],
                    "driverId": resource["driverId"],
                    "homeStation": resource.get("homeStation", ""),
                    "currentStation": resource.get("currentStation", ""),
                    "assignedTrips": [t["id"] for t in assigned_trips],
                    "totalDrivingTime": total_driving,
                    "totalIdleTime": total_idle,
                    "totalTransferTime": total_transfer,
                    "baseMismatch": base_mismatch,
                }
            )

            for t in assigned_trips:
                assigned_ids.add(t["id"])
                assignments.append(
                    {"tripId": t["id"], "busId": resource["busId"], "idleTime": 0}
                )

    unassigned_trips = [t["id"] for t in trips if t["id"] not in assigned_ids]

    metrics = {
        "totalTrips": len(trips),
        "assigned": len(assigned_ids),
        "unassigned": len(unassigned_trips),
        "busesUsed": len(bus_states),
        "totalIdleTime": sum(bs["totalIdleTime"] for bs in bus_states),
        "totalDrivingTime": sum(bs["totalDrivingTime"] for bs in bus_states),
        "totalTransferTime": sum(bs["totalTransferTime"] for bs in bus_states),
        "baseMismatchCount": sum(bs.get("baseMismatch", 0) for bs in bus_states),
        "sequencesProcessed": 0,
    }

    return {
        "assignments": assignments,
        "busStates": bus_states,
        "unusedBuses": [],
        "unassignedTrips": unassigned_trips,
        "metrics": metrics,
    }
