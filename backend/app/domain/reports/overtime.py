from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from app.domain.scheduling.driver_duties import current_publications
from app.domain.workforce.models import WorkforceDriver
from app.domain.workrules import service
from app.domain.workrules.loader import _known_from, published_duty_facts

CLOSE = 0.8


def _month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _share(amount: int, limit: int) -> float:
    return amount / limit if limit > 0 else float(amount > 0)


def _status(share: float) -> str:
    return "reached" if share >= 1 else "close" if share >= CLOSE else "within"


def _projection(used: int, earned: int, limit: int, as_of: date, start: date) -> str | None:
    if used >= limit or earned <= 0 or start > as_of:
        return None
    pace = earned / ((as_of - start).days + 1)
    for month in range(as_of.month, 13):
        if used + pace * (_month_end(date(as_of.year, month, 1)) - as_of).days >= limit:
            return f"{as_of.year}-{month:02d}"
    return None


def overtime_report(db, tenant_id: int, month: date, today: date, found: dict | None = None) -> dict:
    year_start, month_end = date(month.year, 1, 1), _month_end(month)
    as_of = min(month_end, today)
    policy = service.company_policy(db, tenant_id)
    limit, absolute_limit = policy.value("overtime_year"), policy.value("overtime_year_absolute")
    known_from = _known_from(db, tenant_id, month_end)
    timelines, facts = published_duty_facts(db, tenant_id, year_start, month_end)
    if found is None:
        found = current_publications(db, tenant_id, year_start, month_end)
    published = {date.fromisoformat(day) for day in found}
    earlier = {day.month for day in published if day < month and _month_end(day) < today}
    drivers = db.query(WorkforceDriver).filter(WorkforceDriver.tenant_id == tenant_id).order_by(WorkforceDriver.code).all()
    cap, monthly = [], []
    for driver in drivers:
        key = str(driver.id)
        baseline = timelines[key].baseline
        if baseline and baseline.as_of > as_of:
            baseline = None
        parts = facts[key]
        counted = [(d, f) for d, f in parts if not (baseline and d.service_date <= baseline.as_of)]
        carried = baseline.overtime_minutes if baseline and baseline.as_of.year == month.year else 0
        earned = sum(f.overtime_minutes for d, f in counted if not d.emergency and d.service_date <= as_of)
        used = carried + earned
        planned = sum(f.overtime_minutes for d, f in counted if not d.emergency and d.service_date > as_of)
        emergency = sum(f.overtime_minutes for d, f in counted if d.emergency)
        identity = {"driver_id": driver.id, "code": driver.code, "name": f"{driver.first_name} {driver.last_name}"}
        if driver.is_active or used + planned + emergency > 0:
            start = max(year_start, known_from, baseline.as_of + timedelta(days=1) if baseline else year_start)
            cap.append({
                **identity,
                "active": bool(driver.is_active),
                "used": used,
                "planned": planned,
                "remaining": max(0, limit - used - planned),
                "emergency": emergency,
                "absolute_total": used + planned + emergency,
                "status": _status(_share(used + planned, limit)),
                "history_complete": known_from <= year_start or bool(baseline and baseline.as_of.year >= month.year - 1),
                "projection_month": _projection(used, earned, limit, as_of, start),
            })
        inside = [(d, f) for d, f in parts if d.service_date >= month]
        if inside:
            per_month: dict[int, int] = defaultdict(int)
            for d, f in parts:
                per_month[d.service_date.month] += f.overtime_minutes
            monthly.append({
                **identity,
                "overtime": sum(f.overtime_minutes for _, f in inside),
                "work": sum(f.work_minutes for _, f in inside),
                "days": len({d.service_date for d, _ in inside}),
                "year_average": round(sum(per_month[m] for m in earlier) / len(earlier)) if earlier else None,
            })
    cap.sort(key=lambda row: _share(row["used"] + row["planned"], limit), reverse=True)
    monthly.sort(key=lambda row: row["overtime"], reverse=True)
    return {
        "as_of": as_of.isoformat(),
        "known_from": known_from.isoformat(),
        "limit": limit,
        "absolute_limit": absolute_limit,
        "cap": cap,
        "monthly": monthly,
        "published_days": sum(1 for day in published if day >= month),
    }
