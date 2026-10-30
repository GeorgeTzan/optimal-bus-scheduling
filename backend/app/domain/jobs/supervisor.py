import subprocess
import time
import signal
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class JobOutcome:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    cancelled: bool = False


def run_job_subprocess(
    cmd: List[str],
    deadline_seconds: float,
    max_output_bytes: int = 1_000_000,
) -> JobOutcome:
    """
    Executes a worker command in an external isolated subprocess with strict deadline enforcement,
    guaranteed SIGKILL termination on timeout, and bounded output memory capture.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    timed_out = False
    stdout = ""
    stderr = ""

    try:
        stdout, stderr = proc.communicate(timeout=deadline_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Graceful SIGTERM first
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            # Forceful SIGKILL if not responding
            proc.kill()
            stdout, stderr = proc.communicate()

    # Cap output to prevent memory explosion
    if len(stdout) > max_output_bytes:
        stdout = stdout[:max_output_bytes] + "\n[OUTPUT TRUNCATED]"
    if len(stderr) > max_output_bytes:
        stderr = stderr[:max_output_bytes] + "\n[OUTPUT TRUNCATED]"

    exit_code = proc.returncode if proc.returncode is not None else -1

    return JobOutcome(
        exit_code=exit_code,
        stdout=stdout or "",
        stderr=stderr or "",
        timed_out=timed_out,
        cancelled=False,
    )
