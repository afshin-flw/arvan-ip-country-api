import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import psycopg
import structlog
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from ip_country_api.config import Settings, get_settings
from ip_country_api.database.engine import create_database_engine
from ip_country_api.database.session import create_session_factory
from ip_country_api.domain.errors import (
    DatabaseSchemaUnavailableError,
    DatabaseUnavailableError,
)
from ip_country_api.observability.logging import configure_logging
from ip_country_api.observability.metrics import ApplicationMetrics
from ip_country_api.providers.ipinfo import IPinfoLiteProvider
from ip_country_api.repositories.ip_lookup_repository import PostgreSQLLookupRepository
from ip_country_api.services.ip_lookup_service import IPLookupService

logger = structlog.get_logger()


def build_lifespan(configured_settings: Settings | None = None):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = configured_settings or get_settings()
        configure_logging(settings.log_level, settings.log_format)
        metrics = ApplicationMetrics(settings.app_version, settings.metrics_enabled)
        engine = create_database_engine(settings)
        sessions = create_session_factory(engine)
        client = httpx.AsyncClient(
            base_url=settings.geoip_provider_base_url,
            timeout=httpx.Timeout(settings.geoip_provider_timeout_seconds),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": f"ip-country-api/{settings.app_version}",
            },
        )
        provider = IPinfoLiteProvider(
            client,
            settings.ipinfo_token.get_secret_value(),
            settings.geoip_provider_max_retries,
            metrics,
        )
        repository = PostgreSQLLookupRepository(sessions, metrics)

        app.state.app_name = settings.app_name
        app.state.app_version = settings.app_version
        app.state.metrics = metrics
        app.state.lookup_service = IPLookupService(
            repository, provider, settings.geoip_cache_ttl_seconds, metrics
        )
        app.state.readiness_check = _readiness_check(
            engine, settings.database_connect_timeout_seconds
        )
        logger.info("application_starting", **settings.public_summary())
        try:
            yield
        finally:
            await client.aclose()
            await engine.dispose()
            logger.info("application_stopped")

    return lifespan


def _readiness_check(engine: AsyncEngine, timeout_seconds: float):  # type: ignore[no-untyped-def]
    async def check() -> None:
        try:
            async with asyncio.timeout(timeout_seconds), engine.connect() as connection:
                await connection.execute(text("SELECT 1 FROM ip_lookup_cache LIMIT 1"))
        except (TimeoutError, psycopg.OperationalError) as exc:
            raise DatabaseUnavailableError from exc
        except (DBAPIError, SQLAlchemyError) as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
            if sqlstate in {"42P01", "3F000"}:
                raise DatabaseSchemaUnavailableError from exc
            raise DatabaseUnavailableError from exc

    return check
