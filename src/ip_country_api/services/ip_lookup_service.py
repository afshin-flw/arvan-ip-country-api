from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ip_country_api.domain.ip_validation import validate_public_ip
from ip_country_api.domain.models import CacheRecord, LookupResult
from ip_country_api.observability.metrics import ApplicationMetrics
from ip_country_api.providers.base import GeoIPProvider
from ip_country_api.repositories.ip_lookup_repository import LookupRepository


class IPLookupService:
    def __init__(
        self,
        repository: LookupRepository,
        provider: GeoIPProvider,
        ttl_seconds: int,
        metrics: ApplicationMetrics,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._ttl = timedelta(seconds=ttl_seconds)
        self._metrics = metrics
        self._clock = clock or (lambda: datetime.now(UTC))

    async def lookup(self, value: str) -> LookupResult:
        ip = validate_public_ip(value)
        now = self._clock()
        cached = await self._repository.get(ip)
        if cached is not None and cached.expires_at > now:
            self._metrics.lookup("database", "success")
            return LookupResult(
                ip=ip,
                country_code=cached.country_code,
                country_name=cached.country_name,
                source="database",
                fetched_at=cached.fetched_at,
                expires_at=cached.expires_at,
            )

        # A miss is observable as an attempted provider-source lookup. Concurrent
        # misses may call the provider more than once before atomic upserts converge.
        try:
            provider_result = await self._provider.lookup(ip)
            fetched_at = self._clock()
            record = CacheRecord(
                ip=ip,
                country_code=provider_result.country_code,
                country_name=provider_result.country_name,
                provider=provider_result.provider,
                fetched_at=fetched_at,
                expires_at=fetched_at + self._ttl,
            )
            await self._repository.upsert(record)
        except Exception:
            self._metrics.lookup("provider", "error")
            raise

        self._metrics.lookup("provider", "success")
        return LookupResult(
            ip=ip,
            country_code=record.country_code,
            country_name=record.country_name,
            source="provider",
            fetched_at=record.fetched_at,
            expires_at=record.expires_at,
        )
