from typing import Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict


class DriverBase(BaseModel):
    code: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    license_number: Optional[str] = None
    home_station_id: Optional[int] = None
    max_daily_driving_minutes: int = Field(default=540, ge=60, le=900)
    max_continuous_driving_minutes: int = Field(default=270, ge=60, le=360)
    min_daily_rest_minutes: int = Field(default=660, ge=480, le=1440)
    is_active: bool = True
    properties: Dict[str, Any] = Field(default_factory=dict)


class DriverCreate(DriverBase):
    pass


class DriverUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None
    home_station_id: Optional[int] = None
    max_daily_driving_minutes: Optional[int] = None
    max_continuous_driving_minutes: Optional[int] = None
    min_daily_rest_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    properties: Optional[Dict[str, Any]] = None


class DriverRead(DriverBase):
    id: int
    tenant_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DriverQualificationCreate(BaseModel):
    driver_id: int
    qualification_code: str
    valid_until: Optional[date] = None


class DriverQualificationRead(DriverQualificationCreate):
    id: int
    tenant_id: int
    model_config = ConfigDict(from_attributes=True)
