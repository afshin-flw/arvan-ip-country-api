from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-only runtime configuration.

    Database and provider credentials intentionally have no fallback values.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "IP Country API"
    app_env: str = "production"
    app_version: str = "0.1.0"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    database_url: SecretStr
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    database_connect_timeout_seconds: int = Field(default=5, gt=0, le=60)

    geoip_provider: Literal["ipinfo"] = "ipinfo"
    geoip_provider_base_url: str = "https://api.ipinfo.io"
    ipinfo_token: SecretStr
    geoip_provider_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    geoip_provider_max_retries: int = Field(default=2, ge=0, le=5)
    geoip_cache_ttl_seconds: int = Field(default=2_592_000, ge=60, le=31_536_000)

    metrics_enabled: bool = True
    cors_allowed_origins: list[str] = Field(default_factory=list)
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value()
        if not url.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("DATABASE_URL must use PostgreSQL with psycopg")
        return value

    @field_validator("ipinfo_token")
    @classmethod
    def require_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("IPINFO_TOKEN must not be empty")
        return value

    @field_validator("geoip_provider_base_url")
    @classmethod
    def validate_provider_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("provider URL must use HTTPS (except local test endpoints)")
        return value.rstrip("/")

    def public_summary(self) -> dict[str, str | int | float | bool]:
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "app_version": self.app_version,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "geoip_provider": self.geoip_provider,
            "provider_timeout_seconds": self.geoip_provider_timeout_seconds,
            "provider_max_retries": self.geoip_provider_max_retries,
            "cache_ttl_seconds": self.geoip_cache_ttl_seconds,
            "metrics_enabled": self.metrics_enabled,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
