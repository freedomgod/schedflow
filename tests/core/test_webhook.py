"""WebhookEventSink tests."""

import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

from schedflow.core.events import SchedulerEvent
from schedflow.core.scheduler import Scheduler
from schedflow.core.webhook import (
    WebhookConfig,
    WebhookEventSink,
    build_request_body,
    deliver_once,
    notification_text,
    sign_url,
)


class _Receiver(BaseHTTPRequestHandler):
    received: ClassVar[list] = []
    response_status: ClassVar[int] = 200
    response_body: ClassVar[bytes] = b"ok"

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
        self.send_response(type(self).response_status)
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, format, *args):
        pass


def _start_receiver(*, status: int = 200, body: bytes = b"ok"):
    _Receiver.received = []
    _Receiver.response_status = status
    _Receiver.response_body = body
    server = HTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _payload() -> dict:
    return {
        "kind": "job.failed",
        "job_id": "j1",
        "job_name": "每日报表",
        "run_time": "2026-09-16T09:00:00+08:00",
        "detail": None,
        "record": {"node_id": "fetch", "status": "failed", "error": "boom"},
        "log": {"log_id": "flowlog1", "flow_id": "f1", "succeeded": False, "duration": 1.5},
    }


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


def test_deliver_once_posts_payload_with_secret():
    server, thread = _start_receiver()
    try:
        result = deliver_once(
            WebhookConfig(
                url=f"http://127.0.0.1:{server.server_port}/hook",
                secret="s3cret",
                timeout=2.0,
            ),
            {"kind": "job.succeeded", "job_id": "j1"},
        )

        assert result["ok"] is True
        assert result["status_code"] == 200
        assert result["error"] is None
        assert _Receiver.received[-1]["body"]["kind"] == "job.succeeded"
        assert _Receiver.received[-1]["secret"] == "s3cret"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_deliver_once_reports_failure():
    result = deliver_once(
        WebhookConfig(url="http://127.0.0.1:1/nope", timeout=0.2),
        {"kind": "job.succeeded"},
    )

    assert result["ok"] is False
    assert result["error"]


# ── platform adapters ─────────────────────────────────

def test_notification_text_summarises_the_event():
    title, body = notification_text(_payload())

    assert "任务失败" in title
    assert "每日报表" in body
    assert "fetch" in body
    assert "boom" in body


def test_generic_body_keeps_the_internal_payload():
    payload = _payload()

    body = build_request_body(WebhookConfig(url="http://x/hook"), payload)

    assert body is payload


def test_dingtalk_body_uses_markdown_envelope():
    body = build_request_body(
        WebhookConfig(url="http://x/hook", platform="dingtalk"), _payload()
    )

    assert body["msgtype"] == "markdown"
    assert "任务失败" in body["markdown"]["title"]
    assert "每日报表" in body["markdown"]["text"]


def test_dingtalk_signature_is_appended_to_the_url():
    config = WebhookConfig(
        url="http://x/hook?access_token=t",
        platform="dingtalk",
        secret="SEC",
    )

    url = sign_url(config, timestamp_ms=1700000000000)

    digest = hmac.new(
        b"SEC", b"1700000000000\nSEC", hashlib.sha256
    ).digest()
    expected = urllib.parse.quote_plus(base64.b64encode(digest))
    assert url.startswith("http://x/hook?access_token=t&")
    assert f"timestamp=1700000000000&sign={expected}" in url


def test_dingtalk_url_is_untouched_without_a_secret():
    config = WebhookConfig(url="http://x/hook", platform="dingtalk")

    assert sign_url(config, timestamp_ms=1700000000000) == "http://x/hook"


def test_wecom_body_uses_the_content_key():
    body = build_request_body(
        WebhookConfig(url="http://x/hook", platform="wecom"), _payload()
    )

    assert body["msgtype"] == "markdown"
    assert "每日报表" in body["markdown"]["content"]


def test_feishu_body_carries_the_platform_signature():
    body = build_request_body(
        WebhookConfig(url="http://x/hook", platform="feishu", secret="SEC"),
        _payload(),
        timestamp_s=1700000000,
    )

    digest = hmac.new(b"1700000000\nSEC", b"", hashlib.sha256).digest()
    assert body["msg_type"] == "text"
    assert body["timestamp"] == "1700000000"
    assert body["sign"] == base64.b64encode(digest).decode()
    assert "每日报表" in body["content"]["text"]


def test_unknown_platform_falls_back_to_generic():
    config = WebhookConfig.from_dict(
        {"url": "http://x/hook", "platform": "slack"}
    )

    assert config.platform == "generic"


def test_platform_rejection_is_reported_as_failure():
    """DingTalk answers 200 + errcode when it refuses a payload."""
    server, thread = _start_receiver(
        body=json.dumps({"errcode": 300001, "errmsg": "keywords not in content"}).encode()
    )
    try:
        result = deliver_once(
            WebhookConfig(
                url=f"http://127.0.0.1:{server.server_port}/hook",
                platform="dingtalk",
                timeout=2.0,
            ),
            _payload(),
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result["ok"] is False
    assert "300001" in result["error"]
    assert result["status_code"] == 200


def test_feishu_rejection_is_reported_as_failure():
    server, thread = _start_receiver(
        body=json.dumps({"code": 19021, "msg": "msg_type is invalid"}).encode()
    )
    try:
        result = deliver_once(
            WebhookConfig(
                url=f"http://127.0.0.1:{server.server_port}/hook",
                platform="feishu",
                timeout=2.0,
            ),
            _payload(),
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result["ok"] is False
    assert "19021" in result["error"]


def test_deliver_once_reports_platform_and_response_body():
    server, thread = _start_receiver(body=b'{"errcode":0,"errmsg":"ok"}')
    try:
        result = deliver_once(
            WebhookConfig(
                url=f"http://127.0.0.1:{server.server_port}/hook",
                platform="dingtalk",
                timeout=2.0,
            ),
            _payload(),
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result["ok"] is True
    assert result["platform"] == "dingtalk"
    assert "errcode" in result["response"]
