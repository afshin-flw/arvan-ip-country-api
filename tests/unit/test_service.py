from dataclasses import replace
from datetime import timedelta

import pytest

from ip_country_api.services.ip_lookup_service import IPLookupService
from tests.conftest import FakeProvider, FakeRepository

pytestmark = pytest.mark.unit


async def test_cache_hit_does_not_call_provider(now, cached_record, metrics) -> None:  # type: ignore[no-untyped-def]
    repository = FakeRepository(cached_record)
    provider = FakeProvider()
    service = IPLookupService(repository, provider, 300, metrics, clock=lambda: now)

    result = await service.lookup("8.8.8.8")

    assert result.source == "database"
    assert provider.calls == 0
    assert repository.upserts == 0


async def test_cache_miss_calls_provider_and_persists(now, metrics) -> None:  # type: ignore[no-untyped-def]
    repository = FakeRepository()
    provider = FakeProvider()
    service = IPLookupService(repository, provider, 300, metrics, clock=lambda: now)

    result = await service.lookup("2001:4860:4860::8888")

    assert result.source == "provider"
    assert result.expires_at == now + timedelta(seconds=300)
    assert provider.calls == 1
    assert repository.upserts == 1


async def test_expired_record_is_refreshed(now, cached_record, metrics) -> None:  # type: ignore[no-untyped-def]
    expired = replace(cached_record, expires_at=now - timedelta(seconds=1))
    repository = FakeRepository(expired)
    provider = FakeProvider()
    service = IPLookupService(repository, provider, 600, metrics, clock=lambda: now)

    result = await service.lookup("8.8.8.8")

    assert result.source == "provider"
    assert result.expires_at == now + timedelta(seconds=600)
    assert provider.calls == 1
