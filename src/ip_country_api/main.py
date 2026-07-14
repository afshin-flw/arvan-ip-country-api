from time import perf_counter

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ip_country_api.api.errors import (
    app_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from ip_country_api.api.health import router as health_router
from ip_country_api.api.lookups import router as lookup_router
from ip_country_api.api.web import PACKAGE_ROOT
from ip_country_api.api.web import router as web_router
from ip_country_api.config import Settings
from ip_country_api.domain.errors import AppError
from ip_country_api.lifespan import build_lifespan
from ip_country_api.observability.metrics import ApplicationMetrics
from ip_country_api.observability.request_context import request_id_context, request_id_or_new

logger = structlog.get_logger()
EXCLUDED_METRIC_PATHS = frozenset({"/metrics", "/health/live", "/health/ready"})


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(
        title=settings.app_name if settings else "IP Country API",
        version=settings.app_version if settings else "0.1.0",
        lifespan=build_lifespan(settings),
    )
    application.state.app_name = settings.app_name if settings else "IP Country API"
    application.state.app_version = settings.app_version if settings else "0.1.0"
    application.state.metrics = ApplicationMetrics(application.state.app_version)

    trusted_hosts = settings.trusted_hosts if settings else ["localhost", "127.0.0.1"]
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
    if settings and settings.cors_allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )

    @application.middleware("http")
    async def request_observability(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request_id_or_new(request.headers.get("X-Request-ID"))
        token = request_id_context.set(request_id)
        started = perf_counter()
        response: Response
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(token)
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        duration = perf_counter() - started
        if request.url.path not in EXCLUDED_METRIC_PATHS:
            application.state.metrics.http_request(
                request.method, route_path, response.status_code, duration
            )
        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            route=route_path,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )
        return response

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            application.state.metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unexpected_error_handler)
    application.include_router(health_router)
    application.include_router(lookup_router)
    application.include_router(web_router)
    application.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
    return application


app = create_app()
