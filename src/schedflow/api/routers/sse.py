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
        except Exception:  # noqa: BLE001 - any error ends the stream
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


def _serialize_event(event) -> dict:
    payload = {
        "kind": event.kind,
        "job_id": event.job_id,
        "run_time": event.run_time.isoformat() if event.run_time else None,
        "detail": event.detail,
    }
    if event.record is not None:
        payload["record"] = {
            "node_id": event.record.node_id,
            "status": event.record.status,
            "error": event.record.error,
            "skip_reason": event.record.skip_reason,
            "resumed": getattr(event.record, "resumed", False),
        }
    if event.log is not None:
        payload["log"] = {
            "log_id": event.log.log_id,
            "succeeded": event.log.succeeded,
            "duration": event.log.duration,
        }
    return payload


async def _job_events_stream(scheduler: Scheduler, job_id: str):
    """Stream a job's execution events, with a first-run replay and heartbeats."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(event) -> None:
        if event.job_id not in (None, job_id):
            return
        loop.call_soon_threadsafe(queue.put_nowait, _serialize_event(event))

    scheduler.on("*", on_event)
    try:
        if scheduler.get_job(job_id) is None:
            yield (
                "event: error\n"
                f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            )
            return
        try:
            runs = scheduler.list_job_runs(job_id)
        except Exception:  # noqa: BLE001 - replay is best effort
            runs = []
        if runs:
            yield (
                "event: snapshot\n"
                f"data: {json.dumps({'run': runs[0]}, ensure_ascii=False)}\n\n"
            )
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            except asyncio.CancelledError:
                break
            yield (
                f"event: {payload['kind']}\n"
                f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            )
    finally:
        try:
            scheduler.off("*", on_event)
        except Exception as exc:  # noqa: BLE001 - best effort unsubscribe
            import logging

            logging.getLogger(__name__).debug(
                "sse unsubscribe failed: %s", exc
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
            except Exception:  # noqa: BLE001 - any error ends the stream
                break

    return _streaming_response(event_stream())


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    """SSE endpoint streaming job/task execution events for one job."""
    return _streaming_response(_job_events_stream(scheduler, job_id))
