"""HTTP request metrics middleware — API layer performance tracking."""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Match

from app.monitoring.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS


def _route_template(request: Request) -> str:
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return request.url.path


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/metrics", "/health"):
            return await call_next(request)
        route = _route_template(request)
        method = request.method
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            HTTP_REQUESTS.labels(method=method, route=route, status_class="5xx").inc()
            HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(
                time.perf_counter() - start
            )
            raise
        HTTP_REQUESTS.labels(
            method=method,
            route=route,
            status_class=_status_class(response.status_code),
        ).inc()
        HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(
            time.perf_counter() - start
        )
        return response
