from typing import Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict


class VehicleBase(BaseModel):
    registration_plate: Optional[str] = None
    code: Optional[str] = None
    bus_type: str
    capacity: Optional[int] = Field(default=None, ge=1, le=200)
    home_station_id: Optional[int] = None
    is_active: bool = True
    properties: Dict[str, Any] = Field(default_factory=dict)


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(BaseModel):
    registration_plate: Optional[str] = None
    bus_type: Optional[str] = None
    capacity: Optional[int] = None
    home_station_id: Optional[int] = None
    is_active: Optional[bool] = None
    properties: Optional[Dict[str, Any]] = None


class VehicleRead(VehicleBase):
    id: int
    tenant_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
