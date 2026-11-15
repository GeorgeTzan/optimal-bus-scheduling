import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy.orm import joinedload
from fastapi.encoders import jsonable_encoder
from app.domain.fleet.models import Vehicle
from app.domain.office.audit import lock_organization, office_record
from app.domain.scheduling.driver_duties import current_publications
from app.domain.scheduling.models import RevisionAssignment
from app.domain.timetables.models import Route
from app.domain.workforce.models import WorkforceDriver
from app.domain.workrules import legal
from app.domain.workrules.models import CompanyWorkRules, DriverRouteRule, DriverWorkBaseline, DriverWorkProfile, VehicleRouteRule
from app.domain.workrules.policy import LooserThanLawError, build_policy
from db.models import KTEL


def stale(entity):
    return HTTPException(409, {'code': 'stale_version', 'message': f'This {entity} changed. Refresh before saving.'})


def invalid(code, message, **extra):
    return HTTPException(422, {'code': code, 'message': message, **extra})


def record(db, user, entity, payload, response):
    office_record(db, user.ktel_id, user.id, str(uuid.uuid4()), entity, 'update', jsonable_encoder(payload), jsonable_encoder(response))


def company_policy(db, tenant_id):
    row = db.query(CompanyWorkRules).filter_by(tenant_id=tenant_id).first()
    return build_policy(row.overrides, row.warning_rules, row.version) if row else build_policy({}, [], 0)


def company_view(db, tenant_id):
    policy = company_policy(db, tenant_id)
    return {'legal_version': legal.LEGAL_RULES_VERSION, 'company_version': policy.company_version,
            'limits': [{'rule_id': rule_id, 'legal': limit.value, 'value': policy.value(rule_id), 'direction': limit.direction, 'source': limit.source}
                       for rule_id, limit in legal.LEGAL_LIMITS.items()],
            'warning_rules': sorted(policy.warning_rules), 'warning_catalogue': sorted(legal.WARNING_RULES)}


def save_company(db, user, request):
    unknown = sorted(set(request.overrides) - set(legal.LEGAL_LIMITS))
    if unknown:
        raise invalid('unknown_rule', 'This rule does not exist.', rule_id=unknown[0])
    try:
        policy = build_policy(request.overrides, request.warning_rules, request.expected_version)
    except LooserThanLawError as error:
        raise invalid('looser_than_law', 'A company rule cannot be looser than the law.', rule_id=error.rule_id, legal=error.legal) from None
    except KeyError as error:
        raise invalid('unknown_warning_rule', 'This warning rule does not exist.', rule_id=error.args[0]) from None
    lock_organization(db, user.ktel_id)
    row = db.query(CompanyWorkRules).filter_by(tenant_id=user.ktel_id).populate_existing().first()
    current = row.version if row else 0
    if current != request.expected_version:
        raise stale('rule set')
    values = {key: value for key, value in request.overrides.items() if value != legal.LEGAL_LIMITS[key].value}
    if row is None:
        row = CompanyWorkRules(tenant_id=user.ktel_id, version=1)
        db.add(row)
    else:
        row.version += 1
    row.overrides = values
    row.warning_rules = sorted(policy.warning_rules)
    row.updated_by = user.id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    result = company_view(db, user.ktel_id)
    record(db, user, 'work_rules', {'overrides': values, 'warning_rules': row.warning_rules, 'expected_version': request.expected_version}, result)
    return result


def driver(db, tenant_id, driver_id):
    row = db.query(WorkforceDriver).filter_by(tenant_id=tenant_id, id=driver_id).first()
    if row is None:
        raise HTTPException(404, 'Record not found in your organization.')
    return row


def profile_view(db, tenant_id, driver_id):
    row = db.query(DriverWorkProfile).filter_by(tenant_id=tenant_id, driver_id=driver_id).first()
    rules = db.query(DriverRouteRule).filter_by(tenant_id=tenant_id, driver_id=driver_id).order_by(DriverRouteRule.route_id).all()
    return {'driver_id': driver_id, 'version': row.version if row else 0,
            'overnight_allowed': row.overnight_allowed if row else True,
            'split_shift_allowed': row.split_shift_allowed if row else True,
            'must_return_to_base': row.must_return_to_base if row else False,
            'preferred_route_ids': [rule.route_id for rule in rules if rule.kind == 'prefer'],
            'forbidden_route_ids': [rule.route_id for rule in rules if rule.kind == 'forbid']}


def routes_view(db, tenant_id):
    rows = db.query(Route).options(joinedload(Route.origin), joinedload(Route.destination)).filter_by(tenant_id=tenant_id).order_by(Route.id).all()
    return {'routes': [{'id': row.id, 'service_type': row.service_type, 'distance_km': row.distance_km,
                        'origin': {'code': row.origin.code, 'name_el': row.origin.name_el, 'name_en': row.origin.name_en},
                        'destination': {'code': row.destination.code, 'name_el': row.destination.name_el, 'name_en': row.destination.name_en}}
                       for row in rows]}


def known_routes(db, tenant_id, route_ids):
    wanted = set(route_ids)
    found = {row_id for (row_id,) in db.query(Route.id).filter(Route.tenant_id == tenant_id, Route.id.in_(wanted)).all()} if wanted else set()
    if found != wanted:
        raise invalid('unknown_route', 'Choose routes from your organization.')


def save_profile(db, user, driver_id, request):
    driver(db, user.ktel_id, driver_id)
    if set(request.preferred_route_ids) & set(request.forbidden_route_ids):
        raise invalid('route_both_preferred_and_forbidden', 'A route cannot be both preferred and forbidden.')
    known_routes(db, user.ktel_id, [*request.preferred_route_ids, *request.forbidden_route_ids])
    lock_organization(db, user.ktel_id)
    row = db.query(DriverWorkProfile).filter_by(tenant_id=user.ktel_id, driver_id=driver_id).populate_existing().first()
    if (row.version if row else 0) != request.expected_version:
        raise stale('driver profile')
    if row is None:
        row = DriverWorkProfile(tenant_id=user.ktel_id, driver_id=driver_id, version=1)
        db.add(row)
    else:
        row.version += 1
    row.overnight_allowed = request.overnight_allowed
    row.split_shift_allowed = request.split_shift_allowed
    row.must_return_to_base = request.must_return_to_base
    db.query(DriverRouteRule).filter_by(tenant_id=user.ktel_id, driver_id=driver_id).delete()
    db.flush()
    for kind, route_ids in (('prefer', request.preferred_route_ids), ('forbid', request.forbidden_route_ids)):
        for route_id in sorted(set(route_ids)):
            db.add(DriverRouteRule(tenant_id=user.ktel_id, driver_id=driver_id, route_id=route_id, kind=kind))
    db.flush()
    result = profile_view(db, user.ktel_id, driver_id)
    record(db, user, 'driver_work_profile', {'driver_id': driver_id, **request.model_dump()}, result)
    return result


def baseline_view(db, tenant_id, driver_id):
    row = db.query(DriverWorkBaseline).filter_by(tenant_id=tenant_id, driver_id=driver_id).first()
    if row is None:
        return {'driver_id': driver_id, 'version': 0, 'as_of': None, 'overtime_minutes': 0, 'last_duty_end': None,
                'last_weekly_rest_end': None, 'last_weekly_rest_at_base': False, 'owed_rest_minutes': 0}
    return {'driver_id': driver_id, 'version': row.version, 'as_of': row.as_of, 'overtime_minutes': row.overtime_minutes,
            'last_duty_end': row.last_duty_end, 'last_weekly_rest_end': row.last_weekly_rest_end,
            'last_weekly_rest_at_base': row.last_weekly_rest_at_base, 'owed_rest_minutes': row.owed_rest_minutes}


def published_since(db, tenant_id, driver_id, day: date) -> bool:
    for _, revision, snapshot in current_publications(db, tenant_id, day, date.max).values():
        crews = {item['resource_id'] for item in snapshot.problem_data['resources'] if str(item['driver_id']) == str(driver_id)}
        if crews and db.query(RevisionAssignment.id).filter(RevisionAssignment.tenant_id == tenant_id, RevisionAssignment.revision_id == revision.revision_id,
                                                          RevisionAssignment.resource_id.in_(crews), RevisionAssignment.is_cancelled.is_(False)).first():
            return True
    return False


def baseline_refusal(db, tenant_id, driver_id, as_of: date, stored: date | None) -> str | None:
    zone = ZoneInfo(db.query(KTEL.timezone).filter_by(id=tenant_id).scalar() or 'Europe/Athens')
    if as_of >= datetime.now(zone).date():
        return 'baseline_as_of_not_past'
    if driver_id is not None and published_since(db, tenant_id, driver_id, min(as_of, stored or as_of)):
        return 'baseline_locked'
    return None


def save_baseline(db, user, driver_id, request):
    driver(db, user.ktel_id, driver_id)
    lock_organization(db, user.ktel_id)
    row = db.query(DriverWorkBaseline).filter_by(tenant_id=user.ktel_id, driver_id=driver_id).populate_existing().first()
    if (row.version if row else 0) != request.expected_version:
        raise stale('baseline')
    refusal = baseline_refusal(db, user.ktel_id, driver_id, request.as_of, row.as_of if row else None)
    if refusal == 'baseline_as_of_not_past':
        raise invalid(refusal, 'The baseline date must be before today.')
    if refusal:
        raise HTTPException(409, {'code': refusal, 'message': 'A schedule is already published for this driver on or after the baseline date.'})
    if row is None:
        row = DriverWorkBaseline(tenant_id=user.ktel_id, driver_id=driver_id, version=1)
        db.add(row)
    else:
        row.version += 1
    for key in ('as_of', 'overtime_minutes', 'last_duty_end', 'last_weekly_rest_end', 'last_weekly_rest_at_base', 'owed_rest_minutes'):
        setattr(row, key, getattr(request, key))
    row.updated_by = user.id
    db.flush()
    result = baseline_view(db, user.ktel_id, driver_id)
    record(db, user, 'driver_work_baseline', {'driver_id': driver_id, **request.model_dump()}, result)
    return result


def vehicle(db, tenant_id, vehicle_id):
    row = db.query(Vehicle).filter_by(tenant_id=tenant_id, id=vehicle_id).first()
    if row is None:
        raise HTTPException(404, 'Record not found in your organization.')
    return row


def vehicle_routes_view(db, tenant_id, vehicle_id):
    rows = db.query(VehicleRouteRule).filter_by(tenant_id=tenant_id, vehicle_id=vehicle_id).order_by(VehicleRouteRule.route_id).all()
    return {'vehicle_id': vehicle_id, 'route_ids': [row.route_id for row in rows]}


def save_vehicle_routes(db, user, vehicle_id, request):
    vehicle(db, user.ktel_id, vehicle_id)
    known_routes(db, user.ktel_id, request.route_ids)
    lock_organization(db, user.ktel_id)
    db.query(VehicleRouteRule).filter_by(tenant_id=user.ktel_id, vehicle_id=vehicle_id).delete()
    db.flush()
    for route_id in sorted(set(request.route_ids)):
        db.add(VehicleRouteRule(tenant_id=user.ktel_id, vehicle_id=vehicle_id, route_id=route_id))
    db.flush()
    result = vehicle_routes_view(db, user.ktel_id, vehicle_id)
    record(db, user, 'vehicle_route_rules', {'vehicle_id': vehicle_id, 'route_ids': sorted(set(request.route_ids))}, result)
    return result
