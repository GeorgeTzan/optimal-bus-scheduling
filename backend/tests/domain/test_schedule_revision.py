from datetime import date, datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base
from db.models import KTEL
from app.domain.identity.tenant_session import tenant_transaction
from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot
from app.domain.scheduling.models import ScheduleRevision, RevisionAssignment, Publication, ApprovalRequest
from app.domain.scheduling.service import (
    SchedulingService,
    StaleVersionConflictError,
    ImmutableRevisionError,
    LockedAssignmentError,
    PublicationVerificationFailedError,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    ktel1 = KTEL(id=1, name="KTEL Achaias", region="Patras")
    ktel2 = KTEL(id=2, name="KTEL Korinthias", region="Korinthos")
    session.add_all([ktel1, ktel2])
    session.commit()

    yield session
    session.close()


def test_stale_version_is_409(db_session):
    """
    Optimistic concurrency control:
    If client sends expected_version=1 but revision is already at version=2,
    raise StaleVersionConflictError (which maps to HTTP 409 Conflict).
    """
    svc = SchedulingService(db_session, tenant_id=1)
    period = svc.create_period(name="June 2026", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    rev = svc.create_revision(period_id=period.id, author="dispatcher_1")
    assert rev.version == 1

    # First update succeeds, increments version to 2
    patch1 = [
        {
            "trip_id": "T1",
            "resource_id": "R1",
            "start_minutes": 100,
            "end_minutes": 200,
            "start_station": "Patras",
            "end_station": "Athens",
        }
    ]
    rev_updated = svc.apply_assignment_patch(rev.revision_id, patch=patch1, expected_version=1)
    assert rev_updated.version == 2

    # Concurrent user with stale expected_version=1 must be rejected
    patch2 = [
        {
            "trip_id": "T2",
            "resource_id": "R1",
            "start_minutes": 250,
            "end_minutes": 350,
            "start_station": "Athens",
            "end_station": "Patras",
        }
    ]
    with pytest.raises(StaleVersionConflictError):
        svc.apply_assignment_patch(rev.revision_id, patch=patch2, expected_version=1)


def test_published_revision_immutable(db_session):
    """
    Once a revision has status 'published', it cannot be modified by any patch.
    """
    svc = SchedulingService(db_session, tenant_id=1)
    period = svc.create_period(name="June 2026", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    rev = svc.create_revision(period_id=period.id, author="dispatcher_1")

    # Add a valid assignment
    svc.apply_assignment_patch(
        rev.revision_id,
        patch=[{
            "trip_id": "T1",
            "resource_id": "R1",
            "start_minutes": 100,
            "end_minutes": 200,
            "start_station": "Patras",
            "end_station": "Athens",
        }],
        expected_version=1,
    )

    # Approve and publish
    problem = SolverProblem(
        problem_id="P1",
        tenant_id="1",
        service_date=date(2026, 6, 1),
        trips=(
            TripSnapshot(id="T1", start_station="Patras", end_station="Athens", start_minutes=100, end_minutes=200, duration_minutes=100),
        ),
        resources=(
            ResourceSnapshot(resource_id="R1", driver_id="D1", bus_id="B1", home_station="Patras"),
        ),
        chains=(),
    )
    svc.request_publication(rev.revision_id, actor="dispatcher_1")
    svc.approve_publication(rev.revision_id, actor="manager_1")
    svc.publish_verified_revision(rev.revision_id, actor="dispatcher_1", problem=problem)

    # Attempt to modify published revision
    with pytest.raises(ImmutableRevisionError):
        svc.apply_assignment_patch(
            rev.revision_id,
            patch=[{
                "trip_id": "T1",
                "resource_id": "R2",
                "start_minutes": 100,
                "end_minutes": 200,
                "start_station": "Patras",
                "end_station": "Athens",
            }],
            expected_version=2,
        )


def test_failed_verification_blocks_publish(db_session):
    """
    Publishing a revision with conflicting/overlapping assignments fails the independent verifier
    and blocks publication with PublicationVerificationFailedError.
    """
    svc = SchedulingService(db_session, tenant_id=1)
    period = svc.create_period(name="June 2026", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    rev = svc.create_revision(period_id=period.id, author="dispatcher_1")

    # Add overlapping assignments on R1
    svc.apply_assignment_patch(
        rev.revision_id,
        patch=[
            {
                "trip_id": "T1",
                "resource_id": "R1",
                "start_minutes": 100,
                "end_minutes": 200,
                "start_station": "Patras",
                "end_station": "Athens",
            },
            {
                "trip_id": "T2",
                "resource_id": "R1",
                "start_minutes": 150,
                "end_minutes": 250,
                "start_station": "Athens",
                "end_station": "Patras",
            },
        ],
        expected_version=1,
    )

    problem = SolverProblem(
        problem_id="P1",
        tenant_id="1",
        service_date=date(2026, 6, 1),
        trips=(
            TripSnapshot(id="T1", start_station="Patras", end_station="Athens", start_minutes=100, end_minutes=200, duration_minutes=100),
            TripSnapshot(id="T2", start_station="Athens", end_station="Patras", start_minutes=150, end_minutes=250, duration_minutes=100),
        ),
        resources=(
            ResourceSnapshot(resource_id="R1", driver_id="D1", bus_id="B1", home_station="Patras"),
        ),
        chains=(),
    )

    svc.request_publication(rev.revision_id, actor="dispatcher_1")
    svc.approve_publication(rev.revision_id, actor="manager_1")

    with pytest.raises(PublicationVerificationFailedError):
        svc.publish_verified_revision(rev.revision_id, actor="dispatcher_1", problem=problem)


def test_locked_assignment_not_modified(db_session):
    """
    Assignments marked as locked (e.g. pinned by dispatcher) cannot be altered without an explicit unlock.
    """
    svc = SchedulingService(db_session, tenant_id=1)
    period = svc.create_period(name="June 2026", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    rev = svc.create_revision(period_id=period.id, author="dispatcher_1")

    # Add locked assignment
    svc.apply_assignment_patch(
        rev.revision_id,
        patch=[{
            "trip_id": "T-LOCKED",
            "resource_id": "R1",
            "start_minutes": 100,
            "end_minutes": 200,
            "start_station": "Patras",
            "end_station": "Athens",
            "is_locked": True,
        }],
        expected_version=1,
    )

    # Attempt to change resource for T-LOCKED without unlock flag
    with pytest.raises(LockedAssignmentError):
        svc.apply_assignment_patch(
            rev.revision_id,
            patch=[{
                "trip_id": "T-LOCKED",
                "resource_id": "R2",
                "start_minutes": 100,
                "end_minutes": 200,
                "start_station": "Patras",
                "end_station": "Athens",
            }],
            expected_version=2,
        )


def test_approval_audited(db_session):
    """
    Approval workflows create immutable audit trail records with actor, timestamp, and action.
    """
    svc = SchedulingService(db_session, tenant_id=1)
    period = svc.create_period(name="June 2026", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    rev = svc.create_revision(period_id=period.id, author="dispatcher_1")

    req = svc.request_publication(rev.revision_id, actor="dispatcher_1")
    assert req.status == "pending"

    appr = svc.approve_publication(rev.revision_id, actor="operations_chief", comment="Verified with depot")
    assert appr.status == "approved"

    audit_logs = svc.get_audit_trail(rev.revision_id)
    actions = [a.action for a in audit_logs]
    assert "create_revision" in actions
    assert "request_publication" in actions
    assert "approve_publication" in actions


def test_publish_without_problem_is_never_preverified(db_session):
    svc = SchedulingService(db_session, tenant_id=1)
    period = svc.create_period('Test', date(2026,10,30), date(2026,10,30))
    rev = svc.create_revision(period.id)
    svc.request_publication(rev.revision_id)
    svc.approve_publication(rev.revision_id)
    with pytest.raises(PublicationVerificationFailedError):
        svc.publish_verified_revision(rev.revision_id)


def test_published_revision_cannot_request_approval_again(db_session):
    svc = SchedulingService(db_session, tenant_id=1)
    period = svc.create_period('Test', date(2026,10,30), date(2026,10,30))
    rev = svc.create_revision(period.id)
    rev.status = 'published'
    db_session.commit()
    with pytest.raises(ImmutableRevisionError):
        svc.request_publication(rev.revision_id)


def test_legacy_revision_copy_preserves_cancellation_history(db_session):
    svc=SchedulingService(db_session,tenant_id=1)
    period=svc.create_period(name='day',start_date=date(2026,6,1),end_date=date(2026,6,1))
    original=svc.create_revision(period_id=period.id,author='dispatcher')
    db_session.add(RevisionAssignment(tenant_id=1,revision_id=original.revision_id,trip_id='T1',resource_id='UNASSIGNED',
        start_minutes=60,end_minutes=120,start_station='A',end_station='B',is_locked=False,is_cancelled=True,cancellation_reason='Cancelled service'))
    db_session.commit()
    successor=svc.create_revision(period_id=period.id,author='dispatcher',parent_revision_id=original.revision_id)
    row=db_session.query(RevisionAssignment).filter_by(revision_id=successor.revision_id,trip_id='T1').one()
    assert row.is_cancelled is True and row.cancellation_reason=='Cancelled service'


def test_legacy_patch_cannot_mutate_cancelled_trip(db_session):
    svc=SchedulingService(db_session,tenant_id=1)
    period=svc.create_period(name='day',start_date=date(2026,6,1),end_date=date(2026,6,1))
    rev=svc.create_revision(period_id=period.id,author='dispatcher')
    db_session.add(RevisionAssignment(tenant_id=1,revision_id=rev.revision_id,trip_id='T1',resource_id='UNASSIGNED',
        start_minutes=60,end_minutes=120,start_station='A',end_station='B',is_locked=False,is_cancelled=True,cancellation_reason='Cancelled service'))
    db_session.commit()
    with pytest.raises(ValueError,match='cancelled'):
        svc.apply_assignment_patch(rev.revision_id,[{'trip_id':'T1','start_minutes':90}],expected_version=rev.version)
