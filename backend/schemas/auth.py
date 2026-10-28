from pydantic import BaseModel,EmailStr,ConfigDict,Field,computed_field
from typing import Optional


class UserCreate(BaseModel):
    email:EmailStr
    password:str
    full_name:str
    invitation_code:str


class UserLogin(BaseModel):
    email:EmailStr
    password:str=Field(min_length=1,max_length=512)


class UserResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int
    email:EmailStr
    full_name:Optional[str]=None
    is_active:bool
    ktel_id:int
    ktel_name:str
    role:str
    permissions:list[str]
    session_id:str

    @computed_field
    @property
    def is_admin(self)->bool:
        return self.role=='admin'


class Token(BaseModel):
    access_token:str
    token_type:str='bearer'


class LinkRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=20,max_length=200)


class InvitationAccept(LinkRequest):
    password:str=Field(min_length=12,max_length=128)
    full_name:str=Field(min_length=1,max_length=200)


class ResetRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:EmailStr


class ResetConfirm(LinkRequest):
    password:str=Field(min_length=12,max_length=128)
