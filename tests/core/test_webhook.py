"""WebhookEventSink tests."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

from schedflow.core.events import SchedulerEvent
from schedflow.core.scheduler import Scheduler
from schedflow.core.webhook import WebhookConfig, WebhookEventSink


class _Receiver(BaseHTTPRequestHandler):
    received: ClassVar[list] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append(
            {
                "path": self.path,
                "body": json.loads(body),
                "secret": self.headers.get("X-SchedFlow-Secret"),
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


def _start_receiver():
    _Receiver.received = []
    server = HTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_webhook_sink_delivers_matching_events():
    server, thread = _start_receiver()
    scheduler = Scheduler()
    sink = WebhookEventSink(
        [
            {
                "url": f"http://127.0.0.1:{server.server_port}/hook",
                "events": ["job.succeeded"],
                "secret": "s3cret",
            }
        ]
    )
    sink.start(scheduler)
    try:
        scheduler._events.publish(
            SchedulerEvent("job.started", job_id="j1")
        )
        scheduler._events.publish(
            SchedulerEvent("job.succeeded", job_id="j1")
        )

        deadline = time.time() + 5
        while not _Receiver.received and time.time() < deadline:
            time.sleep(0.05)

        assert len(_Receiver.received) == 1
        received = _Receiver.received[0]
        assert received["path"] == "/hook"
        assert received["body"]["kind"] == "job.succeeded"
        assert received["body"]["job_id"] == "j1"
        assert received["secret"] == "s3cret"
    finally:
        sink.close()
        server.shutdown()
        thread.join(timeout=2)


def test_webhook_config_parses_events():
    config = WebhookConfig.from_dict(
        {"url": "http://example.test/hook", "events": ["job.*"]}
    )
    assert config.events == ("job.*",)
    assert config.matches("job.succeeded") is True
    assert config.matches("task.executed") is False
