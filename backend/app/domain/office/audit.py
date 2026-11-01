"""Idempotent, audited office writes. Services flush; the API owns commit."""
import hashlib
import json
from fastapi import HTTPException
from db.models import KTEL
from app.domain.office.models import OfficeAudit


def lock_organization(db, tenant_id: int) -> None:
    """Organization row first, then own rows: the established lock order."""
    db.query(KTEL).filter_by(id=tenant_id).populate_existing().with_for_update().one()


def _digest(actor_id: int, payload: dict) -> str:
    return hashlib.sha256(json.dumps({'actor': actor_id, 'payload': payload}, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def office_replay(db, tenant_id: int, actor_id: int, request_id: str, payload: dict) -> dict | None:
    """Stored response for an exact retry; 409 when the request id is reused with different content. Call under the organization lock."""
    previous = db.query(OfficeAudit).filter_by(tenant_id=tenant_id, request_id=request_id).first()
    if previous is None:
        return None
    if previous.payload_hash != _digest(actor_id, payload):
        raise HTTPException(409, {'code': 'request_changed', 'message': 'This request was already used with different details.'})
    return previous.response_data


def office_record(db, tenant_id: int, actor_id: int, request_id: str, entity: str, action: str, payload: dict, response: dict) -> None:
    """Keep payload and response free of private notes and category."""
    db.add(OfficeAudit(tenant_id=tenant_id, entity=entity, action=action, actor_id=actor_id, request_id=request_id,
                       payload_hash=_digest(actor_id, payload), response_data=response))
    db.flush()
