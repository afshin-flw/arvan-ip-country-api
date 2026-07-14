import pytest

from ip_country_api.domain.errors import ProviderInvalidResponseError
from ip_country_api.domain.ip_validation import validate_public_ip
from ip_country_api.providers.fake import FakeGeoIPProvider

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("ip", "code", "name"),
    [
        ("8.8.8.8", "US", "United States"),
        ("1.1.1.1", "AU", "Australia"),
        ("2001:4860:4860::8888", "US", "United States"),
    ],
)
async def test_fake_provider_returns_documented_fixture(
    ip: str, code: str, name: str, metrics
) -> None:  # type: ignore[no-untyped-def]
    result = await FakeGeoIPProvider(metrics).lookup(validate_public_ip(ip))
    assert result.country_code == code
    assert result.country_name == name
    assert result.provider == "fake"


async def test_fake_provider_rejects_unknown_public_ip(metrics) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ProviderInvalidResponseError):
        await FakeGeoIPProvider(metrics).lookup(validate_public_ip("9.9.9.9"))
