from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.database import Base
from db.models import KTEL
from app.domain.scheduling.models import ScheduleRevision, SchedulingPeriod
from app.domain.scheduling.snapshots import RevisionSnapshot, encode_problem
from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot
from app.domain.jobs.models import Job
from app.domain.jobs.repository import JobRepository
from app.domain.events.outbox import OutboxEvent


def snapshot_hash(data):
    import hashlib, json
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def run_worker_job(problem, config):
    from app.domain.jobs.worker import work_once
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(KTEL(id=1,name='Worker tenant'));db.flush()
        period=SchedulingPeriod(tenant_id=1,name='Test',start_date=date(2026,10,30),end_date=date(2026,10,30))
        db.add(period);db.flush()
        db.add(ScheduleRevision(revision_id='snap',tenant_id=1,period_id=period.id,author='1'));db.flush()
        db.add(RevisionSnapshot(revision_id='snap',tenant_id=1,problem_data=encode_problem(problem),source_data={}))
        db.commit()
        jid=JobRepository(db).enqueue_job(1,'snap',config=config).job_id
    assert not work_once(factory, tenant_id=2, worker_id='worker')
    assert work_once(factory, tenant_id=1, worker_id='worker')
    return factory, jid


def six_trip_problem():
    return SolverProblem('snap', '1', date(2026,10,30),
        tuple(TripSnapshot(f'T{i}', 'A', 'A', 300+i*40, 325+i*40, 25) for i in range(6)),
        tuple(ResourceSnapshot(f'R{i}',f'D{i}',f'B{i}','A') for i in range(6)), (), stations=('A',))


def test_real_cv_worker_persists_candidates_and_progress_without_browser():
    problem = six_trip_problem()
    factory, jid = run_worker_job(problem, {'seed':42,'iterations':2,'time_limit_seconds':15,'cp_sat_workers':1})
    with factory() as db:
        job=db.query(Job).filter_by(job_id=jid).one()
        assert job.status=='completed', job.error_message
        assert job.progress_pct==100
        assert len(job.result_data['candidates']) == 2
        assert job.result_data['candidates'][-1]['assignments']
        assert job.result_data['candidates'][-1]['verification']['valid']
        assert job.result_data['candidates'][-1]['snapshot_hash'] == snapshot_hash(encode_problem(problem))
        events=db.query(OutboxEvent).filter_by(job_id=jid).all()
        assert any(e.event_type=='job.progress' for e in events)
        assert any(e.event_type=='job.candidate' for e in events)
        assert events[-1].event_type=='job.completed'
        assert all(e.payload['job_id']==jid for e in events)
        assert db.query(ScheduleRevision).one().status=='draft'


def test_worker_hashes_stored_snapshot_not_budgeted_input():
    from datetime import datetime, timezone
    from app.domain.workrules.loader import WorkContext
    from app.domain.workrules.policy import build_policy
    from app.domain.workrules.timeline import DriverProfile, DriverTimeline
    problem = six_trip_problem()
    profile = DriverProfile('A', True, True, False, frozenset(), frozenset())
    timelines = {f'D{i}': DriverTimeline(f'D{i}', profile, (), None, date(2026,1,1), {}) for i in range(6)}
    work = WorkContext(build_policy({}, [], 0), timelines, frozenset(), date(2026,10,30),
                       datetime(2026,10,29,21,tzinfo=timezone.utc), {})
    config = {'seed':42,'iterations':1,'time_limit_seconds':15,'cp_sat_workers':1,'work_context':work.to_dict()}
    factory, jid = run_worker_job(problem, config)
    with factory() as db:
        job=db.query(Job).filter_by(job_id=jid).one()
        assert job.status=='completed', job.error_message
        assert job.result_data['candidates'][-1]['snapshot_hash'] == snapshot_hash(encode_problem(problem))


def test_worker_bootstraps_tenant_models_in_fresh_interpreter():
    import subprocess, sys
    result = subprocess.run([sys.executable, '-c',
        'import app.domain.jobs.worker; from db.database import Base; '
        '[fk.column for table in Base.metadata.tables.values() for fk in table.foreign_keys]'],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_worker_parent_attaches_work_budgets_before_solving():
    from datetime import datetime, timezone
    from app.domain.jobs.worker import solver_input
    from app.domain.scheduling.snapshots import decode_problem
    from app.domain.workrules.loader import WorkContext
    from app.domain.workrules.policy import build_policy
    from app.domain.workrules.timeline import DriverProfile, DriverTimeline
    problem = SolverProblem('snap', '1', date(2026,10,30), (TripSnapshot('T1', 'A', 'A', 300, 325, 25),),
        (ResourceSnapshot('R1','D1','B1','A'),), (), stations=('A',), transfer_matrix=((0,),))
    profile = DriverProfile('A', True, True, False, frozenset(), frozenset())
    work = WorkContext(build_policy({}, [], 0), {'D1': DriverTimeline('D1', profile, (), None, date(2026,1,1), {})}, frozenset(),
                       date(2026,10,30), datetime(2026,10,29,21,tzinfo=timezone.utc), {})
    data = encode_problem(problem)
    assert solver_input(data, None) == data
    solved = decode_problem(solver_input(data, work.to_dict()))
    assert solved.work_policy == work.policy.to_dict()
    assert [b['driver_id'] for b in solved.driver_budgets] == ['D1']
