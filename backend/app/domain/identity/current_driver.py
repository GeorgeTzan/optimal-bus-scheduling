"""The driver is always the one linked to the signed-in session; no caller input selects a driver."""
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from api.deps import get_current_user
from db.database import get_db
from app.domain.identity.models import Membership
from app.domain.workforce.models import WorkforceDriver


@dataclass(frozen=True)
class DriverContext:
    user: object
    driver_id: int


def require_driver_permission(permission: str):
    def dependency(user=Depends(get_current_user), db: Session = Depends(get_db)) -> DriverContext:
        if user.role != 'driver' or permission not in user.permissions:
            raise HTTPException(403, {'code': 'not_a_driver', 'message': 'This area is for drivers.'})
        driver_id = db.query(Membership.driver_id).filter_by(tenant_id=user.ktel_id, id=user.membership_id).scalar()
        if driver_id is None:
            raise HTTPException(403, {'code': 'driver_not_linked', 'message': 'Your sign-in is not linked to a driver record yet. Ask the office to link it.'})
        driver = db.query(WorkforceDriver).filter_by(tenant_id=user.ktel_id, id=driver_id).first()
        if driver is None or not driver.is_active:
            raise HTTPException(403, {'code': 'driver_archived', 'message': 'Your driver record is archived. Ask the office for help.'})
        return DriverContext(user, driver_id)
    return dependency
