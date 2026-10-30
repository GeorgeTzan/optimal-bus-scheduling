from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.domain.jobs.models import Job
from app.domain.jobs.repository import JobRepository
from app.domain.optimization.registry import ALLOWED_PRODUCTION_SOLVERS
from app.domain.verification.verifier import HardRuleVerifier


class OptimizationService:
    def __init__(self, db: Session):
        self.db = db
        self.job_repo = JobRepository(db)
        self.verifier = HardRuleVerifier()

    def enqueue_run(
        self,
        tenant_id: int,
        snapshot_id: str,
        solver_version: str = "cv-bounded-v1",
        config: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Job:
        if solver_version not in ALLOWED_PRODUCTION_SOLVERS:
            raise ValueError(
                f"Solver '{solver_version}' is not permitted for production optimization. "
                f"Allowed solvers: {sorted(list(ALLOWED_PRODUCTION_SOLVERS))}"
            )

        return self.job_repo.enqueue_job(
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            solver_version=solver_version,
            config=config or {},
            idempotency_key=idempotency_key,
        )

    def get_run(self, tenant_id: int, run_id: str) -> Optional[Job]:
        job = self.db.query(Job).filter(Job.job_id == run_id).first()
        if not job or job.tenant_id != tenant_id:
            return None
        return job

    def get_candidates(self, tenant_id: int, run_id: str) -> Optional[List[Dict[str, Any]]]:
        job = self.get_run(tenant_id, run_id)
        if not job:
            return None
        if not job.result_data or "candidates" not in job.result_data:
            return []
        return job.result_data["candidates"]
