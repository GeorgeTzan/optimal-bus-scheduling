"""Tenant capabilities are evaluated server-side on every request."""
from fastapi import Depends,HTTPException

PERMISSIONS={
    'admin':{'members.manage','organization.manage','resources.read','drivers.write','fleet.write','timetable.write',
             'imports.read','imports.write','schedule.read','schedule.write','schedule.approve','schedule.publish',
             'optimization.read','optimization.run','reports.read','incidents.manage'},
    'dispatcher':{'resources.read','timetable.write','imports.read','imports.write','schedule.read','schedule.write',
                  'schedule.publish','optimization.read','optimization.run','incidents.manage'},
    'fleet_manager':{'resources.read','fleet.write','schedule.read','optimization.read'},
    'driver':{'driver.self.read','driver.self.acknowledge','driver.self.leave','incidents.self.report'},
    'management':{'resources.read','schedule.read','optimization.read','reports.read'},
    'viewer':{'resources.read','schedule.read','optimization.read'},
}


def require_permission(permission):
    from api.deps import get_current_user
    def authorized(user=Depends(get_current_user)):
        if permission not in getattr(user,'permissions',()):
            raise HTTPException(403,'Your organization role does not allow this action')
        return user
    return authorized
