from typing import List, Optional
from sqlalchemy.orm import Session
from app.domain.workforce.models import WorkforceDriver, DriverQualification
from app.domain.workforce.schemas import DriverCreate, DriverUpdate, DriverQualificationCreate


class WorkforceService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def list_drivers(self, active_only: bool = False) -> List[WorkforceDriver]:
        q = self.db.query(WorkforceDriver).filter(WorkforceDriver.tenant_id == self.tenant_id)
        if active_only:
            q = q.filter(WorkforceDriver.is_active == True)
        return q.all()

    def get_driver(self, driver_id: int) -> Optional[WorkforceDriver]:
        return self.db.query(WorkforceDriver).filter(
            WorkforceDriver.tenant_id == self.tenant_id,
            WorkforceDriver.id == driver_id
        ).first()

    def create_driver(self, data: DriverCreate) -> WorkforceDriver:
        driver = WorkforceDriver(
            tenant_id=self.tenant_id,
            **data.model_dump()
        )
        self.db.add(driver)
        self.db.flush()
        return driver

    def update_driver(self, driver_id: int, data: DriverUpdate) -> Optional[WorkforceDriver]:
        driver = self.get_driver(driver_id)
        if not driver:
            return None
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(driver, k, v)
        self.db.flush()
        return driver

    def add_qualification(self, data: DriverQualificationCreate) -> DriverQualification:
        qual = DriverQualification(
            tenant_id=self.tenant_id,
            **data.model_dump()
        )
        self.db.add(qual)
        self.db.flush()
        return qual
