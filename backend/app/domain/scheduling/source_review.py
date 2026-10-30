"""Read-only source checks for unpublished operational snapshots, without materializing trips."""

from datetime import date
from pydantic import ValidationError
from db.models import KTEL
from app.domain.timetables.calendar import (
    CalendarRule,
    CalendarException,
    resolve_service_day,
)
from app.domain.timetables.models import (
    ServiceTemplate,
    ServiceException,
    DailyPairing,
    Station,
    StationTransfer,
    Route,
    ServiceConnection,
)
from app.domain.workforce.models import WorkforceDriver
from app.domain.fleet.models import Vehicle


def source_review_required(db, revision, snapshot):
    source = snapshot.source_data
    if revision.status == "published" or source.get("source") != "operational":
        return False
    versions = source.get("source_versions")
    if (
        not isinstance(versions, dict)
        or source.get("source_schema_version") not in ("ktel-operational-v1", "ktel-operational-v2")
    ):
        return True
    tenant = revision.tenant_id
    zone = db.query(KTEL.timezone).filter(KTEL.id == tenant).scalar()
    if zone != source.get("timezone"):
        return True
    selected = date.fromisoformat(snapshot.problem_data["service_date"])
    exceptions = {
        row.template_id: row
        for row in db.query(ServiceException)
        .filter_by(tenant_id=tenant, service_date=selected)
        .all()
    }
    current_templates = {}
    current_exceptions = {}
    for row in (
        db.query(ServiceTemplate).filter_by(tenant_id=tenant, is_active=True).all()
    ):
        override = exceptions.get(row.id)
        if override and override.action == "cancel":
            continue
        try:
            rule = CalendarRule.model_validate(
                {key: getattr(row, key) for key in CalendarRule.model_fields}
            )
            exception = (
                CalendarException.model_validate(
                    {
                        key: getattr(override, key)
                        for key in CalendarException.model_fields
                    }
                )
                if override
                else None
            )
            if resolve_service_day(rule, selected, zone, exception) is None:
                continue
        except (ValueError, ValidationError):
            return True
        current_templates[str(row.id)] = row.version
        current_exceptions[str(row.id)] = override.version if override else 0
    if current_templates != versions.get(
        "templates"
    ) or current_exceptions != versions.get("exceptions"):
        return True
    template_ids = [int(identifier) for identifier in current_templates]
    links = db.query(ServiceConnection).filter(ServiceConnection.tenant_id == tenant,
        ServiceConnection.is_active.is_(True), ServiceConnection.incoming_template_id.in_(template_ids),
        ServiceConnection.outgoing_template_id.in_(template_ids)).all()
    if {str(link.id): link.version for link in links} != versions.get('connections', {}):
        return True
    current_pairs = {
        str(row.id): row.version
        for row in db.query(DailyPairing)
        .filter_by(tenant_id=tenant, service_date=selected, is_active=True)
        .all()
    }
    if current_pairs != versions.get("pairings"):
        return True
    for kind, model in {
        "drivers": WorkforceDriver,
        "vehicles": Vehicle,
        "stations": Station,
        "transfers": StationTransfer,
        "routes": Route,
    }.items():
        expected = versions.get(kind)
        if not isinstance(expected, dict):
            return True
        ids = [int(identifier) for identifier in expected]
        actual = (
            {
                str(identifier): version
                for identifier, version in db.query(model.id, model.version)
                .filter(model.tenant_id == tenant, model.id.in_(ids))
                .all()
            }
            if ids
            else {}
        )
        if actual != expected:
            return True
    return False
