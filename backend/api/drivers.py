from fastapi import APIRouter
from dat_parser import parse_drivers

router = APIRouter(tags=["Drivers"])


@router.get("/drivers")
def get_drivers():
    drivers = parse_drivers()
    return {"drivers": drivers}
