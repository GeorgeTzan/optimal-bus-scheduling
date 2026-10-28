import os
import pytest
from fastapi.testclient import TestClient
from main import app
from config import Settings, validate_settings, get_settings


client = TestClient(app, raise_server_exceptions=False)


def test_unauthenticated_solve_trips_drivers_data_rejected(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "REFERENCE_TOOLS_ENABLED", True)
    # Calling protected endpoints without token must return 401 Unauthorized or 403 Forbidden
    endpoints = ["/solve", "/trips", "/drivers", "/data"]
    for ep in endpoints:
        resp = client.get(ep) if ep in ["/trips", "/drivers", "/data"] else client.post(ep, json={})
        assert resp.status_code in (401, 403), f"Expected 401/403 for unauthenticated {ep}, got {resp.status_code}"


def test_registration_requires_invitation():
    # Registration without valid invitation code must be rejected (422 if missing, 403 if invalid)
    payload_missing = {
        "email": "newuser@ktel.gr",
        "password": "Password123!",
        "full_name": "New User",
    }
    resp_missing = client.post("/auth/register", json=payload_missing)
    assert resp_missing.status_code == 422

    payload_invalid = {
        "email": "newuser@ktel.gr",
        "password": "Password123!",
        "full_name": "New User",
        "invitation_code": "INVALID-CODE-XYZ",
    }
    resp_invalid = client.post("/auth/register", json=payload_invalid)
    assert resp_invalid.status_code == 403


def test_no_debug_route_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = get_settings()
    assert settings.ENVIRONMENT == "production"

    # In production, /sentry-debug must return 404
    resp = client.get("/sentry-debug", headers={"X-Environment": "production"})
    assert resp.status_code == 404


def test_missing_secret_fails_startup():
    # In production, default or empty SECRET_KEY must fail validation immediately
    with pytest.raises(ValueError, match="SECRET_KEY"):
        s = Settings(
            ENVIRONMENT="production",
            SECRET_KEY="change-this-in-production",
        )
        validate_settings(s)


def test_no_raw_traceback():
    # A deliberate error route exists only within this test, never in the deployed API.
    async def fail():
        raise RuntimeError("Test-only unhandled failure")
    app.router.add_api_route('/_tests/unhandled', fail, methods=['GET'])
    route = app.router.routes[-1]
    try:
        response = client.get('/_tests/unhandled')
        assert response.status_code == 500
        assert "Traceback" not in response.text
        assert response.json() == {"detail": "Internal Server Error"}
    finally:
        app.router.routes.remove(route)


@pytest.mark.parametrize('changes,expected',[
    ({'PUBLIC_APP_URL':'http://ktel.example.org'},'PUBLIC_APP_URL'),
    ({'SMTP_HOST':'smtp.example.org','SMTP_FROM':'ops@example.org','SMTP_USE_TLS':False},'SMTP_USE_TLS'),
    ({'SMTP_HOST':'smtp.example.org','SMTP_FROM':''},'SMTP_FROM'),
])
def test_production_identity_links_and_mail_transport_are_secure(changes,expected):
    s=Settings(ENVIRONMENT='production',SECRET_KEY='x'*48,DATABASE_URL='postgresql://migration:private@localhost/ktel',
               PUBLIC_APP_URL='https://ktel.example.org',**{k:v for k,v in changes.items() if k!='PUBLIC_APP_URL'})
    if 'PUBLIC_APP_URL' in changes:s.PUBLIC_APP_URL=changes['PUBLIC_APP_URL']
    with pytest.raises(ValueError,match=expected):validate_settings(s)


def test_local_reference_opt_in_never_enables_public_production_fixture_tools(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'production')
    monkeypatch.setattr(settings, 'REFERENCE_TOOLS_ENABLED', True)
    assert client.get('/data').status_code == 404
    assert client.post('/api/v1/scheduling/revisions/import-reference', json={'service_date': '2026-06-01'}).status_code == 404
