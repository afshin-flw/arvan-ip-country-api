from typing import Protocol

from ip_country_api.domain.models import GeoIPResult, IPAddress


class GeoIPProvider(Protocol):
    async def lookup(self, ip: IPAddress) -> GeoIPResult: ...
