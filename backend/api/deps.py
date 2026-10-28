from fastapi import Depends,HTTPException,Request
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import hmac
from db.database import get_db
from db.models import User
from core.security import decode_token
from app.domain.identity.tenant_session import tenant_transaction
from app.domain.identity.service import session_lookup,digest
from app.domain.identity.models import Membership
from app.domain.identity.permissions import PERMISSIONS

security=HTTPBearer(auto_error=False)


def get_current_user(request:Request,credentials:HTTPAuthorizationCredentials|None=Depends(security),db:Session=Depends(get_db)):
    bearer=request.headers.get('Authorization') is not None
    payload=None
    if bearer:
        if credentials is None:
            raise HTTPException(401,'Sign in to continue')
        payload=decode_token(credentials.credentials)
        if payload is None or not payload.get('sid'):
            raise HTTPException(401,'Your session has expired. Please sign in again.')
        session=session_lookup(db,str(payload['sid']),by_id=True)
    else:
        cookie=request.cookies.get('ktel_session')
        if not cookie:
            raise HTTPException(401,'Sign in to continue')
        session=session_lookup(db,digest(cookie))
    if session is None or (payload is not None and str(payload.get('sub'))!=str(session.user_id)):
        raise HTTPException(401,'Your session has expired. Please sign in again.')
    if not bearer and request.method not in ('GET','HEAD','OPTIONS'):
        csrf=request.headers.get('X-CSRF-Token','')
        if not csrf or not hmac.compare_digest(digest(csrf),session.csrf_hash):
            raise HTTPException(403,'This action could not be verified. Refresh the page and try again.')
    with tenant_transaction(db,session.tenant_id):
        user=db.query(User).filter(User.id==session.user_id).first()
        member=db.query(Membership).filter(Membership.id==session.membership_id,Membership.user_id==session.user_id).first()
        if user is None or member is None or not user.is_active or not member.is_active:
            raise HTTPException(401,'Your organization membership is inactive. Contact your administrator.')
        user.role=member.role
        user.permissions=sorted(PERMISSIONS.get(member.role,set()))
        user.session_id=session.id
        user.membership_id=member.id
        yield user
