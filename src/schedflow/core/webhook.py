"""Webhook event sink fed by the in-process EventBus.

Deliveries are sent to a chat platform: the internal event payload is only a
valid request body for ``generic`` targets. DingTalk, WeCom and Feishu each
expect their own envelope, and they report failures as ``HTTP 200`` with an
``errcode``/``code`` field, so the response body is inspected as well.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote_plus

from schedflow.core.metrics import counter_inc

LOGGER = logging.getLogger(__name__)

#: Supported delivery targets. ``generic`` keeps the documented JSON contract.
PLATFORMS = ("generic", "dingtalk", "wecom", "feishu")

#: Human readable event names used as the notification title.
EVENT_TITLES = {
    "scheduler.started": "调度器启动",
    "scheduler.paused": "调度器暂停",
    "scheduler.resumed": "调度器恢复",
    "scheduler.shutdown": "调度器关闭",
    "scheduler.error": "调度器错误",
    "job.added": "任务已创建",
    "job.updated": "任务已更新",
    "job.removed": "任务已删除",
    "job.paused": "任务已暂停",
    "job.resumed": "任务已恢复",
    "job.completed": "任务已完成",
    "job.cancelled": "任务已取消",
    "job.started": "任务开始执行",
    "job.succeeded": "任务成功",
    "job.failed": "任务失败",
    "job.missed": "任务错过执行时间",
    "job.max_instances": "任务实例数超限",
    "task.executed": "节点执行完成",
    "task.error": "节点执行失败",
    "task.skipped": "节点被跳过",
    "task.cancelled": "节点已取消",
}

#: Response bodies are only used for diagnostics; keep them short.
_MAX_RESPONSE_CHARS = 512


@dataclass(frozen=True)
class WebhookConfig:
    url: str
    events: tuple[str, ...] = ("*",)
    secret: str | None = None
    timeout: float = 5.0
    #: One of :data:`PLATFORMS`; decides the request envelope and signing.
    platform: str = "generic"

    @classmethod
    def from_dict(cls, data: dict) -> WebhookConfig:
        platform = str(data.get("platform") or "generic").lower()
        if platform not in PLATFORMS:
            LOGGER.warning(
                "unknown webhook platform %r; falling back to 'generic'",
                platform,
            )
            platform = "generic"
        return cls(
            url=data["url"],
            events=tuple(data.get("events") or ("*",)),
            secret=data.get("secret"),
            timeout=float(data.get("timeout") or 5.0),
            platform=platform,
        )

    def matches(self, kind: str) -> bool:
        for pattern in self.events:
            if pattern == "*" or pattern == kind:
                return True
            if pattern.endswith(".*") and kind.startswith(pattern[:-1]):
                return True
        return False


def event_to_payload(event) -> dict:
    payload = {
        "kind": event.kind,
        "job_id": event.job_id,
        "run_time": event.run_time.isoformat() if event.run_time else None,
        "detail": event.detail,
    }
    if event.record is not None:
        record = event.record
        payload["record"] = {
            "node_id": record.node_id,
            "status": record.status,
            "error": record.error,
            "skip_reason": record.skip_reason,
            "duration": record.duration,
        }
    if event.log is not None:
        payload["log"] = {
            "log_id": event.log.log_id,
            "flow_id": event.log.flow_id,
            "succeeded": event.log.succeeded,
            "duration": event.log.duration,
        }
    return payload


def _shorten(value, limit: int = 400) -> str:
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}…"


def notification_text(payload: dict) -> tuple[str, str]:
    """Turn an event payload into ``(title, plain text body)``.

    Plain text keeps the same string usable as DingTalk/WeCom markdown and as
    Feishu text content.
    """
    kind = str(payload.get("kind") or "event")
    title = f"SchedFlow · {EVENT_TITLES.get(kind, kind)}"

    lines = [f"事件：{kind}"]
    job_name = payload.get("job_name")
    job_id = payload.get("job_id")
    if job_name and job_id:
        lines.append(f"任务：{job_name}（{job_id}）")
    elif job_name or job_id:
        lines.append(f"任务：{job_name or job_id}")
    if payload.get("run_time"):
        lines.append(f"时间：{payload['run_time']}")

    record = payload.get("record") or {}
    if record.get("node_id"):
        lines.append(f"节点：{record['node_id']}（{record.get('status')}）")
    if record.get("error"):
        lines.append(f"错误：{_shorten(record['error'])}")
    if record.get("skip_reason"):
        lines.append(f"跳过原因：{_shorten(record['skip_reason'])}")

    log = payload.get("log") or {}
    if log.get("succeeded") is not None:
        lines.append(f"整体结果：{'成功' if log['succeeded'] else '失败'}")

    detail = payload.get("detail")
    if isinstance(detail, dict) and detail.get("error"):
        lines.append(f"错误：{_shorten(detail['error'])}")

    return title, "\n".join(lines)


def build_request_body(
    config: WebhookConfig, payload: dict, *, timestamp_s: int | None = None
) -> dict:
    """Build the JSON body a platform expects.

    ``generic`` returns the payload untouched, preserving the documented
    contract. ``timestamp_s`` (seconds) is only used to sign Feishu requests.
    """
    if config.platform == "generic":
        return payload

    title, body = notification_text(payload)
    if config.platform == "dingtalk":
        return {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": f"### {title}\n\n{body}"},
        }
    if config.platform == "wecom":
        return {
            "msgtype": "markdown",
            "markdown": {"content": f"### {title}\n{body}"},
        }

    body_dict: dict = {"msg_type": "text", "content": {"text": f"{title}\n{body}"}}
    if config.platform == "feishu" and config.secret and timestamp_s is not None:
        body_dict["timestamp"] = str(timestamp_s)
        body_dict["sign"] = feishu_sign(timestamp_s, config.secret)
    return body_dict


def feishu_sign(timestamp_s: int, secret: str) -> str:
    """Feishu custom-bot signature: HMAC over ``timestamp\\nsecret`` as the key."""
    string_to_sign = f"{timestamp_s}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"), b"", hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def dingtalk_sign(timestamp_ms: int, secret: str) -> str:
    """DingTalk custom-bot 加签: HMAC-SHA256 over ``timestamp\\nsecret``."""
    string_to_sign = f"{timestamp_ms}\n{secret}"
    digest = hmac.new(
        secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
    ).digest()
    return quote_plus(base64.b64encode(digest))


def sign_url(config: WebhookConfig, *, timestamp_ms: int | None = None) -> str:
    """Append DingTalk's ``timestamp``/``sign`` query parameters when needed."""
    if config.platform != "dingtalk" or not config.secret:
        return config.url
    ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    separator = "&" if "?" in config.url else "?"
    return f"{config.url}{separator}timestamp={ts}&sign={dingtalk_sign(ts, config.secret)}"


def platform_error(platform: str, response_text: str) -> str | None:
    """Return the platform's own error message, if it rejected the payload.

    DingTalk/WeCom answer ``{"errcode": 0}`` and Feishu ``{"code": 0}`` on
    success, all with HTTP 200.
    """
    try:
        data = json.loads(response_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    if platform in ("dingtalk", "wecom"):
        code = data.get("errcode")
        if code not in (0, None):
            return f"errcode={code} {data.get('errmsg') or ''}".strip()
    elif platform == "feishu":
        code = data.get("code")
        if code not in (0, None):
            return f"code={code} {data.get('msg') or ''}".strip()
    return None


def deliver_once(config: WebhookConfig, payload: dict) -> dict:
    """POST one payload using the sink's retry policy.

    Returns ``{"ok", "status_code", "error", "duration_ms", "platform",
    "response"}`` and never raises for transport errors, so callers (including
    the settings API) can surface the outcome to users.

    Retries cover transport errors, 5xx and 429. A payload the platform rejects
    (or any other 4xx) will not succeed on retry, so it returns immediately.
    """
    body = json.dumps(
        build_request_body(config, payload, timestamp_s=int(time.time())),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.secret and config.platform == "generic":
        headers["X-SchedFlow-Secret"] = config.secret
    url = sign_url(config)

    started = time.monotonic()
    last_error: Exception | None = None
    status_code: int | None = None
    response_text = ""
    for attempt in range(3):
        request = urllib.request.Request(
            url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                request, timeout=config.timeout
            ) as response:
                status_code = response.status
                response_text = response.read(
                    _MAX_RESPONSE_CHARS
                ).decode("utf-8", "replace")
                if 200 <= status_code < 300:
                    rejected = platform_error(config.platform, response_text)
                    if rejected is not None:
                        return _result(
                            config, False, status_code,
                            f"平台拒绝该消息：{rejected}", started, response_text,
                        )
                    return _result(
                        config, True, status_code, None, started, response_text
                    )
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            last_error = exc
            try:
                response_text = exc.read(_MAX_RESPONSE_CHARS).decode(
                    "utf-8", "replace"
                )
            except Exception:  # noqa: BLE001 - diagnostics are best effort
                response_text = ""
            if 400 <= exc.code < 500 and exc.code != 429:
                break
        except Exception as exc:  # noqa: BLE001 - retry on any transport error
            last_error = exc
        if attempt < 2:
            time.sleep(0.5 * (2**attempt))

    return _result(
        config,
        False,
        status_code,
        str(last_error) if last_error is not None else "delivery failed",
        started,
        response_text,
    )


def _result(
    config: WebhookConfig,
    ok: bool,
    status_code: int | None,
    error: str | None,
    started: float,
    response_text: str,
) -> dict:
    return {
        "ok": ok,
        "status_code": status_code,
        "error": error,
        "duration_ms": (time.monotonic() - started) * 1000,
        "platform": config.platform,
        "response": response_text,
    }


class WebhookEventSink:
    """Bounded, best-effort webhook delivery for scheduler events."""

    def __init__(
        self, configs: list[dict | WebhookConfig], *, queue_size: int = 1000
    ) -> None:
        self._configs = [
            config if isinstance(config, WebhookConfig) else WebhookConfig.from_dict(config)
            for config in configs
        ]
        self._config_lock = threading.RLock()
        self._queue: queue.Queue = queue.Queue(maxsize=max(1, queue_size))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._scheduler = None

    def reload(self, configs: list[dict | WebhookConfig]) -> None:
        with self._config_lock:
            self._configs = [
                config
                if isinstance(config, WebhookConfig)
                else WebhookConfig.from_dict(config)
                for config in configs
            ]

    def start(self, scheduler) -> None:
        self._scheduler = scheduler
        scheduler.on("*", self._on_event)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, name="schedflow-webhook", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if self._scheduler is not None:
            try:
                self._scheduler.off("*", self._on_event)
            except Exception as exc:  # noqa: BLE001 - best effort
                LOGGER.debug("webhook unsubscribe failed: %s", exc)
            self._scheduler = None

    def _on_event(self, event) -> None:
        with self._config_lock:
            configs = [
                config for config in self._configs if config.matches(event.kind)
            ]
        if not configs:
            return
        payload = event_to_payload(event)
        payload.update(self._job_context(event.job_id))
        for config in configs:
            try:
                self._queue.put_nowait((config, payload))
            except queue.Full:
                counter_inc("schedflow_webhook_dropped_total")
                LOGGER.warning(
                    "webhook queue full; dropping %s -> %s",
                    event.kind,
                    config.url,
                )

    def _job_context(self, job_id: str | None) -> dict:
        """Best-effort job name so notifications are readable."""
        if not job_id or self._scheduler is None:
            return {}
        try:
            job = self._scheduler.get_job(job_id)
        except Exception as exc:  # noqa: BLE001 - enrichment must never block
            LOGGER.debug("webhook job lookup failed: %s", exc)
            return {}
        if job is None or not job.name:
            return {}
        return {"job_name": job.name}

    def _worker(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                continue
            config, payload = item
            self._deliver(config, payload)

    def _deliver(self, config: WebhookConfig, payload: dict) -> None:
        result = deliver_once(config, payload)
        if result["ok"]:
            counter_inc("schedflow_webhook_delivered_total")
            return
        counter_inc("schedflow_webhook_failures_total")
        LOGGER.warning(
            "webhook delivery failed url=%s error=%s",
            config.url,
            result["error"],
        )
