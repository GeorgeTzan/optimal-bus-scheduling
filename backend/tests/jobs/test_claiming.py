import time
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import KTEL
from app.domain.identity.tenant_session import tenant_transaction
from app.domain.jobs.models import Job
from app.domain.jobs.repository import JobRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    ktel1 = KTEL(id=1, name="KTEL Achaias", region="Patras")
    ktel2 = KTEL(id=2, name="KTEL Korinthias", region="Korinthos")
    session.add_all([ktel1, ktel2])
    session.commit()

    yield session
    session.close()


def test_duplicate_key_one_job(db_session):
    """
    Enqueueing with the same idempotency key returns the existing job and creates only one record.
    """
    repo = JobRepository(db_session)
    job1 = repo.enqueue_job(
        tenant_id=1,
        snapshot_id="SNAP-001",
        solver_version="cv-bounded-v1",
        config={"seed": 42},
        idempotency_key="request-abc-123",
    )
    job2 = repo.enqueue_job(
        tenant_id=1,
        snapshot_id="SNAP-001",
        solver_version="cv-bounded-v1",
        config={"seed": 42},
        idempotency_key="request-abc-123",
    )

    assert job1.id == job2.id
    total_jobs = db_session.query(Job).filter(Job.tenant_id == 1).count()
    assert total_jobs == 1


def test_concurrent_claim_once(db_session):
    """
    When multiple workers claim, the job is claimed only once by one worker.
    """
    repo = JobRepository(db_session)
    job = repo.enqueue_job(
        tenant_id=1,
        snapshot_id="SNAP-002",
        solver_version="cv-bounded-v1",
        config={},
    )

    claimed1 = repo.claim_next_job(worker_id="worker-A")
    assert claimed1 is not None
    assert claimed1.id == job.id
    assert claimed1.claimed_by == "worker-A"
    assert claimed1.status == "claimed"
    assert claimed1.attempt_token == 1

    # Worker B tries to claim
    claimed2 = repo.claim_next_job(worker_id="worker-B")
    assert claimed2 is None


def test_crash_recovers_lease(db_session):
    """
    If worker A crashes and lease expires, worker B can recover and claim the job.
    Monotonic attempt_token increments to 2, fencing out stale worker A.
    """
    repo = JobRepository(db_session)
    job = repo.enqueue_job(
        tenant_id=1,
        snapshot_id="SNAP-003",
        solver_version="cv-bounded-v1",
        config={},
    )

    # Worker A claims with 1 second lease
    claimed_a = repo.claim_next_job(worker_id="worker-A", lease_duration_seconds=1)
    assert claimed_a is not None
    assert claimed_a.attempt_token == 1

    # Expire the lease manually in DB
    claimed_a.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.commit()

    # Worker B claims the abandoned job
    claimed_b = repo.claim_next_job(worker_id="worker-B", lease_duration_seconds=60)
    assert claimed_b is not None
    assert claimed_b.id == job.id
    assert claimed_b.claimed_by == "worker-B"
    assert claimed_b.attempt_token == 2  # Incremented fencing token

    # Worker A attempts a stale heartbeat with old token 1 - must be rejected
    heartbeat_ok = repo.heartbeat(job_id=job.job_id, worker_id="worker-A", attempt_token=1)
    assert heartbeat_ok is False


def test_tenant_scoped_worker_claim(db_session):
    """
    Worker configured for a specific tenant cannot claim jobs of another tenant.
    """
    repo = JobRepository(db_session)
    repo.enqueue_job(
        tenant_id=2,
        snapshot_id="SNAP-T2",
        solver_version="cv-bounded-v1",
        config={},
    )

    # Worker restricted to tenant 1
    claimed = repo.claim_next_job(worker_id="worker-T1-only", allowed_tenant_id=1)
    assert claimed is None

    # Worker for tenant 2 claims successfully
    claimed_t2 = repo.claim_next_job(worker_id="worker-T2", allowed_tenant_id=2)
    assert claimed_t2 is not None
    assert claimed_t2.tenant_id == 2
