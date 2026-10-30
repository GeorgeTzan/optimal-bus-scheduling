from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User
from api.auth import get_current_user
from app.domain.optimization.service import OptimizationService
from app.domain.scheduling.snapshots import RevisionSnapshot
from app.domain.identity.reference_tools import assert_snapshot_writable
from app.domain.identity.permissions import require_permission


router = APIRouter(prefix="/optimization", tags=["optimization"])


class RunConfig(BaseModel):
    seed: int = Field(default=42, ge=0, le=2147483647)
    iterations: int = Field(default=3, ge=1, le=10)
    time_limit_seconds: int = Field(default=60, ge=1, le=300)
    cp_sat_workers: int = Field(default=1, ge=1, le=4)


class RunCreateRequest(BaseModel):
    snapshot_id: str
    solver_version: str = "cv-bounded-v1"
    config: RunConfig = Field(default_factory=RunConfig)
    idempotency_key: Optional[str] = None


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
def create_run(
    req: RunCreateRequest,
    current_user: User = Depends(require_permission('optimization.run')),
    db: Session = Depends(get_db),
):
    if req.solver_version != 'cv-bounded-v1':
        raise HTTPException(400, f"Solver '{req.solver_version}' is not permitted by the bounded queue worker")
    snapshot = db.query(RevisionSnapshot).filter_by(tenant_id=current_user.ktel_id, revision_id=req.snapshot_id).first()
    if not snapshot:
        raise HTTPException(404, 'Problem snapshot not found')
    assert_snapshot_writable(snapshot.source_data, current_user)
    from app.domain.scheduling.availability_review import availability_review_required
    from app.domain.scheduling.models import ScheduleRevision
    revision = db.query(ScheduleRevision).filter_by(tenant_id=current_user.ktel_id, revision_id=req.snapshot_id).first()
    if revision is not None and availability_review_required(db, revision, snapshot):
        raise HTTPException(409, {'code': 'availability_changed', 'message': 'Driver or vehicle availability changed. Open an updated draft before searching.'})
    service = OptimizationService(db)
    try:
        job = service.enqueue_run(
            tenant_id=current_user.ktel_id,
            snapshot_id=req.snapshot_id,
            solver_version=req.solver_version,
            config=req.config.model_dump(),
            idempotency_key=req.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {
        "run_id": job.job_id,
        "snapshot_id": job.snapshot_id,
        "status": job.status,
        "solver_version": job.solver_version,
        "created_at": job.created_at.isoformat(),
    }


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    current_user: User = Depends(require_permission('optimization.read')),
    db: Session = Depends(get_db),
):
    service = OptimizationService(db)
    job = service.get_run(tenant_id=current_user.ktel_id, run_id=run_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return {
        "run_id": job.job_id,
        "snapshot_id": job.snapshot_id,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "solver_version": job.solver_version,
        "created_at": job.created_at.isoformat(),
        "error_message": job.error_message,
    }


@router.get("/runs/{run_id}/candidates")
def get_run_candidates(
    run_id: str,
    current_user: User = Depends(require_permission('optimization.read')),
    db: Session = Depends(get_db),
):
    service = OptimizationService(db)
    candidates = service.get_candidates(tenant_id=current_user.ktel_id, run_id=run_id)
    if candidates is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return {
        "run_id": run_id,
        "candidates": candidates,
    }
