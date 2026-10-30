"""Authoritative tenant-scoped revision API. Never trust caller timing or tenant IDs."""
from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Optional, Literal
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import or_
from api.deps import get_current_user
from app.domain.identity.permissions import require_permission
from app.domain.identity.reference_tools import require_reference_tools, assert_snapshot_writable
from app.domain.scheduling.availability_review import availability_review_required
from app.domain.scheduling.source_review import source_review_required
from db.database import get_db
from db.models import User
from app.domain.scheduling.models import (
    ScheduleRevision, RevisionAssignment, SchedulingPeriod, SchedulingAuditLog, ApprovalRequest, Publication,
)
from app.domain.scheduling.snapshots import RevisionSnapshot, encode_problem, decode_problem, import_reference_problem, display_metadata
from app.domain.optimization.contracts import Assignment
from app.domain.verification.verifier import HardRuleVerifier

router = APIRouter(prefix='/api/v1/scheduling', tags=['scheduling'])


writer = require_permission('schedule.write')


class VersionRequest(BaseModel):
    version: int = Field(ge=1)


class AssignmentPatch(BaseModel):
    trip_id: str
    new_resource_id: str
    is_locked: Optional[bool] = None


class PatchesRequest(VersionRequest):
    patches: list[AssignmentPatch] = Field(min_length=1, max_length=2500)


class ImportRequest(BaseModel):
    service_date: date


class CreateRevisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    service_date: date


def find_revision(db, tenant_id, rid, version=None):
    query = db.query(ScheduleRevision).filter_by(tenant_id=tenant_id, revision_id=rid)
    rev = query.populate_existing().with_for_update().first()
    if not rev:
        raise HTTPException(404, 'Revision not found')
    if version is not None:
        if rev.version != version:
            raise HTTPException(409, 'Stale revision version; reload before editing')
        if rev.status == 'published':
            raise HTTPException(409, 'Published revisions are immutable')
    return rev


def snapshot_for(db, rev):
    snapshot = db.query(RevisionSnapshot).filter_by(tenant_id=rev.tenant_id, revision_id=rev.revision_id).first()
    if snapshot is None:
        raise HTTPException(409, 'Revision has no immutable problem snapshot')
    return snapshot


def rows_for(db, rev):
    return db.query(RevisionAssignment).filter_by(tenant_id=rev.tenant_id, revision_id=rev.revision_id).order_by(RevisionAssignment.trip_id).all()


def verify(db, rev):
    problem = decode_problem(snapshot_for(db, rev).problem_data)
    assignments = [Assignment(a.resource_id, a.trip_id, a.start_minutes, a.end_minutes, a.start_station, a.end_station)
                   for a in rows_for(db, rev) if a.resource_id != 'UNASSIGNED' and not a.is_cancelled]
    return HardRuleVerifier().verify(problem, assignments)


def serialize(db, rev):
    snapshot = snapshot_for(db, rev)
    return dict(**display_metadata(snapshot), revision_id=rev.revision_id, version=rev.version, status=rev.status, author=rev.author,
                updated_at=rev.updated_at.replace(tzinfo=timezone.utc).isoformat(), problem=snapshot.problem_data,
                source_trips=snapshot.source_data['trips'], source_resources=snapshot.source_data['resources'],
                source_kind='operational' if snapshot.source_data.get('source') == 'operational' else 'reference_archive',
                source_stations=snapshot.source_data.get('stations', []), source_hash=snapshot.source_data.get('source_hash'),
                source_review_required=source_review_required(db, rev, snapshot) or availability_review_required(db, rev, snapshot),
                assignments=[dict(trip_id=a.trip_id, resource_id=a.resource_id, is_locked=a.is_locked, is_cancelled=a.is_cancelled, cancellation_reason=a.cancellation_reason) for a in rows_for(db, rev)],
                verification=asdict(verify(db, rev)))


def audit(db, rev, user, action):
    db.add(SchedulingAuditLog(tenant_id=rev.tenant_id, revision_id=rev.revision_id, actor=str(user.id),
                             action=action, details={'version': rev.version}))


@router.get('/revisions/active')
def active(service_date: date | None = None, source_kind: Literal['operational', 'reference_archive'] = 'operational',
           user: User = Depends(require_permission('schedule.read')), db: Session = Depends(get_db)):
    query = db.query(ScheduleRevision).join(RevisionSnapshot, RevisionSnapshot.revision_id == ScheduleRevision.revision_id).filter(
        ScheduleRevision.tenant_id == user.ktel_id, RevisionSnapshot.tenant_id == user.ktel_id)
    kind = RevisionSnapshot.source_data['source'].as_string()
    query = query.filter(kind == 'operational') if source_kind == 'operational' else query.filter(or_(kind.is_(None), kind != 'operational'))
    if service_date is not None:
        query = query.join(SchedulingPeriod, SchedulingPeriod.id == ScheduleRevision.period_id).filter(
            SchedulingPeriod.tenant_id == user.ktel_id, SchedulingPeriod.start_date <= service_date, SchedulingPeriod.end_date >= service_date)
    rev = query.order_by(ScheduleRevision.created_at.desc(), ScheduleRevision.id.desc()).first()
    if not rev:
        raise HTTPException(404, 'No saved schedule for this selection. Prepare your service day to create a draft.')
    return serialize(db, rev)


@router.post('/revisions', status_code=201)
def create_operational(req: CreateRevisionRequest, user: User = Depends(writer), db: Session = Depends(get_db)):
    from app.domain.scheduling.canonical import create_operational_revision
    revision, created = create_operational_revision(db, user.ktel_id, user.id, req.service_date)
    if created: audit(db, revision, user, 'create_operational_draft')
    db.flush()
    response = serialize(db, revision)
    db.commit()
    return response


@router.get('/revisions/{rid}')
def detail(rid: str, user: User = Depends(require_permission('schedule.read')), db: Session = Depends(get_db)):
    revision = db.query(ScheduleRevision).filter_by(tenant_id=user.ktel_id, revision_id=rid).first()
    if revision is None: raise HTTPException(404, 'Schedule not found in your workspace.')
    return serialize(db, revision)


@router.post('/revisions/import-reference', status_code=201)
def import_reference(req: ImportRequest, user: User = Depends(require_reference_tools), db: Session = Depends(get_db)):
    # Serialize imports per tenant, including the first import.
    from db.models import KTEL
    db.query(KTEL).filter_by(id=user.ktel_id).with_for_update().first()
    existing = db.query(ScheduleRevision).join(RevisionSnapshot, RevisionSnapshot.revision_id == ScheduleRevision.revision_id).filter(
        ScheduleRevision.tenant_id == user.ktel_id).first()
    if existing:
        raise HTTPException(409, 'A reference revision already exists; reload the active revision')
    rid = str(uuid.uuid4())
    problem, source, assignments = import_reference_problem(user.ktel_id, req.service_date, rid)
    period = SchedulingPeriod(tenant_id=user.ktel_id, name='Imported reference service day',
                              start_date=req.service_date, end_date=req.service_date)
    db.add(period)
    db.flush()
    rev = ScheduleRevision(revision_id=rid, tenant_id=user.ktel_id, period_id=period.id,
                           version=1, status='draft', author=str(user.id))
    db.add(rev)
    db.flush()
    db.add(RevisionSnapshot(revision_id=rid, tenant_id=user.ktel_id, problem_data=encode_problem(problem), source_data=source))
    assignment_map = {a['tripId']: a['busId'] for a in assignments}
    for t in problem.trips:
        db.add(RevisionAssignment(tenant_id=user.ktel_id, revision_id=rid, trip_id=t.id,
            resource_id=assignment_map.get(t.id, 'UNASSIGNED'), start_minutes=t.start_minutes,
            end_minutes=t.end_minutes, start_station=t.start_station, end_station=t.end_station, is_locked=False))
    audit(db, rev, user, 'import_reference')
    db.flush()
    response = serialize(db, rev)
    db.commit()
    return response


def prepare_patch(db, user, rid, req, *, lock_sources=False):
    rev = find_revision(db, user.ktel_id, rid, req.version)
    from app.domain.scheduling.change_models import ScheduleChange
    if db.query(ScheduleChange).filter_by(tenant_id=user.ktel_id,successor_revision_id=rid).first():
        raise HTTPException(409, {'code':'reviewed_change_required','message':'Create another reviewed change rather than editing this successor directly.'})
    if lock_sources:
        from db.models import KTEL
        db.query(KTEL).filter_by(id=user.ktel_id).with_for_update().one()
    snapshot=snapshot_for(db, rev)
    assert_snapshot_writable(snapshot.source_data, user)
    if source_review_required(db,rev,snapshot):
        raise HTTPException(409, {'code':'source_changed','message':'Operational inputs changed. Review Service day and open an updated draft.'})
    if availability_review_required(db,rev,snapshot):
        raise HTTPException(409, {'code':'availability_changed','message':'Driver or vehicle availability changed. Review the affected trips and open an updated draft.'})
    problem=decode_problem(snapshot.problem_data)
    resources={r.resource_id for r in problem.resources}|{'UNASSIGNED'}
    assignments={a.trip_id:a for a in rows_for(db,rev)}
    seen=set()
    for item in req.patches:
        if item.trip_id not in assignments or item.new_resource_id not in resources or item.trip_id in seen:
            raise HTTPException(422,'Unknown or duplicate trip/resource')
        seen.add(item.trip_id);row=assignments[item.trip_id]
        if row.is_cancelled:raise HTTPException(409,'Cancelled trips cannot be reassigned.')
        if row.is_locked and row.resource_id!=item.new_resource_id:
            raise HTTPException(409,'Unlock assignment in a separate edit before reassigning')
    return rev,problem,assignments


@router.post('/revisions/{rid}/patches/preview')
def preview_patch(rid:str,req:PatchesRequest,user:User=Depends(writer),db:Session=Depends(get_db)):
    rev,problem,assignments=prepare_patch(db,user,rid,req)
    proposed={item.trip_id:item.new_resource_id for item in req.patches}
    facts=[Assignment(proposed.get(row.trip_id,row.resource_id),row.trip_id,row.start_minutes,row.end_minutes,row.start_station,row.end_station)
           for row in assignments.values() if not row.is_cancelled and proposed.get(row.trip_id,row.resource_id)!='UNASSIGNED']
    report=HardRuleVerifier().verify(problem,facts)
    return {'revision_id':rev.revision_id,'version':rev.version,'verification':asdict(report),
        'changes':[{'trip_id':item.trip_id,'original_resource_id':assignments[item.trip_id].resource_id,
            'new_resource_id':item.new_resource_id,'start_minutes':assignments[item.trip_id].start_minutes,
            'end_minutes':assignments[item.trip_id].end_minutes} for item in req.patches]}


@router.post('/revisions/{rid}/patches')
def patch(rid: str, req: PatchesRequest, user: User = Depends(writer), db: Session = Depends(get_db)):
    rev,problem,assignments=prepare_patch(db,user,rid,req,lock_sources=True)
    for item in req.patches:
        row = assignments[item.trip_id]
        row.resource_id = item.new_resource_id
        if item.is_locked is not None:
            row.is_locked = item.is_locked
    rev.version += 1
    rev.status = 'draft'
    rev.updated_at = datetime.now(timezone.utc)
    for approval in db.query(ApprovalRequest).filter_by(tenant_id=user.ktel_id, revision_id=rid).filter(
            ApprovalRequest.status.in_(['pending', 'approved'])):
        approval.status = 'rejected'
    audit(db, rev, user, 'patch_assignments')
    db.flush()
    response = serialize(db, rev)
    db.commit()
    return response


@router.post('/revisions/{rid}/{action}')
def transition(rid: str, action: str, req: VersionRequest, user: User = Depends(writer), db: Session = Depends(get_db)):
    if action not in ('request-approval', 'approve', 'publish'):
        raise HTTPException(404, 'Unknown revision action')
    needed = 'schedule.approve' if action == 'approve' else 'schedule.publish' if action == 'publish' else 'schedule.write'
    if needed not in user.permissions:
        raise HTTPException(403, 'Your organization role does not allow this action')
    rev = find_revision(db, user.ktel_id, rid, req.version)
    assert_snapshot_writable(snapshot_for(db, rev).source_data, user)
    from db.models import KTEL
    db.query(KTEL).filter_by(id=user.ktel_id).with_for_update().one()
    # A draft based on a publication must still be safe against current
    # publication, source versions and reported operated work at every step.
    from app.domain.scheduling.change_models import ScheduleChange
    change=db.query(ScheduleChange).filter_by(tenant_id=user.ktel_id,successor_revision_id=rid).first()
    if change:
        from app.domain.scheduling.change_schemas import ChangePreview
        from app.domain.scheduling.changes import ScheduleChanges
        base=db.query(ScheduleRevision).filter_by(tenant_id=user.ktel_id,revision_id=change.base_revision_id).first()
        if base is None:raise HTTPException(409, 'The original published schedule is unavailable.')
        request=ChangePreview(publication_id=change.publication_id,version=base.version,reason=change.reason,
            reviewed_not_started=[item['trip_id'] for item in change.changes],
            patches=[({'trip_id':item['trip_id'],'operation':'cancel','reason':item['reason']} if item.get('operation')=='cancel' else {'trip_id':item['trip_id'],'operation':'replace_driver','replacement_resource_id':item['replacement_resource_id'],'driver_version':item['driver_version'],'vehicle_version':item['vehicle_version'],'confirm_replacement':True} if item.get('operation')=='replace_driver' else {'trip_id':item['trip_id'],'new_resource_id':item['new_resource_id']}) for item in change.changes])
        for patch,item in zip(request.patches,change.changes):patch.unlock=bool(item.get('unlocked'))
        service=ScheduleChanges(db,user)
        publication,base,snapshot=service.base(request)
        service.validate(request,publication,base,snapshot)
    if source_review_required(db, rev, snapshot_for(db, rev)):
        raise HTTPException(409, {'code':'source_changed','message':'Operational inputs changed. Review Service day and open an updated draft.'})
    if availability_review_required(db, rev, snapshot_for(db, rev)):
        raise HTTPException(409, {'code':'availability_changed','message':'Driver or vehicle availability changed. Review the affected trips and open an updated draft.'})
    report = verify(db, rev)
    if not report.valid:
        raise HTTPException(422, detail={'message': 'Independent verification failed', 'verification': asdict(report)})
    if action == 'request-approval':
        if rev.status != 'draft':
            raise HTTPException(409, 'Only drafts can request approval')
        db.add(ApprovalRequest(request_id=str(uuid.uuid4()), tenant_id=user.ktel_id, revision_id=rid,
                               requested_by=str(user.id), status='pending'))
        rev.status = 'approval_requested'
    elif action == 'approve':
        if rev.status != 'approval_requested':
            raise HTTPException(409, 'Request approval first')
        approval = db.query(ApprovalRequest).filter_by(tenant_id=user.ktel_id, revision_id=rid, status='pending').first()
        if not approval:
            raise HTTPException(409, 'Missing approval request')
        approval.status, approval.reviewer, approval.reviewed_at = 'approved', str(user.id), datetime.now(timezone.utc)
        rev.status = 'approved'
    else:
        approval = db.query(ApprovalRequest).filter_by(tenant_id=user.ktel_id, revision_id=rid, status='approved').first()
        if rev.status != 'approved' or not approval:
            raise HTTPException(409, 'Approved revision required')
        db.add(Publication(publication_id=str(uuid.uuid4()), tenant_id=user.ktel_id, revision_id=rid,
                           published_by=str(user.id), verification_report=asdict(report)))
        rev.status = 'published'
    rev.version += 1
    rev.updated_at = datetime.now(timezone.utc)
    audit(db, rev, user, action)
    db.flush()
    response = serialize(db, rev)
    db.commit()
    return response
