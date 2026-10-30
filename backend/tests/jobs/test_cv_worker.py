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


def test_real_cv_worker_persists_candidates_and_progress_without_browser():
    from app.domain.jobs.worker import work_once
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    problem = SolverProblem('snap', '1', date(2026,10,30),
        tuple(TripSnapshot(f'T{i}', 'A', 'A', 300+i*40, 325+i*40, 25) for i in range(6)),
        tuple(ResourceSnapshot(f'R{i}',f'D{i}',f'B{i}','A') for i in range(6)), (), stations=('A',))
    with factory() as db:
        db.add(KTEL(id=1,name='Worker tenant'));db.flush()
        period=SchedulingPeriod(tenant_id=1,name='Test',start_date=date(2026,10,30),end_date=date(2026,10,30))
        db.add(period);db.flush()
        db.add(ScheduleRevision(revision_id='snap',tenant_id=1,period_id=period.id,author='1'));db.flush()
        db.add(RevisionSnapshot(revision_id='snap',tenant_id=1,problem_data=encode_problem(problem),source_data={}))
        db.commit()
        jid=JobRepository(db).enqueue_job(1,'snap',config={'seed':42,'iterations':2,'time_limit_seconds':15,'cp_sat_workers':1}).job_id
    assert not work_once(factory, tenant_id=2, worker_id='worker')
    assert work_once(factory, tenant_id=1, worker_id='worker')
    with factory() as db:
        job=db.query(Job).filter_by(job_id=jid).one()
        assert job.status=='completed', job.error_message
        assert job.progress_pct==100
        assert len(job.result_data['candidates']) == 2
        assert job.result_data['candidates'][-1]['assignments']
        assert job.result_data['candidates'][-1]['verification']['valid']
        events=db.query(OutboxEvent).filter_by(job_id=jid).all()
        assert any(e.event_type=='job.progress' for e in events)
        assert any(e.event_type=='job.candidate' for e in events)
        assert events[-1].event_type=='job.completed'
        assert all(e.payload['job_id']==jid for e in events)
        assert db.query(ScheduleRevision).one().status=='draft'


def test_worker_bootstraps_tenant_models_in_fresh_interpreter():
    import subprocess, sys
    result = subprocess.run([sys.executable, '-c',
        'import app.domain.jobs.worker; from db.database import Base; '
        '[fk.column for table in Base.metadata.tables.values() for fk in table.foreign_keys]'],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
