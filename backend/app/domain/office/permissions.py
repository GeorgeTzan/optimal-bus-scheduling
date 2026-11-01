"""Office authority comes from explicit per-member grants, never from a role or title."""
from fastapi import HTTPException
from sqlalchemy import or_
from app.domain.identity.models import Membership
from app.domain.office.models import ApprovalRoute, OfficeGrant


def office_capabilities(db, user) -> list[str]:
    rows = db.query(OfficeGrant.capability).filter_by(tenant_id=user.ktel_id, membership_id=user.membership_id, is_active=True).all()
    return sorted(capability for (capability,) in rows)


def require_office_permission(db, user, capability: str) -> None:
    if capability not in office_capabilities(db, user):
        raise HTTPException(403, {'code': 'office_permission_required', 'message': 'Your organization has not granted you this office action.'})


def resolve_approver_routes(db, tenant_id: int, driver_id: int) -> list[ApprovalRoute]:
    """Driver-specific active routes, else the organization default, else none. Routes to deactivated members are ignored; external contacts stay valid."""
    query = (db.query(ApprovalRoute).outerjoin(Membership, (Membership.tenant_id == ApprovalRoute.tenant_id) & (Membership.id == ApprovalRoute.membership_id))
             .filter(ApprovalRoute.tenant_id == tenant_id, ApprovalRoute.is_active.is_(True), or_(ApprovalRoute.membership_id.is_(None), Membership.is_active.is_(True)))
             .order_by(ApprovalRoute.id))
    return query.filter(ApprovalRoute.driver_id == driver_id).all() or query.filter(ApprovalRoute.driver_id.is_(None)).all()


def read_scope(db, user):
    """(can_read, can_see_private) per driver: availability.manage or a route covering the driver; private data needs notes access or a route."""
    capabilities = office_capabilities(db, user)
    routed = db.query(ApprovalRoute.id).filter_by(tenant_id=user.ktel_id, membership_id=user.membership_id, is_active=True).first() is not None
    if 'availability.manage' not in capabilities and not routed:
        raise HTTPException(403, {'code': 'office_permission_required', 'message': 'Your organization has not granted you this office action.'})
    cache = {}

    def covers(driver_id):
        if driver_id not in cache:
            cache[driver_id] = routed and any(route.membership_id == user.membership_id for route in resolve_approver_routes(db, user.ktel_id, driver_id))
        return cache[driver_id]
    return (lambda driver_id: 'availability.manage' in capabilities or covers(driver_id),
            lambda driver_id: 'office.notes.read' in capabilities or covers(driver_id))
