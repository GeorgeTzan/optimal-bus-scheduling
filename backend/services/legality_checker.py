from typing import List, Dict, Tuple, Set, Optional
from dataclasses import dataclass, field

DEFAULT_MAX_DUTY_MINUTES = 900
DEFAULT_NORMAL_DUTY_MINUTES = 600
DEFAULT_MAX_WORK_MINUTES = 720
DEFAULT_DRIVE_TIME_TO_BREAK = 270
DEFAULT_MIN_BREAK_TIME = 30
DEFAULT_TRANSIT_TIME = 30


@dataclass
class SolverParameters:
    max_duty_minutes: int = DEFAULT_MAX_DUTY_MINUTES
    normal_duty_minutes: int = DEFAULT_NORMAL_DUTY_MINUTES
    max_work_minutes: int = DEFAULT_MAX_WORK_MINUTES
    drive_time_to_break: int = DEFAULT_DRIVE_TIME_TO_BREAK
    min_break_time: int = DEFAULT_MIN_BREAK_TIME
    transit_minutes: int = DEFAULT_TRANSIT_TIME
    max_duty_gaps: int = 5
    min_gap_minutes: int = 15
    min_delay_per_group: Dict[str, int] = field(default_factory=dict)
    min_delay_per_type: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_data(cls, full_data: Dict = None) -> "SolverParameters":
        if not full_data:
            return cls()

        config = full_data.get("configuration", {})
        params = config.get("parameters", {})

        return cls(
            max_duty_minutes=params.get("maxDutyMinutes", DEFAULT_MAX_DUTY_MINUTES),
            normal_duty_minutes=params.get(
                "normalDutyMinutes", DEFAULT_NORMAL_DUTY_MINUTES
            ),
            max_work_minutes=params.get("maxWorkMinutes", DEFAULT_MAX_WORK_MINUTES),
            drive_time_to_break=params.get(
                "driveTimeToBreakMinutes", DEFAULT_DRIVE_TIME_TO_BREAK
            ),
            min_break_time=params.get("minBreakMinutes", DEFAULT_MIN_BREAK_TIME),
            transit_minutes=params.get("transitMinutes", DEFAULT_TRANSIT_TIME),
            max_duty_gaps=params.get("maxDutyGaps", 5),
            min_gap_minutes=params.get("minGapMinutes", 15),
            min_delay_per_group=params.get("minDelayPerGroup", {}),
            min_delay_per_type=params.get("minDelayPerType", {}),
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            "maxDutyMinutes": self.max_duty_minutes,
            "normalDutyMinutes": self.normal_duty_minutes,
            "maxWorkMinutes": self.max_work_minutes,
            "driveTimeToBreakMinutes": self.drive_time_to_break,
            "minBreakMinutes": self.min_break_time,
            "transitMinutes": self.transit_minutes,
            "maxDutyGaps": self.max_duty_gaps,
            "minGapMinutes": self.min_gap_minutes,
        }


@dataclass
class ConstraintsData:
    """Holds global constraints data for quick lookup during legality checks."""

    prohibited_buses: Set[str] = field(default_factory=set)
    prohibited_drivers: Set[str] = field(default_factory=set)
    driver_wishes_positive: Dict[str, Set[str]] = field(default_factory=dict)
    driver_wishes_negative: Dict[str, Set[str]] = field(default_factory=dict)
    trip_prohibited_buses: Dict[str, Set[str]] = field(default_factory=dict)
    trip_prohibited_drivers: Dict[str, Set[str]] = field(default_factory=dict)
    station_transfer_matrix: List[List[str]] = field(default_factory=list)

    @classmethod
    def from_data(cls, full_data: Dict = None) -> "ConstraintsData":
        if not full_data:
            return cls()

        constraints = full_data.get("constraints", {})
        prohibited = constraints.get("prohibited", {})

        instance = cls(
            prohibited_buses=set(prohibited.get("buses", [])),
            prohibited_drivers=set(prohibited.get("drivers", [])),
            station_transfer_matrix=full_data.get("stationTransferMatrix", {}).get(
                "matrix", []
            ),
        )

        for wish in constraints.get("driverWishes", []):
            driver_id = wish.get("driverId", "")
            trip_id = wish.get("tripId", "")
            wish_type = wish.get("type", 0)

            if driver_id and trip_id:
                if wish_type == 1:
                    if driver_id not in instance.driver_wishes_positive:
                        instance.driver_wishes_positive[driver_id] = set()
                    instance.driver_wishes_positive[driver_id].add(trip_id)
                elif wish_type == 2:
                    if driver_id not in instance.driver_wishes_negative:
                        instance.driver_wishes_negative[driver_id] = set()
                    instance.driver_wishes_negative[driver_id].add(trip_id)

        return instance


def get_transfer_duration(
    st1: str, st2: str, constraints_data: ConstraintsData, params: SolverParameters
) -> int:
    """Returns the required duration in minutes to transfer from st1 to st2."""
    if not st1 or not st2 or st1 == st2:
        return 0

    matrix = constraints_data.station_transfer_matrix
    if not matrix:
        return 0

    try:
        idx1 = int(st1) - 1
        idx2 = int(st2) - 1
        if 0 <= idx1 < len(matrix) and 0 <= idx2 < len(matrix[0]):
            transfer_type = matrix[idx1][idx2]
            if transfer_type == "BREAK":
                return params.min_break_time
            if transfer_type == "NONE":
                return 0
    except (ValueError, TypeError, IndexError):
        pass
    return 0


def check_assignment_legality(
    trip: Dict,
    resource: Optional[Dict],
    current_trips: List[Dict],
    params: SolverParameters = None,
    day_index: int = 0,
    constraints_data: ConstraintsData = None,
) -> Tuple[bool, List[str]]:
    """
    Check if assigning a trip to a resource (bus/driver) is legal.

    Implements legacy LC checks:
    - K1: Bus type check
    - K2: Repo/Day-off compatibility (CheckRepo)
    - K3: Base compatibility check
    - K4: Employment/duty time check
    - K5: Driving/work time check
    - K6: First/last trip shift position check
    - K7: Next/prev day rest rule check
    - K8: Max number of duty gaps (gaps >= 15 min)
    - K9: Min delay per bus type
    - K10: Min delay per group
    - K11: Break after X driving hours check
    - K12: Driver wishes check
    - K13: Prohibited routes for driver check
    - K14: Prohibited routes for bus check
    - K15: Days to Repo check

    If resource is None, checks only time-based overlaps between current_trips and the new trip.
    """
    if params is None:
        params = SolverParameters()

    if constraints_data is None:
        constraints_data = ConstraintsData()

    errors = []

    trip_id = trip.get("id", "")

    if resource is None:
        new_start = trip.get("startMinutes", 0)
        new_end = trip.get("endMinutes", 0)
        new_start_station = trip.get("startStation", "")
        new_end_station = trip.get("endStation", "")

        for ct in current_trips:
            ct_start = ct.get("startMinutes", 0)
            ct_end = ct.get("endMinutes", 0)
            ct_start_station = ct.get("startStation", "")
            ct_end_station = ct.get("endStation", "")

            # Overlap check
            if not (new_end <= ct_start or new_start >= ct_end):
                errors.append(f"trip_overlap: {trip_id} overlaps with {ct.get('id')}")
                return False, errors

        # Station check (A->B, B->C)
        if current_trips:
            sorted_current = sorted(
                current_trips, key=lambda x: x.get("startMinutes", 0)
            )

            predecessor = None
            for ct in reversed(sorted_current):
                if ct.get("end_minutes", 0) <= new_start:
                    predecessor = ct
                    break

            if predecessor:
                pred_end_station = predecessor.get("endStation", "")
                if (
                    pred_end_station
                    and new_start_station
                    and pred_end_station != new_start_station
                ):
                    errors.append(
                        f"station_mismatch: Predecessor ended at {pred_end_station}, new starts at {new_start_station}"
                    )
                    return False, errors

            successor = None
            for ct in sorted_current:
                if ct.get("start_minutes", 0) >= new_end:
                    successor = ct
                    break

            if successor:
                succ_start_station = successor.get("startStation", "")
                if (
                    new_end_station
                    and succ_start_station
                    and new_end_station != succ_start_station
                ):
                    errors.append(
                        f"station_mismatch: New ends at {new_end_station}, successor starts at {succ_start_station}"
                    )
                    return False, errors

        return True, []

    bus_attr = resource.get("busAttributes", {})
    bus_type = bus_attr.get("type", "01")
    bus_id = resource.get("busId", "")
    driver_id = resource.get("driverId", "")
    home_station = resource.get("homeStation", "")

    # K14: Check if bus is globally prohibited
    if bus_id in constraints_data.prohibited_buses:
        errors.append(f"bus_prohibited: {bus_id}")
        return False, errors

    # K13: Check if driver is globally prohibited
    if driver_id in constraints_data.prohibited_drivers:
        errors.append(f"driver_prohibited: {driver_id}")
        return False, errors

    # K14: Check if this specific trip is prohibited for this bus
    if trip_id in constraints_data.trip_prohibited_buses:
        if bus_id in constraints_data.trip_prohibited_buses[trip_id]:
            errors.append(f"trip_prohibited_for_bus: {trip_id} -> {bus_id}")
            return False, errors
    # K13: Check if this specific trip is prohibited for this driver
    if trip_id in constraints_data.trip_prohibited_drivers:
        if driver_id in constraints_data.trip_prohibited_drivers[trip_id]:
            errors.append(f"trip_prohibited_for_driver: {trip_id} -> {driver_id}")
            return False, errors

    # K12: Check driver wishes (negative - driver doesn't want this trip)
    if driver_id in constraints_data.driver_wishes_negative:
        if trip_id in constraints_data.driver_wishes_negative[driver_id]:
            errors.append(f"driver_wish_negative: {driver_id} doesn't want {trip_id}")
            return False, errors

    # K1: Bus type compatibility check
    allowed_types = trip.get("classification", {}).get("allowedBusTypes", [])
    specific_overrides = trip.get("classification", {}).get("specificBusOverrides", [])

    allowed_types = [str(t) for t in allowed_types if t and t != "00"]

    if allowed_types and bus_type not in allowed_types:
        if bus_id not in specific_overrides:
            errors.append(f"bus_type_mismatch: Need {allowed_types}, Got {bus_type}")
            return False, errors

    # K3: HOME STATION COMPATIBILITY
    home_station = resource.get("homeStation", "")
    current_station = resource.get("currentStation", "")
    shift_start_str = resource.get("shiftStartTime", "0000")
    try:
        shift_start_minutes = int(shift_start_str[:2]) * 60 + int(shift_start_str[2:])
    except (ValueError, TypeError):
        shift_start_minutes = 0

    raw_alt_stations = trip.get("properties", {}).get("alternativeStationCodes", [])
    active_station_constraints = [s for s in raw_alt_stations if s and s != "000"]

    if active_station_constraints and home_station and home_station != "000":
        trip_start = trip.get("startStation", "")
        trip_end = trip.get("endStation", "")
        valid_stations = set(active_station_constraints)
        if trip_start and trip_start != "000":
            valid_stations.add(trip_start)
        if trip_end and trip_end != "000":
            valid_stations.add(trip_end)

        if home_station not in valid_stations:
            errors.append(f"trip_not_serving_home_station: {home_station}")
            return False, errors

    # K2: Driver day-off check (preassigned breaks today)
    # dayIndex 0 = today (relative)
    preassigned_breaks = resource.get("preassignedBreaks", [])
    for brk in preassigned_breaks:
        if brk.get("dayIndex") == 0 and brk.get("durationMinutes", 0) > 0:
            errors.append("driver_on_break_today")
            return False, errors

    # K2/K7: Repo compatibility (CheckRepo)
    repo_next_day = resource.get("repoNextDay", False)
    repo_pre_day = resource.get("repoPreDay", False)

    trip_props = trip.get("properties", {})
    rest_rule = trip_props.get("nextDayRestRule", "NONE")

    if repo_next_day and rest_rule == "NO_REST_TOMORROW":
        errors.append("trip_forbidden_for_repo_tomorrow")
        return False, errors
    if not repo_next_day and rest_rule == "MUST_REST_TOMORROW":
        errors.append("trip_requires_repo_tomorrow")
        return False, errors
    if repo_pre_day and rest_rule == "NO_REST_YESTERDAY":
        errors.append("trip_forbidden_for_repo_yesterday")
        return False, errors
    if not repo_pre_day and rest_rule == "MUST_REST_YESTERDAY":
        errors.append("trip_requires_repo_yesterday")
        return False, errors

    # K15: Days to Repo check
    days_to_repo_resource = resource.get("daysToRepo", 0)
    days_to_repo_trip = trip_props.get("daysToRestRule", 0)
    if days_to_repo_trip > 0 and days_to_repo_trip != days_to_repo_resource:
        errors.append(
            f"days_to_repo_mismatch: Need {days_to_repo_trip}, Got {days_to_repo_resource}"
        )
        return False, errors

    if not current_trips:
        trip_start_station = trip.get("startStation")
        if (
            current_station
            and trip_start_station
            and current_station != trip_start_station
        ):
            matrix = constraints_data.station_transfer_matrix
            if not matrix:
                errors.append(
                    f"first_station_mismatch: Resource at {current_station}, trip starts at {trip_start_station}"
                )
                return False, errors

            try:
                idx1 = int(current_station) - 1
                idx2 = int(trip_start_station) - 1
                if 0 <= idx1 < len(matrix) and 0 <= idx2 < len(matrix[0]):
                    transfer_type = matrix[idx1][idx2]
                    if transfer_type == "OVERNIGHT":
                        errors.append(
                            f"first_transfer_forbidden: {current_station} -> {trip_start_station} (OVERNIGHT)"
                        )
                        return False, errors

                    trip_start = trip.get("start_minutes", 0)
                    gap = trip_start - shift_start_minutes

                    if transfer_type == "BREAK":
                        if gap < params.min_break_time:
                            errors.append(
                                f"first_transfer_requires_break: {gap} < {params.min_break_time}"
                            )
                            return False, errors
                    elif transfer_type == "NONE":
                        if gap < 0:
                            errors.append("first_trip_starts_before_shift")
                            return False, errors
                else:
                    errors.append(
                        f"first_station_index_out_of_bounds: {current_station} or {trip_start_station}"
                    )
                    return False, errors
            except (ValueError, TypeError):
                errors.append(
                    f"first_invalid_station_code: {current_station} or {trip_start_station}"
                )
                return False, errors
        else:
            trip_start = trip.get("start_minutes", 0)
            if trip_start < shift_start_minutes:
                errors.append("first_trip_starts_before_shift")
                return False, errors

    if current_trips:
        last_trip = current_trips[-1]

        last_constraints = last_trip.get("properties", {}).get("constraints", {})
        if last_constraints.get("shiftPosition") == "MUST_BE_LAST":
            errors.append("previous_trip_must_be_last")
            return False, errors

        last_end = last_trip.get("end_minutes", 0)
        trip_start = trip.get("start_minutes", 0)

        effective_start = trip_start
        if trip_start < last_end and last_end > 1200 and trip_start < 300:
            effective_start = trip_start + 1440
        if effective_start < last_end:
            errors.append("insufficient_time_gap")
            return False, errors

        last_end_station = last_trip.get("endStation")
        trip_start_station = trip.get("startStation")

        if last_end_station != trip_start_station:
            errors.append(
                f"station_mismatch: Last ended at {last_end_station}, next starts at {trip_start_station}"
            )
            return False, errors
        else:
            effective_last_end = last_end
            effective_trip_start = trip_start
            if trip_start < last_end and last_end > 1200 and trip_start < 300:
                effective_trip_start = trip_start + 1440

            gap = effective_trip_start - effective_last_end
            if gap < 0:
                errors.append("insufficient_time_gap")
                return False, errors

        # K9 & K10: Min delay per type/group
        trip_group = trip.get("group", "0")
        if trip_group != "0":
            for prev in reversed(current_trips):
                if prev.get("group") == trip_group:
                    prev_end = prev.get("end_minutes", 0)
                    curr_start = trip.get("start_minutes", 0)
                    if curr_start < prev_end:
                        curr_start += 1440

                    actual_gap = curr_start - prev_end

                    # K10: Group delay
                    min_group_delay = params.min_delay_per_group.get(trip_group, 0)
                    if actual_gap < min_group_delay:
                        errors.append(
                            f"min_group_delay_violated: {actual_gap} < {min_group_delay}"
                        )
                        return False, errors

                    # K9: Type delay
                    min_type_delay = params.min_delay_per_type.get(bus_type, 0)
                    if actual_gap < min_type_delay:
                        errors.append(
                            f"min_type_delay_violated: {actual_gap} < {min_type_delay}"
                        )
                        return False, errors
                    break

    test_trips = current_trips + [trip]

    # K8: Max number of duty gaps
    num_gaps = 0
    for i in range(len(test_trips) - 1):
        t1_end = test_trips[i].get("end_minutes", 0)
        t2_start = test_trips[i + 1].get("start_minutes", 0)
        if t2_start < t1_end:
            t2_start += 1440

        if (t2_start - t1_end) >= params.min_gap_minutes:
            num_gaps += 1

    if num_gaps > params.max_duty_gaps:
        errors.append(f"max_gaps_exceeded: {num_gaps} > {params.max_duty_gaps}")
        return False, errors

    first_start = test_trips[0].get("start_minutes", 0)
    last_end = test_trips[-1].get("end_minutes", 0)

    if last_end < first_start:
        last_end += 1440

    duty_time = last_end - first_start

    # K4: Max duty time check
    if duty_time > params.max_duty_minutes:
        errors.append(f"max_duty_exceeded: {duty_time} > {params.max_duty_minutes}")
        return False, errors

    # K5: Max work/driving time check
    total_driving = sum(t.get("time", {}).get("durationMinutes", 0) for t in test_trips)
    if total_driving > params.max_work_minutes:
        errors.append(f"max_work_exceeded: {total_driving} > {params.max_work_minutes}")
        return False, errors

    # K11: Break requirement check
    if total_driving > params.drive_time_to_break and len(test_trips) > 1:
        has_valid_break = False
        for i in range(len(test_trips) - 1):
            current_end = test_trips[i].get("end_minutes", 0)
            next_start = test_trips[i + 1].get("start_minutes", 0)

            if next_start < current_end:
                next_start += 1440

            gap = next_start - current_end
            if gap >= params.min_break_time:
                has_valid_break = True
                break

        if not has_valid_break:
            errors.append("break_required")
            return False, errors

    # K6: Shift position check (first/last trip constraints)
    constraints = trip.get("properties", {}).get("constraints", {})
    shift_pos = constraints.get("shiftPosition", "ANY")

    if shift_pos == "MUST_BE_FIRST" and len(current_trips) > 0:
        errors.append("trip_must_be_first")
        return False, errors

    # K7: Next Day Rest Rule (from legacy CheckRepo)
    next_day_rest = constraints.get("nextDayRestRule", "NONE")

    if next_day_rest == "NO_REST_TOMORROW":
        for brk in preassigned_breaks:
            if brk.get("dayIndex") == 1 and brk.get("durationMinutes", 0) > 0:
                errors.append("rest_conflict_tomorrow")
                return False, errors

    if next_day_rest == "MUST_REST_TOMORROW":
        has_rest = False
        for brk in preassigned_breaks:
            if brk.get("dayIndex") == 1 and brk.get("durationMinutes", 0) > 0:
                has_rest = True
                break
        if not has_rest:
            errors.append("missing_required_rest_tomorrow")
            return False, errors

    return True, []


def check_driver_wish_bonus(
    trip: Dict,
    resource: Dict,
    constraints_data: ConstraintsData = None,
) -> bool:
    """
    Check if driver has a positive wish for this trip.
    Used for prioritizing assignments (not a hard constraint).
    """
    if constraints_data is None:
        return False

    driver_id = resource.get("driverId", "")
    trip_id = trip.get("id", "")

    if driver_id in constraints_data.driver_wishes_positive:
        return trip_id in constraints_data.driver_wishes_positive[driver_id]

    return False
