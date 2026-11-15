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
