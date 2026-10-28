"""One mail worker serves every organization and reads nothing but the ids of organizations that have mail waiting."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker
from tests.integration.test_identity import identity_setup


def queue_all(setup):
    with setup['owner_factory']() as db:
        db.execute(text("UPDATE domain_email_outbox SET delivery_status='queued'"))
        db.commit()


def test_the_worker_sends_for_every_organization_and_only_sees_organization_ids(identity_setup, restricted_databases, monkeypatch):
    import app.domain.identity.mail as mail
    from config import settings
    sent = []
    monkeypatch.setattr(settings, 'SMTP_HOST', 'smtp.invalid')
    monkeypatch.setattr(settings, 'SMTP_FROM', 'no-reply@example.org')
    monkeypatch.setattr(mail, 'send_email', lambda payload, message_id: sent.append(payload['to']))
    queue_all(identity_setup)
    factory = sessionmaker(bind=restricted_databases['worker'])
    with factory() as db:
        assert sorted(mail.pending_mail_tenants(db)) == sorted([identity_setup['first'].tenant_id, identity_setup['second'].tenant_id])
    assert mail.deliver_all_once(factory, 'worker-1') is True
    assert sorted(sent) == ['first@example.org', 'second@example.org']
    with factory() as db:
        assert mail.pending_mail_tenants(db) == []
    assert mail.deliver_all_once(factory, 'worker-1') is False
    with identity_setup['owner_factory']() as db:
        assert set(db.execute(text('SELECT delivery_status FROM domain_email_outbox')).scalars()) == {'sent'}


def test_a_crashed_workers_expired_lease_is_picked_up_but_a_live_lease_is_not(identity_setup, restricted_databases):
    import app.domain.identity.mail as mail
    with identity_setup['owner_factory']() as db:
        db.execute(text("UPDATE domain_email_outbox SET delivery_status='delivering', lease_expires_at=now()-interval '1 minute' WHERE tenant_id=:t"), {'t': identity_setup['first'].tenant_id})
        db.execute(text("UPDATE domain_email_outbox SET delivery_status='delivering', lease_expires_at=now()+interval '5 minutes' WHERE tenant_id=:t"), {'t': identity_setup['second'].tenant_id})
        db.commit()
    with sessionmaker(bind=restricted_databases['worker'])() as db:
        assert mail.pending_mail_tenants(db) == [identity_setup['first'].tenant_id]


def test_the_function_is_for_the_worker_role_alone_and_the_worker_still_cannot_read_people(identity_setup, restricted_databases):
    with restricted_databases['api'].connect() as connection:
        with pytest.raises(ProgrammingError):
            connection.execute(text('SELECT public.ktel_mail_tenants()'))
    with restricted_databases['worker'].connect() as connection:
        connection.execute(text('SELECT public.ktel_mail_tenants()')).all()
    with restricted_databases['worker'].connect() as connection:
        with pytest.raises(ProgrammingError):
            connection.execute(text('SELECT email FROM users'))


def test_one_unreadable_message_does_not_stop_mail_for_other_organizations(identity_setup, restricted_databases, monkeypatch):
    import app.domain.identity.mail as mail
    from config import settings
    sent = []
    monkeypatch.setattr(settings, 'SMTP_HOST', 'smtp.invalid')
    monkeypatch.setattr(settings, 'SMTP_FROM', 'no-reply@example.org')
    monkeypatch.setattr(mail, 'send_email', lambda payload, message_id: sent.append(payload['to']))
    queue_all(identity_setup)
    with identity_setup['owner_factory']() as db:  # the encryption key changed while this message waited
        db.execute(text("UPDATE domain_email_outbox SET encrypted_payload='not-a-valid-token' WHERE tenant_id=:t"), {'t': identity_setup['first'].tenant_id})
        db.commit()
    factory = sessionmaker(bind=restricted_databases['worker'])
    assert mail.deliver_all_once(factory, 'worker-1') is True
    assert sent == ['second@example.org']
    with identity_setup['owner_factory']() as db:
        states = dict(db.execute(text('SELECT tenant_id, delivery_status FROM domain_email_outbox')).all())
    assert states[identity_setup['first'].tenant_id] == 'failed' and states[identity_setup['second'].tenant_id] == 'sent'
    assert mail.deliver_all_once(factory, 'worker-1') is False  # nothing is retried forever
