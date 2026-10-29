"""Recurring wall-clock rules with explicit dated exceptions and DST resolution."""
from datetime import date,datetime,time,timedelta
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,StringConstraints,field_validator,model_validator
from app.domain.timetables.time_service import TripInstant,normalize_service_trip

Clock=Annotated[str,StringConstraints(strip_whitespace=True,pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')]
Weekday=Annotated[int,Field(strict=True,ge=0,le=6)]
ArrivalDay=Annotated[int,Field(strict=True,ge=0,le=2)]
Fold=Annotated[int,Field(strict=True,ge=0,le=1)]


class CalendarRule(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    valid_from:date
    valid_until:date
    operating_weekdays:tuple[Weekday,...]=Field(min_length=1,max_length=7)
    departure_time:Clock
    arrival_time:Clock
    arrival_day_offset:ArrivalDay

    @field_validator('operating_weekdays')
    @classmethod
    def unique_days(cls,value):
        if len(value)!=len(set(value)):
            raise ValueError('Choose each operating weekday once')
        return tuple(sorted(value))

    @model_validator(mode='after')
    def ordered_range(self):
        if self.valid_until<self.valid_from:
            raise ValueError('The validity end date must be on or after its start date')
        return self


class CalendarException(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    action:Literal['inherit','run','cancel']
    departure_time:Clock|None=None
    arrival_time:Clock|None=None
    arrival_day_offset:ArrivalDay|None=None
    fold_start:Fold|None=None
    fold_end:Fold|None=None

    @model_validator(mode='after')
    def cancellation_has_no_hidden_override(self):
        if self.action=='cancel' and any(getattr(self,key) is not None for key in
            ('departure_time','arrival_time','arrival_day_offset','fold_start','fold_end')):
            raise ValueError('A cancellation cannot also change trip times')
        return self


def resolve_service_day(rule:CalendarRule,service_date:date,iana_timezone:str,
                        exception:CalendarException|None=None)->TripInstant|None:
    if exception and exception.action=='cancel':
        return None
    in_range=rule.valid_from<=service_date<=rule.valid_until
    if not in_range:
        if exception and exception.action=='run':
            raise ValueError('Extend the timetable validity range before adding this service date')
        return None
    if service_date.weekday() not in rule.operating_weekdays and not (exception and exception.action=='run'):
        return None
    departure=exception.departure_time if exception and exception.departure_time is not None else rule.departure_time
    arrival=exception.arrival_time if exception and exception.arrival_time is not None else rule.arrival_time
    offset=exception.arrival_day_offset if exception and exception.arrival_day_offset is not None else rule.arrival_day_offset
    result=normalize_service_trip(
        datetime.combine(service_date,time.fromisoformat(departure)),
        datetime.combine(service_date+timedelta(days=offset),time.fromisoformat(arrival)),
        iana_timezone,fold_start=exception.fold_start if exception else None,
        fold_end=exception.fold_end if exception else None,service_date=service_date)
    if result.duration_minutes<=0:
        raise ValueError('Arrival must follow departure; choose next-day arrival for an overnight trip')
    return result
