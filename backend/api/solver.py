from fastapi import APIRouter
from pydantic import BaseModel, Field

from dat_parser import parse_trips, parse_drivers, get_full_data
from services.solver import run_constructive_heuristic
from services.simulated_annealing import (
    optimize_with_simulated_annealing,
    SAConfig,
    SAWeights,
)
from services.legality_checker import SolverParameters, ConstraintsData

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
        duty_balance=req.w_fairness,
        overtime_over_8h=req.w_over8h,
        idle_time=req.w_idle,
        unused_bus=req.w_unused,
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
