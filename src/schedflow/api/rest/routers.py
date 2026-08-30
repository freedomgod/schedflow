"""REST API routes for jobs and scheduler control."""

from fastapi import APIRouter, Depends, HTTPException, Request

from schedflow.api.rest.schemas import (
    JobCreateRequest,
    JobUpdateRequest,
    RescheduleRequest,
)
from schedflow.api.schemas import APIResponse
from schedflow.core.jobstore import JobConflictError, JobNotFoundError
from schedflow.core.scheduler import (
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_STOPPED,
)
from schedflow.core.workflow import CycleError

router = APIRouter(prefix="/api", tags=["api"])

_STATE_NAMES = {
    STATE_STOPPED: "STOPPED",
    STATE_RUNNING: "RUNNING",
    STATE_PAUSED: "PAUSED",
}


def _get_scheduler(request: Request):
    # Prefer the scheduler bound by mount_routes(); fall back to the
    # app-level scheduler (e.g. when a legacy app co-hosts this router).
    state = request.app.state
    scheduler = getattr(state, "scheduler_api", None)
    if scheduler is None:
        scheduler = getattr(state, "scheduler", None)
    return scheduler


def _build_workflow_and_trigger(request):
    try:
        workflow = request.workflow.to_workflow()
        trigger = request.trigger.to_trigger() if request.trigger is not None else None
    except (ValueError, CycleError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return workflow, trigger


@router.post("/jobs")
def create_job(request: JobCreateRequest, scheduler=Depends(_get_scheduler)):
    workflow, trigger = _build_workflow_and_trigger(request)
    try:
        job = scheduler.add_job(
            workflow,
            trigger=trigger,
            job_id=request.job_id,
            name=request.name,
            description=request.description,
            executor_alias=request.executor_alias,
            jobstore_alias=request.jobstore_alias,
            misfire_grace_time=request.misfire_grace_time,
            coalesce=request.coalesce,
            max_instances=request.max_instances,
            replace=request.replace,
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return APIResponse(data=job.to_dict())


@router.get("/jobs")
def list_jobs(scheduler=Depends(_get_scheduler)):
    return APIResponse(data=[job.to_dict() for job in scheduler.get_jobs()])


@router.get("/jobs/{job_id}")
def get_job(job_id: str, scheduler=Depends(_get_scheduler)):
    job = scheduler.get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    return APIResponse(data=job.to_dict())


@router.put("/jobs/{job_id}")
def update_job(
    job_id: str,
    request: JobUpdateRequest,
    scheduler=Depends(_get_scheduler),
):
    changes = request.model_dump(exclude_none=True)
    workflow = None
    trigger = None
    if "workflow" in changes:
        workflow = changes.pop("workflow").to_workflow()
    if "trigger" in changes:
        trigger = changes.pop("trigger").to_trigger()
    try:
        job = scheduler.update_job(job_id, workflow=workflow, trigger=trigger, **changes)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, CycleError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return APIResponse(data=job.to_dict())


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, scheduler=Depends(_get_scheduler)):
    try:
        scheduler.remove_job(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return APIResponse(message=f"Job {job_id} removed")


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str, scheduler=Depends(_get_scheduler)):
    try:
        job = scheduler.pause_job(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return APIResponse(data=job.to_dict())


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, scheduler=Depends(_get_scheduler)):
    try:
        job = scheduler.resume_job(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return APIResponse(data=job.to_dict())


@router.post("/jobs/{job_id}/run")
def run_job_now(job_id: str, scheduler=Depends(_get_scheduler)):
    try:
        log = scheduler.run_job_now(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return APIResponse(data=log.to_dict())


@router.post("/jobs/{job_id}/reschedule")
def reschedule_job(
    job_id: str,
    request: RescheduleRequest,
    scheduler=Depends(_get_scheduler),
):
    try:
        trigger = request.trigger.to_trigger()
        job = scheduler.reschedule_job(job_id, trigger)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return APIResponse(data=job.to_dict())


@router.get("/jobs/{job_id}/logs")
def get_job_logs(job_id: str, scheduler=Depends(_get_scheduler)):
    if scheduler.get_job(job_id) is None:
        raise JobNotFoundError(job_id)
    return APIResponse(
        data=[log.to_dict() for log in scheduler.get_job_logs(job_id)]
    )


@router.get("/jobs/{job_id}/logs/{log_id}")
def get_job_log(job_id: str, log_id: str, scheduler=Depends(_get_scheduler)):
    log = scheduler.get_job_log(job_id, log_id)
    if log is None:
        raise JobNotFoundError(log_id)
    return APIResponse(data=log.to_dict())


@router.get("/scheduler/status")
def scheduler_status(scheduler=Depends(_get_scheduler)):
    return APIResponse(
        data={
            "state": scheduler.state,
            "state_name": _STATE_NAMES.get(scheduler.state, "UNKNOWN"),
            "job_count": len(scheduler.get_jobs()),
        }
    )


@router.post("/scheduler/start")
def scheduler_start(scheduler=Depends(_get_scheduler)):
    scheduler.start()
    return APIResponse(message="Scheduler started")


@router.post("/scheduler/pause")
def scheduler_pause(scheduler=Depends(_get_scheduler)):
    scheduler.pause()
    return APIResponse(message="Scheduler paused")


@router.post("/scheduler/resume")
def scheduler_resume(scheduler=Depends(_get_scheduler)):
    scheduler.resume()
    return APIResponse(message="Scheduler resumed")


@router.post("/scheduler/shutdown")
def scheduler_shutdown(scheduler=Depends(_get_scheduler)):
    scheduler.shutdown()
    return APIResponse(message="Scheduler shut down")
