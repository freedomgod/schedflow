"""Minimal dependency-free Prometheus metrics registry."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

_LOCK = threading.RLock()

DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _key(labels: dict[str, str] | None) -> tuple:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _format_labels(key: tuple, extra: tuple = ()) -> str:
    pairs = [f'{k}="{v}"' for k, v in (*key, *extra)]
    return "{" + ",".join(pairs) + "}" if pairs else ""


@dataclass
class _Metric:
    kind: str
    help: str = ""


@dataclass
class _Counter(_Metric):
    kind: str = "counter"
    values: dict[tuple, float] = field(default_factory=dict)


@dataclass
class _Gauge(_Metric):
    kind: str = "gauge"
    values: dict[tuple, float] = field(default_factory=dict)


@dataclass
class _Histogram(_Metric):
    kind: str = "histogram"
    buckets: tuple = DEFAULT_BUCKETS
    counts: dict[tuple, list[int]] = field(default_factory=dict)
    totals: dict[tuple, float] = field(default_factory=dict)
    samples: dict[tuple, int] = field(default_factory=dict)


_METRICS: dict[str, _Metric] = {}


def _get(name: str, factory) -> _Metric:
    with _LOCK:
        metric = _METRICS.get(name)
        if metric is None:
            metric = factory()
            _METRICS[name] = metric
        return metric


def counter_inc(
    name: str, value: float = 1, labels: dict[str, str] | None = None
) -> None:
    with _LOCK:
        metric = _get(name, _Counter)
        key = _key(labels)
        metric.values[key] = metric.values.get(key, 0.0) + value


def gauge_set(
    name: str, value: float, labels: dict[str, str] | None = None
) -> None:
    with _LOCK:
        metric = _get(name, _Gauge)
        metric.values[_key(labels)] = float(value)


def histogram_observe(
    name: str, value: float, labels: dict[str, str] | None = None
) -> None:
    with _LOCK:
        metric = _get(name, _Histogram)
        key = _key(labels)
        counts = metric.counts.setdefault(key, [0] * len(metric.buckets))
        for index, bucket in enumerate(metric.buckets):
            if value <= bucket:
                counts[index] += 1
        metric.totals[key] = metric.totals.get(key, 0.0) + value
        metric.samples[key] = metric.samples.get(key, 0) + 1


def render_prometheus() -> str:
    """Render all metrics in Prometheus text exposition format."""
    lines: list[str] = []
    with _LOCK:
        for name in sorted(_METRICS):
            metric = _METRICS[name]
            lines.append(f"# TYPE {name} {metric.kind}")
            if isinstance(metric, (_Counter, _Gauge)):
                for key, value in sorted(metric.values.items()):
                    lines.append(f"{name}{_format_labels(key)} {value:g}")
            elif isinstance(metric, _Histogram):
                for key in sorted(metric.counts):
                    counts = metric.counts[key]
                    for index, bucket in enumerate(metric.buckets):
                        lines.append(
                            f"{name}_bucket"
                            f"{_format_labels(key, (('le', bucket),))} "
                            f"{counts[index]}"
                        )
                    lines.append(
                        f"{name}_bucket"
                        f"{_format_labels(key, (('le', '+Inf'),))} "
                        f"{metric.samples.get(key, 0)}"
                    )
                    lines.append(
                        f"{name}_sum{_format_labels(key)} "
                        f"{metric.totals.get(key, 0.0):g}"
                    )
                    lines.append(
                        f"{name}_count{_format_labels(key)} "
                        f"{metric.samples.get(key, 0)}"
                    )
    return "\n".join(lines) + "\n"


def reset_metrics() -> None:
    """Test helper: clear all registered metrics."""
    with _LOCK:
        _METRICS.clear()
