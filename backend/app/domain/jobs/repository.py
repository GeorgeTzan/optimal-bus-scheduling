import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from sqlalchemy.exc import OperationalError

from app.domain.jobs.models import Job


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def enqueue_job(
        self,
        tenant_id: int,
        snapshot_id: str,
        solver_version: str = "cv-bounded-v1",
        config: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Job:
        if idempotency_key:
            existing = self.db.query(Job).filter(
                Job.tenant_id == tenant_id,
                Job.idempotency_key == idempotency_key,
            ).first()
            if existing:
                return existing

        job_uuid = str(uuid.uuid4())
        job = Job(
            job_id=job_uuid,
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            solver_version=solver_version,
            config=config or {},
            idempotency_key=idempotency_key,
            status="queued",
            attempt_token=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(job)
        self.db.flush()  # Persist parent before the transactional outbox FK is checked.
        from app.domain.events.outbox import OutboxEvent
        self.db.add(OutboxEvent(tenant_id=tenant_id, job_id=job_uuid, event_type='job.queued',
                               payload={'job_id': job_uuid, 'status': 'queued', 'progress_pct': 0}))
        self.db.commit()
        return job

    def claim_next_job(
        self,
        worker_id: str,
        lease_duration_seconds: int = 60,
        allowed_tenant_id: Optional[int] = None,
    ) -> Optional[Job]:
        now = datetime.now(timezone.utc)

        query = self.db.query(Job).filter(
            Job.status.in_(["queued", "claimed", "running"]),
            or_(
                Job.lease_expires_at == None,
                Job.lease_expires_at < now,
            )
        )

        if allowed_tenant_id is not None:
            query = query.filter(Job.tenant_id == allowed_tenant_id)

        query = query.order_by(Job.created_at.asc())

        # Fail closed on database errors: a failed locking query must never become an unlocked claim.
        job = query.with_for_update(skip_locked=True).first()

        if not job:
            return None

        job.status = "claimed"
        job.claimed_by = worker_id
        job.claimed_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
        job.heartbeat_at = now
        job.attempt_token += 1
        job.updated_at = now

        self.db.commit()
        return job

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        attempt_token: int,
        extend_seconds: int = 60,
    ) -> bool:
        now = datetime.now(timezone.utc)
        job = self.db.query(Job).filter(
            Job.job_id == job_id,
            Job.claimed_by == worker_id,
            Job.attempt_token == attempt_token,
            Job.status.in_(["claimed", "running"]),
        ).first()

        if not job:
            return False

        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=extend_seconds)
        job.updated_at = now
        self.db.commit()
        return True

    def record_progress(
        self,
        job_id: str,
        worker_id: str,
        attempt_token: int,
        progress_pct: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        job = self.db.query(Job).filter(
            Job.job_id == job_id,
            Job.claimed_by == worker_id,
            Job.attempt_token == attempt_token,
            Job.status.in_(["claimed", "running"]),
        ).first()

        if not job:
            return False

        job.status = "running"
        job.progress_pct = max(0, min(100, progress_pct))
        job.heartbeat_at = now
        job.updated_at = now
        self.db.commit()
        return True

    def complete_job(
        self,
        job_id: str,
        worker_id: str,
        attempt_token: int,
        result_data: Dict[str, Any],
    ) -> bool:
        now = datetime.now(timezone.utc)
        job = self.db.query(Job).filter(
            Job.job_id == job_id,
            Job.claimed_by == worker_id,
            Job.attempt_token == attempt_token,
            Job.status.in_(["claimed", "running"]),
        ).first()

        if not job:
            return False

        job.status = "completed"
        job.progress_pct = 100
        job.result_data = result_data
        job.lease_expires_at = None
        job.updated_at = now
        self.db.commit()
        return True

    def fail_job(self, job_id: str, error_message: str) -> bool:
        now = datetime.now(timezone.utc)
        job = self.db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return False

        job.status = "failed"
        job.error_message = error_message
        job.lease_expires_at = None
        job.updated_at = now
        self.db.commit()
        return True

    def cancel_job(self, job_id: str, actor: str) -> Optional[Job]:
        now = datetime.now(timezone.utc)
        job = self.db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return None

        job.status = "cancelled"
        job.lease_expires_at = None
        job.updated_at = now
        self.db.commit()
        return job
