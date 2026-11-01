"""Strict office contracts. Tenant and actor never come from the request."""
from datetime import date, datetime, time
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from app.domain.office.models import Capability

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
ContactName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class GrantSet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    membership_id: int = Field(ge=1, strict=True)
    capability: Capability
    is_active: bool = True
    expected_version: int | None = Field(default=None, ge=1, strict=True)


class RouteCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    driver_id: int | None = Field(default=None, ge=1, strict=True)
    membership_id: int | None = Field(default=None, ge=1, strict=True)
    external_contact_name: ContactName | None = None

    @model_validator(mode='after')
    def one_approver(self):
        if (self.membership_id is None) == (self.external_contact_name is None):
            raise ValueError('Choose either an organization member or an external contact.')
        return self


class RoutePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    is_active: bool


class PatternItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    driver_id: int = Field(ge=1, strict=True)
    weekday_mask: int = Field(ge=1, le=127, strict=True)
    local_start: time
    local_end: time
    ends_next_day: bool = False
    valid_from: date
    valid_until: date
    status: Literal['active', 'retired'] = 'active'
    pattern_id: int | None = Field(default=None, ge=1, strict=True)
    expected_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode='after')
    def consistent(self):
        if not 0 <= (self.valid_until - self.valid_from).days <= 366:
            raise ValueError('A working pattern is valid for at most 366 days.')
        if not self.ends_next_day and self.local_end <= self.local_start:
            raise ValueError('The shift must end after it starts, or end the next day.')
        if (self.pattern_id is None) != (self.expected_version is None):
            raise ValueError('Give both the pattern and its version to change an existing pattern.')
        return self


class PatternBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    items: list[PatternItem] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_rows(self):
        ids = [item.pattern_id for item in self.items if item.pattern_id is not None]
        if len(set(ids)) != len(ids):
            raise ValueError('Each pattern may appear only once.')
        return self


class PeriodItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    driver_id: int = Field(ge=1, strict=True)
    kind: Literal['available', 'unavailable']
    start_local: datetime
    end_local: datetime | None = None
    fold_start: Literal[0, 1] | None = None
    fold_end: Literal[0, 1] | None = None
    category: Literal['sick', 'training', 'other'] | None = None
    status: Literal['active', 'retired'] = 'active'
    period_id: int | None = Field(default=None, ge=1, strict=True)
    expected_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode='after')
    def consistent(self):
        if self.start_local.tzinfo is not None or (self.end_local is not None and self.end_local.tzinfo is not None):
            raise ValueError('Give local clock times without a time zone; the organization time zone applies.')
        if self.kind == 'available' and (self.end_local is None or self.category is not None):
            raise ValueError('A working period needs an end and has no category.')
        if self.kind == 'unavailable' and self.category is None:
            raise ValueError('Choose a category for an unavailable period.')
        if (self.period_id is None) != (self.expected_version is None):
            raise ValueError('Give both the period and its version to change an existing period.')
        return self


class PeriodBatch(PatternBatch):
    items: list[PeriodItem] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_rows(self):
        ids = [item.period_id for item in self.items if item.period_id is not None]
        if len(set(ids)) != len(ids):
            raise ValueError('Each period may appear only once.')
        return self


class DriverLeaveCreate(BaseModel):
    """A driver's own request: there is no driver field; the session decides."""
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    start_local: datetime
    end_local: datetime
    fold_start: Literal[0, 1] | None = None
    fold_end: Literal[0, 1] | None = None
    category: Literal['annual', 'sick', 'unpaid', 'other']
    private_note: Note | None = None

    @model_validator(mode='after')
    def bounded_local_interval(self):
        if self.start_local.tzinfo is not None or self.end_local.tzinfo is not None:
            raise ValueError('Give local clock times without a time zone; the organization time zone applies.')
        if (self.end_local - self.start_local).days > 366:
            raise ValueError('Leave may span at most 366 days.')
        return self


class LeaveCreate(DriverLeaveCreate):
    driver_id: int = Field(ge=1, strict=True)


class DriverLeaveCancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class LeaveDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    decision: Literal['approved', 'rejected']
    note: Note | None = None
    external_route_id: int | None = Field(default=None, ge=1, strict=True)


class LeaveCancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    reason: Reason
    external_route_id: int | None = Field(default=None, ge=1, strict=True)


class VehiclePeriodSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    vehicle_id: int = Field(ge=1, strict=True)
    kind: Literal['planned_maintenance', 'out_of_service']
    start_local: datetime
    end_local: datetime | None = None
    estimated_end_local: datetime | None = None
    fold_start: Literal[0, 1] | None = None
    fold_end: Literal[0, 1] | None = None
    fold_estimate: Literal[0, 1] | None = None
    responsible_label: ContactName | None = None
    period_id: int | None = Field(default=None, ge=1, strict=True)
    expected_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode='after')
    def consistent(self):
        if any(value is not None and value.tzinfo is not None for value in (self.start_local, self.end_local, self.estimated_end_local)):
            raise ValueError('Give local clock times without a time zone; the organization time zone applies.')
        if self.kind == 'planned_maintenance' and (self.end_local is None or self.estimated_end_local is not None):
            raise ValueError('A planned reservation needs a known end and has no estimate.')
        if self.kind == 'out_of_service' and self.end_local is not None:
            raise ValueError('An out-of-service period stays open until it is released; give an estimate instead of an end.')
        if (self.period_id is None) != (self.expected_version is None):
            raise ValueError('Give both the period and its version to change an existing period.')
        return self


class VehicleRelease(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    released_at_local: datetime
    fold_released: Literal[0, 1] | None = None
    note: Note

    @model_validator(mode='after')
    def naive(self):
        if self.released_at_local.tzinfo is not None:
            raise ValueError('Give local clock times without a time zone; the organization time zone applies.')
        return self


class VehicleCancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    reason: Reason


class Retire(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=1, strict=True)
