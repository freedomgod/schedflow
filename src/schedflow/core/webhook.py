"""Webhook event sink fed by the in-process EventBus."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.request
from dataclasses import dataclass

from schedflow.core.metrics import counter_inc

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookConfig:
    url: str
    events: tuple[str, ...] = ("*",)
    secret: str | None = None
    timeout: float = 5.0

    @classmethod
    def from_dict(cls, data: dict) -> WebhookConfig:
        return cls(
            url=data["url"],
            events=tuple(data.get("events") or ("*",)),
            secret=data.get("secret"),
            timeout=float(data.get("timeout") or 5.0),
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


def deliver_once(config: WebhookConfig, payload: dict) -> dict:
    """POST one payload using the sink's retry policy.

    Returns ``{"ok", "status_code", "error", "duration_ms"}`` and never raises
    for transport errors, so callers (including the settings API) can surface
    the outcome to users.
    """
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.secret:
        headers["X-SchedFlow-Secret"] = config.secret
    started = time.monotonic()
    last_error: Exception | None = None
    status_code: int | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            config.url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                request, timeout=config.timeout
            ) as response:
                status_code = response.status
                if 200 <= status_code < 300:
                    return {
                        "ok": True,
                        "status_code": status_code,
                        "error": None,
                        "duration_ms": (time.monotonic() - started) * 1000,
                    }
        except Exception as exc:  # noqa: BLE001 - retry on any failure
            last_error = exc
        time.sleep(0.5 * (2**attempt))
    return {
        "ok": False,
        "status_code": status_code,
        "error": str(last_error) if last_error is not None else "delivery failed",
        "duration_ms": (time.monotonic() - started) * 1000,
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
