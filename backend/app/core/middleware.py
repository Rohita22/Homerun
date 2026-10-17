"""Cross-cutting request middleware: request_id + latency, used by audit logging and the
observability requirement in PRD section 13 ("Trace IDs and model version in every
recommendation/handoff").
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import get_metrics_collector

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or f"req-{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Elapsed-Ms"] = f"{elapsed_ms:.2f}"
        # Only API calls are service metrics: the static UI also serves assets, and a stray 404 for
        # one of those is not an API error.
        if request.url.path.startswith("/api/"):
            get_metrics_collector().record(elapsed_ms, is_error=response.status_code >= 400)
        return response
