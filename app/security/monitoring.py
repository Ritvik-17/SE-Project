"""Monitoring (steps 17-18): request and model-call metrics in Prometheus text format at GET /metrics.

In-process counters (reset on restart): requests by route, method and status class; request latency; LLM calls,
filtered outputs and agent-permission denials. Scrape with Prometheus/Grafana in a real deployment; the audit log
remains the system of record for who did what.
"""

import re
import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple, float] = defaultdict(float)


def route_of(path: str) -> str:
    return re.sub(r"/\d+", "/{id}", re.sub(r"/[0-9a-f]{32}", "/{session}", path))


def inc(name: str, value: float = 1.0, **labels) -> None:
    with _lock:
        _counters[(name, tuple(sorted(labels.items())))] += value


def render() -> str:
    lines = []
    with _lock:
        items = sorted(_counters.items())
    for (name, labels), value in items:
        label = ",".join(f'{k}="{v}"' for k, v in labels)
        lines.append(f"rera_{name}{{{label}}} {value:g}")
    return "\n".join(lines) + "\n"
