from datetime import date, datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base
from db.models import KTEL, User
from app.domain.incidents.models import Incident, RecoveryProposal
from app.domain.incidents.service import IncidentService
from app.domain.scheduling.service import SchedulingService


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
    user_disp = User(id=1, email="dispatcher@ktel.gr", hashed_password="pw", full_name="Chief Dispatcher", is_active=True, ktel_id=1)
    user_driver = User(id=2, email="driver_nikos@ktel.gr", hashed_password="pw", full_name="Nikos Driver", is_active=True, ktel_id=1)
    session.add_all([ktel1, ktel2, user_disp, user_driver])
    session.commit()

    yield session
    session.close()


def test_incident_reporting_and_audit(db_session):
    """
    Reporting an operational breakdown logs an incident with timestamp, reporter, and details.
    """
    svc = IncidentService(db_session, tenant_id=1)
    incident = svc.report_incident(
        incident_type="VEHICLE_BREAKDOWN",
        resource_id="PAIR_DRV1_BUS10",
        trip_id="TRIP-401",
        description="Coolant leak at Patras depot",
        reported_by="driver_nikos@ktel.gr",
    )

    assert incident.id is not None
    assert incident.incident_type == "VEHICLE_BREAKDOWN"
    assert incident.status == "open"
    assert incident.resource_id == "PAIR_DRV1_BUS10"


def test_recovery_requires_dispatcher_approval(db_session):
    """
    A generated recovery proposal remains in 'pending' status and is NOT applied
    to live operations until an authorized dispatcher explicitly approves it.
    """
    svc = IncidentService(db_session, tenant_id=1)
    incident = svc.report_incident(
        incident_type="VEHICLE_BREAKDOWN",
        resource_id="PAIR_DRV1_BUS10",
        trip_id="TRIP-401",
        description="Coolant leak",
        reported_by="driver_nikos@ktel.gr",
    )

    proposal = svc.propose_recovery(
        incident_id=incident.id,
        as_of_minutes=600,
        reassignments=[
            {"trip_id": "TRIP-401", "old_resource_id": "PAIR_DRV1_BUS10", "new_resource_id": "RESERVE_PAIR"}
        ],
    )
    assert proposal.status == "pending_approval"

    # Driver cannot approve
    with pytest.raises(PermissionError):
        svc.approve_recovery(proposal.id, actor="driver_nikos@ktel.gr", user_role="driver")

    # Dispatcher approves
    approved = svc.approve_recovery(proposal.id, actor="dispatcher@ktel.gr", user_role="dispatcher")
    assert approved.status == "approved"
    assert approved.approved_by == "dispatcher@ktel.gr"


def test_driver_sees_only_own_assigned_duties(db_session):
    """
    Driver portal queries return strictly the duties assigned to that driver,
    hiding other drivers' assignments.
    """
    sched_svc = SchedulingService(db_session, tenant_id=1)
    period = sched_svc.create_period(name="June 2026", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    rev = sched_svc.create_revision(period_id=period.id, author="dispatcher")

    sched_svc.apply_assignment_patch(
        rev.revision_id,
        patch=[
            {
                "trip_id": "T1",
                "resource_id": "DRIVER_NIKOS",
                "start_minutes": 480,
                "end_minutes": 660,
                "start_station": "Patras",
                "end_station": "Athens",
            },
            {
                "trip_id": "T2",
                "resource_id": "DRIVER_GIORGOS",
                "start_minutes": 500,
                "end_minutes": 680,
                "start_station": "Athens",
                "end_station": "Patras",
            },
        ],
        expected_version=1,
    )

    incident_svc = IncidentService(db_session, tenant_id=1)
    duties_nikos = incident_svc.get_driver_duties(
        revision_id=rev.revision_id,
        driver_resource_id="DRIVER_NIKOS",
    )

    assert len(duties_nikos) == 1
    assert duties_nikos[0].trip_id == "T1"
    assert duties_nikos[0].resource_id == "DRIVER_NIKOS"
