"""Pending invitations for the Team screen: list and resend. Callers hold the organization lock and own the commit. Never returns a token or link."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.domain.identity.models import EmailOutbox, IdentityToken
from app.domain.identity.service import issue_invitation

EXPIRED_VISIBLE_DAYS, LIST_LIMIT = 30, 200
SUPERSEDABLE = ('queued', 'not_configured')  # a row already being delivered or sent is left as it is


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def list_invitations(db, tenant_id: int, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = (db.query(IdentityToken).filter(IdentityToken.tenant_id == tenant_id, IdentityToken.kind == 'invitation', IdentityToken.consumed_at.is_(None),
            IdentityToken.revoked_at.is_(None), IdentityToken.expires_at > now - timedelta(days=EXPIRED_VISIBLE_DAYS))
            .order_by(IdentityToken.created_at.desc()).limit(LIST_LIMIT).all())
    status = dict(db.query(EmailOutbox.identity_token_id, EmailOutbox.delivery_status).filter(EmailOutbox.tenant_id == tenant_id,
                  EmailOutbox.identity_token_id.in_([row.id for row in rows] or [''])).all())
    return [{'id': row.id, 'email': row.email, 'role': row.role, 'driver_id': row.driver_id, 'expires_at': _aware(row.expires_at).isoformat(),
             'created_at': _aware(row.created_at).isoformat(), 'expired': _aware(row.expires_at) <= now, 'delivery_status': status.get(row.id)} for row in rows]


def discard_queued_mail(db, tenant_id: int, token_id: str) -> None:
    db.query(EmailOutbox).filter(EmailOutbox.tenant_id == tenant_id, EmailOutbox.identity_token_id == token_id,
                                 EmailOutbox.delivery_status.in_(SUPERSEDABLE)).update({'delivery_status': 'discarded'}, synchronize_session=False)


def resend_invitation(db, tenant_id: int, invitation_id: str):
    """New invitation with the same email, role and driver; the old link and its unsent mail stop working. Returns the IssuedInvitation."""
    token = db.query(IdentityToken).filter_by(tenant_id=tenant_id, id=invitation_id, kind='invitation').with_for_update().first()
    if token is None or token.consumed_at is not None or token.revoked_at is not None:
        raise HTTPException(404, 'Invitation not found')
    now = datetime.now(timezone.utc)
    token.revoked_at, token.expires_at = now, min(_aware(token.expires_at), now)
    discard_queued_mail(db, tenant_id, token.id)
    db.flush()
    return issue_invitation(db, tenant_id, token.email, token.role, token.driver_id)
