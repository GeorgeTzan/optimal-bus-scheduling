"""
Bounded CV Solver (v1).
Production scheduling engine incorporating safety bounds, configured PRNG seeds,
subproblem timeout and worker controls, progress sinks, and honest metrics calculation.
"""

from __future__ import annotations
import time
import random
from datetime import datetime, time as dtime, timedelta, timezone
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
from app.domain.workrules.budget import DriverDayBudget, day_baseline, legal_duty
from app.domain.workrules.facts import duty_facts
from app.domain.workrules.policy import WorkRulePolicy
from app.domain.workrules.timeline import DriverProfile, DriverTimeline, Duty, DutyTrip
from app.domain.optimization.cv_legacy import (
    validate_cv_input,
    problem_snapshot_to_legacy_dict,
)


def _duty(problem: SolverProblem, driver_id: str, resources, legs) -> Duty:
    origin = datetime.combine(problem.service_date, dtime(), timezone.utc)
    trips = {t.id: t for t in problem.trips}
    duty_legs = []
    for resource_id, trip_id in legs:
        trip = trips[trip_id]
        duty_legs.append(DutyTrip(
            trip_id=trip.id,
            start=origin + timedelta(minutes=trip.start_minutes),
            end=origin + timedelta(minutes=trip.end_minutes),
            origin=trip.start_station,
            destination=trip.end_station,
            origin_is_depot=trip.origin_is_depot,
            destination_is_depot=trip.destination_is_depot,
            vehicle_id=resources[resource_id].bus_id,
            route_id=trip.route_id,
            urban=trip.urban,
            long_route=trip.long_route,
            en_route_break_minutes=trip.en_route_break_minutes,
        ))
    return Duty(driver_id, problem.service_date, tuple(duty_legs), "draft")


def _timeline(problem: SolverProblem, driver_id: str, home_station: str, budget: DriverDayBudget | None) -> DriverTimeline:
    profile = DriverProfile(
        home_station=home_station,
        overnight_allowed=budget.overnight_allowed if budget else True,
        split_shift_allowed=budget.split_shift_allowed if budget else True,
        must_return_to_base=budget.must_return_to_base if budget else False,
        forbidden_routes=frozenset(budget.forbidden_route_ids if budget else ()),
        preferred_routes=frozenset(budget.preferred_route_ids if budget else ()),
    )
    vehicles = {k: frozenset(v) for k, v in budget.forbidden_vehicle_route_ids.items()} if budget else {}
    return DriverTimeline(driver_id, profile, (), None, problem.service_date, vehicles)


class DutyRules:
    def __init__(self, problem: SolverProblem):
        self.problem = problem
        self.policy = WorkRulePolicy.from_dict(problem.work_policy)
        self.budgets = {b["driver_id"]: DriverDayBudget.from_dict(b) for b in problem.driver_budgets}
        self.resources = {r.resource_id: r for r in problem.resources}
        self.resource_by_bus = {r.bus_id: r for r in problem.resources}
        self.homes: Dict[str, str] = {}
        for r in problem.resources:
            self.homes.setdefault(str(r.driver_id), r.home_station)
        self.starts = {t.id: (t.start_minutes, t.id) for t in problem.trips}
        self.index = {station: i for i, station in enumerate(problem.stations)}
        self.origin = datetime.combine(problem.service_date, dtime(), timezone.utc)
        self.timelines: Dict[str, DriverTimeline] = {}
        self.baselines: Dict[str, tuple] = {}
        self.verdicts: Dict[tuple, bool] = {}

    def transfer(self, a: str, b: str):
        return self.problem.transfer_matrix[self.index[a]][self.index[b]] if a in self.index and b in self.index else None

    def shift_fits(self, bus_id, trip_ids) -> bool:
        resource = self.resource_by_bus[bus_id]
        return self.fits(str(resource.driver_id), [(resource.resource_id, trip_id) for trip_id in trip_ids])

    def fits(self, driver_id: str, legs) -> bool:
        if not legs:
            return True
        key = (driver_id, tuple(sorted(legs)))
        if key not in self.verdicts:
            self.verdicts[key] = self.judge(driver_id, sorted(legs, key=lambda leg: self.starts[leg[1]]))
        return self.verdicts[key]

    def judge(self, driver_id: str, legs) -> bool:
        budget = self.budgets.get(driver_id)
        if driver_id not in self.timelines:
            self.timelines[driver_id] = _timeline(self.problem, driver_id, self.homes[driver_id], budget)
            self.baselines[driver_id] = day_baseline(self.timelines[driver_id], self.policy, self.problem.service_date, self.transfer)
        timeline = self.timelines[driver_id]
        duty = _duty(self.problem, driver_id, self.resources, legs)
        if budget is not None:
            facts = duty_facts(duty, timeline.profile, self.policy, self.transfer)
            if (
                facts.start < self.origin + timedelta(minutes=budget.earliest_start_minutes)
                or facts.end > self.origin + timedelta(minutes=budget.latest_end_minutes)
                or facts.work_minutes > budget.max_work_minutes
                or facts.long_route_driving_minutes > budget.max_long_route_driving_minutes
            ):
                return False
        return legal_duty(duty, timeline, self.policy, self.transfer, kinds=("legal", "warning"), baseline=self.baselines[driver_id])[0]


def legal_assignments(problem: SolverProblem, assignments, rules: DutyRules | None = None) -> tuple[Assignment, ...]:
    assignments = tuple(assignments)
    if problem.work_policy is None:
        return assignments
    rules = rules or DutyRules(problem)
    mates = {trip_id: chain.trip_ids for chain in problem.chains for trip_id in chain.trip_ids}
    released: set = set()
    while True:
        grouped: Dict[str, List[Assignment]] = {}
        for assignment in assignments:
            if assignment.resource_id in rules.resources and assignment.trip_id not in released:
                grouped.setdefault(str(rules.resources[assignment.resource_id].driver_id), []).append(assignment)
        before = len(released)
        for driver_id, items in grouped.items():
            items = sorted(items, key=lambda a: (a.start_minutes, a.trip_id))
            while not rules.fits(driver_id, [(a.resource_id, a.trip_id) for a in items]):
                dropped = set(mates.get(items[-1].trip_id, (items[-1].trip_id,)))
                released |= dropped
                items = [a for a in items if a.trip_id not in dropped]
        if len(released) == before:
            return tuple(a for a in assignments if a.trip_id not in released)


def fill_gaps(solver, problem: SolverProblem, assignments) -> List[Assignment]:
    trips = {t.id: t for t in problem.trips}
    duties: Dict[str, List[str]] = {}
    for assignment in assignments:
        duties.setdefault(assignment.resource_id, []).append(assignment.trip_id)
    taken = {a.trip_id for a in assignments}
    added: List[Assignment] = []
    for trip in sorted(problem.trips, key=lambda t: (t.start_minutes, t.id)):
        group = solver.trip_to_chain[trip.id].trip_ids if trip.id in solver.trip_to_chain else (trip.id,)
        if taken & set(group):
            continue
        for resource in problem.resources:
            legs = sorted(duties.get(resource.resource_id, []) + list(group), key=lambda t: (trips[t].start_minutes, t))
            if solver.is_valid((resource.bus_id, legs))[0]:
                duties[resource.resource_id] = legs
                taken |= set(group)
                added += [Assignment(resource.resource_id, t, trips[t].start_minutes, trips[t].end_minutes,
                                     trips[t].start_station, trips[t].end_station) for t in group]
                break
    return [*assignments, *added]


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
        self.rules: DutyRules | None = None

    def is_valid(self, shift):
        valid, error = self.is_valid_partial(shift)
        bus_id, legs = shift
        if valid and bus_id is not None and self.rules is not None and not self.rules.shift_fits(bus_id, legs):
            return False, "work_rules"
        return valid, error

    def is_valid_partial(self, shift):
        """The reference legality check plus frozen availability: trips and travel must fit usable windows, and chain mates must too."""
        valid, error = super().is_valid(shift)
        bus_id, legs = shift
        if valid and bus_id is not None and not self.within_budget(self.driver_lookup[bus_id].raw, legs):
            return False, "work_budget"
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

    def within_budget(self, raw, legs) -> bool:
        if "earliestStartMinutes" not in raw or not legs:
            return True
        trips = [self.trip_lookup[leg] for leg in legs]
        covered = {mate for leg in legs for mate in (self.trip_to_chain[leg].trip_ids if leg in self.trip_to_chain else (leg,))}
        if covered & set(raw["prohibitedTripIds"]):
            return False
        if any(self.trip_lookup[t].start_minutes < raw["earliestStartMinutes"] or self.trip_lookup[t].end_minutes > raw["latestEndMinutes"] for t in covered):
            return False
        if max(t.end_minutes for t in trips) - min(t.start_minutes for t in trips) > raw["maxDutyMinutes"]:
            return False
        return sum(t.duration_minutes for t in trips if t.raw.get("longRoute", True)) <= raw["maxWorkMinutes"]

    def sanitize(self, solution: Solution) -> Solution:
        """The shared greedy seed knows nothing about absences or work rules. Trim each shift from its end until it is valid."""
        states, released = [], list(solution.unassigned_trips)
        for duty in solution.assignments:
            kept = list(duty.assigned_trip_ids)
            while kept and not self.is_valid((duty.bus_id, kept))[0]:
                released.append(kept.pop())
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
                    success, _ = self.is_valid_partial((bus_id, [leg_id]))
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
        solver.rules = DutyRules(problem) if problem.work_policy is not None else None

        start_time = time.time()
        sol_best, cost_best = None, float("inf")

        for i in range(config.iterations):
            if i == 0:
                greedy = GreedySASolver(use_sa=False)
                sol = greedy.solve(legacy_problem)
                if problem.availability_enforced or problem.driver_budgets or solver.rules is not None:
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
                progress.candidate(legal_assignments(problem, observed, solver.rules), i + 1)

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

        assignments = list(legal_assignments(problem, fill_gaps(solver, problem, legal_assignments(problem, assignments, solver.rules)), solver.rules))
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

