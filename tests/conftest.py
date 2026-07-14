from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import httpx
import pytest
from pydantic import SecretStr

from ip_country_api.config import Settings
from ip_country_api.domain.models import CacheRecord, GeoIPResult, IPAddress
from ip_country_api.main import create_app
from ip_country_api.observability.metrics import ApplicationMetrics


class FakeRepository:
    def __init__(self, record: CacheRecord | None = None) -> None:
        self.record = record
        self.reads = 0
        self.upserts = 0

    async def get(self, ip: IPAddress) -> CacheRecord | None:
        self.reads += 1
        return self.record if self.record is not None and self.record.ip == ip else None

    async def upsert(self, record: CacheRecord) -> None:
        self.upserts += 1
        self.record = record


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def lookup(self, _ip: IPAddress) -> GeoIPResult:
        self.calls += 1
        return GeoIPResult("US", "United States", "fake")


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 7, 14, 12, tzinfo=UTC)


@pytest.fixture
def cached_record(now: datetime) -> CacheRecord:
    return CacheRecord(
        ip=ip_address("8.8.8.8"),
        country_code="US",
        country_name="United States",
        provider="fake",
        fetched_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=1),
    )


@pytest.fixture
def metrics() -> ApplicationMetrics:
    return ApplicationMetrics("test")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=SecretStr("postgresql+psycopg://localhost/test"),
        ipinfo_token=SecretStr("explicit-test-placeholder"),
        trusted_hosts=["testserver", "localhost"],
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    application = create_app(settings)
    application.state.readiness_check = _ready
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


async def _ready() -> None:
    return None
