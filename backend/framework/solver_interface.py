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

        # Access basic data
        # print(trips[0].raw, "\n")  # Example of accessing raw data for a trip
        # print(drivers[0].raw)  # Example of accessing raw data for a driver

        # ATTEMPT 1: shifts for every bus and every leg
        # SHIFT DATA STRUCTURE: BUS_ID, List[Leg]
        def get_cost(shift):
            bus_id = shift[0]
            legs = shift[1]
            if bus_id is None:
                return int(10_000 / len(legs))
            if len(legs) == 0:
                return 5_000
            idle_cost = ...
            return idle_cost

        def is_valid(shift):
            # check feasibility of shift
            ...

        def get_total_cost(shift_list):
            total = 0
            for shift in shift_list:
                total += get_cost(shift)
            return total

        busses = []  # to be filled with bus_ids
        legs = []  # to be filled with ΔΡΟΜΟΛΟΓΙΑ ids
        shift_list = []
        for bus_id in busses:
            shift_list.append((bus_id, []))
        for leg_id in legs:
            shift_list.append((None, [leg_id]))

        import random

        total_cost = get_total_cost()
        print(f"{total_cost=}")
        c = 0
        while True:
            shift1, shift2 = random.sample(shift_list, 2)
            cost1 = get_cost(shift1)
            cost2 = get_cost(shift2)

            # 1. check if all legs of shift1 can be appended at the start of shift2 ==> shift3, shift4
            shift3 = (shift1[0], shift1[1] + shift2[1])
            shift4 = (shift2[0], [])
            if is_valid(shift3):
                cost3 = get_cost(shift3)
                cost4 = get_cost(shift4)

                if cost3 + cost4 < cost1 + cost2:
                    shift_list.remove(shift1)
                    shift_list.remove(shift2)
                    if shift3[0] is not None or len(shift3[1]) > 0:
                        shift_list.append(shift3)
                    if shift4[0] is not None or len(shift4[1]) > 0:
                        shift_list.append(shift4)
                    continue

            # 2. check if all legs of shift1 can be appended at the finish of shift2 ==> shift3, shift4
            shift3 = (shift1[0], shift2[1] + shift1[1])
            shift4 = (shift2[0], [])
            if is_valid(shift3):
                cost3 = get_cost(shift3)
                cost4 = get_cost(shift4)

                if cost3 + cost4 < cost1 + cost2:
                    shift_list.remove(shift1)
                    shift_list.remove(shift2)
                    if shift3[0] is not None or len(shift3[1]) > 0:
                        shift_list.append(shift3)
                    if shift4[0] is not None or len(shift4[1]) > 0:
                        shift_list.append(shift4)
                    continue

            # 3. check if all legs of shift2 can be appended at the start of shift 1 ==> shift3, shift4
            shift3 = (shift1[0], [])
            shift4 = (shift2[0], shift2[1] + shift1[1])
            if is_valid(shift4):
                cost3 = get_cost(shift3)
                cost4 = get_cost(shift4)

                if cost3 + cost4 < cost1 + cost2:
                    shift_list.remove(shift1)
                    shift_list.remove(shift2)
                    if shift3[0] is not None or len(shift3[1]) > 0:
                        shift_list.append(shift3)
                    if shift4[0] is not None or len(shift4[1]) > 0:
                        shift_list.append(shift4)
                    continue

            # 2. check if all legs of shift3 can be appended at the finish of shift1 ==> shift3, shift4
            shift3 = (shift1[0], [])
            shift4 = (shift2[0], shift1[1] + shift2[1])
            if is_valid(shift4):
                cost3 = get_cost(shift3)
                cost4 = get_cost(shift4)

                if cost3 + cost4 < cost1 + cost2:
                    shift_list.remove(shift1)
                    shift_list.remove(shift2)
                    if shift3[0] is not None or len(shift3[1]) > 0:
                        shift_list.append(shift3)
                    if shift4[0] is not None or len(shift4[1]) > 0:
                        shift_list.append(shift4)
                    continue

            c += 1
            if c == 1000:
                break

        total_cost = get_total_cost()
        print(f"{total_cost=}")

        # --- YOUR ALGORITHM ---
        # naive solver: iterate over all bus_drivers, assign one random trip to each driver.
        import random

        bus_states: List[Dict[str, Any]] = []
        for driver in drivers:
            a_trip = random.choice(trips)
            trips.remove(a_trip)
            bus_states.append(
                {
                    "busId": driver.bus_id,
                    "driverId": driver.driver_id,  # BASE DATA 1
                    "homeStation": driver.home_station,
                    "assignedTrips": [a_trip.id],  # List of IDs # BASE DATA 2
                    "totalDrivingTime": a_trip.duration_minutes,  # Minutes
                    "totalIdleTime": 0,  # Minutes
                    "baseMismatch": (
                        1 if a_trip.end_station != driver.home_station else 0
                    ),  # 1 if ends away from home
                }
            )

        # Legality check
        # To check if a trip is legal for a driver (example for driver 0), you can use:
        # assigned = []
        # for trip in trips:
        #     ok, errors = check_assignment_legality(
        #         trip=trip_lookup[trip.id].raw,
        #         resource=driver_lookup[drivers[0].bus_id].raw,
        #         current_trips=assigned,
        #         params=problem.solver_params,
        #         constraints_data=problem.constraints_data,
        #     )
        #     # print("Is legal?", ok)
        #     if not ok:
        #         print("Errors:", errors)
        #     else:
        #         assigned.append(
        #             trip.raw
        #         )  # USE .raw HERE! check_assignment_legality needs dictionaries
        # print("Assigned trips for driver 0:", len(assigned))

        # ---------------------------------------------------------

        assigned_trip_ids: Set[str] = set()
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
