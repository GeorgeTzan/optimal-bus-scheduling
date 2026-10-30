"""Freeze tenant-owned operational inputs; outer API owns the transaction."""

from dataclasses import replace
from datetime import date
from uuid import uuid4
from fastapi import HTTPException
from app.domain.identity.tenant_session import set_tenant_scope
from app.domain.timetables.operations import (
    build_operational_snapshot,
    operational_readiness,
)
from app.domain.optimization.adapter import to_cv_problem
from app.domain.scheduling.models import (
    ScheduleRevision,
    SchedulingPeriod,
    RevisionAssignment,
)
from app.domain.scheduling.snapshots import RevisionSnapshot, encode_problem
from db.models import KTEL


def create_operational_revision(db, tenant_id: int, actor_id: int, service_date: date):
    set_tenant_scope(db, tenant_id)
    db.query(KTEL).filter_by(id=tenant_id).with_for_update().one()
    readiness = operational_readiness(db, tenant_id, service_date)
    if not readiness["inputs_ready"]:
        issues = list(readiness["issues"])
        if readiness["missing_transfer_count"]:
            issues.append(
                {
                    "code": "transfers_required",
                    "message": "Add the remaining verified travel times.",
                    "remaining": readiness["missing_transfer_count"],
                }
            )
        raise HTTPException(
            422,
            {
                "code": "day_not_ready",
                "message": "Complete the service-day review before creating a draft.",
                "next_step": "planning",
                "service_date": service_date.isoformat(),
                "issues": issues,
            },
        )
    source = build_operational_snapshot(db, tenant_id, service_date)
    revisions = (
        db.query(ScheduleRevision)
        .join(
            RevisionSnapshot,
            RevisionSnapshot.revision_id == ScheduleRevision.revision_id,
        )
        .filter(
            ScheduleRevision.tenant_id == tenant_id,
            RevisionSnapshot.tenant_id == tenant_id,
            RevisionSnapshot.source_data["source"].as_string() == "operational",
        )
    )
    existing = (
        revisions.filter(
            RevisionSnapshot.source_data["source_hash"].as_string()
            == source.snapshot_hash
        )
        .order_by(ScheduleRevision.created_at.desc(), ScheduleRevision.id.desc())
        .first()
    )
    if existing is not None:
        return existing, False
    parent = (
        revisions.join(
            SchedulingPeriod, SchedulingPeriod.id == ScheduleRevision.period_id
        )
        .filter(
            SchedulingPeriod.tenant_id == tenant_id,
            SchedulingPeriod.start_date == service_date,
            SchedulingPeriod.end_date == service_date,
        )
        .order_by(ScheduleRevision.created_at.desc(), ScheduleRevision.id.desc())
        .first()
    )
    period = (
        db.query(SchedulingPeriod)
        .filter_by(
            tenant_id=tenant_id,
            name=f"Service day {service_date.isoformat()}",
            start_date=service_date,
            end_date=service_date,
        )
        .first()
    )
    if period is None:
        period = SchedulingPeriod(
            tenant_id=tenant_id,
            name=f"Service day {service_date.isoformat()}",
            start_date=service_date,
            end_date=service_date,
        )
        db.add(period)
        db.flush()
    identifier = str(uuid4())
    problem = replace(to_cv_problem(source), problem_id=identifier)
    revision = ScheduleRevision(
        tenant_id=tenant_id,
        revision_id=identifier,
        period_id=period.id,
        parent_revision_id=parent.revision_id if parent else None,
        version=1,
        status="draft",
        author=str(actor_id),
    )
    db.add(revision)
    db.flush()
    db.add(
        RevisionSnapshot(
            tenant_id=tenant_id,
            revision_id=identifier,
            problem_data=encode_problem(problem),
            source_data={**source.source_data, "source_hash": source.snapshot_hash},
        )
    )
    db.add_all(
        [
            RevisionAssignment(
                tenant_id=tenant_id,
                revision_id=identifier,
                trip_id=trip.id,
                resource_id="UNASSIGNED",
                start_minutes=trip.start_minutes,
                end_minutes=trip.end_minutes,
                start_station=trip.start_station,
                end_station=trip.end_station,
                is_locked=False,
            )
            for trip in problem.trips
        ]
    )
    db.flush()
    return revision, True
