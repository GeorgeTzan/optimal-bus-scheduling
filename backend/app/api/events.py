import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User
from app.domain.identity.permissions import require_permission, PERMISSIONS
from app.domain.identity.models import AuthSession, Membership
from app.domain.events.outbox import OutboxService


router = APIRouter(tags=["events"])


@router.get("/events")
async def sse_events(
    request: Request,
    cursor: int = Query(default=0, ge=0),
    once: bool = Query(default=False),
    current_user: User = Depends(require_permission('optimization.read')),
    db: Session = Depends(get_db),
):
    outbox = OutboxService(db)
    tenant_id = current_user.ktel_id
    user_id = current_user.id
    session_id = current_user.session_id

    async def event_generator():
        current_cursor = cursor
        # Initial heartbeat
        yield ": heartbeat\n\n"

        while True:
            # End each polling transaction: revocation and role changes must be visible,
            # and an idle browser must not retain a database transaction/connection.
            db.rollback()
            member = (db.query(Membership.role).join(AuthSession, AuthSession.membership_id == Membership.id)
                .join(User, User.id == Membership.user_id)
                .filter(AuthSession.id == session_id, AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None), AuthSession.expires_at > datetime.now(timezone.utc),
                    Membership.is_active.is_(True), User.is_active.is_(True)).first())
            if member is None or 'optimization.read' not in PERMISSIONS.get(member.role,set()):
                db.rollback()
                break
            events = outbox.get_events_after(tenant_id=tenant_id, cursor=current_cursor, limit=50)
            frames = [(event.id, event.event_type, json.dumps({**event.payload, "job_id": event.job_id})) for event in events]
            db.rollback()
            for identifier, event_type, data_str in frames:
                current_cursor = identifier
                yield f"id: {identifier}\nevent: {event_type}\ndata: {data_str}\n\n"

            if once:
                break

            if await request.is_disconnected():
                break

            await asyncio.sleep(1.0)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
