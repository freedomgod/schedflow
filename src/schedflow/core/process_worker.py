"""Module-level worker entry point for the process pool (spawn-safe).

The worker receives only JSON-serializable data (job dict + run time) and
returns the execution log as JSON, so no scheduler, lock or live callable
objects are ever pickled across processes.
"""

from __future__ import annotations

from typing import Optional

from schedflow.core.job import Job


def run_job_in_process(
    job_dict: dict,
    run_time_iso: str,
    project_root: Optional[str],
) -> dict:
    """Rebuild the job, execute it and return the serialized execution log."""
    job = Job.from_dict(job_dict, project_root=project_root)
    log = job.run()
    return log.to_dict()
