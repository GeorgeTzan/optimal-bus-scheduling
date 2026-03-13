from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import os
import traceback

from dat_parser import parse_trips, parse_drivers, get_full_data
from services.solver import run_constructive_heuristic
from framework.problem import Problem
from framework.cv_solver import CustomSolver
from services.simulated_annealing import (
    optimize_with_simulated_annealing,
    SAConfig,
    SAWeights,
)
from services.legality_checker import SolverParameters, ConstraintsData
from services.legacy_loader import load_legacy_solution
from services.lahc import optimize_with_lahc, LAHCConfig

router = APIRouter(tags=["Solver"])


class SolveRequest(BaseModel):
    mode: str = Field(default="greedy", description="greedy | sa")
    sa_iters: int = Field(default=4000, ge=1, le=200000)
    sa_temp: float = Field(default=50.0, gt=0)
    sa_cooling: float = Field(default=0.999, gt=0, lt=1)
    w_fairness: float = Field(default=1.0, ge=0)
    w_over8h: float = Field(default=4.0, ge=0)
    w_idle: float = Field(default=1.0, ge=0)
    w_unused: float = Field(default=250.0, ge=0)


@router.post("/solve")
def solve(req: SolveRequest = SolveRequest()):
    trips = parse_trips()
    drivers = parse_drivers()
    full_data = get_full_data()

    greedy = run_constructive_heuristic(trips, drivers, full_data)

    if req.mode.lower() != "sa":
        return greedy

    params = SolverParameters.from_data(full_data)
    constraints = ConstraintsData.from_data(full_data)
    config = SAConfig(
        max_iters=req.sa_iters,
        start_temp=req.sa_temp,
        cooling=req.sa_cooling,
    )
    weights = SAWeights(
        fairness_term=req.w_fairness,
        overtime_minutes=req.w_over8h,
        idle_minutes=req.w_idle,
    )

    return optimize_with_simulated_annealing(
        full_data=full_data,
        greedy_result=greedy,
        params=params,
        constraints_data=constraints,
        config=config,
        weights=weights,
        verbose=False,
    )


@router.post("/solve/legacy")
def solve_legacy():
    shifts_path = "/app/shifts.dat"

    if not os.path.exists(shifts_path):
        local_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "shifts.dat"
        )
        if os.path.exists(local_path):
            shifts_path = local_path

    if not os.path.exists(shifts_path):
        return {
            "error": f"Legacy shifts file not found at {shifts_path}",
            "metrics": None,
        }

    return load_legacy_solution(shifts_path)


class LAHCRequest(BaseModel):
    previous_solution: Optional[dict] = Field(default=None)


@router.post("/solve/lahc")
def solve_lahc(req: LAHCRequest = LAHCRequest()):
    full_data = get_full_data()
    params = SolverParameters.from_data(full_data)
    constraints = ConstraintsData.from_data(full_data)
    config = LAHCConfig()
    weights = SAWeights()

    return optimize_with_lahc(
        full_data=full_data,
        params=params,
        constraints_data=constraints,
        config=config,
        weights=weights,
        previous_solution=req.previous_solution,
        verbose=False,
    )


class CVSolveRequest(BaseModel):
    iterations: int = Field(default=5, ge=1, le=50)


@router.post("/solve/cv")
def solve_cv(req: CVSolveRequest = CVSolveRequest()):
    try:
        print(f"Starting CV Solver with {req.iterations} iterations...")
        full_data = get_full_data()
        problem = Problem(full_data)
        solver = CustomSolver()
        solution = solver.solve(problem, iterations=req.iterations)

        if solution is None:
            raise ValueError(
                "Solver returned no solution (all iterations failed to improve)"
            )

        result = {
            "assignments": [
                {
                    "tripId": tid,
                    "busId": a.bus_id,
                    "idleTime": a.total_idle_time / max(1, len(a.assigned_trip_ids)),
                }
                for a in solution.assignments
                for tid in a.assigned_trip_ids
            ],
            "busStates": [
                {
                    "busId": a.bus_id,
                    "driverId": a.driver_id,
                    "homeStation": a.home_station,
                    "assignedTrips": a.assigned_trip_ids,
                    "totalIdleTime": a.total_idle_time,
                    "totalDrivingTime": a.total_driving_time,
                    "baseMismatch": a.base_mismatch,
                }
                for a in solution.assignments
                if a.is_used
            ],
            "unassignedTrips": solution.unassigned_trips,
            "metrics": {
                "totalTrips": solution.total_trips,
                "assigned": solution.num_assigned,
                "unassigned": solution.num_unassigned,
                "busesUsed": solution.buses_used,
                "totalIdleTime": solution.total_idle,
                "totalDrivingTime": solution.total_driving,
                "totalTransferTime": solution.total_transfer,
                "baseMismatchCount": solution.base_mismatch,
            },
            "solveTime": solution.solve_time,
            "solverName": solution.solver_name,
        }
        print("CV Solver finished, returning result")
        return result

    except Exception as e:
        err = traceback.format_exc()
        print(f"CV Solver error:\n{err}")
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__}: {str(e)}\n\n{err}"
        )
