import hashlib
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from sqlalchemy import func

from app.domain.incidents.operations_models import OperationalEvent, OperationalTripState
from app.domain.reports.coverage import coverage_report, line_days, month_trips
from app.domain.reports.files import pdf_bytes, xlsx_bytes
from app.domain.reports.models import ReportExport
from app.domain.reports.overtime import _month_end, overtime_report
from app.domain.scheduling.driver_duties import current_publications
from app.domain.scheduling.models import Publication
from app.domain.scheduling.snapshots import RevisionSnapshot
from app.domain.workrules.models import DriverWorkBaseline
from app.domain.workrules.service import company_policy
from db.models import KTEL, User

MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def tenant_timezone(db, tenant_id: int) -> str:
    return db.query(KTEL.timezone).filter(KTEL.id == tenant_id).scalar()


def tenant_today(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


def parse_month(value: str, today: date) -> date:
    if not MONTH.fullmatch(value):
        raise HTTPException(422, {"code": "invalid_month", "message": "The month must be written as YYYY-MM."})
    month = date(int(value[:4]), int(value[5:]), 1)
    if month > today.replace(day=1) or month < date(today.year - 2, 1, 1):
        raise HTTPException(422, {"code": "month_out_of_range", "message": "This month is outside the reporting period."})
    return month


def requested_month(db, tenant_id: int, value: str) -> date:
    return parse_month(value, tenant_today(tenant_timezone(db, tenant_id)))


def _delay_log(db, tenant_id: int, first: date, last: date) -> list:
    service_day = RevisionSnapshot.problem_data["service_date"].as_string()
    return list(
        db.query(func.count(OperationalEvent.id), func.max(OperationalEvent.id))
        .join(OperationalTripState, (OperationalTripState.tenant_id == OperationalEvent.tenant_id) & (OperationalTripState.id == OperationalEvent.state_id))
        .join(Publication, (Publication.tenant_id == OperationalTripState.tenant_id) & (Publication.publication_id == OperationalTripState.publication_id))
        .join(RevisionSnapshot, (RevisionSnapshot.tenant_id == Publication.tenant_id) & (RevisionSnapshot.revision_id == Publication.revision_id))
        .filter(
            OperationalEvent.tenant_id == tenant_id,
            OperationalEvent.kind == "delay",
            RevisionSnapshot.source_data["source"].as_string() == "operational",
            service_day.between(first.isoformat(), last.isoformat()),
        )
        .one()
    )


def fingerprint(db, tenant_id: int, month: date, found: dict | None = None) -> str:
    year_start, month_end = date(month.year, 1, 1), _month_end(month)
    if found is None:
        found = current_publications(db, tenant_id, year_start, month_end)
    baselines = db.query(DriverWorkBaseline.driver_id, DriverWorkBaseline.version).filter(DriverWorkBaseline.tenant_id == tenant_id).all()
    parts = [
        sorted(publication.publication_id for publication, _, _ in found.values()),
        company_policy(db, tenant_id).company_version,
        sorted([driver_id, version] for driver_id, version in baselines),
        _delay_log(db, tenant_id, year_start, month_end),
    ]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _build(db, user, month: date) -> tuple[dict, dict, list[dict], str]:
    timezone = tenant_timezone(db, user.ktel_id)
    found = current_publications(db, user.ktel_id, date(month.year, 1, 1), _month_end(month))
    trips = month_trips(db, user.ktel_id, month, found)
    current = fingerprint(db, user.ktel_id, month, found)
    last = (db.query(ReportExport, User)
            .join(User, (User.ktel_id == ReportExport.tenant_id) & (User.id == ReportExport.generated_by))
            .filter(ReportExport.tenant_id == user.ktel_id, ReportExport.month == month)
            .order_by(ReportExport.generated_at.desc(), ReportExport.id.desc()).first())
    report = {
        "month": month.strftime("%Y-%m"),
        "timezone": timezone,
        "overtime": overtime_report(db, user.ktel_id, month, tenant_today(timezone), found),
        "coverage": coverage_report(db, user.ktel_id, month, trips),
        "last_export": {"format": last[0].format, "generated_at": last[0].generated_at.isoformat(), "by": last[1].full_name or last[1].email} if last else None,
        "changed_since_export": bool(last) and last[0].fingerprint != current,
    }
    return report, found, trips, current


def monthly(db, user, month: date) -> dict:
    return _build(db, user, month)[0]


def export(db, user, month: date, format: str, lang: str) -> bytes:
    report, found, trips, current = _build(db, user, month)
    contexts: dict[str, dict[str, int]] = {}
    for row in report["coverage"]:
        row["days"] = line_days(db, user.ktel_id, month, row["line"], trips, contexts) if row["uncovered"] or row["cancelled"] else []
    meta = {
        "organization": db.query(KTEL.name).filter(KTEL.id == user.ktel_id).scalar(),
        "month": report["month"],
        "generated_at": datetime.now(ZoneInfo(report["timezone"])).strftime("%Y-%m-%d %H:%M"),
        "generated_by": user.full_name or user.email,
        "timezone": report["timezone"],
        "published_days": len(found),
        "fingerprint": current[:12],
    }
    content = (xlsx_bytes if format == "xlsx" else pdf_bytes)(report, lang, meta)
    db.add(ReportExport(tenant_id=user.ktel_id, month=month, format=format, generated_by=user.id, fingerprint=current))
    db.commit()
    return content
