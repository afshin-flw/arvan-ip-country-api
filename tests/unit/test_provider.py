import httpx
import pytest

from ip_country_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from ip_country_api.domain.ip_validation import validate_public_ip
from ip_country_api.providers.ipinfo import IPinfoLiteProvider

pytestmark = pytest.mark.unit


def provider_for(handler, metrics, max_retries: int = 0) -> IPinfoLiteProvider:  # type: ignore[no-untyped-def]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://provider.test"
    )
    return IPinfoLiteProvider(client, "explicit-test-placeholder", max_retries, metrics)


async def test_provider_success(metrics) -> None:  # type: ignore[no-untyped-def]
    provider = provider_for(
        lambda request: httpx.Response(
            200, json={"country_code": "us", "country": "United States"}, request=request
        ),
        metrics,
    )
    result = await provider.lookup(validate_public_ip("8.8.8.8"))
    assert result.country_code == "US"
    assert result.country_name == "United States"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (429, ProviderRateLimitedError),
    ],
)
async def test_provider_maps_status(status: int, error: type[Exception], metrics) -> None:  # type: ignore[no-untyped-def]
    provider = provider_for(lambda request: httpx.Response(status, request=request), metrics)
    with pytest.raises(error):
        await provider.lookup(validate_public_ip("8.8.8.8"))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"country_code": "USA", "country": "United States"},
        {"country_code": "US", "country": ""},
    ],
)
async def test_provider_rejects_malformed_response(payload: object, metrics) -> None:  # type: ignore[no-untyped-def]
    provider = provider_for(
        lambda request: httpx.Response(200, json=payload, request=request), metrics
    )
    with pytest.raises(ProviderInvalidResponseError):
        await provider.lookup(validate_public_ip("8.8.8.8"))


async def test_provider_maps_timeout(metrics) -> None:  # type: ignore[no-untyped-def]
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout", request=request)

    provider = provider_for(timeout, metrics)
    with pytest.raises(ProviderTimeoutError):
        await provider.lookup(validate_public_ip("8.8.8.8"))


async def test_provider_retries_unavailability_with_a_strict_bound(metrics) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def unavailable(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="internal upstream detail", request=request)

    provider = provider_for(unavailable, metrics, max_retries=2)
    with pytest.raises(ProviderUnavailableError) as raised:
        await provider.lookup(validate_public_ip("8.8.8.8"))
    assert calls == 3
    assert "internal upstream detail" not in str(raised.value)


async def test_provider_retries_timeout_with_a_strict_bound(metrics) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("internal timeout detail", request=request)

    provider = provider_for(timeout, metrics, max_retries=1)
    with pytest.raises(ProviderTimeoutError) as raised:
        await provider.lookup(validate_public_ip("8.8.8.8"))
    assert calls == 2
    assert "internal timeout detail" not in str(raised.value)
