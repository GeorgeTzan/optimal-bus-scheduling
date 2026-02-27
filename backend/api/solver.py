from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
import os

from dat_parser import parse_trips, parse_drivers, get_full_data
from services.solver import run_constructive_heuristic
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
