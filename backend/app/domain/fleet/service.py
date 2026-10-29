from typing import List, Optional
from sqlalchemy.orm import Session
from app.domain.fleet.models import Vehicle
from app.domain.fleet.schemas import VehicleCreate, VehicleUpdate


class FleetService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def list_vehicles(self, active_only: bool = False) -> List[Vehicle]:
        q = self.db.query(Vehicle).filter(Vehicle.tenant_id == self.tenant_id)
        if active_only:
            q = q.filter(Vehicle.is_active == True)
        return q.all()

    def get_vehicle(self, vehicle_id: int) -> Optional[Vehicle]:
        return self.db.query(Vehicle).filter(
            Vehicle.tenant_id == self.tenant_id,
            Vehicle.id == vehicle_id
        ).first()

    def create_vehicle(self, data: VehicleCreate) -> Vehicle:
        vehicle = Vehicle(
            tenant_id=self.tenant_id,
            **data.model_dump()
        )
        self.db.add(vehicle)
        self.db.flush()
        return vehicle

    def update_vehicle(self, vehicle_id: int, data: VehicleUpdate) -> Optional[Vehicle]:
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return None
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(vehicle, k, v)
        self.db.flush()
        return vehicle
