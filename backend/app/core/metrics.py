"""In-process request metrics (PRD section 9/13: "Monitor CPU/RAM, requests, p50/p95 latency,
error rates; expose health and secured metrics"). A bounded in-memory ring buffer is sufficient
for a single-process hackathon deployment; swap for a Prometheus client in production without
touching callers, since everything reads through :func:`get_metrics_collector`.
"""

from __future__ import annotations

import threading
from collections import deque
from functools import lru_cache


class MetricsCollector:
    def __init__(self, max_samples: int = 2000) -> None:
        self._lock = threading.Lock()
        self._latencies_ms: deque[float] = deque(maxlen=max_samples)
        self._request_count = 0
        self._error_count = 0

    def record(self, latency_ms: float, is_error: bool) -> None:
        with self._lock:
            self._latencies_ms.append(latency_ms)
            self._request_count += 1
            if is_error:
                self._error_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            samples = sorted(self._latencies_ms)
            request_count = self._request_count
            error_count = self._error_count

        def percentile(p: float) -> float:
            if not samples:
                return 0.0
            idx = min(len(samples) - 1, int(len(samples) * p))
            return round(samples[idx], 2)

        return {
            "request_count": request_count,
            "error_count": error_count,
            "p50_latency_ms": percentile(0.50),
            "p95_latency_ms": percentile(0.95),
        }


@lru_cache
def get_metrics_collector() -> MetricsCollector:
    return MetricsCollector()
