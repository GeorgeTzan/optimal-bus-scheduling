from datetime import datetime, date, timezone, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import KTEL
from app.domain.identity.tenant_session import tenant_transaction
from app.domain.workforce.models import Driver, WorkforceDriver
from app.domain.workforce.schemas import DriverCreate
from app.domain.workforce.service import WorkforceService
from app.domain.fleet.models import Vehicle
from app.domain.fleet.schemas import VehicleCreate
from app.domain.fleet.service import FleetService
from app.domain.timetables.models import Station, Route, TripInstance
from app.domain.timetables.schemas import StationCreate, TripInstanceCreate
from app.domain.timetables.service import TimetableService
from app.domain.timetables.time_service import normalize_service_trip


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


def test_driver_vehicle_records_independent(db_session):
    """
    Drivers and vehicles are independent entities in the canonical data model.
    A driver can be created without an attached vehicle, and vice versa.
    """
    with tenant_transaction(db_session, tenant_id=1):
        workforce_svc = WorkforceService(db_session, tenant_id=1)
        fleet_svc = FleetService(db_session, tenant_id=1)

        driver = workforce_svc.create_driver(DriverCreate(
            code="DRV-001",
            first_name="Nikos",
            last_name="Papadopoulos",
            license_number="EL-12345",
            max_daily_driving_minutes=540,
            is_active=True,
        ))
        vehicle = fleet_svc.create_vehicle(VehicleCreate(
            registration_plate="IBZ-8899",
            bus_type="standard_12m",
            capacity=50,
            is_active=True,
        ))

        assert driver.id is not None
        assert vehicle.id is not None
        assert driver.code == "DRV-001"
        assert vehicle.registration_plate == "IBZ-8899"


def test_tenant_isolation_on_canonical_resources(db_session):
    """
    Resources created by tenant 1 are invisible to tenant 2.
    """
    with tenant_transaction(db_session, tenant_id=1):
        wf1 = WorkforceService(db_session, tenant_id=1)
        wf1.create_driver(DriverCreate(
            code="DRV-TENANT-1",
            first_name="Giorgos",
            last_name="Alexiou",
        ))

    with tenant_transaction(db_session, tenant_id=2):
        wf2 = WorkforceService(db_session, tenant_id=2)
        drivers_t2 = wf2.list_drivers()
        assert len(drivers_t2) == 0


def test_cross_day_rest_input():
    """
    Cross-day rest validation:
    A driver finishes duty on day 1 at 23:00 UTC and is scheduled on day 2 at 06:00 UTC.
    The rest between duties is 7 hours (420 minutes), which is less than 11 hours (660 minutes).
    Verify that cross-day rest calculation between TripInstants accurately calculates UTC gap.
    """
    t1 = normalize_service_trip(
        local_start=datetime(2026, 6, 1, 14, 0),
        local_end=datetime(2026, 6, 1, 23, 0),
        iana_timezone="Europe/Athens",
    )
    t2 = normalize_service_trip(
        local_start=datetime(2026, 6, 2, 6, 0),
        local_end=datetime(2026, 6, 2, 14, 0),
        iana_timezone="Europe/Athens",
    )

    rest_gap_seconds = (t2.start_utc - t1.end_utc).total_seconds()
    rest_gap_minutes = int(rest_gap_seconds // 60)
    assert rest_gap_minutes == 420  # 7 hours
    assert rest_gap_minutes < 660  # violates minimum 11-hour daily rest
