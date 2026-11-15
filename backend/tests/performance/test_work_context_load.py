import time
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta

from tests.integration.conftest import postgres_engine, restricted_databases
from tests.integration.test_identity import identity_setup
from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews

PUBLISHED_DAYS = 300
EXTRA_TRIPS = 200
SERVICE_DATE = date(2026, 1, 1) + timedelta(days=PUBLISHED_DAYS + 28)


def clone_publications(db, tenant_id, revision_id, days, stretch=0, filler_trips=EXTRA_TRIPS):
    from app.domain.scheduling.models import Publication, RevisionAssignment, ScheduleRevision
    from app.domain.scheduling.snapshots import RevisionSnapshot
    revision = db.query(ScheduleRevision).filter_by(tenant_id=tenant_id, revision_id=revision_id).one()
    snapshot = db.query(RevisionSnapshot).filter_by(tenant_id=tenant_id, revision_id=revision_id).one()
    publication = db.query(Publication).filter_by(tenant_id=tenant_id, revision_id=revision_id).one()
    rows = db.query(RevisionAssignment).filter_by(tenant_id=tenant_id, revision_id=revision_id).all()
    source_day = date.fromisoformat(snapshot.problem_data['service_date'])
    origin = datetime.fromisoformat(snapshot.source_data['service_day_start_utc'])
    filler = [{**snapshot.problem_data['trips'][0], 'id': f'X{n:04d}'} for n in range(filler_trips)]
    for day in days:
        if day == source_day and not stretch:
            continue
        new_id = str(uuid.uuid4())
        db.add(ScheduleRevision(revision_id=new_id, tenant_id=tenant_id, period_id=revision.period_id, status=revision.status,
                                author=revision.author, version=1))
        db.flush()
        db.add(RevisionSnapshot(revision_id=new_id, tenant_id=tenant_id,
                                problem_data={**snapshot.problem_data, 'service_date': day.isoformat(),
                                              'trips': [*snapshot.problem_data['trips'], *filler]},
                                source_data={**snapshot.source_data, 'service_day_start_utc': (origin + (day - source_day)).isoformat()}))
        db.add(Publication(publication_id=str(uuid.uuid4()), tenant_id=tenant_id, revision_id=new_id,
                           published_by=publication.published_by, verification_report={}))
        for row in rows:
            db.add(RevisionAssignment(tenant_id=tenant_id, revision_id=new_id, trip_id=row.trip_id, resource_id=row.resource_id,
                                      start_minutes=row.start_minutes, end_minutes=row.end_minutes + stretch, start_station=row.start_station,
                                      end_station=row.end_station, is_locked=row.is_locked, is_cancelled=row.is_cancelled))
        for trip in filler:
            db.add(RevisionAssignment(tenant_id=tenant_id, revision_id=new_id, trip_id=trip['id'], resource_id='R_FILLER',
                                      start_minutes=rows[0].start_minutes, end_minutes=rows[0].end_minutes,
                                      start_station=rows[0].start_station, end_station=rows[0].end_station))
    db.flush()


def timed_load(factory, tenant_id, problem):
    from app.domain.workrules.loader import load_work_context
    with factory() as db:
        started = time.perf_counter()
        ctx = load_work_context(db, tenant_id, problem, None)
        return time.perf_counter() - started, ctx


def test_load_work_context_with_a_year_of_publications(identity_setup):
    from app.domain.scheduling.snapshots import decode_problem
    from app.domain.workrules import loader
    client, headers, revision, first, other = customer_with_two_confirmed_crews(identity_setup)
    tenant_id = identity_setup['first'].tenant_id
    factory = identity_setup['owner_factory']
    with factory() as db:
        clone_publications(db, tenant_id, revision['revision_id'], [date(2026, 1, 1) + timedelta(days=n) for n in range(PUBLISHED_DAYS)])
        db.commit()
    problem = replace(decode_problem(revision['problem']), service_date=SERVICE_DATE)
    loader._cache.clear()
    cold, ctx = timed_load(factory, tenant_id, problem)
    warm, again = timed_load(factory, tenant_id, problem)
    assert again.to_dict() == ctx.to_dict()
    assert {t.prior_year for t in ctx.timelines.values()} == {SERVICE_DATE.year}
    assert all(t.prior_overtime == 0 for t in ctx.timelines.values())
    assert warm < 0.5
    with factory() as db:
        clone_publications(db, tenant_id, revision['revision_id'], [date(2026, 3, 2)], stretch=600, filler_trips=0)
        db.commit()
    _, changed = timed_load(factory, tenant_id, problem)
    loader._cache.clear()
    _, fresh = timed_load(factory, tenant_id, problem)
    assert any(t.prior_overtime > 0 for t in changed.timelines.values())
    assert changed.to_dict() == fresh.to_dict()
    assert any(t.prior_overtime > 0 for t in fresh.timelines.values())
