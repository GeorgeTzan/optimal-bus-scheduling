"""Shared resource contracts for manual entry and reviewed imports."""
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field,StringConstraints,model_validator
Text=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=160)]
Code=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=64)]

class ResourceInput(BaseModel):
    model_config=ConfigDict(extra='forbid')

class DriverCreate(ResourceInput):
    code:Code|None=None
    first_name:Text
    last_name:Text
    phone:Annotated[str,StringConstraints(strip_whitespace=True,max_length=40)]|None=None
    license_number:Code|None=None
    home_station_id:int|None=Field(default=None,ge=1)
    is_active:bool=True

class DriverPatch(ResourceInput):
    version:int=Field(ge=1)
    code:Code|None=None
    first_name:Text|None=None
    last_name:Text|None=None
    phone:Annotated[str,StringConstraints(strip_whitespace=True,max_length=40)]|None=None
    license_number:Code|None=None
    home_station_id:int|None=Field(default=None,ge=1)
    is_active:bool|None=None
    @model_validator(mode='after')
    def validate_changes(self):
        validate_patch(self,('code','first_name','last_name','is_active'))
        return self

class VehicleCreate(ResourceInput):
    code:Code|None=None
    registration_plate:Code|None=None
    bus_type:Code
    capacity:int|None=Field(default=None,ge=1,le=200)
    home_station_id:int|None=Field(default=None,ge=1)
    is_active:bool=True
    @model_validator(mode='after')
    def identity(self):
        if not self.code and not self.registration_plate:raise ValueError('Enter a registration or vehicle reference')
        return self

class VehiclePatch(ResourceInput):
    version:int=Field(ge=1)
    code:Code|None=None
    registration_plate:Code|None=None
    bus_type:Code|None=None
    capacity:int|None=Field(default=None,ge=1,le=200)
    home_station_id:int|None=Field(default=None,ge=1)
    is_active:bool|None=None
    @model_validator(mode='after')
    def validate_changes(self):
        validate_patch(self,('code','bus_type','is_active'))
        return self

class StationCreate(ResourceInput):
    code:Code|None=None
    name_el:Text
    name_en:Text|None=None
    is_depot:bool=False
    is_active:bool=True
    latitude:float|None=Field(default=None,ge=-90,le=90)
    longitude:float|None=Field(default=None,ge=-180,le=180)

class StationPatch(ResourceInput):
    version:int=Field(ge=1)
    code:Code|None=None
    name_el:Text|None=None
    name_en:Text|None=None
    is_depot:bool|None=None
    is_active:bool|None=None
    latitude:float|None=Field(default=None,ge=-90,le=90)
    longitude:float|None=Field(default=None,ge=-180,le=180)
    @model_validator(mode='after')
    def validate_changes(self):
        validate_patch(self,('code','name_el','name_en','is_depot','is_active'))
        return self


def validate_patch(value,nonnull):
    changed=value.model_fields_set-{'version'}
    if not changed:raise ValueError('Choose a field to change')
    if any(field in changed and getattr(value,field) is None for field in nonnull):
        raise ValueError('Required fields cannot be cleared')
