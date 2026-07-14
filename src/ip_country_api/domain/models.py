from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IPAddress = IPv4Address | IPv6Address


@dataclass(frozen=True, slots=True)
class GeoIPResult:
    country_code: str
    country_name: str
    provider: str


@dataclass(frozen=True, slots=True)
class CacheRecord:
    ip: IPAddress
    country_code: str
    country_name: str
    provider: str
    fetched_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LookupResult:
    ip: IPAddress
    country_code: str
    country_name: str
    source: Literal["database", "provider"]
    fetched_at: datetime
    expires_at: datetime


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ip: str = Field(min_length=2, max_length=45, examples=["8.8.8.8"])


class LookupResponse(BaseModel):
    ip: str
    country_code: str
    country_name: str
    source: Literal["database", "provider"]
    fetched_at: datetime
    expires_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
