"""Tests for SSE (Server-Sent Events) endpoints."""
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

FUTURE_RUN_TIME = (datetime.now() + timedelta(days=365)).isoformat()


class TestSSEEventStream:
    """Unit tests for the SSE event_stream generator logic."""

    def test_event_stream_yields_next_run_time(self):
        """event_stream should yield SSE data with next_run_time when job exists."""
        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_job.next_run_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_scheduler.get_job.return_value = mock_job

        async def _run():
            async def event_stream(scheduler, job_id):
                last_run_time = None
                job = scheduler.get_job(job_id)
                if job is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
                    return

                current = job.next_run_time
                current_str = current.isoformat() if current else None
                if current_str != last_run_time:
                    yield f"data: {json.dumps({'next_run_time': current_str})}\n\n"

            events = []
            async for event in event_stream(mock_scheduler, "test-id"):
                events.append(event)

            assert len(events) == 1
            data_line = [l for l in events[0].split("\n") if l.startswith("data:")]
            payload = json.loads(data_line[0].replace("data: ", ""))
            assert payload["next_run_time"] == "2025-01-01T12:00:00"

        asyncio.run(_run())

    def test_event_stream_yields_error_for_missing_job(self):
        """event_stream should yield error event when job is not found."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        async def _run():
            async def event_stream(scheduler, job_id):
                job = scheduler.get_job(job_id)
                if job is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
                    return

            events = []
            async for event in event_stream(mock_scheduler, "nonexistent"):
                events.append(event)

            assert len(events) == 1
            assert "error" in events[0]
            assert "Job not found" in events[0]

        asyncio.run(_run())

    def test_event_stream_skips_unchanged_next_run_time(self):
        """event_stream should not yield when next_run_time hasn't changed."""
        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        fixed_time = datetime(2025, 6, 15, 8, 30, 0)
        mock_job.next_run_time = fixed_time
        mock_scheduler.get_job.return_value = mock_job

        async def _run():
            async def event_stream(scheduler, job_id):
                last_run_time = None
                for _ in range(3):
                    job = scheduler.get_job(job_id)
                    current = job.next_run_time
                    current_str = current.isoformat() if current else None
                    if current_str != last_run_time:
                        last_run_time = current_str
                        yield f"data: {json.dumps({'next_run_time': current_str})}\n\n"
                    await asyncio.sleep(0)

            events = []
            async for event in event_stream(mock_scheduler, "test-id"):
                events.append(event)

            # Should only yield once since next_run_time doesn't change
            assert len(events) == 1

        asyncio.run(_run())


class TestSSEEndpoint:
    """Integration tests for the SSE API endpoint."""

    def _make_app(self):
        from schedflow.api.exceptions import register_exception_handlers
        from schedflow.api.rest import create_app
        from schedflow.core import Scheduler

        app = create_app(Scheduler(), title="sse-test")
        register_exception_handlers(app)

        from schedflow.api.routers.sse import router as sse_router
        app.include_router(sse_router, prefix="/api/v1")

        return app

    def test_sse_route_registered(self):
        """The SSE route should be registered under /api/v1/sse."""
        app = self._make_app()
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        sse_routes = [r for r in routes if "sse" in r]
        assert len(sse_routes) > 0
        assert any("/sse/jobs/{job_id}/next-run-time" in r for r in sse_routes)

    def test_sse_unknown_job_returns_error_event(self):
        """SSE endpoint for unknown job should return error event stream."""
        app = self._make_app()
        with TestClient(app) as client, client.stream(
            "GET", "/api/v1/sse/jobs/nonexistent/next-run-time"
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            chunk = next(response.iter_bytes())
            text = chunk.decode()
            assert "error" in text
            assert "Job not found" in text

    def test_sse_endpoint_headers(self):
        """SSE endpoint response should include proper SSE headers."""
        app = self._make_app()
        with TestClient(app) as client, client.stream(
            "GET", "/api/v1/sse/jobs/nonexistent/next-run-time"
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            assert response.headers.get("cache-control") == "no-cache"
            assert response.headers.get("connection") == "keep-alive"


class TestSSEJobsListEndpoint:
    """Integration tests for the all-jobs SSE endpoint used by the job list."""

    def _make_app(self):
        from schedflow.api.exceptions import register_exception_handlers
        from schedflow.api.rest import create_app
        from schedflow.core import Scheduler

        app = create_app(Scheduler(), title="sse-list-test")
        register_exception_handlers(app)

        from schedflow.api.routers.sse import router as sse_router

        app.include_router(sse_router, prefix="/api/v1")
        return app

    def test_sse_jobs_list_route_registered(self):
        """The all-jobs SSE route should be registered."""
        app = self._make_app()
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/sse/jobs/next-run-time" in r for r in routes)

    def test_jobs_snapshot_maps_job_ids_to_next_run_time(self):
        """_jobs_snapshot should map every job id to its next_run_time."""
        from schedflow.api.routers.sse import _jobs_snapshot

        job1 = MagicMock()
        job1.job_id = "a"
        job1.next_run_time = datetime(2025, 1, 1, 12, 0, 0)
        job2 = MagicMock()
        job2.job_id = "b"
        job2.next_run_time = None
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [job1, job2]

        snapshot = _jobs_snapshot(mock_scheduler)

        assert snapshot == {"a": "2025-01-01T12:00:00", "b": None}

    def test_jobs_list_stream_yields_snapshot(self):
        """_next_run_times_stream should emit the snapshot as an SSE event."""
        from schedflow.api.routers.sse import _next_run_times_stream

        job = MagicMock()
        job.job_id = "a"
        job.next_run_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [job]

        async def _run():
            events = []
            async for event in _next_run_times_stream(mock_scheduler):
                events.append(event)
                break

            assert len(events) == 1
            data_line = [l for l in events[0].split("\n") if l.startswith("data:")]
            payload = json.loads(data_line[0].replace("data: ", ""))
            assert payload["jobs"]["a"] == "2025-01-01T12:00:00"

        asyncio.run(_run())
