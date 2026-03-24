# class SAWeights:
#     unassigned_trip: float = 100_000_000.0
#     unused_bus: float = 50_000.0
#     overtime_minutes: float = 100.0
#     idle_minutes: float = 1.0
#     transfer_penalty: float = 10.0
#     fairness_term: float = 5.0
#     return_to_base_penalty: float = 200.0

import time
import random
from collections import defaultdict
from itertools import permutations, combinations

from ortools.sat.python import cp_model
from framework.graph import Graph

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set

from framework.problem import Problem, Trip, Driver, Chain, Parameters
from framework.solution import Solution
from services.legality_checker import check_assignment_legality
from framework.greedy_sa_solver import GreedySASolver


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
        return "CV Solver"

    def set_problem(self, problem: Problem):
        self.problem = problem

        # 1. ACCESS PROBLEM DATA (Ready to use)
        self.trips: List[Trip] = problem.trips
        self.drivers: List[Driver] = problem.drivers
        self.chains: List[Chain] = problem.chains
        self.params: Parameters = problem.parameters
        self.transfer_matrix: List[List[str]] = problem.station_transfer_matrix

        # Helper lookups
        self.trip_lookup = {t.id: t for t in self.trips}
        self.driver_lookup = {d.bus_id: d for d in self.drivers}
        self.trip_to_chain = {tid: c for c in self.chains for tid in c.trip_ids}
        self.chained_trip_ids = {tid for c in self.chains for tid in c.trip_ids}

    def get_driver(self, bus_id):
        return self.driver_lookup[bus_id]

    def get_leg(self, leg_id):
        return self.trip_lookup[leg_id]

    def get_driving_time(self, shift):
        tot = 0
        for leg_id in shift[1]:
            leg = self.get_leg(leg_id)
            tot += leg.duration_minutes
        return tot

    def get_idle_time(self, shift):
        bus_id = shift[0]
        legs = shift[1]  # δρομολόγια
        sorted_legs = sorted(legs, key=lambda lid: self.trip_lookup[lid].start_minutes)
        first_start = self.trip_lookup[sorted_legs[0]].start_minutes
        last_end = self.trip_lookup[sorted_legs[-1]].end_minutes
        total_driving = sum(
            self.trip_lookup[lid].duration_minutes for lid in sorted_legs
        )
        idle_cost = (last_end - first_start) - total_driving
        return max(idle_cost, 0)

    def get_cost(self, shift):
        bus_id = shift[0]
        legs = shift[1]  # δρομολόγια
        if len(legs) == 0:
            return 50_000  # bus without legs
        if bus_id is None:
            return 1_000_000 * len(legs)  # legs not assigned to a bus
        return self.get_idle_time(shift)

    def is_valid(self, shift):
        # check feasibility of shift (is bus_id with list of legs legal?)
        # να μην λαμβάνει υπόψη κανόνες που μπορούν να ικανοποιηθούν με μελλοντικές αναθέσεις (π.χ. διανυκτέρευση)
        bus_id = shift[0]
        legs = shift[1]  # δρομολόγια

        driver_raw = None
        if bus_id is not None:
            driver_raw = self.driver_lookup[bus_id].raw

        sorted_legs = (
            legs  # sorted(legs, key=lambda lid: self.trip_lookup[lid].start_minutes)
        )

        for leg1, leg2 in zip(sorted_legs, sorted_legs[1:]):
            if (
                self.trip_lookup[leg1].end_minutes
                > self.trip_lookup[leg2].start_minutes
            ):
                return False, None

        assigned = []
        for lid in sorted_legs:
            ok, err = check_assignment_legality(
                trip=self.trip_lookup[lid].raw,
                resource=driver_raw,
                current_trips=assigned,
                params=self.problem.solver_params,
                constraints_data=self.problem.constraints_data,
            )
            if not ok:
                return (
                    False,
                    err,
                )  # valid, error = is_valid(shift3) -> if not valid: print(error)
            assigned.append(self.trip_lookup[lid].raw)
        return True, None

    def get_total_cost(self, shift_list):
        total = 0
        for shift in shift_list:
            total += self.get_cost(shift)
        return total

    def two_opt(self) -> Solution:
        start = time.time()

        # Access basic data
        # print(trips[0].raw, "\n")  # Example of accessing raw data for a trip
        # print(drivers[0].raw)  # Example of accessing raw data for a driver

        # ATTEMPT 1: shifts for every bus and every leg
        # SHIFT DATA STRUCTURE: BUS_ID, List[Leg]

        busses = [d.bus_id for d in self.drivers]  # to be filled with bus_ids
        legs = [t.id for t in self.trips]  # to be filled with ΔΡΟΜΟΛΟΓΙΑ ids
        shift_list = []
        for bus_id in busses:
            shift_list.append((bus_id, []))
        for leg_id in legs:
            shift_list.append((None, [leg_id]))

        ITERATIONS_LIMIT = 10_000
        c = 0
        total_cost_seq = [self.get_total_cost(shift_list)]
        while True:
            total_cost = self.get_total_cost(shift_list)
            if total_cost != total_cost_seq[-1]:
                print(f"Better solution at iteration {c+1} {total_cost=}")
                total_cost_seq.append(total_cost)
            shift1, shift2 = random.sample(shift_list, 2)
            cost1 = self.get_cost(shift1)
            cost2 = self.get_cost(shift2)

            # 1. check if all legs of shift1 can be appended at the start of shift2 ==> shift3, shift4
            shift3 = (shift1[0], shift1[1] + shift2[1])
            shift4 = (shift2[0], [])
            success, error = self.is_valid(shift3)
            if success:
                cost3 = self.get_cost(shift3)
                cost4 = self.get_cost(shift4)

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
            success, error = self.is_valid(shift3)
            if success:
                cost3 = self.get_cost(shift3)
                cost4 = self.get_cost(shift4)

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
            success, error = self.is_valid(shift4)
            if success:
                cost3 = self.get_cost(shift3)
                cost4 = self.get_cost(shift4)

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
            success, error = self.is_valid(shift4)
            if success:
                cost3 = self.get_cost(shift3)
                cost4 = self.get_cost(shift4)

                if cost3 + cost4 < cost1 + cost2:
                    shift_list.remove(shift1)
                    shift_list.remove(shift2)
                    if shift3[0] is not None or len(shift3[1]) > 0:
                        shift_list.append(shift3)
                    if shift4[0] is not None or len(shift4[1]) > 0:
                        shift_list.append(shift4)
                    continue

            c += 1
            if c == ITERATIONS_LIMIT:
                break

        bus_states: List[Dict[str, Any]] = []
        for shift in shift_list:
            bus_id = shift[0]
            legs = shift[1]
            if bus_id is None:
                continue
            if len(legs) == 0:
                continue
            driver = self.get_driver(bus_id)
            leg = self.get_leg(legs[-1])
            bus_states.append(
                {
                    "busId": bus_id,
                    "driverId": driver.driver_id,
                    "homeStation": driver.home_station,
                    "assignedTrips": legs,
                    "totalDrivingTime": self.get_driving_time(shift),
                    "totalIdleTime": self.get_idle_time(shift),
                    "baseMismatch": 1 if leg.end_station == driver.home_station else 0,
                }
            )

        # ---------------------------------------------------------

        assigned_trip_ids: Set[str] = set()
        for bs in bus_states:
            for tid in bs.get("assignedTrips", []):
                assigned_trip_ids.add(tid)

        unassigned: List[str] = [
            t.id for t in self.trips if t.id not in assigned_trip_ids
        ]
        total_driving = sum(bs.get("totalDrivingTime", 0) for bs in bus_states)
        total_idle = sum(bs.get("totalIdleTime", 0) for bs in bus_states)
        total_mismatch = sum(bs.get("baseMismatch", 0) for bs in bus_states)

        return Solution(
            solver_name=self.name,
            bus_states=bus_states,
            unassigned_trips=unassigned,
            metrics={
                "totalTrips": len(self.trips),
                "totalIdleTime": total_idle,
                "totalDrivingTime": total_driving,
                "totalTransferTime": 0,
                "baseMismatchCount": total_mismatch,
                "totalOver8h": 0,
                "fairness": 0.0,
            },
            solve_time=time.time() - start,
        )

    def k_opt(self, k=2, iter_limit=500, sol: Solution = None) -> tuple[Solution, int]:
        start = time.time()

        # Access basic data
        # print(trips[0].raw, "\n")  # Example of accessing raw data for a trip
        # print(drivers[0].raw)  # Example of accessing raw data for a driver

        # ATTEMPT 1: shifts for every bus and every leg
        # SHIFT DATA STRUCTURE: BUS_ID, List[Leg]

        busses = [d.bus_id for d in self.drivers]  # to be filled with bus_ids
        legs = [t.id for t in self.trips]  # to be filled with ΔΡΟΜΟΛΟΓΙΑ ids

        # initial solution: (buses, no legs) and (no bus, one leg)
        shift_list = []
        if sol is None:
            for bus_id in busses:
                shift_list.append((bus_id, []))
            for leg_id in legs:
                shift_list.append((None, [leg_id]))

        # initial solution from greedy solver
        else:
            busses_used = []
            for assi in sol.assignments:
                shift = (assi.bus_id, assi.assigned_trip_ids)
                success, error = self.is_valid(shift)
                if success:
                    shift_list.append(shift)
                    busses_used.append(assi.bus_id)
                else:
                    print(f"not valid: {error=} {shift=}")
                    for leg_id in assi.assigned_trip_ids:
                        shift_list.append((None, [leg_id]))

            for bus_id in busses:
                if bus_id not in busses_used:
                    shift_list.append((bus_id, []))
            for leg_id in sol.unassigned_trips:
                shift_list.append((None, [leg_id]))

        # n1 = 2 !!!, n2 = 386
        n1 = legs.count("110016")
        n2 = len(set(legs))

        c = 0  # iteration counter
        total_cost_seq = [self.get_total_cost(shift_list)]

        while True:
            total_cost = self.get_total_cost(shift_list)
            if total_cost != total_cost_seq[-1]:
                print(f"Better solution at iteration {c+1} {total_cost=}")
                total_cost_seq.append(total_cost)

            # choose k random shifts
            # pre_shifts = random.sample(shift_list, k)
            pre_shifts = random.sample(shift_list, random.randint(k, 2 * k))

            # add some shifts with no legs (only bus)
            num, max_num = 0, 2
            for sh in shift_list:
                if len(sh[1]) == 0 and sh not in pre_shifts:
                    pre_shifts.append(sh)
                    num += 1
                    if num == max_num:
                        break

            # add some shifts with no bus (only legs)
            num, max_num = 0, 2
            for sh in shift_list:
                if sh[0] is None and sh not in pre_shifts:
                    pre_shifts.append(sh)
                    num += 1
                    if num == max_num:
                        break

            pre_cost = sum(self.get_cost(sh) for sh in pre_shifts)

            # generate shifts for all busses for legs in shift1, shift2
            # choose shifts solving a SPP
            pre_bus = [sh[0] for sh in pre_shifts if sh[0] is not None]
            pre_leg = []
            for sh in pre_shifts:
                pre_leg.extend(sh[1])

            bus_num = len(pre_bus)
            leg_num = len(pre_leg)

            if bus_num == 0 or leg_num == 0:
                continue

            # dict to have the SPP row of a bus_id or a leg_id
            row_ind = {bus_leg_id: i for i, bus_leg_id in enumerate(pre_bus + pre_leg)}

            # rows of SPP -> bus_num + leg_num
            # cols of SPP ->
            #   previous shifts + (a solution to start) +
            #   bus_num (shifts with only bus, no legs) + (for feasibility)
            #   leg_num (shifts with only 1 leg, no bus) + (for feasibility)
            #   new generated shifts
            spp_shifts = pre_shifts[:]
            spp_shifts.extend([(bus_id, []) for bus_id in pre_bus])
            spp_shifts.extend([(None, [leg_id]) for leg_id in pre_leg])

            # build a graph for shifts generation
            # Initialize the graph
            graph = Graph()

            # Add vertices for buses and legs
            for bus_id in pre_bus:
                graph.add_node(bus_id)

            for leg_id in pre_leg:
                graph.add_node(leg_id)

            # Add edges between buses and legs
            for bus_id in pre_bus:
                for leg_id in pre_leg:
                    success, error = self.is_valid((bus_id, [leg_id]))
                    if success:  # Check if the bus can handle the leg
                        # cost = self.get_cost((bus_id, [leg_id]))
                        graph.add_edge(bus_id, leg_id)

            for leg1, leg2 in permutations(pre_leg, 2):
                # if self.trip_lookup[leg1].end_minutes > self.trip_lookup[leg2].start_minutes:
                # continue
                success, error = self.is_valid((None, [leg1, leg2]))
                if success:
                    graph.add_edge(leg1, leg2)

            # Find all valid paths from buses in pre_bus
            # print(f'generating... {bus_num=} {leg_num=}')
            all_paths = graph.find_paths_from_buses(
                pre_bus, max_bus_paths=30, max_bus_legs=15
            )  # 30)
            if not all_paths:
                continue

            for path in all_paths:
                bus_id = path[0]
                legs = path[1:]
                new_shift = (bus_id, legs)
                success, error = self.is_valid(new_shift)
                if success:
                    spp_shifts.append(new_shift)

            # ---
            model = cp_model.CpModel()

            # a binary var for each shift
            x_vars = [model.NewBoolVar(f"x_{i}") for i in range(len(spp_shifts))]

            # every bus must be used by exactly one shift
            for row in range(bus_num):
                v_list = [
                    x_vars[i]
                    for i, sh in enumerate(spp_shifts)
                    if sh[0] is not None and row_ind[sh[0]] == row
                ]
                model.add(sum(v_list) == 1)

            # every leg must be used by exactly one shift
            for row in range(leg_num):
                v_list = []
                for i, sh in enumerate(spp_shifts):
                    for leg_id in sh[1]:
                        if row_ind[leg_id] == bus_num + row:
                            v_list.append(x_vars[i])
                            break
                model.add(sum(v_list) == 1)

            # hints for previous shifts
            for i, sh in enumerate(pre_shifts):
                model.add_hint(x_vars[i], 1)

            # objective
            obj = sum(self.get_cost(sh) * x_vars[i] for i, sh in enumerate(spp_shifts))
            model.Minimize(obj)

            # print(f'solving... {bus_num=} {leg_num=} {len(spp_shifts)=} {len(all_paths)=}')
            solver = cp_model.CpSolver()
            status = solver.Solve(model)
            # status = solver.Solve(model, solution_callback=cp_model.ObjectiveSolutionPrinter())

            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                new_cost = int(solver.ObjectiveValue())
                if new_cost < pre_cost:
                    # print(f'k-opt: {new_cost=} {pre_cost=} improve={pre_cost-new_cost}')
                    for sh in pre_shifts:
                        shift_list.remove(sh)
                    for i, sh in enumerate(spp_shifts):
                        if solver.value(x_vars[i]) == 1:
                            shift_list.append(sh)
            else:
                print(f"no solution, {solver.status_name(status)}")
                # print(f'{row_ind=}')
                # print(f'{pre_bus=} {pre_leg=}')
                # print('pre_shifts')
                # for sh in pre_shifts:
                #     print(sh)
                # print('spp_shifts')
                # for sh in spp_shifts:
                #     print(sh)

            c += 1
            if c == iter_limit:
                break

        bus_states: List[Dict[str, Any]] = []
        for shift in shift_list:
            bus_id = shift[0]
            legs = shift[1]
            if bus_id is None:
                continue
            if len(legs) == 0:
                continue
            driver = self.get_driver(bus_id)
            leg = self.get_leg(legs[-1])
            bus_states.append(
                {
                    "busId": bus_id,
                    "driverId": driver.driver_id,
                    "homeStation": driver.home_station,
                    "assignedTrips": legs,
                    "totalDrivingTime": self.get_driving_time(shift),
                    "totalIdleTime": self.get_idle_time(shift),
                    "baseMismatch": 1 if leg.end_station == driver.home_station else 0,
                }
            )

        # ---------------------------------------------------------

        assigned_trip_ids: Set[str] = set()
        for bs in bus_states:
            for tid in bs.get("assignedTrips", []):
                assigned_trip_ids.add(tid)

        unassigned: List[str] = [
            t.id for t in self.trips if t.id not in assigned_trip_ids
        ]
        total_driving = sum(bs.get("totalDrivingTime", 0) for bs in bus_states)
        total_idle = sum(bs.get("totalIdleTime", 0) for bs in bus_states)
        total_mismatch = sum(bs.get("baseMismatch", 0) for bs in bus_states)

        return (
            Solution(
                solver_name=self.name,
                bus_states=bus_states,
                unassigned_trips=unassigned,
                metrics={
                    "totalTrips": len(self.trips),
                    "totalIdleTime": total_idle,
                    "totalDrivingTime": total_driving,
                    "totalTransferTime": 0,
                    "baseMismatchCount": total_mismatch,
                    "totalOver8h": 0,
                    "fairness": 0.0,
                },
                solve_time=time.time() - start,
            ),
            total_cost_seq[-1],
        )

    # --------------------------------------------
    def solve(self, problem: Problem, iterations=5, previous_solution=None) -> Solution:
        # random.seed(123)
        self.set_problem(problem)

        # return self.two_opt()
        sol_best, cost_best = None, float('inf')
        for i in range(iterations):
            print(f'--- iter {i+1}/{iterations} {cost_best=} ---')
            if i == 0 and previous_solution is not None:
                sol = Solution(
                    solver_name=previous_solution.get("solverName", "Previous"),
                    bus_states=previous_solution.get("busStates", []),
                    unassigned_trips=previous_solution.get("unassignedTrips", []),
                    metrics=previous_solution.get("metrics", {}),
                    solve_time=previous_solution.get("solveTime", 0.0),
                )
            else:
                greedy = GreedySASolver(use_sa=False)
                sol = greedy.solve(self.problem)

            sol_cost = self.k_opt(k=3, iter_limit=1_000, sol=sol)

            if sol_cost[1] < cost_best:
                sol_best, cost_best = sol_cost

        return sol_best
