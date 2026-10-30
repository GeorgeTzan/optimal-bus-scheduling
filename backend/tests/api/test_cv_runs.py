from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
from db.models import KTEL, User
from app.domain.identity.tenant_session import tenant_transaction
from main import app
from tests.support import create_test_access_token
from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot, Assignment, SolverResult
from app.domain.optimization.metrics import calculate_metrics, CandidateMetrics
from app.domain.verification.verifier import HardRuleVerifier


@pytest.fixture
def test_setup(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "REFERENCE_TOOLS_ENABLED", True)
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
    user1 = User(id=1, email="dispatcher@ktel-achaias.gr", hashed_password="pw", full_name="Dispatcher 1", is_active=True, is_admin=True, ktel_id=1)
    user2 = User(id=2, email="dispatcher@ktel-korinthias.gr", hashed_password="pw", full_name="Dispatcher 2", is_active=True, is_admin=True, ktel_id=2)
    session.add_all([ktel1, ktel2, user1, user2])
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    token_user1 = create_test_access_token(session,user1.id)
    token_user2 = create_test_access_token(session,user2.id)

    client = TestClient(app)
    imported = client.post('/api/v1/scheduling/revisions/import-reference',
        headers={'Authorization': f'Bearer {token_user1}'}, json={'service_date':'2026-10-30'})
    assert imported.status_code == 201
    snapshot_id = imported.json()['revision_id']

    yield {
        "client": client,
        "snapshot_id": snapshot_id,
        "token1": token_user1,
        "token2": token_user2,
        "session": session,
    }

    app.dependency_overrides.clear()
    session.close()


def test_cv_default_production(test_setup):
    """
    Submitting an optimization run without specifying a solver defaults to cv-bounded-v1.
    """
    client = test_setup["client"]
    token = test_setup["token1"]

    resp = client.post(
        "/optimization/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "snapshot_id": test_setup["snapshot_id"],
            "config": {"time_limit_seconds": 30},
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["solver_version"] == "cv-bounded-v1"
    assert data["status"] == "queued"


def test_other_solver_not_callable_from_production_route(test_setup):
    """
    Research algorithms (greedy, simulated annealing, lahc) cannot be called from the production optimization route.
    """
    client = test_setup["client"]
    token = test_setup["token1"]

    for forbidden in ["greedy", "simulated_annealing", "lahc", "tabu"]:
        resp = client.post(
            "/optimization/runs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "snapshot_id": test_setup["snapshot_id"],
                "solver_version": forbidden,
            },
        )
        assert resp.status_code == 400
        assert "not permitted" in resp.json()["detail"].lower()


def test_tenant_cannot_read_other_candidate(test_setup):
    """
    Tenant 2 cannot read or fetch run candidates belonging to Tenant 1.
    """
    client = test_setup["client"]
    token1 = test_setup["token1"]
    token2 = test_setup["token2"]

    # Tenant 1 creates a run
    resp1 = client.post(
        "/optimization/runs",
        headers={"Authorization": f"Bearer {token1}"},
        json={"snapshot_id": test_setup["snapshot_id"]},
    )
    run_id = resp1.json()["run_id"]

    # Tenant 2 tries to fetch the run
    resp2 = client.get(
        f"/optimization/runs/{run_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp2.status_code == 404

    # Tenant 2 tries to fetch candidates
    resp3 = client.get(
        f"/optimization/runs/{run_id}/candidates",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp3.status_code == 404


def test_unknown_metrics_not_reported_as_zero():
    """
    Candidate metrics must not report unknown / unmeasured metrics as 0.
    For example, uncalculated carbon emissions or fuel usage should be None, not 0.
    """
    prob = SolverProblem(
        problem_id="P1",
        tenant_id="1",
        service_date=date(2026, 6, 1),
        trips=(
            TripSnapshot(id="T1", start_station="A", end_station="B", start_minutes=100, end_minutes=200, duration_minutes=100),
        ),
        resources=(
            ResourceSnapshot(resource_id="R1", driver_id="D1", bus_id="B1", home_station="A"),
        ),
        chains=(),
    )
    res = SolverResult(
        solver_id="cv-bounded-v1",
        solver_version="1.0.0",
        assignments=(
            Assignment(resource_id="R1", trip_id="T1", start_minutes=100, end_minutes=200, start_station="A", end_station="B"),
        ),
        unassigned_trip_ids=(),
        metrics={},
        solve_time_seconds=1.5,
        status="OPTIMAL",
    )

    metrics = calculate_metrics(prob, res)
    assert metrics.total_driving_minutes == 100
    assert metrics.total_deadhead_minutes is None  # Unmeasured positioning time is not zero.
    assert metrics.fuel_liters_estimate is None  # NOT 0.0!
    assert metrics.deadhead_kilometers is None  # NOT 0.0 when transfer matrix not available!


def test_unassigned_trip_visible():
    """
    If a solver fails to schedule all trips, unassigned trips are explicitly listed and counted.
    """
    prob = SolverProblem(
        problem_id="P1",
        tenant_id="1",
        service_date=date(2026, 6, 1),
        trips=(
            TripSnapshot(id="T1", start_station="A", end_station="B", start_minutes=100, end_minutes=200, duration_minutes=100),
            TripSnapshot(id="T2", start_station="A", end_station="B", start_minutes=150, end_minutes=250, duration_minutes=100),
        ),
        resources=(
            ResourceSnapshot(resource_id="R1", driver_id="D1", bus_id="B1", home_station="A"),
        ),
        chains=(),
    )
    res = SolverResult(
        solver_id="cv-bounded-v1",
        solver_version="1.0.0",
        assignments=(
            Assignment(resource_id="R1", trip_id="T1", start_minutes=100, end_minutes=200, start_station="A", end_station="B"),
        ),
        unassigned_trip_ids=("T2",),
        metrics={},
        solve_time_seconds=1.5,
        status="FEASIBLE",
    )

    metrics = calculate_metrics(prob, res)
    assert metrics.assigned_trips_count == 1
    assert metrics.unassigned_trips_count == 1
    assert "T2" in metrics.unassigned_trip_ids


def test_invalid_candidate_not_publishable():
    """
    A candidate that fails verification (e.g. temporal overlap) is marked invalid and not publishable.
    """
    prob = SolverProblem(
        problem_id="P1",
        tenant_id="1",
        service_date=date(2026, 6, 1),
        trips=(
            TripSnapshot(id="T1", start_station="A", end_station="B", start_minutes=100, end_minutes=200, duration_minutes=100),
            TripSnapshot(id="T2", start_station="B", end_station="C", start_minutes=150, end_minutes=250, duration_minutes=100),
        ),
        resources=(
            ResourceSnapshot(resource_id="R1", driver_id="D1", bus_id="B1", home_station="A"),
        ),
        chains=(),
    )
    # Overlapping assignments on R1
    bad_result = SolverResult(
        solver_id="cv-bounded-v1",
        solver_version="1.0.0",
        assignments=(
            Assignment(resource_id="R1", trip_id="T1", start_minutes=100, end_minutes=200, start_station="A", end_station="B"),
            Assignment(resource_id="R1", trip_id="T2", start_minutes=150, end_minutes=250, start_station="B", end_station="C"),
        ),
        unassigned_trip_ids=(),
        metrics={},
        solve_time_seconds=1.0,
        status="FEASIBLE",
    )

    verifier = HardRuleVerifier()
    report = verifier.verify(prob, bad_result)
    assert report.is_feasible is False
    assert len(report.violations) > 0
