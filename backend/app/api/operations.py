"""Authorized, CSRF-protected staff reports; immutable publication facts are read-only."""
from datetime import date
from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User
from app.domain.identity.permissions import require_permission
from app.domain.incidents.operations import Operations
from app.domain.incidents.operations_schemas import ReportRequest,ResolutionRequest
router=APIRouter(prefix='/api/v1/operations',tags=['daily operations'])

@router.get('/day')
def day(service_date:date|None=None,publication_id:str|None=Query(default=None,max_length=100),q:str=Query(default='',max_length=160),
        trip_id:str|None=Query(default=None,min_length=1,max_length=100),open_only:bool=False,page:int=Query(default=1,ge=1,le=100000),page_size:int=Query(default=25,ge=1,le=50),
        user:User=Depends(require_permission('schedule.read')),db:Session=Depends(get_db)):
    return Operations(db,user).day(service_date,publication_id,q,open_only,page,page_size,trip_id)

@router.post('/reports',status_code=201)
def report(req:ReportRequest,user:User=Depends(require_permission('incidents.manage')),db:Session=Depends(get_db)):
    response=Operations(db,user).record(req);db.commit();return response

@router.post('/reports/{identifier}/resolve',status_code=201)
def resolve(identifier:int,req:ResolutionRequest,user:User=Depends(require_permission('incidents.manage')),db:Session=Depends(get_db)):
    response=Operations(db,user).record(req,identifier);db.commit();return response
