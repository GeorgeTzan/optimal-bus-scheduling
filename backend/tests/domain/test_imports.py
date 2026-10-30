import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import KTEL
from app.domain.identity.tenant_session import tenant_transaction
from app.domain.timetables.models import TripInstance
from app.domain.imports.legacy_staging import ImportBatch, StagedRow
from app.domain.imports.legacy_service import LegacyReferenceImportService as ImportService
from app.domain.imports.legacy_validation import ValidationError


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    from db.metadata import load_domain_metadata
    load_domain_metadata().create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    ktel1 = KTEL(id=1, name="KTEL Achaias", region="Patras")
    ktel2 = KTEL(id=2, name="KTEL Korinthias", region="Korinthos")
    session.add_all([ktel1, ktel2])
    session.commit()

    yield session
    session.close()


def test_import_preview_does_not_write_live_data(db_session):
    """
    Staging and previewing an import batch does NOT insert rows into the live TripInstance table.
    """
    csv_data = """trip_code,origin,destination,start_time,end_time
TRIP-101,Patras,Athens,08:00,11:00
TRIP-102,Athens,Patras,12:00,15:00
"""
    svc = ImportService(db_session, tenant_id=1)
    batch = svc.stage_import(csv_data.encode("utf-8"), file_format="csv", service_date="2026-06-01")
    
    assert batch.status == "staged"
    preview = svc.preview_import(batch.batch_id)
    assert preview.total_rows == 2
    assert len(preview.sample_rows) == 2
    assert preview.is_valid is True

    # Verify live tables are still empty
    with tenant_transaction(db_session, tenant_id=1):
        live_count = db_session.query(TripInstance).count()
        assert live_count == 0


def test_rejects_duplicate_source_ids(db_session):
    """
    Import batch containing duplicate trip codes in the same service day must be flagged with validation errors.
    """
    csv_data = """trip_code,origin,destination,start_time,end_time
TRIP-DUP,Patras,Athens,08:00,11:00
TRIP-DUP,Patras,Athens,09:00,12:00
"""
    svc = ImportService(db_session, tenant_id=1)
    batch = svc.stage_import(csv_data.encode("utf-8"), file_format="csv", service_date="2026-06-01")
    preview = svc.preview_import(batch.batch_id)

    assert preview.is_valid is False
    assert any("duplicate" in issue.lower() for issue in preview.issues)


def test_import_rolls_back_on_invalid_rows(db_session):
    """
    Committing an import with invalid rows must fail, roll back, and leave live tables untouched.
    """
    csv_data = """trip_code,origin,destination,start_time,end_time
VALID-1,Patras,Athens,08:00,11:00
INVALID-2,Patras,Athens,25:99,99:99
"""
    svc = ImportService(db_session, tenant_id=1)
    batch = svc.stage_import(csv_data.encode("utf-8"), file_format="csv", service_date="2026-06-01")
    
    with pytest.raises(ValidationError):
        svc.commit_import(batch.batch_id)

    with tenant_transaction(db_session, tenant_id=1):
        assert db_session.query(TripInstance).count() == 0


def test_cross_tenant_import_denied(db_session):
    """
    Tenant 2 cannot preview or commit an import batch belonging to Tenant 1.
    """
    csv_data = """trip_code,origin,destination,start_time,end_time
TRIP-T1,Patras,Athens,08:00,11:00
"""
    svc1 = ImportService(db_session, tenant_id=1)
    batch = svc1.stage_import(csv_data.encode("utf-8"), file_format="csv", service_date="2026-06-01")

    svc2 = ImportService(db_session, tenant_id=2)
    with pytest.raises(PermissionError):
        svc2.preview_import(batch.batch_id)

    with pytest.raises(PermissionError):
        svc2.commit_import(batch.batch_id)


def test_round_trip_fixture(db_session):
    """
    Successful staging, preview, and commit of valid trips commits exactly the expected rows.
    """
    csv_data = """trip_code,origin,destination,start_time,end_time
T-01,Patras,Athens,08:00,11:00
T-02,Athens,Patras,12:00,15:00
T-03,Patras,Aigio,16:00,17:00
"""
    svc = ImportService(db_session, tenant_id=1)
    batch = svc.stage_import(csv_data.encode("utf-8"), file_format="csv", service_date="2026-06-01")
    preview = svc.preview_import(batch.batch_id)
    assert preview.is_valid is True

    result = svc.commit_import(batch.batch_id)
    assert result.committed_rows == 3

    with tenant_transaction(db_session, tenant_id=1):
        trips = db_session.query(TripInstance).filter(TripInstance.tenant_id == 1).all()
        assert len(trips) == 3
        codes = {t.trip_code for t in trips}
        assert codes == {"T-01", "T-02", "T-03"}
