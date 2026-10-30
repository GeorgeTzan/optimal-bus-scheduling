"""Requests for reviewed changes to an immutable published schedule."""
from uuid import UUID
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,StringConstraints,model_validator
Identifier=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=100)]
Reason=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=1000)]

class ChangePatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    trip_id:Identifier
    operation:Literal['move','unassign','cancel','replace_driver']= 'move'
    new_resource_id:Identifier|None=None
    reason:Reason|None=None
    replacement_resource_id:Identifier|None=None
    driver_version:int|None=Field(default=None,ge=1,strict=True)
    vehicle_version:int|None=Field(default=None,ge=1,strict=True)
    confirm_replacement:bool|None=Field(default=None,strict=True)
    unlock:bool=Field(default=False,strict=True)  # releases the lock only when the trip has an availability conflict

    @model_validator(mode='after')
    def valid_action(self):
        if self.operation == 'move' and (self.new_resource_id is None or self.reason is not None):
            raise ValueError('Choose a destination for a move.')
        if self.operation == 'unassign' and (self.new_resource_id is not None or self.reason is not None):
            raise ValueError('Unassignment does not take a destination or cancellation reason.')
        if self.operation == 'cancel' and (self.new_resource_id is not None or self.reason is None):
            raise ValueError('Give a cancellation reason without a destination.')
        replacement_fields=(self.replacement_resource_id,self.driver_version,self.vehicle_version,self.confirm_replacement)
        if self.operation == 'replace_driver':
            if self.new_resource_id is not None or self.reason is not None or any(value is None for value in replacement_fields) or self.confirm_replacement is not True:
                raise ValueError('Confirm a replacement driver and current source versions.')
        elif any(value is not None for value in replacement_fields):
            raise ValueError('Replacement details only apply to driver replacement.')
        return self

class ChangePreview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    publication_id:Identifier
    version:int=Field(ge=1,strict=True)
    reason:Reason
    reviewed_not_started:list[Identifier]=Field(min_length=1,max_length=2500)
    patches:list[ChangePatch]=Field(min_length=1,max_length=2500)

    @model_validator(mode='after')
    def unique_confirmed_trips(self):
        ids=[item.trip_id for item in self.patches]
        if len(set(ids))!=len(ids) or len(set(self.reviewed_not_started))!=len(self.reviewed_not_started):
            raise ValueError('Each trip may appear only once.')
        if set(ids)!=set(self.reviewed_not_started):
            raise ValueError('Confirm that each changed trip has not started.')
        return self

class ChangeCreate(ChangePreview):
    request_id:UUID
