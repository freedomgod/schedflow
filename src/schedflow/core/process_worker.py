"""Module-level worker entry point for the process pool (spawn-safe).

The worker receives only JSON-serializable data (job dict + run time) and
returns the execution log as JSON, so no scheduler, lock or live callable
objects are ever pickled across processes.
"""

from __future__ import annotations

from schedflow.core.job import Job
from schedflow.core.run import RunRequest


def run_job_in_process(
    job_dict: dict,
    run_time_iso: str,
    project_root: str | None,
    request_dict: dict | None = None,
) -> dict:
    """Rebuild the job, execute it and return the serialized execution log."""
    job = Job.from_dict(job_dict, project_root=project_root)
    log = job.run(request=RunRequest.from_dict(request_dict))
    return log.to_dict()
