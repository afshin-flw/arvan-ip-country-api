from typing import Annotated

from fastapi import APIRouter, Depends

from ip_country_api.api.dependencies import get_lookup_service
from ip_country_api.domain.models import ErrorResponse, LookupRequest, LookupResponse
from ip_country_api.services.ip_lookup_service import IPLookupService

router = APIRouter(prefix="/api/v1/lookups", tags=["lookups"])


@router.post(
    "",
    response_model=LookupResponse,
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def create_lookup(
    payload: LookupRequest,
    service: Annotated[IPLookupService, Depends(get_lookup_service)],
) -> LookupResponse:
    result = await service.lookup(payload.ip)
    return LookupResponse(
        ip=str(result.ip),
        country_code=result.country_code,
        country_name=result.country_name,
        source=result.source,
        fetched_at=result.fetched_at,
        expires_at=result.expires_at,
    )
