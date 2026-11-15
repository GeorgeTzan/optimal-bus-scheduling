from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from db.database import get_db
from app.domain.identity.permissions import require_permission
from app.domain.workrules import loader, service
from app.domain.workrules.schemas import CompanyRulesUpdate, DriverBaselineUpdate, DriverProfileUpdate, VehicleRoutesUpdate

router = APIRouter(prefix='/api/v1/work-rules', tags=['Work rules'])


def committed(db, value):
    db.commit()
    return value


@router.get('')
def get_rules(user=Depends(require_permission('resources.read')), db: Session = Depends(get_db)):
    return service.company_view(db, user.ktel_id)


@router.get('/routes')
def get_routes(user=Depends(require_permission('resources.read')), db: Session = Depends(get_db)):
    return service.routes_view(db, user.ktel_id)


@router.put('')
def put_rules(request: CompanyRulesUpdate, user=Depends(require_permission('organization.manage')), db: Session = Depends(get_db)):
    return committed(db, service.save_company(db, user, request))


@router.get('/drivers/{driver_id}/profile')
def get_profile(driver_id: int, user=Depends(require_permission('resources.read')), db: Session = Depends(get_db)):
    service.driver(db, user.ktel_id, driver_id)
    return service.profile_view(db, user.ktel_id, driver_id)


@router.put('/drivers/{driver_id}/profile')
def put_profile(driver_id: int, request: DriverProfileUpdate, user=Depends(require_permission('drivers.write')), db: Session = Depends(get_db)):
    return committed(db, service.save_profile(db, user, driver_id, request))


@router.get('/drivers/{driver_id}/baseline')
def get_baseline(driver_id: int, user=Depends(require_permission('resources.read')), db: Session = Depends(get_db)):
    service.driver(db, user.ktel_id, driver_id)
    return service.baseline_view(db, user.ktel_id, driver_id)


@router.get('/drivers/{driver_id}/week')
def get_week(driver_id: int, day: date = Query(alias='date'), user=Depends(require_permission('resources.read')), db: Session = Depends(get_db)):
    return loader.driver_week(db, user.ktel_id, driver_id, day)


@router.put('/drivers/{driver_id}/baseline')
def put_baseline(driver_id: int, request: DriverBaselineUpdate, user=Depends(require_permission('drivers.write')), db: Session = Depends(get_db)):
    return committed(db, service.save_baseline(db, user, driver_id, request))


@router.get('/vehicles/{vehicle_id}/forbidden-routes')
def get_vehicle_routes(vehicle_id: int, user=Depends(require_permission('resources.read')), db: Session = Depends(get_db)):
    service.vehicle(db, user.ktel_id, vehicle_id)
    return service.vehicle_routes_view(db, user.ktel_id, vehicle_id)


@router.put('/vehicles/{vehicle_id}/forbidden-routes')
def put_vehicle_routes(vehicle_id: int, request: VehicleRoutesUpdate, user=Depends(require_permission('fleet.write')), db: Session = Depends(get_db)):
    return committed(db, service.save_vehicle_routes(db, user, vehicle_id, request))
