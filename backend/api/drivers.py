from fastapi import APIRouter, Depends
from dat_parser import parse_drivers
from api.deps import get_current_user
from db.models import User

router = APIRouter(tags=["Drivers"])


@router.get("/drivers")
def get_drivers(current_user: User = Depends(get_current_user)):
    drivers = parse_drivers()
    return {"drivers": drivers}
