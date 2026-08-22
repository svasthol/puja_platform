"""
FastAPI application factory.

Start locally:
    uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import EXCEPTION_HANDLERS
from app.core.logging import RequestIDMiddleware, configure_logging
from app.core.redis_client import (
    RedisUnavailable,
    close_redis,
    init_redis,
    redis_ping,
)
from app.db.engine import engine
from app.monitoring.middleware import MonitoringMiddleware
from app.monitoring.metrics import get_metrics_content_type, render_metrics
from app.monitoring.sentry_bridge import init_sentry

settings = get_settings()
configure_logging(debug=settings.DEBUG)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=settings.APP_ENV)
    init_sentry(settings.SENTRY_DSN, environment=settings.APP_ENV)
    await init_redis()
    app.state.redis_ready = True
    yield
    await engine.dispose()
    await close_redis()
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        default_response_class=ORJSONResponse,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
        exception_handlers=EXCEPTION_HANDLERS,  # type: ignore[arg-type]
    )

    app.add_middleware(RequestIDMiddleware)
    if settings.METRICS_ENABLED:
        app.add_middleware(MonitoringMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health/live")
    async def health_live():
        """Liveness only — no DB/Redis (use for device LAN reachability probes)."""
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        """Liveness + DB/Redis readiness (so LBs don't route to a broken pod)."""
        db_ok = redis_ok = False
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            log.error("health_db_fail", error=str(exc))
        try:
            redis_ok = await redis_ping()
        except Exception as exc:  # noqa: BLE001
            log.error("health_redis_fail", error=str(exc))
        status = "ok" if (db_ok and redis_ok) else "degraded"
        return ORJSONResponse(
            status_code=200 if status == "ok" else 503,
            content={"status": status, "db": db_ok, "redis": redis_ok, "env": settings.APP_ENV},
        )

    if settings.METRICS_ENABLED:

        @app.get("/metrics")
        async def metrics():
            """Prometheus / OpenMetrics scrape endpoint."""
            from starlette.responses import Response

            return Response(content=render_metrics(), media_type=get_metrics_content_type())

    return app


app = create_app()
