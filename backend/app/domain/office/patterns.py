"""Weekly working patterns: the routine basis for who can work."""
from fastapi import HTTPException
from app.domain.office.availability import require_drivers
from app.domain.office.models import DriverWorkingPattern


def save_patterns(db, user, items) -> list[DriverWorkingPattern]:
    tenant_id, actor_id = user.ktel_id, user.id
    drivers = require_drivers(db, tenant_id, {item.driver_id for item in items})
    rows = []
    for item in items:
        if item.status == 'active' and not drivers[item.driver_id].is_active:
            raise HTTPException(409, {'code': 'driver_archived', 'message': 'This driver is archived.'})
        values = item.model_dump(exclude={'pattern_id', 'expected_version', 'driver_id'})
        if item.pattern_id is None:
            row = DriverWorkingPattern(tenant_id=tenant_id, driver_id=item.driver_id, recorded_by=actor_id, **values)
            db.add(row)
        else:
            row = db.query(DriverWorkingPattern).filter_by(tenant_id=tenant_id, id=item.pattern_id).populate_existing().with_for_update().first()
            if row is None:
                raise HTTPException(404, 'Pattern not found')
            if row.driver_id != item.driver_id:
                raise HTTPException(422, 'A pattern cannot move to another driver.')
            if row.version != item.expected_version:
                raise HTTPException(409, {'code': 'version_conflict', 'message': 'This pattern changed. Refresh before editing.'})
            for name, value in values.items():
                setattr(row, name, value)
            row.recorded_by, row.version = actor_id, row.version + 1
        rows.append(row)
    db.flush()
    return rows


def retire_pattern(db, user, pattern_id: int, expected_version: int) -> DriverWorkingPattern:
    row = db.query(DriverWorkingPattern).filter_by(tenant_id=user.ktel_id, id=pattern_id).populate_existing().with_for_update().first()
    if row is None:
        raise HTTPException(404, 'Pattern not found')
    if row.version != expected_version or row.status != 'active':
        raise HTTPException(409, {'code': 'version_conflict', 'message': 'This pattern changed. Refresh before editing.'})
    row.status, row.recorded_by, row.version = 'retired', user.id, row.version + 1
    db.flush()
    return row
