from fastapi import APIRouter
from dat_parser import parse_trips, parse_drivers, get_full_data
from services.solver import run_constructive_heuristic

router = APIRouter(tags=["Solver"])


@router.post("/solve")
def solve():
    trips = parse_trips()
    drivers = parse_drivers()
    full_data = get_full_data()
    solution = run_constructive_heuristic(trips, drivers, full_data)
    return solution
