"""Tenant-scoped durable CV consumer. Run independently: python -m app.domain.jobs.worker --tenant-id 1."""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import queue
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker
import db.models  # Register FK targets in the standalone worker interpreter.
import app.domain.scheduling.models
from app.domain.identity.tenant_session import set_tenant_scope
from app.domain.jobs.models import Job
from app.domain.jobs.repository import JobRepository
from app.domain.events.outbox import OutboxEvent
from app.domain.scheduling.snapshots import RevisionSnapshot, decode_problem
from app.domain.optimization.contracts import SolverConfig, SolverResult
from app.domain.optimization.metrics import calculate_metrics
from app.domain.verification.verifier import HardRuleVerifier


def _candidate(problem, assignments, config, iteration, runtime=0):
    assigned = {a.trip_id for a in assignments}
    result = SolverResult('cv-solver', 'cv-bounded-v1', tuple(assignments),
                          tuple(t.id for t in problem.trips if t.id not in assigned), {}, runtime, 'completed')
    report = HardRuleVerifier().verify(problem, result)
    return dict(id=f'iteration-{iteration}', assignments=[asdict(a) for a in assignments],
                metrics=asdict(calculate_metrics(problem, result)), verification=asdict(report),
                seed=config.seed, solver_version='cv-bounded-v1', iteration=iteration, solve_time_seconds=runtime)


def solve_child(problem_data, config_data, messages):
    # Spawned interpreter receives only serializable input; no SQLAlchemy sessions/pools.
    # Suppress legacy solver output at the OS descriptor level; only bounded messages leave this process.
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    try:
        from app.domain.optimization.cv_bounded import CVBoundedV1
        problem = decode_problem(problem_data)
        config = SolverConfig(**config_data)
        class Progress:
            def update(self, iteration, max_iterations, current_cost, best_cost, message=''):
                messages.put(('progress', {'progress_pct': min(99, int(iteration/max_iterations*100))}), timeout=5)
            def candidate(self, assignments, iteration):
                messages.put(('candidate', _candidate(problem, assignments, config, iteration)), timeout=5)
        result = CVBoundedV1().solve(problem, config, Progress())
        final = _candidate(problem, result.assignments, config, config.iterations, result.solve_time_seconds)
        final['snapshot_hash'] = hashlib.sha256(json.dumps(problem_data, sort_keys=True).encode()).hexdigest()
        messages.put(('completed', final), timeout=5)
    except Exception:
        messages.put(('failed', {'error': 'CV execution failed; inspect worker diagnostics'}), timeout=5)


def record(factory, jid, tenant_id, worker_id, token, kind, data):
    """Fence every transition and commit state + event in the same transaction."""
    with factory() as db:
        set_tenant_scope(db, tenant_id)
        job = db.query(Job).filter_by(job_id=jid, tenant_id=tenant_id, claimed_by=worker_id,
            attempt_token=token).filter(Job.status.in_(['claimed','running'])).with_for_update().first()
        if not job:
            return False
        now = datetime.now(timezone.utc)
        job.heartbeat_at, job.updated_at = now, now
        job.lease_expires_at = now + timedelta(seconds=30)
        payload = {'job_id': jid}
        if kind == 'heartbeat':
            db.commit()
            return True
        if kind == 'progress':
            job.status = 'running'
            job.progress_pct = max(job.progress_pct or 0, min(99, data['progress_pct']))
            payload.update(status=job.status, progress_pct=job.progress_pct)
        elif kind in ('candidate','completed'):
            previous = (job.result_data or {}).get('candidates', [])
            job.result_data = {'candidates': [c for c in previous if c['id'] != data['id']] + [data]}
            if kind == 'completed':
                job.status, job.progress_pct, job.lease_expires_at = 'completed', 100, None
            else:
                job.status = 'running'
            payload.update(status=job.status, progress_pct=job.progress_pct)
        else:
            job.status, job.error_message, job.lease_expires_at = 'failed', data['error'], None
            payload.update(status='failed', error=job.error_message)
        db.add(OutboxEvent(tenant_id=tenant_id, job_id=jid, event_type=f'job.{kind}', payload=payload))
        db.commit()
        return True


def work_once(factory, tenant_id, worker_id):
    with factory() as db:
        set_tenant_scope(db, tenant_id)
        job = JobRepository(db).claim_next_job(worker_id, lease_duration_seconds=30, allowed_tenant_id=tenant_id)
        if not job:
            return False
        jid, token = job.job_id, job.attempt_token
        snap = db.query(RevisionSnapshot).filter_by(tenant_id=tenant_id, revision_id=job.snapshot_id).first()
        if not snap:
            record(factory, jid, tenant_id, worker_id, token, 'failed', {'error': 'Problem snapshot is unavailable'})
            return True
        problem_data = snap.problem_data
        config_data = {k: job.config.get(k, default) for k, default in
                       [('seed',42), ('iterations',3), ('time_limit_seconds',60), ('cp_sat_workers',1)]}
    context = mp.get_context('spawn')
    messages = context.Queue(maxsize=8)
    process = context.Process(target=solve_child, args=(problem_data, config_data, messages))
    process.start()
    deadline = time.monotonic() + config_data['time_limit_seconds']
    heartbeat = time.monotonic()
    terminal = False
    try:
        while time.monotonic() < deadline:
            try:
                kind, data = messages.get(timeout=.25)
                if not record(factory, jid, tenant_id, worker_id, token, kind, data):
                    terminal = True # cancelled or lease ownership lost; discard result
                    break
                if kind in ('completed','failed'):
                    terminal = True
                    break
            except queue.Empty:
                if not process.is_alive():
                    break
            if time.monotonic()-heartbeat >= 1:
                if not record(factory, jid, tenant_id, worker_id, token, 'heartbeat', {}):
                    terminal = True
                    break
                heartbeat = time.monotonic()
        if not terminal:
            record(factory, jid, tenant_id, worker_id, token, 'failed',
                   {'error': 'CV worker exceeded its deadline or exited without a result'})
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        messages.close()
        messages.cancel_join_thread()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tenant-id', type=int, required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    from sqlalchemy import create_engine
    from config import settings
    from db.migrations import assert_schema_current
    from db.tenant_schema import assert_runtime_role
    worker_engine = create_engine(settings.DATABASE_WORKER_URL,hide_parameters=True)
    with worker_engine.connect() as connection:
        assert_schema_current(connection)
        assert_runtime_role(connection)
    SessionLocal = sessionmaker(bind=worker_engine)
    worker_id = str(uuid.uuid4())
    while True:
        worked = work_once(SessionLocal, args.tenant_id, worker_id)
        if args.once:
            return
        if not worked:
            time.sleep(1)


if __name__ == '__main__':
    main()
