from time import perf_counter

from ip_country_api.domain.errors import ProviderInvalidResponseError
from ip_country_api.domain.models import GeoIPResult, IPAddress
from ip_country_api.observability.metrics import ApplicationMetrics

FIXTURES: dict[str, tuple[str, str]] = {
    "8.8.8.8": ("US", "United States"),
    "1.1.1.1": ("AU", "Australia"),
    "2001:4860:4860::8888": ("US", "United States"),
}


class FakeGeoIPProvider:
    """Deterministic, test-only provider with no network dependency."""

    name = "fake"

    def __init__(self, metrics: ApplicationMetrics) -> None:
        self._metrics = metrics

    async def lookup(self, ip: IPAddress) -> GeoIPResult:
        started = perf_counter()
        try:
            country_code, country_name = FIXTURES[str(ip)]
        except KeyError as exc:
            self._metrics.provider_error(self.name, "fixture_not_found")
            self._metrics.provider_request(self.name, "error", perf_counter() - started)
            raise ProviderInvalidResponseError from exc

        self._metrics.provider_request(self.name, "success", perf_counter() - started)
        return GeoIPResult(
            country_code=country_code,
            country_name=country_name,
            provider=self.name,
        )
