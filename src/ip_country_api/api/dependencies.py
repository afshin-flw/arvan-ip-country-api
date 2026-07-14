from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Request

from ip_country_api.services.ip_lookup_service import IPLookupService

ReadinessCheck = Callable[[], Awaitable[None]]


def get_lookup_service(request: Request) -> IPLookupService:
    return cast(IPLookupService, request.app.state.lookup_service)


def get_readiness_check(request: Request) -> ReadinessCheck:
    return cast(ReadinessCheck, request.app.state.readiness_check)
