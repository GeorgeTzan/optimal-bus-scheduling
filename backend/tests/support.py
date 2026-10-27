"""Unit API fixtures issue the same registered sessions used by real login."""
from db.models import User
from app.domain.identity.models import Membership
from app.domain.identity.service import create_session
from app.domain.identity.tenant_session import tenant_transaction


def create_test_access_token(db,user_id):
    user=db.query(User).filter_by(id=user_id).one()
    with tenant_transaction(db,user.ktel_id):
        member=db.query(Membership).filter_by(user_id=user.id).first()
        if member is None:
            member=Membership(tenant_id=user.ktel_id,user_id=user.id,role='admin' if user.is_admin else 'viewer',is_active=True)
            db.add(member);db.flush()
        credentials=create_session(db,user,member)
        db.commit()
        return credentials.bearer_token
