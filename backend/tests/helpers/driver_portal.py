"""Link a driver's sign-in the way the office does: invite from the driver record, accept the queued mail."""
import uuid
from urllib.parse import parse_qs, urlsplit
from sqlalchemy import text
from app.domain.identity.mail import decrypt_payload


def link_driver(setup, admin_headers, driver_id, email='driver@example.org', password='StrongTenantPassword123!'):
    client = setup['client']
    invited = client.post('/api/v1/identity/invitations', headers=admin_headers, json={'email': email, 'role': 'driver', 'driver_id': driver_id, 'request_id': str(uuid.uuid4())})
    assert invited.status_code == 202, invited.text
    with setup['owner_factory']() as db:
        rows = db.execute(text("SELECT encrypted_payload FROM domain_email_outbox WHERE kind='invitation' ORDER BY created_at DESC")).all()
    token = next(parse_qs(urlsplit(data['link']).fragment)['token'][0] for (payload,) in rows if (data := decrypt_payload(payload))['to'] == email)
    accepted = client.post('/auth/accept-invitation', json={'token': token, 'password': password, 'full_name': 'Test Driver'})
    assert accepted.status_code == 200, accepted.text
    return {'Authorization': 'Bearer ' + accepted.json()['access_token']}


def freeze_today(monkeypatch, day='2026-06-01'):
    """Fix the driver portal's notion of today so seeded June trips fall inside its window."""
    from datetime import date
    import app.domain.scheduling.driver_duties as module
    real = module.driver_duties
    monkeypatch.setattr(module, 'driver_duties', lambda db, tenant, driver, today=None: real(db, tenant, driver, date.fromisoformat(day)))
