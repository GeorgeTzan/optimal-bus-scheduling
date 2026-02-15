# class SAWeights:
#     unassigned_trip: float = 100_000_000.0
#     unused_bus: float = 50_000.0
#     overtime_minutes: float = 100.0
#     idle_minutes: float = 1.0
#     transfer_penalty: float = 10.0
#     fairness_term: float = 5.0
#     return_to_base_penalty: float = 200.0

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
        return "CV_CG Solver"

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

        def get_driver(bus_id):
            return driver_lookup[bus_id]

        def get_leg(leg_id):
            return trip_lookup[leg_id]

        def get_driving_time(shift):
            tot = 0
            for leg_id in shift[1]:
                leg = get_leg(leg_id)
                tot += leg.duration_minutes
            return tot

        def get_idle_time(shift):
            bus_id = shift[0]
            legs = shift[1]  # δρομολόγια
            sorted_legs = sorted(legs, key=lambda lid: trip_lookup[lid].start_minutes)
            first_start = trip_lookup[sorted_legs[0]].start_minutes
            last_end = trip_lookup[sorted_legs[-1]].end_minutes
            total_driving = sum(
                trip_lookup[lid].duration_minutes for lid in sorted_legs
            )
            idle_cost = (last_end - first_start) - total_driving
            return max(idle_cost, 0)

        def get_cost(shift):
            bus_id = shift[0]
            legs = shift[1]  # δρομολόγια
            if len(legs) == 0:
                return 50_000  # bus without legs
            if bus_id is None:
                return 1_000_000 * len(legs)  # legs not assigned to a bus
            return get_idle_time(shift)

        def is_valid(shift):
            # check feasibility of shift (is bus_id with list of legs legal?)
            # να μην λαμβάνει υπόψη κανόνες που μπορούν να ικανοποιηθούν με μελλοντικές αναθέσεις (π.χ. διανυκτέρευση)
            bus_id = shift[0]
            legs = shift[1]  # δρομολόγια
            if bus_id is None or len(legs) == 0:
                return True, None
            driver = driver_lookup[bus_id]
            sorted_legs = sorted(legs, key=lambda lid: trip_lookup[lid].start_minutes)
            assigned = []
            for lid in sorted_legs:
                ok, err = check_assignment_legality(
                    trip=trip_lookup[lid].raw,
                    resource=driver.raw,
                    current_trips=assigned,
                    params=problem.solver_params,
                    constraints_data=problem.constraints_data,
                )
                if not ok:
                    return (
                        False,
                        err,
                    )  # valid, error = is_valid(shift3) -> if not valid: print(error)
                assigned.append(trip_lookup[lid].raw)
            return True, None

        def get_total_cost(shift_list):
            total = 0
            for shift in shift_list:
                total += get_cost(shift)
            return total

        busses = [d.bus_id for d in drivers]  # to be filled with bus_ids
        legs = [t.id for t in trips]  # to be filled with ΔΡΟΜΟΛΟΓΙΑ ids
        shift_list = []
        for bus_id in busses:
            shift_list.append((bus_id, []))
        for leg_id in legs:
            shift_list.append((None, [leg_id]))

        import random

        ITERATIONS_LIMIT = 10_000
        c = 0
        total_cost_seq = [get_total_cost(shift_list)]
        while True:
            c += 1
            if c == ITERATIONS_LIMIT:
                break

            total_cost = get_total_cost(shift_list)
            if total_cost != total_cost_seq[-1]:
                print(f"Better solution at iteration {c+1} {total_cost=}")
                total_cost_seq.append(total_cost)
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

        bus_states: List[Dict[str, Any]] = []
        for shift in shift_list:
            bus_id = shift[0]
            legs = shift[1]
            if bus_id is None:
                continue
            if len(legs) == 0:
                continue
            driver = get_driver(bus_id)
            leg = get_leg(legs[-1])
            bus_states.append(
                {
                    "busId": bus_id,
                    "driverId": driver.driver_id,
                    "homeStation": driver.home_station,
                    "assignedTrips": legs,
                    "totalDrivingTime": get_driving_time(shift),
                    "totalIdleTime": get_idle_time(shift),
                    "baseMismatch": 1 if leg.end_station == driver.home_station else 0,
                }
            )

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
