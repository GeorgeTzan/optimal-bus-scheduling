from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.domain.timetables.models import Station, Route, ServiceTemplate, TripInstance
from app.domain.timetables.schemas import StationCreate, RouteCreate, ServiceTemplateCreate, TripInstanceCreate


class TimetableService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    # Stations
    def list_stations(self) -> List[Station]:
        return self.db.query(Station).filter(Station.tenant_id == self.tenant_id).all()

    def create_station(self, data: StationCreate) -> Station:
        station = Station(tenant_id=self.tenant_id, **data.model_dump())
        self.db.add(station)
        self.db.flush()
        return station

    # Routes
    def list_routes(self) -> List[Route]:
        return self.db.query(Route).filter(Route.tenant_id == self.tenant_id).all()

    def create_route(self, data: RouteCreate) -> Route:
        route = Route(tenant_id=self.tenant_id, **data.model_dump())
        self.db.add(route)
        self.db.flush()
        return route

    # Templates
    def list_templates(self) -> List[ServiceTemplate]:
        return self.db.query(ServiceTemplate).filter(ServiceTemplate.tenant_id == self.tenant_id).all()

    def create_template(self, data: ServiceTemplateCreate) -> ServiceTemplate:
        template = ServiceTemplate(tenant_id=self.tenant_id, **data.model_dump())
        self.db.add(template)
        self.db.flush()
        return template

    # Trip Instances
    def list_trips(self, service_date: Optional[date] = None) -> List[TripInstance]:
        q = self.db.query(TripInstance).filter(TripInstance.tenant_id == self.tenant_id)
        if service_date:
            q = q.filter(TripInstance.service_date == service_date)
        return q.order_by(TripInstance.start_utc).all()

    def create_trip(self, data: TripInstanceCreate) -> TripInstance:
        trip = TripInstance(tenant_id=self.tenant_id, **data.model_dump())
        self.db.add(trip)
        self.db.flush()
        return trip
