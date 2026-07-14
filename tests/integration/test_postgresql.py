import asyncio
import os
import subprocess
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from ip_country_api.database.models import IPLookupCache
from ip_country_api.database.session import create_session_factory
from ip_country_api.domain.errors import DatabaseSchemaUnavailableError
from ip_country_api.domain.models import CacheRecord, GeoIPResult, IPAddress
from ip_country_api.lifespan import _readiness_check
from ip_country_api.observability.metrics import ApplicationMetrics
from ip_country_api.repositories.ip_lookup_repository import PostgreSQLLookupRepository
from ip_country_api.services.ip_lookup_service import IPLookupService

pytestmark = pytest.mark.integration
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.skip(
        "TEST_DATABASE_URL is not set; isolated PostgreSQL is required", allow_module_level=True
    )


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def lookup(self, _ip: IPAddress) -> GeoIPResult:
        self.calls += 1
        return GeoIPResult("US", "United States", "fake")


@pytest_asyncio.fixture(scope="module")
async def database():  # type: ignore[no-untyped-def]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = TEST_DATABASE_URL or ""
    environment["IPINFO_TOKEN"] = "explicit-test-placeholder"
    subprocess.run(["uv", "run", "alembic", "downgrade", "base"], check=True, env=environment)
    url = (TEST_DATABASE_URL or "").replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_async_engine(url)
    with pytest.raises(DatabaseSchemaUnavailableError):
        await _readiness_check(engine, 2)()
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=environment)
    await _readiness_check(engine, 2)()
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def repository(database):  # type: ignore[no-untyped-def]
    async with database.begin() as connection:
        await connection.execute(text("TRUNCATE ip_lookup_cache"))
    return PostgreSQLLookupRepository(
        create_session_factory(database), ApplicationMetrics("integration")
    )


async def test_migration_created_inet_table(database) -> None:  # type: ignore[no-untyped-def]
    async with database.connect() as connection:
        data_type = await connection.scalar(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='ip_lookup_cache' AND column_name='ip_address'"
            )
        )
    assert data_type == "inet"


async def test_first_lookup_persists_and_second_uses_database(repository, database) -> None:  # type: ignore[no-untyped-def]
    provider = CountingProvider()
    service = IPLookupService(repository, provider, 3600, ApplicationMetrics("integration"))
    first = await service.lookup("8.8.8.8")
    second = await service.lookup("8.8.8.8")
    assert first.source == "provider"
    assert second.source == "database"
    assert provider.calls == 1
    async with create_session_factory(database)() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(IPLookupCache)
            .where(IPLookupCache.ip_address == "8.8.8.8")
        )
    assert count == 1


async def test_expired_record_is_refreshed(repository) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    address = ip_address("1.1.1.1")
    await repository.upsert(
        CacheRecord(
            address,
            "AU",
            "Australia",
            "old",
            now - timedelta(days=2),
            now - timedelta(days=1),
        )
    )
    provider = CountingProvider()
    result = await IPLookupService(
        repository, provider, 3600, ApplicationMetrics("integration")
    ).lookup(str(address))
    assert result.source == "provider"
    assert provider.calls == 1


async def test_concurrent_upserts_converge_to_one_row(repository, database) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    record = CacheRecord(
        ip_address("9.9.9.9"), "US", "United States", "fake", now, now + timedelta(hours=1)
    )
    await asyncio.gather(*(repository.upsert(record) for _ in range(10)))
    async with create_session_factory(database)() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(IPLookupCache)
            .where(IPLookupCache.ip_address == "9.9.9.9")
        )
    assert count == 1


@pytest.mark.parametrize("value", ["8.8.8.8", "2001:4860:4860::8888"])
async def test_inet_round_trip(repository, value: str) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    await repository.upsert(
        CacheRecord(ip_address(value), "US", "United States", "fake", now, now + timedelta(hours=1))
    )
    stored = await repository.get(ip_address(value))
    assert stored is not None
    assert stored.ip == ip_address(value)


async def test_readiness_fails_when_schema_missing(database) -> None:  # type: ignore[no-untyped-def]
    async with database.begin() as connection:
        await connection.execute(
            text("ALTER TABLE ip_lookup_cache RENAME TO ip_lookup_cache_hidden")
        )
    try:
        with pytest.raises(DatabaseSchemaUnavailableError):
            await _readiness_check(database, 2)()
    finally:
        async with database.begin() as connection:
            await connection.execute(
                text("ALTER TABLE ip_lookup_cache_hidden RENAME TO ip_lookup_cache")
            )
