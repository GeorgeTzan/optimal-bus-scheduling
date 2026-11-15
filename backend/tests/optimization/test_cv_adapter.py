from datetime import datetime, date, timezone
import pytest

from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot
from app.domain.optimization.adapter import (
    OperationalSnapshot,
    SyntheticResourcePair,
    to_cv_problem,
)


def test_fixed_pairings_no_mid_duty_swap():
    """
    CV v1 maps each pre-approved driver-vehicle pairing to a synthetic resource for a service day.
    Mid-duty driver/bus swaps are prohibited; each synthetic resource maintains an immutable pairing.
    """
    pairs = [
        SyntheticResourcePair(driver_id=1, vehicle_id=101, home_station="Patras", bus_type="01"),
        SyntheticResourcePair(driver_id=2, vehicle_id=102, home_station="Athens", bus_type="01"),
    ]
    snapshot = OperationalSnapshot(
        tenant_id=1,
        service_date=date(2026, 6, 1),
        pairings=pairs,
        transfer_durations={("Patras","Athens"):180,("Athens","Patras"):180},
        trips=[
            {
                "id": "T1",
                "origin": "Patras",
                "destination": "Athens",
                "start_time": "08:00",
                "arrival_day_offset": 0,
                "allowed_bus_types": ["01"],
                "end_time": "11:00",
            },
            {
                "id": "T2",
                "origin": "Athens",
                "destination": "Patras",
                "start_time": "12:00",
                "arrival_day_offset": 0,
                "allowed_bus_types": ["01"],
                "end_time": "15:00",
            },
        ],
    )

    cv_problem = to_cv_problem(snapshot)
    assert len(cv_problem.resources) == 2
    # Resources are synthetic pairs
    r1 = cv_problem.resources[0]
    r2 = cv_problem.resources[1]
    assert r1.resource_id == "PAIR_1_101"
    assert r2.resource_id == "PAIR_2_102"
    assert r1.driver_id == "1"
    assert r1.bus_id == "101"
    assert r1.home_station == "Patras"
    assert r2.home_station == "Athens"


def test_cv_adapter_calculates_true_elapsed_offsets():
    """
    Ensure the adapter normalizes trip times using the time_service to produce accurate minute offsets.
    """
    pairs = [
        SyntheticResourcePair(driver_id=1, vehicle_id=101, home_station="Patras", bus_type="01"),
    ]
    snapshot = OperationalSnapshot(
        tenant_id=1,
        service_date=date(2026, 6, 1),
        pairings=pairs,
        transfer_durations={("Patras","Athens"):180,("Athens","Patras"):180},
        trips=[
            {
                "id": "TRIP-MORNING",
                "origin": "Patras",
                "destination": "Athens",
                "start_time": "07:30",
                "arrival_day_offset": 0,
                "allowed_bus_types": ["01"],
                "end_time": "10:45",
            },
        ],
    )

    cv_problem = to_cv_problem(snapshot)
    assert len(cv_problem.trips) == 1
    t = cv_problem.trips[0]
    assert t.id == "TRIP-MORNING"
    assert t.start_minutes == 7 * 60 + 30  # 450
    assert t.end_minutes == 10 * 60 + 45   # 645
    assert t.duration_minutes == 195


def test_adapter_carries_route_facts():
    snapshot = OperationalSnapshot(
        tenant_id=1,
        service_date=date(2026, 6, 1),
        pairings=[SyntheticResourcePair(driver_id=1, vehicle_id=101, home_station="Patras", bus_type="01")],
        transfer_durations={("Patras", "Athens"): 180, ("Athens", "Patras"): 180},
        trips=[
            {"id": "T1", "origin": "Patras", "destination": "Athens", "start_time": "07:30", "end_time": "10:45",
             "arrival_day_offset": 0, "allowed_bus_types": ["01"], "route_id": 9, "urban": True, "long_route": False,
             "origin_is_depot": True, "destination_is_depot": False},
            {"id": "T2", "origin": "Athens", "destination": "Patras", "start_time": "12:00", "end_time": "15:00",
             "arrival_day_offset": 0, "allowed_bus_types": ["01"]},
        ],
    )
    first, second = to_cv_problem(snapshot).trips
    assert (first.route_id, first.urban, first.long_route, first.origin_is_depot, first.destination_is_depot) == (9, True, False, True, False)
    assert (second.route_id, second.urban, second.long_route, second.origin_is_depot) == (None, False, True, False)


def test_legacy_dict_carries_budget_limits():
    from app.domain.optimization.cv_legacy import problem_snapshot_to_legacy_dict
    from app.domain.workrules.budget import DriverDayBudget
    from app.domain.workrules.policy import build_policy

    def budget(driver, **values):
        base = dict(driver_id=driver, earliest_start_minutes=0, latest_end_minutes=2880, max_work_minutes=600,
                    max_long_route_driving_minutes=600, continuous_driving_minutes=270, overnight_allowed=True,
                    split_shift_allowed=True, must_return_to_base=False, forbidden_route_ids=(),
                    preferred_route_ids=(), forbidden_vehicle_route_ids={})
        return DriverDayBudget(**{**base, **values}).to_dict()

    trips = (
        TripSnapshot("T1", "A", "B", 480, 540, 60, route_id=1),
        TripSnapshot("T2", "B", "A", 600, 660, 60, route_id=2, long_route=False),
        TripSnapshot("T3", "A", "B", 700, 760, 60, route_id=3),
    )
    resources = (ResourceSnapshot("PAIR_1", "1", "V1", "A"), ResourceSnapshot("PAIR_2", "2", "V2", "A"))
    problem = SolverProblem(
        "P", "1", date(2026, 6, 1), trips, resources, (), ("A", "B"), ((0, 30), (30, 0)),
        work_policy=build_policy({"continuous_driving": 240}, [], 1).to_dict(),
        driver_budgets=(
            budget("1", earliest_start_minutes=600, latest_end_minutes=1500, max_work_minutes=420,
                   max_long_route_driving_minutes=300, forbidden_route_ids=(1,), preferred_route_ids=(3,)),
            budget("2", forbidden_vehicle_route_ids={"V2": (2,), "V1": (3,)}),
        ),
    )
    data = problem_snapshot_to_legacy_dict(problem)
    assert data["configuration"]["parameters"] == {
        "maxDutyMinutes": 600, "normalDutyMinutes": 480, "maxWorkMinutes": 600,
        "driveTimeToBreakMinutes": 240, "minBreakMinutes": 45, "transitMinutes": 30,
    }
    first, second = data["resources"]
    assert (first["earliestStartMinutes"], first["latestEndMinutes"], first["maxDutyMinutes"], first["maxWorkMinutes"]) == (600, 1500, 420, 300)
    assert first["prohibitedTripIds"] == ["T1"] and second["prohibitedTripIds"] == ["T2"]
    assert data["constraints"]["driverWishes"] == [{"driverId": "1", "tripId": "T3", "type": 1}]
    assert [t["longRoute"] for t in data["trips"]] == [True, False, True]


def test_legacy_dict_without_work_rules_keeps_reference_parameters():
    from app.domain.optimization.cv_legacy import problem_snapshot_to_legacy_dict
    problem = SolverProblem("P", "1", date(2026, 6, 1), (TripSnapshot("T1", "A", "A", 480, 540, 60),),
                            (ResourceSnapshot("R1", "1", "V1", "A"),), ())
    data = problem_snapshot_to_legacy_dict(problem)
    assert data["configuration"]["parameters"] == {
        "maxDutyMinutes": 600, "normalDutyMinutes": 600, "maxWorkMinutes": 900,
        "driveTimeToBreakMinutes": 270, "minBreakMinutes": 30, "transitMinutes": 30,
    }
    assert "earliestStartMinutes" not in data["resources"][0] and "longRoute" not in data["trips"][0]
    assert "driverWishes" not in data["constraints"]
