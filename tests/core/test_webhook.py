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
    job_link,
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
    # ISO run times are rendered readably, not echoed verbatim.
    assert "2026-09-16 09:00:00 +08:00" in body


def test_notification_text_appends_the_jump_link():
    title, body = notification_text(_payload(), link_base="https://flow.test/")

    assert "任务失败" in title
    assert "https://flow.test/jobs/j1" in body


def test_generic_body_keeps_the_internal_payload():
    payload = _payload()

    body = build_request_body(WebhookConfig(url="http://x/hook"), payload)

    assert body is payload


def test_job_link_targets_the_log_view_for_task_events():
    base = "https://flow.test"

    assert job_link(_payload(), base) == "https://flow.test/jobs/j1"
    assert job_link({"kind": "task.error", "job_id": "j1"}, base) == (
        "https://flow.test/logs?jobId=j1"
    )
    assert job_link(_payload(), None) is None
    assert job_link({"kind": "job.failed"}, base) is None
    # A relative origin would produce a broken button, so it is ignored.
    assert job_link(_payload(), "/schedflow") is None


def test_dingtalk_body_uses_an_action_card():
    body = build_request_body(
        WebhookConfig(url="http://x/hook", platform="dingtalk"), _payload()
    )

    assert body["msgtype"] == "actionCard"
    assert "任务失败" in body["actionCard"]["title"]
    assert "每日报表" in body["actionCard"]["text"]
    assert "**错误**：boom" in body["actionCard"]["text"]
    # No link_base means no button, but the card is still valid.
    assert "singleURL" not in body["actionCard"]


def test_dingtalk_card_carries_the_jump_button():
    body = build_request_body(
        WebhookConfig(
            url="http://x/hook",
            platform="dingtalk",
            link_base="https://flow.test",
        ),
        _payload(),
    )

    card = body["actionCard"]
    assert card["singleURL"] == "https://flow.test/jobs/j1"
    assert card["singleTitle"] == "查看详情"
    assert "[查看详情](https://flow.test/jobs/j1)" in card["text"]


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


def test_wecom_body_falls_back_to_markdown_without_a_link():
    body = build_request_body(
        WebhookConfig(url="http://x/hook", platform="wecom"), _payload()
    )

    assert body["msgtype"] == "markdown"
    assert "每日报表" in body["markdown"]["content"]
    assert "**错误**：boom" in body["markdown"]["content"]


def test_wecom_body_uses_a_template_card_when_a_link_is_available():
    body = build_request_body(
        WebhookConfig(
            url="http://x/hook",
            platform="wecom",
            link_base="https://flow.test",
        ),
        _payload(),
    )

    card = body["template_card"]
    assert body["msgtype"] == "template_card"
    assert card["card_type"] == "text_notice"
    assert "任务失败" in card["main_title"]["title"]
    assert card["emphasis_content"] == {"title": "失败", "desc": "结果"}
    assert card["card_action"] == {"type": 1, "url": "https://flow.test/jobs/j1"}
    assert card["jump_list"][0]["url"] == "https://flow.test/jobs/j1"
    assert "boom" in card["sub_title_text"]


def test_wecom_card_respects_the_platform_byte_limits():
    long_payload = {
        "kind": "job.max_instances",
        "job_id": "j1",
        "job_name": "每日销售报表汇总与推送（华东区）",
        "run_time": "2026-09-16T09:00:00+08:00",
        "log": {"log_id": "l", "flow_id": "f", "succeeded": False, "duration": 74.2},
        "record": {"node_id": "fetch", "status": "failed", "error": "错误" * 200},
    }

    card = build_request_body(
        WebhookConfig(
            url="http://x/hook", platform="wecom", link_base="https://flow.test"
        ),
        long_payload,
    )["template_card"]

    assert len(card["main_title"]["title"].encode()) <= 24
    assert len(card["main_title"]["desc"].encode()) <= 30
    assert len(card["sub_title_text"].encode()) <= 112
    assert len(card["jump_list"][0]["title"].encode()) <= 10
    assert len(card["emphasis_content"]["title"].encode()) <= 10
    assert len(card["horizontal_content_list"]) <= 6
    for row in card["horizontal_content_list"]:
        assert len(row["keyname"].encode()) <= 10
        assert len(row["value"].encode()) <= 30
    # Truncation must not split a multi-byte character.
    card["sub_title_text"].encode("utf-8").decode("utf-8")


def test_feishu_body_carries_the_platform_signature():
    body = build_request_body(
        WebhookConfig(url="http://x/hook", platform="feishu", secret="SEC"),
        _payload(),
        timestamp_s=1700000000,
    )

    digest = hmac.new(b"1700000000\nSEC", b"", hashlib.sha256).digest()
    assert body["msg_type"] == "interactive"
    assert body["timestamp"] == "1700000000"
    assert body["sign"] == base64.b64encode(digest).decode()
    assert body["card"]["header"]["title"]["content"] == "SchedFlow · 任务失败"
    # Failures get a red header; successes a green one.
    assert body["card"]["header"]["template"] == "red"
    fields = body["card"]["elements"][0]["text"]["content"]
    assert "每日报表" in fields
    assert "**节点**：fetch（失败）" in fields


def test_feishu_card_adds_a_button_only_when_a_link_exists():
    payload = {"kind": "job.succeeded", "job_id": "j1", "job_name": "报表"}

    without = build_request_body(
        WebhookConfig(url="http://x/hook", platform="feishu"), payload
    )
    with_link = build_request_body(
        WebhookConfig(
            url="http://x/hook",
            platform="feishu",
            link_base="https://flow.test",
        ),
        payload,
    )

    assert [element["tag"] for element in without["card"]["elements"]] == ["div"]
    assert with_link["card"]["header"]["template"] == "green"
    button = with_link["card"]["elements"][-1]
    assert button["tag"] == "action"
    assert button["actions"][0]["url"] == "https://flow.test/jobs/j1"


def test_unknown_platform_falls_back_to_generic():
    config = WebhookConfig.from_dict(
        {"url": "http://x/hook", "platform": "slack"}
    )

    assert config.platform == "generic"


def test_config_normalises_the_link_base():
    config = WebhookConfig.from_dict(
        {"url": "http://x/hook", "link_base": "https://flow.test/"}
    )
    relative = WebhookConfig.from_dict(
        {"url": "http://x/hook", "link_base": "flow.test"}
    )

    assert config.link_base == "https://flow.test"
    assert relative.link_base is None


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
