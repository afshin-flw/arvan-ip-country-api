import pytest

pytestmark = pytest.mark.api


async def test_web_ui_has_accessible_lookup_structure(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/")

    assert response.status_code == 200
    assert '<form id="lookup-form"' in response.text
    assert '<label for="ip-address">IP address</label>' in response.text
    assert 'id="ip-address"' in response.text
    assert 'type="submit"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'aria-live="assertive"' in response.text
    assert 'aria-busy="false"' in response.text


async def test_web_ui_contains_presentation_content(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/")

    expected = (
        "Find the country behind any public IP address",
        "FastAPI",
        "PostgreSQL",
        "Prometheus",
        "Built for the ArvanCloud Site Reliability Engineer Challenge",
    )
    assert all(text in response.text for text in expected)


async def test_web_ui_uses_only_local_frontend_assets(client) -> None:  # type: ignore[no-untyped-def]
    page = (await client.get("/")).text
    css = (await client.get("/static/app.css")).text
    javascript = (await client.get("/static/app.js")).text

    assert 'href="/static/app.css"' in page
    assert 'src="/static/app.js"' in page
    combined = page + css + javascript
    assert "https://" not in combined
    assert "http://" not in combined
    assert "@import" not in css
    assert "fonts.googleapis" not in combined


async def test_web_ui_javascript_preserves_api_contract(client) -> None:  # type: ignore[no-untyped-def]
    javascript = (await client.get("/static/app.js")).text

    assert 'const API_PATH = "/api/v1/lookups"' in javascript
    assert "fetch(API_PATH" in javascript
    assert 'method: "POST"' in javascript
    assert "JSON.stringify({ip})" in javascript
    for field in ("country_name", "country_code", "fetched_at", "expires_at"):
        assert f"payload.{field}" in javascript
    assert "payload.source" in javascript
    assert 'label: "Fresh provider lookup"' in javascript
    assert 'label: "PostgreSQL cache"' in javascript
    assert "AbortController" in javascript
    assert ".textContent" in javascript
    assert ".innerHTML" not in javascript


async def test_web_ui_maps_stable_error_codes(client) -> None:  # type: ignore[no-untyped-def]
    javascript = (await client.get("/static/app.js")).text

    expected_codes = (
        "INVALID_IP",
        "NON_PUBLIC_IP",
        "DATABASE_UNAVAILABLE",
        "PROVIDER_TIMEOUT",
        "PROVIDER_AUTHENTICATION_FAILED",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_INVALID_RESPONSE",
        "PROVIDER_UNAVAILABLE",
        "INTERNAL_ERROR",
    )
    assert all(f"{code}:" in javascript for code in expected_codes)


async def test_web_ui_css_covers_responsive_and_accessible_states(client) -> None:  # type: ignore[no-untyped-def]
    css = (await client.get("/static/app.css")).text

    assert "@media (max-width: 23.5rem)" in css
    assert "@media (max-width: 48rem)" in css
    assert "@media (prefers-color-scheme: dark)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
    assert "overflow-x: hidden" in css
    assert "overflow-wrap: anywhere" in css
