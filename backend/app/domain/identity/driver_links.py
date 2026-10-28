"""Driver sign-in links: state, revoke and unlink. Callers hold the organization lock and own the commit."""
from datetime import datetime, timezone
from fastapi import HTTPException
from db.models import User
from app.domain.identity.models import AuthSession, EmailOutbox, IdentityToken, Membership


def list_driver_links(db, tenant_id: int, driver_ids: list[int]) -> dict[int, dict]:
    """unlinked | invited | expired | linked per driver, with the email and the honest delivery status."""
    now = datetime.now(timezone.utc)
    result = {driver: {'state': 'unlinked', 'email': None, 'membership_id': None, 'invitation_id': None, 'expires_at': None, 'delivery_status': None} for driver in driver_ids}
    for member, person in (db.query(Membership, User).join(User, (User.id == Membership.user_id) & (User.ktel_id == Membership.tenant_id))
                           .filter(Membership.tenant_id == tenant_id, Membership.driver_id.in_(driver_ids)).all()):
        result[member.driver_id].update(state='linked', email=person.email, membership_id=member.id)
    for token in (db.query(IdentityToken).filter(IdentityToken.tenant_id == tenant_id, IdentityToken.kind == 'invitation', IdentityToken.driver_id.in_(driver_ids),
                  IdentityToken.consumed_at.is_(None), IdentityToken.revoked_at.is_(None)).order_by(IdentityToken.created_at).all()):
        if result[token.driver_id]['state'] == 'linked':
            continue
        expires = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
        mail = db.query(EmailOutbox.delivery_status).filter_by(tenant_id=tenant_id, identity_token_id=token.id).scalar()
        result[token.driver_id].update(state='invited' if expires > now else 'expired', email=token.email, invitation_id=token.id, expires_at=expires.isoformat(), delivery_status=mail)
    return result


def revoke_invitation(db, tenant_id: int, invitation_id: str) -> None:
    token = db.query(IdentityToken).filter_by(tenant_id=tenant_id, id=invitation_id, kind='invitation').with_for_update().first()
    if token is None:
        raise HTTPException(404, 'Invitation not found')
    if token.revoked_at is not None:
        raise HTTPException(404, 'Invitation not found')
    if token.consumed_at is not None:
        raise HTTPException(409, {'code': 'already_accepted', 'message': 'This invitation was already accepted. Unlink the sign-in instead.'})
    now = datetime.now(timezone.utc)
    token.revoked_at, token.expires_at = now, now
    from app.domain.identity.invitations import discard_queued_mail
    discard_queued_mail(db, tenant_id, token.id)


def unlink_driver(db, tenant_id: int, driver_id: int) -> None:
    """Detach the login and end its sessions; the login keeps the driver role and can be linked again by a new invitation."""
    member = db.query(Membership).filter_by(tenant_id=tenant_id, driver_id=driver_id).with_for_update().first()
    if member is None:
        raise HTTPException(404, {'code': 'not_linked', 'message': 'No sign-in is linked to this driver.'})
    member.driver_id, member.version = None, member.version + 1
    db.query(AuthSession).filter_by(tenant_id=tenant_id, membership_id=member.id).filter(AuthSession.revoked_at.is_(None)).update(
        {'revoked_at': datetime.now(timezone.utc)}, synchronize_session=False)
