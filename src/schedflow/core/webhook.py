"""Webhook event sink fed by the in-process EventBus.

Deliveries are sent to a chat platform: the internal event payload is only a
valid request body for ``generic`` targets. DingTalk, WeCom and Feishu each
expect their own envelope, and they report failures as ``HTTP 200`` with an
``errcode``/``code`` field, so the response body is inspected as well.

Chat platforms are rendered as rich messages -- DingTalk ``actionCard``,
WeCom ``template_card`` (markdown fallback) and Feishu interactive cards --
so notifications carry a coloured headline, key/value rows and, when
``link_base`` is configured, a "查看详情" jump into the SchedFlow UI.
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
from datetime import datetime
from urllib.parse import quote, quote_plus

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

#: Severity of an event kind; drives the card accent colour per platform.
SEVERITY_BY_KIND = {
    "job.succeeded": "success",
    "job.completed": "success",
    "task.executed": "success",
    "job.failed": "error",
    "task.error": "error",
    "scheduler.error": "error",
    "job.missed": "warning",
    "job.max_instances": "warning",
    "job.cancelled": "warning",
    "job.paused": "warning",
    "task.skipped": "warning",
    "task.cancelled": "warning",
}

#: ``headline`` decoration; keeps the status readable at a glance.
SEVERITY_MARKS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
}

#: Feishu card header colours per severity.
FEISHU_TEMPLATES = {
    "success": "green",
    "error": "red",
    "warning": "orange",
    "info": "blue",
}

#: ``TaskRecord.status`` values rendered in notifications.
STATUS_LABELS = {
    "pending": "待执行",
    "running": "执行中",
    "succeeded": "成功",
    "failed": "失败",
    "skipped": "已跳过",
    "cancelled": "已取消",
}

#: WeCom caps ``template_card`` key names at 10 bytes, so long labels are
#: shortened there only (the markdown/other renderers keep the full wording).
WECOM_KEY_ALIASES = {
    "节点耗时": "耗时",
    "跳过原因": "跳过",
}


def normalize_link_base(value) -> str | None:
    """Return an absolute ``http(s)`` origin for jump links, else ``None``.

    Notifications must never carry a broken/relative URL, so anything that is
    not an absolute http(s) address is dropped instead of being sent along.
    """
    if not value:
        return None
    base = str(value).strip().rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        LOGGER.warning(
            "webhook link_base %r is not an http(s) URL; jump links disabled",
            value,
        )
        return None
    return base


def job_link(payload: dict, link_base: str | None = None) -> str | None:
    """Absolute SchedFlow UI URL for the job an event belongs to.

    Job-level events open the workflow detail page; task-level events open the
    log viewer filtered by job. Returns ``None`` when either the UI origin or
    the job id is unknown.
    """
    base = normalize_link_base(link_base)
    job_id = payload.get("job_id")
    if not base or not job_id:
        return None
    encoded = quote(str(job_id), safe="")
    kind = str(payload.get("kind") or "")
    if kind.startswith("task."):
        return f"{base}/logs?jobId={encoded}"
    return f"{base}/jobs/{encoded}"


def _format_run_time(value) -> str | None:
    """Render an ISO run time as ``2026-09-20 16:28:00 +08:00``."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    stamp = parsed.strftime("%Y-%m-%d %H:%M:%S")
    offset = parsed.utcoffset()
    if offset is None:
        return stamp
    total = int(offset.total_seconds())
    sign = "-" if total < 0 else "+"
    total = abs(total)
    return f"{stamp} {sign}{total // 3600:02d}:{total % 3600 // 60:02d}"


def _format_duration(seconds) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    if value < 1:
        return f"{value * 1000:.0f} 毫秒"
    if value < 60:
        return f"{value:.2f} 秒"
    minutes, secs = divmod(int(value), 60)
    return f"{minutes} 分 {secs} 秒"


def _clip_bytes(value, limit: int) -> str:
    """Truncate to a UTF-8 byte budget.

    WeCom sizes ``template_card`` fields in bytes (24 for the headline, 10 for
    list keys, ...), so a character count would still get the card rejected.
    """
    text = " ".join(str(value).split())
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    budget = max(0, limit - len("…".encode()))
    clipped = raw[:budget]
    while clipped:
        try:
            return clipped.decode("utf-8") + "…"
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "…"


@dataclass(frozen=True)
class WebhookConfig:
    url: str
    events: tuple[str, ...] = ("*",)
    secret: str | None = None
    timeout: float = 5.0
    #: One of :data:`PLATFORMS`; decides the request envelope and signing.
    platform: str = "generic"
    #: SchedFlow UI origin (e.g. ``https://flow.example.com``) used to build
    #: the "查看详情" jump link carried by chat notifications.
    link_base: str | None = None

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
            link_base=normalize_link_base(data.get("link_base")),
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


@dataclass(frozen=True)
class WebhookNotice:
    """Platform-agnostic summary of one event, rendered per delivery target."""

    kind: str
    #: Card/notification title, e.g. ``SchedFlow · 任务失败``.
    title: str
    #: Event name without the product prefix, e.g. ``任务失败``.
    headline: str
    #: ``success`` | ``error`` | ``warning`` | ``info``.
    severity: str
    fields: tuple[tuple[str, str], ...] = ()
    notes: tuple[tuple[str, str], ...] = ()
    link: str | None = None
    link_label: str = "查看详情"

    @property
    def marked_headline(self) -> str:
        mark = SEVERITY_MARKS.get(self.severity)
        return f"{mark} {self.headline}" if mark else self.headline


def build_notice(payload: dict, *, link_base: str | None = None) -> WebhookNotice:
    """Summarise an event payload into the fields every renderer needs."""
    kind = str(payload.get("kind") or "event")
    headline = EVENT_TITLES.get(kind, kind)
    severity = SEVERITY_BY_KIND.get(kind, "info")

    fields: list[tuple[str, str]] = [("事件", kind)]
    job_name = payload.get("job_name")
    job_id = payload.get("job_id")
    if job_name and job_id:
        fields.append(("任务", f"{job_name}（{job_id}）"))
    elif job_name or job_id:
        fields.append(("任务", str(job_name or job_id)))
    run_time = _format_run_time(payload.get("run_time"))
    if run_time:
        fields.append(("时间", run_time))

    record = payload.get("record") or {}
    if record.get("node_id"):
        node = str(record["node_id"])
        if record.get("status"):
            node = f"{node}（{STATUS_LABELS.get(str(record['status']), record['status'])}）"
        fields.append(("节点", node))

    log = payload.get("log") or {}
    if log.get("succeeded") is not None:
        fields.append(("整体结果", "成功" if log["succeeded"] else "失败"))
    if log.get("duration") is not None:
        fields.append(("耗时", _format_duration(log["duration"])))
    if record.get("duration") is not None:
        fields.append(("节点耗时", _format_duration(record["duration"])))

    notes: list[tuple[str, str]] = []
    if record.get("error"):
        notes.append(("错误", _shorten(record["error"])))
    if record.get("skip_reason"):
        notes.append(("跳过原因", _shorten(record["skip_reason"])))
    detail = payload.get("detail")
    if isinstance(detail, dict) and detail.get("error"):
        notes.append(("错误", _shorten(detail["error"])))
    elif isinstance(detail, str) and detail:
        notes.append(("详情", _shorten(detail)))

    return WebhookNotice(
        kind=kind,
        title=f"SchedFlow · {headline}",
        headline=headline,
        severity=severity,
        fields=tuple(fields),
        notes=tuple(notes),
        link=job_link(payload, link_base),
    )


def notification_text(
    payload: dict, *, link_base: str | None = None
) -> tuple[str, str]:
    """Turn an event payload into ``(title, plain text body)``.

    Kept for log-less targets and callers that only need a text rendering.
    """
    notice = build_notice(payload, link_base=link_base)
    lines = [
        f"{label}：{value}" for label, value in (*notice.fields, *notice.notes)
    ]
    if notice.link:
        lines.append(f"{notice.link_label}：{notice.link}")
    return notice.title, "\n".join(lines)


def _markdown_lines(notice: WebhookNotice, *, bullet: bool) -> list[str]:
    prefix = "- " if bullet else ""
    lines = [f"### {notice.marked_headline}"]
    lines += [f"{prefix}**{label}**：{value}" for label, value in notice.fields]
    lines += [f"> **{label}**：{value}" for label, value in notice.notes]
    return lines


def _dingtalk_body(notice: WebhookNotice) -> dict:
    """DingTalk 群机器人：actionCard，正文为 markdown，链接做成跳转按钮。"""
    lines = _markdown_lines(notice, bullet=True)
    card: dict = {"title": notice.title, "text": "\n".join(lines)}
    if notice.link:
        card["text"] = "\n".join(
            [*lines, "", f"[{notice.link_label}]({notice.link})"]
        )
        card["btnOrientation"] = "0"
        card["singleTitle"] = notice.link_label
        card["singleURL"] = notice.link
    return {"msgtype": "actionCard", "actionCard": card}


def _wecom_markdown_body(notice: WebhookNotice) -> dict:
    """企业微信 markdown：标题 + 键值行 + 引用，链接用 markdown 语法。"""
    lines = _markdown_lines(notice, bullet=False)
    if notice.link:
        lines += ["", f"[{notice.link_label}]({notice.link})"]
    return {"msgtype": "markdown", "markdown": {"content": "\n".join(lines)}}


def _wecom_card_body(notice: WebhookNotice) -> dict:
    """企业微信模板卡片（文本通知型）。

    卡片必须带 ``card_action``，所以只有存在跳转链接时才使用；字段长度按
    平台的**字节**限制裁剪，避免平台以 ``errcode`` 拒收。
    """
    # ``main_title.desc`` already carries the event kind, and the outcome is
    # promoted to ``emphasis_content``, so neither needs a list row.
    rows = [
        {
            "keyname": _clip_bytes(WECOM_KEY_ALIASES.get(label, label), 10),
            "value": _clip_bytes(value, 30),
        }
        for label, value in notice.fields
        if label not in ("事件", "整体结果")
    ][:6]
    card: dict = {
        "card_type": "text_notice",
        "source": {"desc": "SchedFlow", "desc_color": 0},
        "main_title": {
            "title": _clip_bytes(notice.marked_headline, 24),
            "desc": _clip_bytes(notice.kind, 30),
        },
        "card_action": {"type": 1, "url": notice.link},
        "jump_list": [
            {
                "type": 1,
                "url": notice.link,
                "title": _clip_bytes("详情", 10),
            }
        ],
    }
    result = dict(notice.fields).get("整体结果")
    if result:
        card["emphasis_content"] = {"title": _clip_bytes(result, 10), "desc": "结果"}
    if rows:
        card["horizontal_content_list"] = rows
    notes = "；".join(f"{label}：{value}" for label, value in notice.notes)
    if notes:
        card["sub_title_text"] = _clip_bytes(notes, 112)
    return {"msgtype": "template_card", "template_card": card}


def _feishu_body(notice: WebhookNotice) -> dict:
    """飞书自定义机器人：interactive 卡片，标题栏按结果着色。"""
    elements: list[dict] = []
    if notice.fields:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n".join(
                        f"**{label}**：{value}" for label, value in notice.fields
                    ),
                },
            }
        )
    if notice.notes:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n".join(
                        f"**{label}**：{value}" for label, value in notice.notes
                    ),
                },
            }
        )
    if notice.link:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": notice.link_label},
                        "type": "primary",
                        "url": notice.link,
                    }
                ],
            }
        )
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": FEISHU_TEMPLATES.get(notice.severity, "blue"),
                "title": {"tag": "plain_text", "content": notice.title},
            },
            "elements": elements,
        },
    }


def build_request_body(
    config: WebhookConfig, payload: dict, *, timestamp_s: int | None = None
) -> dict:
    """Build the JSON body a platform expects.

    ``generic`` returns the payload untouched, preserving the documented
    contract. ``timestamp_s`` (seconds) is only used to sign Feishu requests.
    """
    if config.platform == "generic":
        return payload

    notice = build_notice(payload, link_base=config.link_base)
    if config.platform == "dingtalk":
        return _dingtalk_body(notice)
    if config.platform == "wecom":
        # 模板卡片必须带 card_action（跳转地址）；没有链接时退回 markdown。
        return (
            _wecom_card_body(notice)
            if notice.link
            else _wecom_markdown_body(notice)
        )

    body_dict: dict = _feishu_body(notice)
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
