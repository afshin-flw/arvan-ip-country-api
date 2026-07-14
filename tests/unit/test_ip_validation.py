import pytest

from ip_country_api.domain.errors import InvalidIPError, NonPublicIPError
from ip_country_api.domain.ip_validation import validate_public_ip

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [("8.8.8.8", "8.8.8.8"), ("2001:4860:4860:0:0:0:0:8888", "2001:4860:4860::8888")],
)
def test_accepts_and_normalizes_public_addresses(raw: str, normalized: str) -> None:
    assert str(validate_public_ip(raw)) == normalized


@pytest.mark.parametrize("raw", ["not-an-ip", "999.1.1.1", ""])
def test_rejects_malformed_addresses(raw: str) -> None:
    with pytest.raises(InvalidIPError):
        validate_public_ip(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "10.0.0.1",
        "fd00::1",
        "127.0.0.1",
        "::1",
        "169.254.1.1",
        "fe80::1",
        "224.0.0.1",
        "ff02::1",
        "0.0.0.0",
        "::",
        "192.0.2.1",
    ],
)
def test_rejects_every_non_global_address(raw: str) -> None:
    with pytest.raises(NonPublicIPError):
        validate_public_ip(raw)
