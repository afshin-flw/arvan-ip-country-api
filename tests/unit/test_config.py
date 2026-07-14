import pytest
from pydantic import SecretStr, ValidationError

from ip_country_api.config import Settings

pytestmark = pytest.mark.unit


def test_fake_provider_needs_no_token_outside_production() -> None:
    settings = Settings(
        app_env="development",
        database_url=SecretStr("postgresql+psycopg://localhost/test"),
        geoip_provider="fake",
    )
    assert settings.ipinfo_token is None


def test_fake_provider_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            database_url=SecretStr("postgresql+psycopg://localhost/test"),
            geoip_provider="fake",
        )


def test_ipinfo_requires_token() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="development",
            database_url=SecretStr("postgresql+psycopg://localhost/test"),
            geoip_provider="ipinfo",
        )
