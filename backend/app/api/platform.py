import hmac
from datetime import date,datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,EmailStr,Field
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session,sessionmaker
from api.auth import trusted_origin
from config import settings
from app.domain.identity.service import digest
from app.domain.identity.throttle import consume_budget
from db.database import get_db
from app.domain.platform import customers,service,support

engine=create_engine(settings.DATABASE_PLATFORM_URL,hide_parameters=True)
PlatformSessionLocal=sessionmaker(autocommit=False,autoflush=False,bind=engine)
SESSION_COOKIE='ktel_platform_session'
CSRF_COOKIE='ktel_platform_csrf'
SESSION_COOKIE_PATH='/api/v1/platform'
CSRF_COOKIE_PATH='/platform'


def get_platform_db():
    db=PlatformSessionLocal()
    try:
        yield db
    finally:
        db.close()


def client_address(request:Request):
    return request.client.host if request.client else 'unknown'


def current_operator(request:Request,db:Session=Depends(get_platform_db)):
    token=request.cookies.get(SESSION_COOKIE)
    operator=service.session_operator(db,digest(token)) if token else None
    if operator is None:
        raise HTTPException(401,'Sign in to continue')
    if request.method not in ('GET','HEAD','OPTIONS'):
        csrf=request.headers.get('X-CSRF-Token','')
        if not csrf or not hmac.compare_digest(digest(csrf),operator['csrf_hash']):
            raise HTTPException(403,'This action could not be verified. Refresh the page and try again.')
    db.commit()
    return operator


class CustomerCreate(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    region:str|None=Field(default=None,max_length=200)
    timezone:str=Field(default='Europe/Athens',max_length=64)
    status:Literal['trial','active']='trial'
    trial_ends_on:date|None=None
    admin_email:EmailStr


class CustomerUpdate(BaseModel):
    status:Literal['trial','active','suspended','cancelled']|None=None
    trial_ends_on:date|None=None
    plan_note:str|None=Field(default=None,max_length=2000)
    region:str|None=Field(default=None,max_length=200)


class SupportStart(BaseModel):
    reason:str=Field(max_length=500)
    ticket:str|None=Field(default=None,max_length=100)


class OperatorLogin(BaseModel):
    email:str=Field(max_length=320)
    password:str=Field(max_length=4096)
    code:str=Field(max_length=16)


router=APIRouter(prefix='/api/v1/platform',tags=['Platform operators'],dependencies=[Depends(trusted_origin)])


@router.post('/auth/login',status_code=204)
def login(credentials:OperatorLogin,request:Request,response:Response,db:Session=Depends(get_platform_db)):
    address=client_address(request)
    if not consume_budget(db,'platform_login',credentials.email,address,settings.AUTH_LOGIN_LIMIT,900):
        service.record_throttled(db,email=credentials.email,ip=address)
        raise HTTPException(429,'Too many sign-in attempts. Please wait and try again.',headers={'Retry-After':'900'})
    issued=service.sign_in(db,email=credentials.email,password=credentials.password,code=credentials.code,ip=address)
    if issued is None:
        raise HTTPException(401,'The email, password or code is incorrect. Please try again.')
    token,csrf=issued
    secure=settings.ENVIRONMENT=='production'
    response.headers['Cache-Control']='no-store'
    response.set_cookie(SESSION_COOKIE,token,httponly=True,secure=secure,samesite='strict',path=SESSION_COOKIE_PATH)
    response.set_cookie(CSRF_COOKIE,csrf,httponly=False,secure=secure,samesite='strict',path=CSRF_COOKIE_PATH)


@router.post('/auth/logout',status_code=204)
def logout(request:Request,response:Response,operator=Depends(current_operator),db:Session=Depends(get_platform_db)):
    support.end(db,operator,tenant_id=None,ip=client_address(request),by='logout')
    service.sign_out(db,operator,ip=client_address(request))
    secure=settings.ENVIRONMENT=='production'
    response.delete_cookie(support.COOKIE,path='/',secure=secure,httponly=True,samesite='strict')
    response.delete_cookie(SESSION_COOKIE,path=SESSION_COOKIE_PATH,secure=secure,httponly=True,samesite='strict')
    response.delete_cookie(CSRF_COOKIE,path=CSRF_COOKIE_PATH,secure=secure,samesite='strict')


@router.get('/me')
def me(operator=Depends(current_operator)):
    return {'id':operator['id'],'email':operator['email']}


@router.get('/customers')
def list_customers(operator=Depends(current_operator),db:Session=Depends(get_platform_db)):
    health=customers.customer_health(db)
    return [{**customer,'health':health.get(customer['id'])} for customer in customers.list_customers(db)]


@router.get('/customers/{tenant_id}/health')
def customer_health(tenant_id:int,operator=Depends(current_operator),db:Session=Depends(get_platform_db)):
    health=customers.customer_health(db).get(tenant_id)
    if health is None:
        raise HTTPException(404,'Customer not found')
    return health


@router.post('/customers',status_code=201)
def create_customer(body:CustomerCreate,request:Request,response:Response,operator=Depends(current_operator),db:Session=Depends(get_platform_db)):
    try:
        tenant_id,link=customers.create_customer(db,operator,ip=client_address(request),**body.model_dump())
    except customers.CustomerError as error:
        raise HTTPException(422,str(error)) from None
    except IntegrityError as error:
        db.rollback()
        if getattr(error.orig,'pgcode',None)!='23505':
            raise
        raise HTTPException(409,'An organization with this name already exists') from None
    response.headers['Cache-Control']='no-store'
    return {'id':tenant_id,'invitation_link':link}


@router.patch('/customers/{tenant_id}')
def update_customer(tenant_id:int,body:CustomerUpdate,request:Request,operator=Depends(current_operator),db:Session=Depends(get_platform_db)):
    if 'status' in body.model_fields_set and body.status is None:
        raise HTTPException(422,'A status is required')
    customer=customers.update_customer(db,operator,tenant_id,body.model_dump(include=body.model_fields_set),ip=client_address(request))
    if customer is None:
        raise HTTPException(404,'Customer not found')
    return customer


@router.get('/customers/{tenant_id}/support-session')
def support_state(tenant_id:int,operator=Depends(current_operator),db:Session=Depends(get_platform_db)):
    found=support.state(db,operator,tenant_id)
    if found is None:
        raise HTTPException(404,'Customer not found')
    return found


@router.post('/customers/{tenant_id}/support-session',status_code=201)
def start_support(tenant_id:int,body:SupportStart,request:Request,response:Response,operator=Depends(current_operator),
                  db:Session=Depends(get_platform_db),tenant_db:Session=Depends(get_db)):
    if not body.reason.strip():
        raise HTTPException(422,'A reason is required')
    try:
        token,ends_at=support.start(db,operator,tenant_id,reason=body.reason,ticket=body.ticket,ip=client_address(request))
    except support.SupportError as error:
        raise HTTPException(error.status,{'code':error.code,'message':error.message} if error.code else error.message) from None
    mail_status=support.notify_administrators(tenant_db,tenant_id,body.reason.strip(),ends_at)
    seconds=max(1,int((ends_at-datetime.now(timezone.utc)).total_seconds()))
    response.headers['Cache-Control']='no-store'
    response.set_cookie(support.COOKIE,token,httponly=True,secure=settings.ENVIRONMENT=='production',samesite='strict',max_age=seconds,path='/')
    return {'redirect':'/','ends_at':ends_at,'mail_status':mail_status}


@router.delete('/customers/{tenant_id}/support-session',status_code=204)
def end_support(tenant_id:int,request:Request,response:Response,operator=Depends(current_operator),db:Session=Depends(get_platform_db)):
    support.end(db,operator,tenant_id=tenant_id,ip=client_address(request),by='operator')
    response.delete_cookie(support.COOKIE,path='/',secure=settings.ENVIRONMENT=='production',httponly=True,samesite='strict')
