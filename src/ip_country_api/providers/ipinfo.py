from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ip_country_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from ip_country_api.domain.models import GeoIPResult, IPAddress
from ip_country_api.observability.metrics import ApplicationMetrics


class IPinfoLiteResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    country_code: str
    country: str

    @field_validator("country_code")
    @classmethod
    def country_code_is_iso_like(cls, value: str) -> str:
        value = value.upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("invalid country code")
        return value

    @field_validator("country")
    @classmethod
    def country_name_is_usable(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 128:
            raise ValueError("invalid country name")
        return value


class _RetryableProviderError(Exception):
    pass


class _RetryableProviderTimeout(_RetryableProviderError):
    pass


class IPinfoLiteProvider:
    name = "ipinfo"

    def __init__(
        self,
        client: httpx.AsyncClient,
        token: str,
        max_retries: int,
        metrics: ApplicationMetrics,
    ) -> None:
        self._client = client
        self._token = token
        self._max_retries = max_retries
        self._metrics = metrics

    async def lookup(self, ip: IPAddress) -> GeoIPResult:
        started = perf_counter()
        result = "error"
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries + 1),
                wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
                retry=retry_if_exception_type((_RetryableProviderError, _RetryableProviderTimeout)),
                reraise=True,
            ):
                with attempt:
                    response = await self._request(ip)
            parsed = self._parse(response.json())
            result = "success"
            return GeoIPResult(
                country_code=parsed.country_code,
                country_name=parsed.country,
                provider=self.name,
            )
        except _RetryableProviderTimeout as exc:
            self._metrics.provider_error(self.name, "timeout")
            raise ProviderTimeoutError from exc
        except _RetryableProviderError as exc:
            self._metrics.provider_error(self.name, "unavailable")
            raise ProviderUnavailableError from exc
        except (httpx.DecodingError, ValueError, ValidationError) as exc:
            self._metrics.provider_error(self.name, "invalid_response")
            raise ProviderInvalidResponseError from exc
        finally:
            self._metrics.provider_request(self.name, result, perf_counter() - started)

    async def _request(self, ip: IPAddress) -> httpx.Response:
        try:
            response = await self._client.get(
                f"/lite/{ip}", headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx.TimeoutException as exc:
            raise _RetryableProviderTimeout from exc
        except httpx.RequestError as exc:
            raise _RetryableProviderError from exc

        if response.status_code in {401, 403}:
            self._metrics.provider_error(self.name, "authentication")
            raise ProviderAuthenticationError
        if response.status_code == 429:
            self._metrics.provider_error(self.name, "rate_limited")
            raise ProviderRateLimitedError
        if response.status_code >= 500:
            raise _RetryableProviderError
        if response.status_code >= 400:
            self._metrics.provider_error(self.name, "invalid_response")
            raise ProviderInvalidResponseError
        return response

    @staticmethod
    def _parse(payload: Any) -> IPinfoLiteResponse:
        return IPinfoLiteResponse.model_validate(payload)
