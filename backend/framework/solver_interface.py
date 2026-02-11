import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set

from framework.problem import Problem, Trip, Driver, Chain, Parameters
from framework.solution import Solution
from services.legality_checker import check_assignment_legality


# Template/Blueprint
class Solver(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name used in comparison table."""
        pass

    @abstractmethod
    def solve(self, problem: Problem) -> Solution:
        """Implement your logic here."""
        pass


# You write in this
class CustomSolver(Solver):
    """
    EDIT THIS CLASS DIRECTLY.
    Write your implementation in the solve() method.
    """

    @property
    def name(self) -> str:
        return "Custom Solver"

    def solve(self, problem: Problem) -> Solution:
        start = time.time()

        # 1. ACCESS PROBLEM DATA (Ready to use)
        trips: List[Trip] = problem.trips
        drivers: List[Driver] = problem.drivers
        chains: List[Chain] = problem.chains
        params: Parameters = problem.parameters
        transfer_matrix: List[List[str]] = problem.station_transfer_matrix

        # Helper lookups
        trip_lookup = {t.id: t for t in trips}
        driver_lookup = {d.bus_id: d for d in drivers}
        trip_to_chain = {tid: c for c in chains for tid in c.trip_ids}
        chained_trip_ids = {tid for c in chains for tid in c.trip_ids}

        print(trips[0].raw, "\n")  # Example of accessing raw data for a trip
        print(drivers[0].raw)  # Example of accessing raw data for a driver

        # To check if a trip is legal for a driver, you can use:
        assigned = []
        for trip in trips:
            ok, errors = check_assignment_legality(
                trip=trip_lookup[trip.id].raw,
                resource=driver_lookup[drivers[0].bus_id].raw,
                current_trips=assigned,
                params=problem.solver_params,
                constraints_data=problem.constraints_data,
            )
            print("Is legal?", ok)
            if not ok:
                print("Errors:", errors)
            else:
                assigned.append(
                    trip.raw
                )  # USE .raw HERE! check_assignment_legality needs dictionaries

        print("Assigned trips for driver 0:", len(assigned))

        # --- STEP 1: YOUR ALGORITHM ---

        my_results = []  # Replace with your algorithm output
        # ---------------------------------------------------------
        # STEP 2: REPORT RESULTS (Fill bus_states)
        # For every bus/driver used, add their assignment details.

        bus_states: List[Dict[str, Any]] = []
        assigned_trip_ids: Set[str] = set()

        # Loop through your results and fill this:
        for res in my_results:
            bus_states.append(
                {
                    "busId": "bus_id_here",
                    "driverId": "driver_id_here",
                    "homeStation": "home_station_here",
                    "assignedTrips": ["trip_id_1", "trip_id_2"],  # List of IDs
                    "totalDrivingTime": 0,  # Minutes
                    "totalIdleTime": 0,  # Minutes
                    "baseMismatch": 0,  # 1 if ends away from home
                }
            )

        # ---------------------------------------------------------
        for bs in bus_states:
            for tid in bs.get("assignedTrips", []):
                assigned_trip_ids.add(tid)

        unassigned: List[str] = [t.id for t in trips if t.id not in assigned_trip_ids]
        total_driving = sum(bs.get("totalDrivingTime", 0) for bs in bus_states)
        total_idle = sum(bs.get("totalIdleTime", 0) for bs in bus_states)
        total_mismatch = sum(bs.get("baseMismatch", 0) for bs in bus_states)

        return Solution(
            solver_name=self.name,
            bus_states=bus_states,
            unassigned_trips=unassigned,
            metrics={
                "totalTrips": len(trips),
                "totalIdleTime": total_idle,
                "totalDrivingTime": total_driving,
                "totalTransferTime": 0,
                "baseMismatchCount": total_mismatch,
                "totalOver8h": 0,
                "fairness": 0.0,
            },
            solve_time=time.time() - start,
        )
