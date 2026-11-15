from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from app.domain.imports.catalog import ref_key, ref_row
from db.models import KTEL

PROFILE_KEYS = ("overnight_allowed", "split_shift_allowed", "must_return_to_base")
BASELINE_KEYS = (
    "baseline_as_of",
    "baseline_overtime_hours",
    "baseline_last_duty_end",
    "baseline_last_weekly_rest_end",
    "baseline_last_weekly_rest_at_base",
    "baseline_owed_rest_hours",
)
WORK_FIELDS = frozenset(PROFILE_KEYS + BASELINE_KEYS)
PROFILE_DEFAULTS = {"overnight_allowed": True, "split_shift_allowed": True, "must_return_to_base": False}
DEFAULT_ZONE = "Europe/Athens"
REFUSALS = {
    "baseline_locked": (
        "A schedule is already published for this driver on or after the baseline date. Leave the baseline unchanged.",
        "Υπάρχει ήδη δημοσιευμένο πρόγραμμα για τον οδηγό την ημερομηνία αρχικού ιστορικού ή μετά από αυτήν. Αφήστε το ιστορικό ως έχει.",
    ),
    "baseline_as_of_not_past": (
        "The baseline date must be before today.",
        "Η ημερομηνία αρχικού ιστορικού πρέπει να είναι πριν από σήμερα.",
    ),
}


def tenant_zone(planner):
    if not hasattr(planner, "zone"):
        name = planner.db.query(KTEL.timezone).filter_by(id=planner.batch.tenant_id).scalar()
        planner.zone = ZoneInfo(name or DEFAULT_ZONE)
    return planner.zone


def utc_instant(value, zone):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc)
    if parsed.replace(tzinfo=zone, fold=0).utcoffset() != parsed.replace(tzinfo=zone, fold=1).utcoffset():
        return None
    return parsed.replace(tzinfo=zone).astimezone(timezone.utc)


def stored_instant(value):
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def plan_driver_work(planner, row):
    from app.domain.workrules.service import baseline_refusal

    values = row.values
    if not WORK_FIELDS.intersection(values):
        return
    target = row.plan["target"]
    driver_id = target["id"] if target else None
    profile, baseline, _ = planner.catalog.driver_work(driver_id)
    work = {}
    changed = []
    current = {key: getattr(profile, key) if profile else default for key, default in PROFILE_DEFAULTS.items()}
    given = {key: values[key] for key in PROFILE_KEYS if key in values}
    moved = [key for key, value in given.items() if value != current[key]]
    if moved:
        work["profile"] = {**current, **given}
        changed += moved
    if any(key in values for key in BASELINE_KEYS):
        zone = tenant_zone(planner)
        as_of = values.get("baseline_as_of") or (baseline.as_of.isoformat() if baseline else None)
        if as_of is None:
            planner.error(
                row,
                "baseline_as_of_required",
                "Enter the baseline date. It is required when baseline values are given for a driver without a saved baseline.",
                "Συμπληρώστε την ημερομηνία αρχικού ιστορικού. Απαιτείται όταν δίνονται αρχικές τιμές για οδηγό χωρίς αποθηκευμένο ιστορικό.",
                "baseline_as_of",
            )
            return
        merged = {
            "as_of": as_of,
            "overtime_minutes": baseline.overtime_minutes if baseline else 0,
            "last_duty_end": stored_instant(baseline.last_duty_end) if baseline else None,
            "last_weekly_rest_end": stored_instant(baseline.last_weekly_rest_end) if baseline else None,
            "last_weekly_rest_at_base": baseline.last_weekly_rest_at_base if baseline else False,
            "owed_rest_minutes": baseline.owed_rest_minutes if baseline else 0,
        }
        columns = {
            "as_of": "baseline_as_of",
            "overtime_minutes": "baseline_overtime_hours",
            "last_duty_end": "baseline_last_duty_end",
            "last_weekly_rest_end": "baseline_last_weekly_rest_end",
            "last_weekly_rest_at_base": "baseline_last_weekly_rest_at_base",
            "owed_rest_minutes": "baseline_owed_rest_hours",
        }
        before = dict(merged)
        for key in ("last_duty_end", "last_weekly_rest_end"):
            column = columns[key]
            if column in values:
                instant = utc_instant(values[column], zone)
                if instant is None:
                    planner.error(
                        row,
                        "ambiguous_local_time",
                        "This local time does not exist or occurs twice because of a clock change. Add the UTC offset, for example +03:00.",
                        "Η τοπική ώρα δεν υπάρχει ή εμφανίζεται δύο φορές λόγω αλλαγής ώρας. Προσθέστε μετατόπιση UTC, π.χ. +03:00.",
                        column,
                    )
                    return
                merged[key] = instant
        if "baseline_overtime_hours" in values:
            merged["overtime_minutes"] = round(values["baseline_overtime_hours"] * 60)
        if "baseline_owed_rest_hours" in values:
            merged["owed_rest_minutes"] = round(values["baseline_owed_rest_hours"] * 60)
        if "baseline_last_weekly_rest_at_base" in values:
            merged["last_weekly_rest_at_base"] = values["baseline_last_weekly_rest_at_base"]
        moved = [
            columns[key]
            for key in merged
            if columns[key] in values and merged[key] != before[key]
        ]
        if baseline is None:
            moved = [column for column in columns.values() if column in values]
        if moved:
            refusal = baseline_refusal(
                planner.db, planner.batch.tenant_id, driver_id, date.fromisoformat(as_of), baseline.as_of if baseline else None
            )
            if refusal:
                planner.error(row, refusal, *REFUSALS[refusal], "baseline_as_of")
                return
            work["baseline"] = {
                key: value.isoformat() if isinstance(value, datetime) else value for key, value in merged.items()
            }
            changed += moved
    row.plan["work"] = work
    row.plan["work_changed"] = changed


def apply_driver_work(service, row, driver):
    from app.domain.workrules.schemas import DriverBaselineUpdate, DriverProfileUpdate
    from app.domain.workrules.service import baseline_view, profile_view, save_baseline, save_profile

    work = row.plan.get("work")
    if not work:
        return
    user = SimpleNamespace(ktel_id=service.tenant_id, id=service.actor_id)
    if "profile" in work:
        view = profile_view(service.db, service.tenant_id, driver.id)
        save_profile(
            service.db,
            user,
            driver.id,
            DriverProfileUpdate(
                expected_version=view["version"],
                preferred_route_ids=view["preferred_route_ids"],
                forbidden_route_ids=view["forbidden_route_ids"],
                **work["profile"],
            ),
        )
    if "baseline" in work:
        view = baseline_view(service.db, service.tenant_id, driver.id)
        save_baseline(
            service.db, user, driver.id, DriverBaselineUpdate(expected_version=view["version"], **work["baseline"])
        )


def saved_station(planner, row, code, field):
    target = planner.catalog.alias("stations", "code:" + code) or planner.catalog.code("stations", code)
    if target is None:
        planner.error(
            row,
            "unknown_reference",
            "Choose a saved station reference.",
            "Επιλέξτε αποθηκευμένο κωδικό σταθμού.",
            field,
        )
    return target


def plan_route_rule(planner, row):
    values = row.values
    row.plan.update(target=None, candidates=[], before={}, changed_fields=[], aliases=[])
    if row.plan["issues"]:
        return
    if bool(values.get("driver_code")) == bool(values.get("vehicle_code")):
        planner.error(
            row,
            "rule_subject",
            "Enter either a driver reference or a vehicle reference.",
            "Συμπληρώστε είτε κωδικό οδηγού είτε κωδικό οχήματος.",
            "driver_code",
        )
        return
    kind, field = ("drivers", "driver_code") if values.get("driver_code") else ("vehicles", "vehicle_code")
    ref = planner.record_ref(row, kind, values[field], field)
    if ref is None:
        return
    if not planner.active(ref):
        planner.error(
            row,
            "inactive_reference",
            "Choose an active related record, or correct its row first.",
            "Επιλέξτε ενεργή σχετική εγγραφή ή διορθώστε πρώτα τη γραμμή της.",
            field,
        )
        return
    rule = values["rule"]
    if kind == "vehicles" and rule != "forbid":
        planner.error(
            row,
            "vehicle_rule_forbid_only",
            "Vehicles can only be forbidden from a route.",
            "Τα οχήματα μπορούν μόνο να αποκλειστούν από διαδρομή.",
            "rule",
        )
        return
    origin = saved_station(planner, row, values["origin_station_code"], "origin_station_code")
    destination = saved_station(planner, row, values["destination_station_code"], "destination_station_code")
    if origin is None or destination is None:
        return
    routes = planner.catalog.routes_between(origin.id, destination.id)
    if not routes:
        planner.error(
            row,
            "unknown_route",
            "No saved route runs between these stations. Import the timetable first.",
            "Δεν υπάρχει αποθηκευμένη διαδρομή μεταξύ των σταθμών. Εισαγάγετε πρώτα το δρομολόγιο.",
            "destination_station_code",
        )
        return
    route_ids = [route.id for route in routes]
    existing = ref.get("id")
    if kind == "drivers":
        current = planner.catalog.driver_work(existing)[2]
        states = [current.get(route_id) for route_id in route_ids]
        done = all(state == rule for state in states)
        fresh = all(state is None for state in states)
    else:
        current = planner.catalog.vehicle_rules(existing)
        done = all(route_id in current for route_id in route_ids)
        fresh = not any(route_id in current for route_id in route_ids)
    seen = planner.rule_seen.setdefault(ref_key(ref), {})
    for route_id in route_ids:
        previous = seen.get(route_id)
        if previous and previous[0] != rule:
            for member in (previous[1], row):
                planner.error(
                    member,
                    "route_both_preferred_and_forbidden",
                    "A route cannot be both preferred and forbidden for one driver.",
                    "Μια διαδρομή δεν μπορεί να είναι ταυτόχρονα προτιμώμενη και απαγορευμένη για τον ίδιο οδηγό.",
                    "rule",
                )
        else:
            seen[route_id] = (rule, row)
    row.plan.update(
        payload={"rule": rule, "route_ids": route_ids, "subject": kind},
        relations={("driver_id" if kind == "drivers" else "vehicle_id"): ref},
        ref=ref_row("route_rules", row.id),
        action="unchanged" if done else "new" if fresh else "update",
        changed_fields=[] if done else ["rule"],
    )


def apply_route_rule(service, row, payload, planner, saved):
    from app.domain.workrules.schemas import DriverProfileUpdate, VehicleRoutesUpdate
    from app.domain.workrules.service import profile_view, save_profile, save_vehicle_routes, vehicle_routes_view

    plan = row.plan
    column = "driver_id" if payload["subject"] == "drivers" else "vehicle_id"
    subject = service.resolve(plan["relations"][column], saved, planner)
    if plan["action"] == "unchanged":
        return subject
    user = SimpleNamespace(ktel_id=service.tenant_id, id=service.actor_id)
    if column == "driver_id":
        view = profile_view(service.db, service.tenant_id, subject.id)
        preferred = set(view["preferred_route_ids"]) - set(payload["route_ids"])
        forbidden = set(view["forbidden_route_ids"]) - set(payload["route_ids"])
        (preferred if payload["rule"] == "prefer" else forbidden).update(payload["route_ids"])
        save_profile(
            service.db,
            user,
            subject.id,
            DriverProfileUpdate(
                expected_version=view["version"],
                overnight_allowed=view["overnight_allowed"],
                split_shift_allowed=view["split_shift_allowed"],
                must_return_to_base=view["must_return_to_base"],
                preferred_route_ids=sorted(preferred),
                forbidden_route_ids=sorted(forbidden),
            ),
        )
    else:
        view = vehicle_routes_view(service.db, service.tenant_id, subject.id)
        save_vehicle_routes(
            service.db,
            user,
            subject.id,
            VehicleRoutesUpdate(route_ids=sorted({*view["route_ids"], *payload["route_ids"]})),
        )
    return subject
