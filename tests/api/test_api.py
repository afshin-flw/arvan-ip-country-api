from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest

from ip_country_api.domain.errors import (
    DatabaseSchemaUnavailableError,
    DatabaseUnavailableError,
)
from ip_country_api.domain.models import LookupResult

pytestmark = pytest.mark.api


class StubService:
    def __init__(self, source: str = "provider") -> None:
        self.source = source

    async def lookup(self, _value: str) -> LookupResult:
        now = datetime(2026, 7, 14, 12, tzinfo=UTC)
        return LookupResult(
            ip=ip_address("8.8.8.8"),
            country_code="US",
            country_name="United States",
            source=self.source,  # type: ignore[arg-type]
            fetched_at=now,
            expires_at=now + timedelta(days=30),
        )


class BrokenService:
    async def lookup(self, _value: str) -> LookupResult:
        raise RuntimeError("internal detail must not reach the response")


@pytest.mark.parametrize("source", ["provider", "database"])
async def test_successful_lookup(client, source: str) -> None:  # type: ignore[no-untyped-def]
    client._transport.app.state.lookup_service = StubService(source)  # type: ignore[attr-defined]
    response = await client.post("/api/v1/lookups", json={"ip": "8.8.8.8"})
    assert response.status_code == 200
    assert response.json()["source"] == source
    assert response.json()["ip"] == "8.8.8.8"


@pytest.mark.parametrize(
    "payload", [{}, {"ip": "bad"}, {"ip": "127.0.0.1"}, {"ip": "8.8.8.8", "extra": 1}]
)
async def test_stable_error_envelope(client, payload: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
    from ip_country_api.observability.metrics import ApplicationMetrics
    from ip_country_api.services.ip_lookup_service import IPLookupService
    from tests.conftest import FakeProvider, FakeRepository

    client._transport.app.state.lookup_service = IPLookupService(  # type: ignore[attr-defined]
        FakeRepository(), FakeProvider(), 300, ApplicationMetrics("test")
    )
    response = await client.post("/api/v1/lookups", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}


async def test_request_id_is_generated(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


async def test_valid_request_id_is_propagated(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/health/live", headers={"X-Request-ID": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"


async def test_invalid_request_id_is_replaced(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/health/live", headers={"X-Request-ID": "contains spaces"})
    assert response.headers["x-request-id"] != "contains spaces"


async def test_liveness(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/health/live")
    assert response.json() == {"status": "alive", "version": "0.1.0"}


async def test_readiness_success(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["schema"] == "available"


async def test_readiness_failure(client) -> None:  # type: ignore[no-untyped-def]
    async def unavailable() -> None:
        raise DatabaseUnavailableError

    client._transport.app.state.readiness_check = unavailable  # type: ignore[attr-defined]
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


async def test_readiness_schema_failure(client) -> None:  # type: ignore[no-untyped-def]
    async def unavailable() -> None:
        raise DatabaseSchemaUnavailableError

    client._transport.app.state.readiness_check = unavailable  # type: ignore[attr-defined]
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "available"
    assert response.json()["schema"] == "unavailable"


async def test_metrics_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "ip_country_build_info" in response.text
    assert "ip_country_lookup_total" in response.text


async def test_web_page(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/")
    assert response.status_code == 200
    assert "IP country lookup" in response.text
    assert 'id="lookup-form"' in response.text


async def test_openapi_routes(client) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/redoc")).status_code == 200
    assert (await client.get("/openapi.json")).status_code == 200


async def test_unexpected_error_is_sanitized(client) -> None:  # type: ignore[no-untyped-def]
    client._transport.app.state.lookup_service = BrokenService()  # type: ignore[attr-defined]
    response = await client.post("/api/v1/lookups", json={"ip": "8.8.8.8"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "internal detail" not in response.text
