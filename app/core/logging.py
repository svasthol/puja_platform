"""
Structlog configuration + a request-id middleware.

JSON logs in production, human-readable in dev. Every request is wrapped with a
bound request_id so all logs for one request correlate. Referenced by
STACK_VERSIONS.md (structlog) and project.mdc (structlog everywhere, no print).
"""
from __future__ import annotations

import logging
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def configure_logging(*, debug: bool) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.dev.ConsoleRenderer()
        if debug
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Binds a request_id (from X-Request-ID or generated) into contextvars."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        log = structlog.get_logger()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_unhandled_error")
            raise
        response.headers["X-Request-ID"] = request_id
        log.info("request_completed", status_code=response.status_code)
        return response
