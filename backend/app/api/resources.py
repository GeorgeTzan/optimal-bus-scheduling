"""Canonical operational registers, independent from legacy reference fixture routes."""
from datetime import date
from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session
from db.database import get_db
from app.domain.identity.permissions import require_permission
from app.domain.resources.service import ResourceService,readiness
from app.domain.resources.schemas import DriverCreate,DriverPatch,VehicleCreate,VehiclePatch,StationCreate,StationPatch

router=APIRouter(prefix='/api/v1',tags=['Operational resources'])

def register(kind,create_type,patch_type,permission):
    def listing(q:str=Query(default='',max_length=160),page:int=Query(default=1,ge=1),page_size:int=Query(default=25,ge=1,le=100),active_only:bool=False,
                user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
        return ResourceService(db,user.ktel_id,kind).list(q.strip(),page,page_size,active_only)
    def get_one(identifier:int,user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
        service=ResourceService(db,user.ktel_id,kind);return service.view(service.get(identifier))
    def create(request:create_type,user=Depends(require_permission(permission)),db:Session=Depends(get_db)):
        result=ResourceService(db,user.ktel_id,kind).create(request)
        db.commit()
        return result
    def update(identifier:int,request:patch_type,user=Depends(require_permission(permission)),db:Session=Depends(get_db)):
        result=ResourceService(db,user.ktel_id,kind).update(identifier,request)
        db.commit()
        return result
    router.add_api_route('/'+kind,listing,methods=['GET'],name='list_'+kind)
    router.add_api_route('/'+kind+'/{identifier}',get_one,methods=['GET'],name='get_'+kind)
    router.add_api_route('/'+kind,create,methods=['POST'],status_code=201,name='create_'+kind)
    router.add_api_route('/'+kind+'/{identifier}',update,methods=['PATCH'],name='update_'+kind)

register('drivers',DriverCreate,DriverPatch,'drivers.write')
register('vehicles',VehicleCreate,VehiclePatch,'fleet.write')
register('stations',StationCreate,StationPatch,'timetable.write')

@router.get('/setup/readiness')
def setup_readiness(service_date:date|None=None,user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    from app.domain.timetables.operations import operational_readiness
    return operational_readiness(db,user.ktel_id,service_date)
