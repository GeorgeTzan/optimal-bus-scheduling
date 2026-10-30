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
