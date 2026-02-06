import time
from framework.solver_interface import Solver
from framework.problem import Problem
from framework.solution import Solution

from services.solver import run_constructive_heuristic
from services.simulated_annealing import (
    optimize_with_simulated_annealing,
    SAConfig,
    SAWeights,
)
from services.legality_checker import SolverParameters, ConstraintsData


class GreedySASolver(Solver):
    def __init__(
        self,
        use_sa: bool = True,
        sa_config: SAConfig = None,
        sa_weights: SAWeights = None,
    ):
        self.use_sa = use_sa
        self.sa_config = sa_config or SAConfig(
            max_iters=200000, start_temp=100.0, cooling=0.9999
        )
        self.sa_weights = sa_weights or SAWeights()

    @property
    def name(self) -> str:
        return "Greedy + SA" if self.use_sa else "Greedy"

    def solve(self, problem: Problem) -> Solution:
        start = time.time()

        drivers = [
            {"busId": d.bus_id, "homeStation": d.home_station} for d in problem.drivers
        ]
        data = problem.raw

        greedy_result = run_constructive_heuristic(data["trips"], drivers, data)

        if self.use_sa:
            params = SolverParameters.from_data(data)
            constraints_data = ConstraintsData.from_data(data)
            result = optimize_with_simulated_annealing(
                full_data=data,
                greedy_result=greedy_result,
                params=params,
                constraints_data=constraints_data,
                config=self.sa_config,
                weights=self.sa_weights,
                verbose=True,
            )
        else:
            result = greedy_result

        elapsed = time.time() - start

        all_bus_states = result.get("busStates", []) + result.get("unusedBuses", [])

        return Solution(
            solver_name=self.name,
            bus_states=all_bus_states,
            unassigned_trips=result.get("unassignedTrips", []),
            metrics=result.get("metrics", {}),
            solve_time=elapsed,
            raw=result,
        )
