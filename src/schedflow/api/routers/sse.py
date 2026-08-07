"""SSE (Server-Sent Events) endpoints for real-time job updates."""
import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from schedflow.api.deps import get_core_scheduler
from schedflow.core.scheduler import Scheduler

router = APIRouter(prefix="/sse", tags=["sse"])


def _next_run_time_str(job) -> str | None:
    return job.next_run_time.isoformat() if job.next_run_time else None


def _jobs_snapshot(scheduler: Scheduler) -> dict[str, str | None]:
    return {job.job_id: _next_run_time_str(job) for job in scheduler.get_jobs()}


async def _next_run_times_stream(scheduler: Scheduler):
    """Async generator emitting every job's next_run_time when it changes."""
    last_snapshot = None
    while True:
        try:
            snapshot = _jobs_snapshot(scheduler)
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                yield f"data: {json.dumps({'jobs': snapshot})}\n\n"

            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception:
            break


def _streaming_response(event_stream) -> StreamingResponse:
    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/next-run-time")
async def stream_all_next_run_times(
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    """SSE endpoint that streams a snapshot of every job's next_run_time.

    The job list page subscribes to this stream and live-updates the
    "next run time" column without polling the whole job list.
    """

    return _streaming_response(_next_run_times_stream(scheduler))


@router.get("/jobs/{job_id}/next-run-time")
async def stream_next_run_time(
    job_id: str,
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    """SSE endpoint that streams the job's next_run_time as it changes."""

    async def event_stream():
        last_run_time = None
        while True:
            try:
                job = scheduler.get_job(job_id)
                if job is None:
                    yield (
                        "event: error\n"
                        f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                    )
                    break

                current_str = _next_run_time_str(job)
                if current_str != last_run_time:
                    last_run_time = current_str
                    yield f"data: {json.dumps({'next_run_time': current_str})}\n\n"

                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    return _streaming_response(event_stream())
