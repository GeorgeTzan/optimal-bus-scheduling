import sys
import time
from datetime import datetime
import pytest

from app.domain.jobs.supervisor import run_job_subprocess, JobOutcome


def test_deadline_kills_child():
    """
    If a job subprocess exceeds the hard deadline, the supervisor terminates it (SIGKILL)
    and reports timed_out=True without hanging indefinitely.
    """
    # Run a python command that sleeps for 10 seconds, but deadline is 1.0 second
    script = "import time; time.sleep(10)"
    cmd = [sys.executable, "-c", script]

    start = time.time()
    outcome = run_job_subprocess(cmd, deadline_seconds=1.0)
    elapsed = time.time() - start

    assert outcome.timed_out is True
    assert outcome.exit_code != 0
    assert elapsed < 3.0  # Killed promptly within 3 seconds


def test_subprocess_normal_completion():
    """
    Subprocess completing within deadline captures exit code 0 and stdout.
    """
    script = "print('SOLVER_PROGRESS: 50%'); print('SOLVER_DONE')"
    cmd = [sys.executable, "-c", script]

    outcome = run_job_subprocess(cmd, deadline_seconds=5.0)
    assert outcome.timed_out is False
    assert outcome.exit_code == 0
    assert "SOLVER_DONE" in outcome.stdout


def test_capped_stdout_prevents_memory_bomb():
    """
    A subprocess producing millions of characters has its captured output capped
    to prevent memory exhaustion.
    """
    script = "print('A' * 200_000)"
    cmd = [sys.executable, "-c", script]

    outcome = run_job_subprocess(cmd, deadline_seconds=5.0, max_output_bytes=10_000)
    assert outcome.exit_code == 0
    assert len(outcome.stdout) <= 10_000 + 50  # Capped within limit + truncation notice
    assert "[OUTPUT TRUNCATED]" in outcome.stdout
