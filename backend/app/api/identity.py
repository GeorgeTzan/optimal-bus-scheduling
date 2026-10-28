"""Organization member actions require server-side tenant administrator capabilities."""
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator,EmailStr
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User,KTEL
from app.domain.identity.models import Membership,AuthSession,IdentityToken,EmailOutbox
from app.domain.identity.permissions import require_permission

router=APIRouter(prefix='/api/v1/identity',tags=['Organization access'])


class MemberPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    role:Literal['admin','dispatcher','fleet_manager','driver','management','viewer']|None=None
    is_active:bool|None=None
    request_id:UUID|None=None

    @model_validator(mode='after')
    def has_changes(self):
        if self.role is None and self.is_active is None:
            raise ValueError('Choose a role or an active status to change')
        return self


def member_view(member,user):
    return {'id':member.id,'user_id':user.id,'email':user.email,'full_name':user.full_name,
            'role':member.role,'is_active':member.is_active,'version':member.version,'driver_id':member.driver_id}


@router.get('/members')
def list_members(user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    rows=db.query(Membership,User).join(User,User.id==Membership.user_id).order_by(Membership.id).all()
    return {'members':[member_view(member,person) for member,person in rows]}


@router.patch('/members/{member_id}')
def update_member(member_id:int,req:MemberPatch,user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    from uuid import uuid4
    current=db.query(Membership).filter_by(id=member_id).first()
    if current is None:
        raise HTTPException(404,'Organization member not found')
    if (req.role is None or req.role==current.role) and (req.is_active is None or req.is_active==current.is_active):
        # Nothing to change: no version bump, no audit record, no ended sessions.
        return member_view(current,db.query(User).filter_by(id=current.user_id).one())

    def work():
        # Serialize role changes per organization (taken by once() before this runs); lock the member row, then the person.
        member=db.query(Membership).filter_by(id=member_id).populate_existing().with_for_update().first()
        if member is None:
            raise HTTPException(404,'Organization member not found')
        if member.version!=req.version:
            raise HTTPException(409,'This member has changed. Refresh the list before editing.')
        if member.user_id==user.id:
            raise HTTPException(403,{'code':'own_membership','message':'You cannot change your own role or status. Ask another administrator.'})
        new_role=req.role if req.role is not None else member.role
        new_active=req.is_active if req.is_active is not None else member.is_active
        if new_role=='driver' and member.role!='driver':
            raise HTTPException(422,{'code':'driver_needs_record','message':'A driver sign-in is created by inviting from a driver record, not by changing a role.'})
        if member.role=='admin' and member.is_active and (new_role!='admin' or not new_active):
            if db.query(Membership).filter_by(role='admin',is_active=True).count()<=1:
                raise HTTPException(409,'Keep at least one active organization administrator.')
        member.role=new_role;member.is_active=new_active;member.version+=1
        if new_role!='driver':
            member.driver_id=None
        person=db.query(User).filter_by(id=member.user_id).with_for_update().one()
        person.is_admin=new_role=='admin'
        db.query(AuthSession).filter_by(user_id=person.id).filter(AuthSession.revoked_at.is_(None)).update(
            {'revoked_at':datetime.now(timezone.utc)},synchronize_session=False)
        db.flush()
        return member_view(member,person)
    payload={'member_id':member_id,**req.model_dump(mode='json',exclude={'request_id'})}
    return once(db,user,req.request_id or uuid4(),'member','change',payload,work)


class InvitationCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:EmailStr
    role:Literal['admin','dispatcher','fleet_manager','driver','management','viewer']
    driver_id:int|None=Field(default=None,ge=1,strict=True)
    request_id:UUID|None=None

    @model_validator(mode='after')
    def driver_link_needs_driver_role(self):
        if self.driver_id is not None and self.role!='driver':
            raise ValueError('Only the driver role can be linked to a driver record')
        if self.role=='driver' and self.driver_id is None:
            raise ValueError('A driver sign-in is created from a driver record: invite from the driver, not from the team list')
        return self


class LinkRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID


def once(db,user,request_id,entity,action,payload,work):
    """Organization lock, exact-retry replay, one unit of work, audit, commit."""
    from app.domain.office.audit import lock_organization,office_replay,office_record
    lock_organization(db,user.ktel_id)
    previous=office_replay(db,user.ktel_id,user.id,str(request_id),payload)
    if previous is not None:
        return previous
    result=work()
    office_record(db,user.ktel_id,user.id,str(request_id),entity,action,payload,result)
    db.commit()
    return result


def invitation_result(db,issue):
    from app.domain.identity.service import digest
    token=db.query(IdentityToken).filter_by(token_hash=digest(issue.token)).one()
    delivery=db.query(EmailOutbox).filter_by(identity_token_id=token.id).one()
    return {'id':token.id,'email':token.email,'role':token.role,'driver_id':token.driver_id,'expires_at':token.expires_at.isoformat(),
            'delivery_status':delivery.delivery_status}


@router.post('/invitations',status_code=202)
def invite_member(req:InvitationCreate,user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    from uuid import uuid4
    from sqlalchemy import func
    from app.domain.identity.service import issue_invitation
    def work():
        email=str(req.email).strip().lower()
        # Only people of THIS organization are refused here; another organization's email gets the same answer as a new one.
        found=db.query(Membership,User).join(User,User.id==Membership.user_id).filter(Membership.tenant_id==user.ktel_id,func.lower(User.email)==email).first()
        if found is not None and not (found[0].role=='driver' and found[0].driver_id is None and found[0].is_active and req.driver_id is not None):
            raise HTTPException(409,{'code':'member_exists','message':'This person is already in your team. Reactivate them or change their role instead.'})
        return invitation_result(db,issue_invitation(db,user.ktel_id,str(req.email),req.role,req.driver_id))
    return once(db,user,req.request_id or uuid4(),'driver_link' if req.driver_id is not None else 'invitation','invite',req.model_dump(mode='json'),work)


@router.get('/invitations')
def pending_invitations(user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    from app.domain.identity.invitations import list_invitations
    return {'invitations':list_invitations(db,user.ktel_id)}


@router.post('/invitations/{invitation_id}/resend',status_code=202)
def resend(invitation_id:str,req:LinkRequest,user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    from app.domain.identity.invitations import resend_invitation
    return once(db,user,req.request_id,'invitation','resend',{'invitation_id':invitation_id,**req.model_dump(mode='json')},
                lambda:invitation_result(db,resend_invitation(db,user.ktel_id,invitation_id)))


@router.get('/driver-links')
def driver_links(driver_ids:str,user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    from app.domain.identity.driver_links import list_driver_links
    try:
        ids=sorted({int(part) for part in driver_ids.split(',') if part.strip()})
    except ValueError:
        raise HTTPException(422,'driver_ids must be a comma-separated list of numbers') from None
    if not 1<=len(ids)<=100:
        raise HTTPException(422,'Ask for between 1 and 100 drivers')
    return {'links':{str(driver):value for driver,value in list_driver_links(db,user.ktel_id,ids).items()}}


@router.post('/invitations/{invitation_id}/revoke')
def revoke(invitation_id:str,req:LinkRequest,user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    from app.domain.identity.driver_links import revoke_invitation
    def work():
        revoke_invitation(db,user.ktel_id,invitation_id)
        return {'id':invitation_id,'revoked':True}
    return once(db,user,req.request_id,'driver_link','revoke',{'invitation_id':invitation_id,**req.model_dump(mode='json')},work)


@router.post('/drivers/{driver_id}/unlink')
def unlink(driver_id:int,req:LinkRequest,user=Depends(require_permission('members.manage')),db:Session=Depends(get_db)):
    from app.domain.identity.driver_links import unlink_driver
    def work():
        unlink_driver(db,user.ktel_id,driver_id)
        return {'driver_id':driver_id,'unlinked':True}
    return once(db,user,req.request_id,'driver_link','unlink',{'driver_id':driver_id,**req.model_dump(mode='json')},work)
