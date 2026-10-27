"""
Bounded CV Solver (v1).
Production scheduling engine incorporating safety bounds, configured PRNG seeds,
subproblem timeout and worker controls, progress sinks, and honest metrics calculation.
"""

from __future__ import annotations
import time
import random
from types import SimpleNamespace
from itertools import permutations
from typing import Any, Dict, List

from ortools.sat.python import cp_model
from framework.graph import Graph
from framework.problem import Problem
from framework.solution import Solution
from framework.cv_solver import CustomSolver
from framework.greedy_sa_solver import GreedySASolver

from app.domain.optimization.availability import availability_allows_transition, availability_allows_trip
from app.domain.optimization.contracts import (
    SolverProblem,
    SolverConfig,
    SolverResult,
    Assignment,
    ProgressSink,
    SchedulingSolver,
)
from app.domain.optimization.cv_legacy import (
    validate_cv_input,
    problem_snapshot_to_legacy_dict,
)
from app.domain.optimization.registry import register_solver


class BoundedCustomSolver(CustomSolver):
    """
    Subclass of CustomSolver overriding k_opt with:
    1. Local PRNG seeding
    2. Guaranteed iteration termination (c += 1 on all paths including continue)
    3. Safe sampling bounds when shifts are small
    4. Configured CP-SAT solver parameters (workers, seed, time limit)
    """

    def __init__(self, seed: int = 42, cp_sat_workers: int = 1, subproblem_timeout_seconds: float = 2.0):
        super().__init__()
        self.rng = random.Random(seed)
        self.seed = seed
        self.cp_sat_workers = cp_sat_workers
        self.subproblem_timeout_seconds = subproblem_timeout_seconds

    def is_valid(self, shift):
        """The reference legality check plus frozen availability: trips and travel must fit usable windows, and chain mates must too."""
        valid, error = super().is_valid(shift)
        bus_id, legs = shift
        windows = self.driver_lookup[bus_id].raw.get("availableWindows") if valid and bus_id is not None else None
        if windows is None:
            return valid, error
        crew = SimpleNamespace(available_windows=tuple(tuple(w) for w in windows))
        trips = sorted((self.trip_lookup[leg] for leg in legs), key=lambda trip: (trip.start_minutes, trip.end_minutes))
        for trip in trips:
            mates = self.trip_to_chain[trip.id].trip_ids if trip.id in self.trip_to_chain else ()
            if not availability_allows_trip(crew, trip) or any(not availability_allows_trip(crew, self.trip_lookup[mate]) for mate in mates):
                return False, "availability"
        index = {station: position for position, station in enumerate(self.problem.raw.get("availability", {}).get("stations", []))}
        matrix = self.problem.raw.get("availability", {}).get("transfer", [])
        for previous, following in zip(trips, trips[1:]):
            needed = 0 if previous.end_station == following.start_station else matrix[index[previous.end_station]][index[following.start_station]]
            if not availability_allows_transition(crew, previous, following, needed):
                return False, "availability_transfer"
        return True, None

    def sanitize(self, solution: Solution) -> Solution:
        """The shared greedy seed knows nothing about absences. Release trips availability forbids; a shift left invalid is released whole."""
        states, released = [], list(solution.unassigned_trips)
        for duty in solution.assignments:
            kept = [trip for trip in duty.assigned_trip_ids if self.is_valid((duty.bus_id, [trip]))[0]]
            released += [trip for trip in duty.assigned_trip_ids if trip not in kept]
            if kept and not self.is_valid((duty.bus_id, kept))[0]:
                released, kept = released + kept, []
            states.append({"busId": duty.bus_id, "driverId": duty.driver_id, "homeStation": duty.home_station, "assignedTrips": kept,
                           "totalDrivingTime": duty.total_driving_time, "totalIdleTime": duty.total_idle_time, "baseMismatch": duty.base_mismatch})
        return Solution(solution.solver_name, states, released, solution.metrics, solution.solve_time, solution.raw)

    def k_opt_bounded(
        self,
        k: int = 3,
        iter_limit: int = 50,
        sol: Solution = None,
    ):
        start = time.time()
        shift_list = []
        if sol is not None:
            for asg in sol.assignments:
                shift_list.append((asg.bus_id, list(asg.assigned_trip_ids)))
            if sol.unassigned_trips:
                shift_list.append((None, list(sol.unassigned_trips)))
        else:
            shift_list = [(d.bus_id, []) for d in self.drivers]
            shift_list.append((None, [t.id for t in self.trips]))

        c = 0
        total_cost_seq = [self.get_total_cost(shift_list)]

        while c < iter_limit:
            total_cost = self.get_total_cost(shift_list)
            if total_cost != total_cost_seq[-1]:
                total_cost_seq.append(total_cost)

            # Safe sampling bounded by available shifts
            n_shifts = len(shift_list)
            low_bound = min(k, n_shifts)
            high_bound = min(2 * k, n_shifts)
            sample_size = self.rng.randint(low_bound, max(low_bound, high_bound))
            pre_shifts = self.rng.sample(shift_list, sample_size)

            # Add some empty shifts
            num, max_num = 0, 2
            for sh in shift_list:
                if len(sh[1]) == 0 and sh not in pre_shifts:
                    pre_shifts.append(sh)
                    num += 1
                    if num == max_num:
                        break

            # Add unassigned shifts
            num, max_num = 0, 2
            for sh in shift_list:
                if sh[0] is None and sh not in pre_shifts:
                    pre_shifts.append(sh)
                    num += 1
                    if num == max_num:
                        break

            pre_cost = sum(self.get_cost(sh) for sh in pre_shifts)

            pre_bus = [sh[0] for sh in pre_shifts if sh[0] is not None]
            pre_leg = []
            for sh in pre_shifts:
                pre_leg.extend(sh[1])

            bus_num = len(pre_bus)
            leg_num = len(pre_leg)

            if bus_num == 0 or leg_num == 0:
                c += 1
                continue

            row_ind = {bus_leg_id: i for i, bus_leg_id in enumerate(pre_bus + pre_leg)}

            spp_shifts = pre_shifts[:]
            spp_shifts.extend([(bus_id, []) for bus_id in pre_bus])
            spp_shifts.extend([(None, [leg_id]) for leg_id in pre_leg])

            # Build graph for path search
            graph = Graph()
            for bus_id in pre_bus:
                graph.add_node(bus_id)
            for leg_id in pre_leg:
                graph.add_node(leg_id)

            for bus_id in pre_bus:
                for leg_id in pre_leg:
                    success, _ = self.is_valid((bus_id, [leg_id]))
                    if success:
                        graph.add_edge(bus_id, leg_id)

            for leg1, leg2 in permutations(pre_leg, 2):
                success, _ = self.is_valid((None, [leg1, leg2]))
                if success:
                    graph.add_edge(leg1, leg2)

            all_paths = graph.find_paths_from_buses(
                pre_bus, max_bus_paths=30, max_bus_legs=15
            )
            if not all_paths:
                c += 1
                continue

            for path in all_paths:
                bus_id = path[0]
                legs = path[1:]
                new_shift = (bus_id, legs)
                success, _ = self.is_valid(new_shift)
                if success:
                    spp_shifts.append(new_shift)

            # Build CP-SAT SPP model
            model = cp_model.CpModel()
            x_vars = [model.NewBoolVar(f"x_{i}") for i in range(len(spp_shifts))]

            for row in range(bus_num):
                v_list = [
                    x_vars[i]
                    for i, sh in enumerate(spp_shifts)
                    if sh[0] is not None and row_ind[sh[0]] == row
                ]
                model.add(sum(v_list) == 1)

            for row in range(leg_num):
                v_list = []
                for i, sh in enumerate(spp_shifts):
                    for leg_id in sh[1]:
                        if row_ind[leg_id] == bus_num + row:
                            v_list.append(x_vars[i])
                            break
                model.add(sum(v_list) == 1)

            for i, sh in enumerate(pre_shifts):
                model.add_hint(x_vars[i], 1)

            obj = sum(self.get_cost(sh) * x_vars[i] for i, sh in enumerate(spp_shifts))
            model.Minimize(obj)

            # Configure CP-SAT solver
            solver = cp_model.CpSolver()
            solver.parameters.num_search_workers = self.cp_sat_workers
            solver.parameters.random_seed = self.seed
            solver.parameters.max_time_in_seconds = self.subproblem_timeout_seconds

            status = solver.Solve(model)

            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                new_cost = int(solver.ObjectiveValue())
                if new_cost < pre_cost:
                    for sh in pre_shifts:
                        if sh in shift_list:
                            shift_list.remove(sh)
                    for i, sh in enumerate(spp_shifts):
                        if solver.value(x_vars[i]) == 1:
                            shift_list.append(sh)

            c += 1

        bus_states: List[Dict[str, Any]] = []
        for shift in shift_list:
            bus_id = shift[0]
            legs = shift[1]
            if bus_id is None or len(legs) == 0:
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

        assigned_trip_ids = set()
        for bs in bus_states:
            for tid in bs.get("assignedTrips", []):
                assigned_trip_ids.add(tid)

        unassigned = [t.id for t in self.trips if t.id not in assigned_trip_ids]
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
                    "baseMismatchCount": total_mismatch,
                    "assignedTripsCount": len(assigned_trip_ids),
                    "coveragePercent": round(len(assigned_trip_ids) / len(self.trips) * 100.0, 2)
                    if self.trips
                    else 100.0,
                },
                solve_time=time.time() - start,
            ),
            total_cost_seq[-1],
        )


class CVBoundedV1(SchedulingSolver):
    """
    Production-grade, bounded implementation of Christos Valouxis's CV Solver.
    """

    @property
    def algorithm_id(self) -> str:
        return "cv-solver"

    @property
    def version(self) -> str:
        return "cv-bounded-v1"

    def solve(
        self,
        problem: SolverProblem,
        config: SolverConfig,
        progress: ProgressSink | None = None,
    ) -> SolverResult:
        validate_cv_input(problem, minimum_resources=1)

        legacy_dict = problem_snapshot_to_legacy_dict(problem)
        legacy_problem = Problem(legacy_dict)

        solver = BoundedCustomSolver(
            seed=config.seed,
            cp_sat_workers=config.cp_sat_workers,
            subproblem_timeout_seconds=min(5.0, config.time_limit_seconds / max(1, config.iterations)),
        )
        solver.set_problem(legacy_problem)

        start_time = time.time()
        sol_best, cost_best = None, float("inf")

        for i in range(config.iterations):
            if i == 0:
                greedy = GreedySASolver(use_sa=False)
                sol = greedy.solve(legacy_problem)
                if problem.availability_enforced:
                    sol = solver.sanitize(sol)
            else:
                sol = sol_best

            sol_cost = solver.k_opt_bounded(
                k=3,
                iter_limit=25,
                sol=sol,
            )

            current_sol, current_cost = sol_cost
            if current_cost < cost_best or sol_best is None:
                sol_best, cost_best = current_sol, current_cost

            if progress is not None and hasattr(progress, "candidate"):
                # Observation hook only: expose the current best without changing search decisions.
                trip_lookup = {t.id: t for t in problem.trips}
                bus_lookup = {r.bus_id: r.resource_id for r in problem.resources}
                observed = []
                for duty in sol_best.assignments:
                    for tid in duty.assigned_trip_ids:
                        t = trip_lookup.get(tid)
                        if t:
                            observed.append(Assignment(bus_lookup[duty.bus_id], t.id, t.start_minutes,
                                                       t.end_minutes, t.start_station, t.end_station))
                progress.candidate(tuple(observed), i + 1)

            if progress is not None:
                progress.update(
                    iteration=i + 1,
                    max_iterations=config.iterations,
                    current_cost=current_cost,
                    best_cost=cost_best,
                    message=f"Completed CV iteration {i + 1}/{config.iterations}",
                )

        elapsed = time.time() - start_time
        trip_map = {t.id: t for t in problem.trips}
        resource_by_bus = {r.bus_id: r for r in problem.resources}

        assignments: List[Assignment] = []
        for da in sol_best.assignments:
            bus_id = da.bus_id
            res = resource_by_bus.get(bus_id)
            res_id = res.resource_id if res else str(bus_id)

            for tid in da.assigned_trip_ids:
                t = trip_map.get(tid)
                if t:
                    assignments.append(
                        Assignment(
                            resource_id=res_id,
                            trip_id=t.id,
                            start_minutes=t.start_minutes,
                            end_minutes=t.end_minutes,
                            start_station=t.start_station,
                            end_station=t.end_station,
                        )
                    )

        assigned_trip_ids = {a.trip_id for a in assignments}
        unassigned_trips = [t.id for t in problem.trips if t.id not in assigned_trip_ids]
        metrics = dict(sol_best.metrics)
        metrics["assignedTripsCount"] = len(assigned_trip_ids)
        metrics["unassignedTripsCount"] = len(unassigned_trips)
        metrics["coveragePercent"] = round(
            len(assigned_trip_ids) / len(problem.trips) * 100.0, 2
        ) if problem.trips else 100.0

        return SolverResult(
            solver_id=self.algorithm_id,
            solver_version=self.version,
            assignments=tuple(assignments),
            unassigned_trip_ids=tuple(unassigned_trips),
            metrics=metrics,
            solve_time_seconds=elapsed,
            status="completed",
            diagnostics={
                "assigned_drivers_count": len(sol_best.assignments),
                "iterations_completed": config.iterations,
                "seed": config.seed,
                "best_cost": cost_best,
            },
        )


# Register in production allowlist
register_solver("cv-bounded-v1", CVBoundedV1)
