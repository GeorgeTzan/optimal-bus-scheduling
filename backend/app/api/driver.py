"""Driver self-service. The driver comes from the session only; no route accepts a driver id."""
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from db.database import get_db
from app.domain.identity.current_driver import DriverContext, require_driver_permission
from datetime import date
from fastapi import HTTPException, Query
from app.api.identity import once
from app.domain.office.leave import cancel_own_pending_leave, leave_view, list_leave, request_own_leave
from app.domain.office.schemas import DriverLeaveCancel, DriverLeaveCreate
from app.domain.scheduling import driver_duties as duties_module
from app.domain.scheduling.driver_acks import acknowledge
from app.domain.workforce.models import WorkforceDriver
from db.models import KTEL

router = APIRouter(prefix='/api/v1/driver', tags=['Driver'])
read = require_driver_permission('driver.self.read')


@router.get('/me')
def me(ctx: DriverContext = Depends(read), db: Session = Depends(get_db)):
    driver = db.query(WorkforceDriver).filter_by(tenant_id=ctx.user.ktel_id, id=ctx.driver_id).one()
    return {'driver_name': f'{driver.first_name} {driver.last_name}'.strip(), 'driver_code': driver.code, 'timezone': db.query(KTEL.timezone).filter_by(id=ctx.user.ktel_id).scalar()}


@router.get('/duties')
def duties(ctx: DriverContext = Depends(read), db: Session = Depends(get_db)):
    return duties_module.driver_duties(db, ctx.user.ktel_id, ctx.driver_id)


class AckRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    publication_id: str = Field(min_length=1, max_length=64)
    trip_ids: list[str] = Field(min_length=1, max_length=200)


@router.post('/acknowledgments')
def acknowledgments(req: AckRequest, ctx: DriverContext = Depends(require_driver_permission('driver.self.acknowledge')), db: Session = Depends(get_db)):
    if len(set(req.trip_ids)) != len(req.trip_ids):
        raise HTTPException(422, 'List each trip once.')
    return once(db, ctx.user, req.request_id, 'driver_ack', 'acknowledge', {**req.model_dump(mode='json'), 'driver_id': ctx.driver_id},
                lambda: acknowledge(db, ctx.user, ctx.driver_id, req.publication_id, req.trip_ids, str(req.request_id)))


leave_permission = require_driver_permission('driver.self.leave')


@router.get('/leave-requests')
def my_leave(date_from: date, date_to: date = Query(), ctx: DriverContext = Depends(leave_permission), db: Session = Depends(get_db)):
    if not 0 <= (date_to - date_from).days <= 62:
        raise HTTPException(422, 'Choose a date range of at most 62 days.')
    return {'items': [leave_view(row, True) for row in list_leave(db, ctx.user.ktel_id, date_from, date_to, ctx.driver_id)]}


@router.post('/leave-requests', status_code=201)
def create_my_leave(req: DriverLeaveCreate, ctx: DriverContext = Depends(leave_permission), db: Session = Depends(get_db)):
    return once(db, ctx.user, req.request_id, 'driver_leave', 'create', {**req.model_dump(mode='json'), 'driver_id': ctx.driver_id},
                lambda: leave_view(request_own_leave(db, ctx.user, ctx.driver_id, req), True))


@router.post('/leave-requests/{leave_id}/cancel')
def cancel_my_leave(leave_id: int, req: DriverLeaveCancel, ctx: DriverContext = Depends(leave_permission), db: Session = Depends(get_db)):
    return once(db, ctx.user, req.request_id, 'driver_leave', 'cancel', {**req.model_dump(mode='json'), 'leave_id': leave_id, 'driver_id': ctx.driver_id},
                lambda: leave_view(cancel_own_pending_leave(db, ctx.user, ctx.driver_id, leave_id, req), True))
