from datetime import date
from typing import Annotated, Optional
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Minutes = Annotated[int, Field(strict=True, gt=0)]
NonNegative = Annotated[int, Field(strict=True, ge=0)]
Version = Annotated[int, Field(strict=True, ge=0)]


class CompanyRulesUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: Version
    overrides: dict[str, Minutes] = Field(default_factory=dict)
    warning_rules: list[str] = Field(default_factory=list)


class DriverProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: Version
    overnight_allowed: bool
    split_shift_allowed: bool
    must_return_to_base: bool
    preferred_route_ids: list[int] = Field(default_factory=list)
    forbidden_route_ids: list[int] = Field(default_factory=list)


class DriverBaselineUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: Version
    as_of: date
    overtime_minutes: NonNegative
    last_duty_end: Optional[AwareDatetime] = None
    last_weekly_rest_end: Optional[AwareDatetime] = None
    last_weekly_rest_at_base: bool = False
    owed_rest_minutes: NonNegative


class VehicleRoutesUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    route_ids: list[int] = Field(default_factory=list)
