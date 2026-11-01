from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from db.database import get_db
from app.domain.identity.permissions import require_permission
from app.domain.scheduling.change_schemas import ChangePreview,ChangeCreate
from app.domain.scheduling.changes import ScheduleChanges
router=APIRouter(prefix='/api/v1/scheduling/changes',tags=['schedule changes'])

@router.post('/preview')
def preview(request:ChangePreview,user=Depends(require_permission('schedule.write')),db:Session=Depends(get_db)):
    return ScheduleChanges(db,user).preview(request)

@router.post('',status_code=201)
def create(request:ChangeCreate,user=Depends(require_permission('schedule.write')),db:Session=Depends(get_db)):
    response=ScheduleChanges(db,user).create(request);db.commit();return response
