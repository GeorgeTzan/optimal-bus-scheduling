"""Tenant-scoped recurring timetables, dated materialization and daily pairing API."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session
from db.database import get_db
from app.domain.identity.permissions import require_permission
from app.domain.timetables.models import ServiceTemplate,ServiceException,DailyPairing,StationTransfer
from app.domain.timetables.operations import OperationsService,materialize_service_date,trip_view,dated_trip_views
from app.domain.timetables.operational_schemas import (
    TimetableCreate,TimetablePatch,ExceptionCreate,ExceptionPatch,MaterializeRequest,
    PairingCreate,PairingPatch,PairingCopy,TransferCreate,TransferPatch,TransferBatch,
)
from app.domain.timetables.transfer_editor import TransferEditor,TransferEdits

router=APIRouter(prefix='/api/v1',tags=['Timetables and daily planning'])


def service(db,user):return OperationsService(db,user.ktel_id,user.id)


def committed(db,value):db.commit();return value


@router.get('/timetables')
def list_timetables(q:str=Query(default='',max_length=160),page:int=Query(default=1,ge=1),
    page_size:int=Query(default=25,ge=1,le=100),active_only:bool=False,
    user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    source=service(db,user);query=source.query(ServiceTemplate)
    if active_only:query=query.filter_by(is_active=True)
    if q:query=query.filter(ServiceTemplate.trip_code.icontains(q,autoescape=True))
    total=query.count()
    return {'items':[source.template_view(row) for row in query.order_by(ServiceTemplate.id).offset((page-1)*page_size).limit(page_size)],
            'total':total,'page':page,'page_size':page_size}


@router.post('/timetables',status_code=201)
def create_timetable(request:TimetableCreate,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).create_template(request))


@router.post('/timetables/materialize')
def materialize(request:MaterializeRequest,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    rows=materialize_service_date(db,user.ktel_id,request.service_date,request.template_versions)
    return committed(db,{'service_date':request.service_date,'trips':[trip_view(row) for row in rows]})


@router.get('/timetables/source-versions')
def source_versions(user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    rows=service(db,user).query(ServiceTemplate).filter_by(is_active=True).all()
    return {'template_versions':{str(row.id):row.version for row in rows}}


@router.get('/timetables/dated-trips')
def dated_trips(service_date:date,user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    from db.models import KTEL
    timezone=db.query(KTEL).filter_by(id=user.ktel_id).one().timezone
    rows=dated_trip_views(db,user.ktel_id,service_date)
    return {'items':rows,'service_date':service_date,'timezone':timezone}


@router.get('/timetables/{identifier}')
def get_timetable(identifier:int,user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    source=service(db,user);return source.template_view(source.get(ServiceTemplate,identifier))


@router.patch('/timetables/{identifier}')
def update_timetable(identifier:int,request:TimetablePatch,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).update_template(identifier,request))


@router.get('/timetables/{identifier}/exceptions')
def list_exceptions(identifier:int,user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    source=service(db,user);source.get(ServiceTemplate,identifier)
    return {'items':[source.exception_view(row) for row in source.query(ServiceException).filter_by(template_id=identifier).order_by(ServiceException.service_date).all()]}


@router.post('/timetables/{identifier}/exceptions',status_code=201)
def create_exception(identifier:int,request:ExceptionCreate,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).save_exception(identifier,request))


@router.patch('/timetables/{identifier}/exceptions/{exception_id}')
def update_exception(identifier:int,exception_id:int,request:ExceptionPatch,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).save_exception(identifier,request,exception_id))


@router.get('/pairings')
def list_pairings(service_date:date,user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    source=service(db,user)
    return {'items':[source.pairing_view(row) for row in source.query(DailyPairing).filter_by(service_date=service_date).order_by(DailyPairing.id).all()]}


@router.post('/pairings',status_code=201)
def create_pairing(request:PairingCreate,user=Depends(require_permission('schedule.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).save_pairing(request))


@router.post('/pairings/copy',status_code=201)
def copy_pairings(request:PairingCopy,user=Depends(require_permission('schedule.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).copy_pairings(request))


@router.patch('/pairings/{identifier}')
def update_pairing(identifier:int,request:PairingPatch,user=Depends(require_permission('schedule.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).save_pairing(request,identifier))


@router.get('/transfers')
def list_transfers(user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    source=service(db,user)
    return {'items':[source.transfer_view(row) for row in source.query(StationTransfer).order_by(StationTransfer.id).all()]}


@router.post('/transfers',status_code=201)
def create_transfer(request:TransferCreate,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).save_transfer(request))


@router.post('/transfers/batch',status_code=201)
def create_transfer_batch(request:TransferBatch,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    source=service(db,user)
    # The service flushes, while this route commits once for the entire review.
    return committed(db,{'items':[source.save_transfer(item) for item in request.items]})


@router.patch('/transfers/{identifier}')
def update_transfer(identifier:int,request:TransferPatch,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    return committed(db,service(db,user).save_transfer(request,identifier))


@router.get('/transfers/editor')
def transfer_editor(service_date:date,filter_kind:Literal['required','missing','all']=Query(default='required',alias='filter'),
    page:int=Query(default=1,ge=1,le=100000),page_size:int=Query(default=25,ge=1,le=50),
    user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    return TransferEditor(db,user.ktel_id,user.id).list(service_date,filter_kind,page,page_size)


@router.post('/transfers/editor')
def save_transfer_editor(request:TransferEdits,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    return committed(db,TransferEditor(db,user.ktel_id,user.id).save(request))


@router.get('/connections')
def list_connections(page:int=Query(default=1,ge=1),page_size:int=Query(default=25,ge=1,le=100),active_only:bool=False,
    user=Depends(require_permission('resources.read')),db:Session=Depends(get_db)):
    from app.domain.timetables.connections import ConnectionService
    return ConnectionService(db,user.ktel_id,user.id).list(page,page_size,active_only)


from app.domain.timetables.connections import ConnectionCreate,ConnectionPatch

@router.post('/connections',status_code=201)
def create_connection(request:ConnectionCreate,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    from app.domain.timetables.connections import ConnectionService
    return committed(db,ConnectionService(db,user.ktel_id,user.id).create(request))


@router.patch('/connections/{identifier}')
def update_connection(identifier:int,request:ConnectionPatch,user=Depends(require_permission('timetable.write')),db:Session=Depends(get_db)):
    from app.domain.timetables.connections import ConnectionService
    return committed(db,ConnectionService(db,user.ktel_id,user.id).update(identifier,request))
