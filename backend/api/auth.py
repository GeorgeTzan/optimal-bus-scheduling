from fastapi import APIRouter,Depends,HTTPException,Response,Request
from sqlalchemy.orm import Session
from datetime import datetime,timezone
from db.database import get_db
from db.models import User,KTEL
from schemas.auth import UserCreate,UserLogin,UserResponse,Token,LinkRequest,InvitationAccept,ResetRequest,ResetConfirm
from core.security import verify_password,create_access_token
from api.deps import get_current_user
from config import settings
from app.domain.identity.lookup import lookup_identity
from app.domain.identity.models import Membership,AuthSession
from app.domain.identity.tenant_session import tenant_transaction
from app.domain.identity.service import create_session,accept_invitation,valid_invitation,SESSION_SECONDS,request_password_reset,confirm_password_reset
from app.domain.identity.throttle import consume_budget

def trusted_origin(request:Request):
    origin=request.headers.get('Origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in settings.ALLOWED_ORIGINS:
        raise HTTPException(403,'Open this action from your KTEL application and try again.')


router=APIRouter(prefix='/auth',tags=['Authentication'],dependencies=[Depends(trusted_origin)])


def session_response(response,credentials):
    response.headers['Cache-Control']='no-store'
    secure=settings.ENVIRONMENT=='production'
    response.set_cookie('ktel_session',credentials.cookie_token,httponly=True,secure=secure,samesite='lax',max_age=SESSION_SECONDS,path='/')
    response.set_cookie('ktel_csrf',credentials.csrf_token,httponly=False,secure=secure,samesite='lax',max_age=SESSION_SECONDS,path='/')
    return Token(access_token=credentials.bearer_token)


@router.post('/register')
def register(user_data:UserCreate):
    raise HTTPException(403,'Use the invitation link from your KTEL administrator to create an account.')


@router.post('/login',response_model=Token)
def login(credentials:UserLogin,response:Response,request:Request,db:Session=Depends(get_db)):
    address=request.client.host if request.client else 'unknown'
    if not consume_budget(db,'login',str(credentials.email),address,settings.AUTH_LOGIN_LIMIT,900):
        raise HTTPException(429,'Too many sign-in attempts. Please wait and try again.',headers={'Retry-After':'900'})
    found=lookup_identity(db,str(credentials.email).strip().lower(),login=True)
    if found is None or found.ktel_id is None:
        raise HTTPException(401,'The email or password is incorrect. Please try again.')
    with tenant_transaction(db,found.ktel_id):
        # Re-read while locked: a concurrent password reset must not authorize a stale password.
        user=db.query(User).filter_by(id=found.id).populate_existing().with_for_update().first()
        if user is None or not verify_password(credentials.password,user.hashed_password):
            raise HTTPException(401,'The email or password is incorrect. Please try again.')
        if not user.is_active:
            raise HTTPException(403,'Your account is inactive. Contact your KTEL administrator.')
        member=db.query(Membership).filter_by(user_id=user.id,is_active=True).first()
        if member is None:
            raise HTTPException(403,'Your organization membership is inactive. Contact your administrator.')
        session=create_session(db,user,member)
        db.commit()
    return session_response(response,session)


@router.get('/me',response_model=UserResponse)
def me(current_user:User=Depends(get_current_user)):
    current_user.ktel_name=current_user.ktel.name
    return current_user


@router.post('/logout',status_code=204)
def logout(response:Response,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    session=db.query(AuthSession).filter_by(id=current_user.session_id).one()
    session.revoked_at=datetime.now(timezone.utc)
    db.commit()
    secure=settings.ENVIRONMENT=='production'
    response.delete_cookie('ktel_session',path='/',secure=secure,httponly=True,samesite='lax')
    response.delete_cookie('ktel_csrf',path='/',secure=secure,samesite='lax')


@router.post('/invitations/preview')
def invitation_preview(req:LinkRequest,db:Session=Depends(get_db)):
    token=valid_invitation(db,req.token)
    with tenant_transaction(db,token.tenant_id):
        tenant=db.query(KTEL).filter_by(id=token.tenant_id).one()
        return {'organization_name':tenant.name,'email':token.email,'role':token.role}


@router.post('/accept-invitation',response_model=Token)
def invitation_accept(req:InvitationAccept,response:Response,db:Session=Depends(get_db)):
    return session_response(response,accept_invitation(db,req.token,req.password,req.full_name))


@router.post('/password-reset/request',status_code=202)
def reset_request(req:ResetRequest,request:Request,db:Session=Depends(get_db)):
    address=request.client.host if request.client else 'unknown'
    if consume_budget(db,'reset',str(req.email),address,settings.AUTH_RESET_LIMIT,3600):
        request_password_reset(db,str(req.email))
    return {'message':'If this account is active, a reset link will be sent. Check your email or contact your administrator.'}


@router.post('/password-reset/confirm')
def reset_confirm(req:ResetConfirm,db:Session=Depends(get_db)):
    confirm_password_reset(db,req.token,req.password)
    return {'message':'Your password has been updated. Sign in with your new password.'}
