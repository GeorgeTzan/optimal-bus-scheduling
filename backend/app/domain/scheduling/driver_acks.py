"""Record that a driver acknowledged specific trips of the current publication. Callers hold the organization lock and own the commit."""
from datetime import datetime, timezone
from fastapi import HTTPException
from app.domain.identity.driver_models import DriverAcknowledgment
from app.domain.scheduling import driver_duties as duties_module


def acknowledge(db, user, driver_id: int, publication_id: str, trip_ids: list[str], request_id: str) -> dict:
    """All or nothing. A trip already acknowledged for this publication keeps its first time and is not written again."""
    day = next((item for item in duties_module.driver_duties(db, user.ktel_id, driver_id)['days'] if item['publication_id'] == publication_id), None)
    if day is None:
        raise HTTPException(409, {'code': 'publication_replaced', 'message': 'This schedule was replaced by a newer one or is outside your duty days. Reload to see the current duties.'})
    own = {item['trip_id'] for item in day['duties']}
    if not set(trip_ids) <= own:
        raise HTTPException(409, {'code': 'not_your_duty', 'message': 'One of these trips is not one of your duties.'})
    known = {row.trip_id: row for row in db.query(DriverAcknowledgment).filter_by(tenant_id=user.ktel_id, publication_id=publication_id, driver_id=driver_id)
             .filter(DriverAcknowledgment.trip_id.in_(trip_ids)).all()}
    now = datetime.now(timezone.utc)
    for trip_id in trip_ids:
        if trip_id not in known:
            known[trip_id] = DriverAcknowledgment(tenant_id=user.ktel_id, publication_id=publication_id, revision_id=day['revision_id'], revision_version=day['revision_version'],
                                                  trip_id=trip_id, driver_id=driver_id, acknowledged_by=user.id, acknowledged_at=now, request_id=request_id)
            db.add(known[trip_id])
    db.flush()
    return {'acknowledged': [{'trip_id': trip_id, 'acknowledged_at': known[trip_id].acknowledged_at.astimezone(timezone.utc).isoformat()} for trip_id in trip_ids]}
