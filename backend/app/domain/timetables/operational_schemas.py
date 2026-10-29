"""Validated manual/import contracts for recurring services and daily resource pairings."""
from datetime import date
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
from app.domain.resources.schemas import Code,validate_patch
from app.domain.timetables.calendar import CalendarRule,CalendarException,Clock,ArrivalDay,Fold,Weekday

Positive=Annotated[int,Field(strict=True,ge=1)]

class TimetableCreate(CalendarRule):
    trip_code:Code
    origin_station_id:Positive
    destination_station_id:Positive
    allowed_bus_types:tuple[Code,...]=Field(min_length=1,max_length=64)
    distance_km:float|None=Field(default=None,ge=0,le=10000)
    is_active:bool=True

    @field_validator('allowed_bus_types')
    @classmethod
    def unique_types(cls,value):return tuple(sorted(set(value)))


class TimetablePatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:Positive
    trip_code:Code|None=None
    origin_station_id:Positive|None=None
    destination_station_id:Positive|None=None
    departure_time:Clock|None=None
    arrival_time:Clock|None=None
    arrival_day_offset:ArrivalDay|None=None
    operating_weekdays:tuple[Weekday,...]|None=None
    valid_from:date|None=None
    valid_until:date|None=None
    allowed_bus_types:tuple[Code,...]|None=None
    distance_km:float|None=Field(default=None,ge=0,le=10000)
    is_active:bool|None=None
    @model_validator(mode='after')
    def changes(self):
        validate_patch(self,tuple(key for key in type(self).model_fields if key not in ('version','distance_km')))
        return self


class ExceptionCreate(CalendarException):
    service_date:date


class ExceptionPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:Positive
    action:str|None=None
    departure_time:Clock|None=None
    arrival_time:Clock|None=None
    arrival_day_offset:ArrivalDay|None=None
    fold_start:Fold|None=None
    fold_end:Fold|None=None
    @model_validator(mode='after')
    def changes(self):
        validate_patch(self,('action',))
        return self


class MaterializeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    service_date:date
    template_versions:dict[int,Positive]


class PairingCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    service_date:date
    driver_id:Positive
    vehicle_id:Positive
    home_station_id:Positive
    driver_version:Positive
    vehicle_version:Positive
    home_station_version:Positive
    confirm:bool=False


class PairingPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:Positive
    driver_id:Positive|None=None
    vehicle_id:Positive|None=None
    home_station_id:Positive|None=None
    driver_version:Positive|None=None
    vehicle_version:Positive|None=None
    home_station_version:Positive|None=None
    confirm:bool|None=None
    is_active:bool|None=None

    @model_validator(mode='after')
    def changes(self):
        validate_patch(self,tuple(key for key in type(self).model_fields if key!='version'))
        if not self.model_fields_set-{'version','driver_version','vehicle_version','home_station_version'}:
            raise ValueError('Choose a pairing change or confirmation')
        if self.confirm and any(getattr(self,key) is None for key in ('driver_version','vehicle_version','home_station_version')):
            raise ValueError('Review the current driver, vehicle and base before confirming')
        return self


class PairingCopy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    from_date:date
    to_date:date


class TransferCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    origin_station_id:Positive
    destination_station_id:Positive
    minutes:Annotated[int,Field(strict=True,ge=0,le=1440)]
    source_note:str|None=Field(default=None,max_length=300)


class TransferPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:Positive
    minutes:Annotated[int,Field(strict=True,ge=0,le=1440)]
    source_note:str|None=Field(default=None,max_length=300)


class TransferBatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items:list[TransferCreate]=Field(min_length=1,max_length=100)
