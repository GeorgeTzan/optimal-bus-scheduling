from typing import Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict


class StationBase(BaseModel):
    code: str
    name_el: str
    name_en: str
    is_depot: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class StationCreate(StationBase):
    pass


class StationRead(StationBase):
    id: int
    tenant_id: int
    model_config = ConfigDict(from_attributes=True)


class RouteBase(BaseModel):
    origin_station_id: int
    destination_station_id: int
    distance_km: Optional[float] = None
    typical_duration_minutes: Optional[int] = None


class RouteCreate(RouteBase):
    pass


class RouteRead(RouteBase):
    id: int
    tenant_id: int
    model_config = ConfigDict(from_attributes=True)


class ServiceTemplateBase(BaseModel):
    route_id: int
    trip_code: str
    departure_time: str
    arrival_time: str
    is_active: bool = True


class ServiceTemplateCreate(ServiceTemplateBase):
    pass


class ServiceTemplateRead(ServiceTemplateBase):
    id: int
    tenant_id: int
    model_config = ConfigDict(from_attributes=True)


class TripInstanceBase(BaseModel):
    trip_code: str
    service_date: date
    origin_station_id: int
    destination_station_id: int
    start_utc: datetime
    end_utc: datetime
    template_id: Optional[int] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class TripInstanceCreate(TripInstanceBase):
    pass


class TripInstanceRead(TripInstanceBase):
    id: int
    tenant_id: int
    model_config = ConfigDict(from_attributes=True)
