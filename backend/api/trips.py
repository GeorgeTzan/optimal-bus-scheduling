from fastapi import APIRouter, Depends
from dat_parser import parse_trips
from api.deps import get_current_user
from db.models import User

router = APIRouter(tags=["Trips"])


@router.get("/trips")
def get_trips(current_user: User = Depends(get_current_user)):
    trips = parse_trips()
    return {"trips": trips}
