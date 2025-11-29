from fastapi import APIRouter
from dat_parser import parse_trips

router = APIRouter(tags=["Trips"])


@router.get("/trips")
def get_trips():
    trips = parse_trips()
    return {"trips": trips}
