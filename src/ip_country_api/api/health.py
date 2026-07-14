from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ip_country_api.api.dependencies import ReadinessCheck, get_readiness_check
from ip_country_api.domain.errors import (
    DatabaseSchemaUnavailableError,
    DatabaseUnavailableError,
)

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live(request: Request) -> dict[str, str]:
    return {"status": "alive", "version": request.app.state.app_version}


@router.get("/health/ready")
async def ready(
    request: Request,
    check: Annotated[ReadinessCheck, Depends(get_readiness_check)],
) -> JSONResponse:
    try:
        await check()
    except DatabaseSchemaUnavailableError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "available",
                "schema": "unavailable",
                "version": request.app.state.app_version,
            },
        )
    except DatabaseUnavailableError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "unavailable",
                "schema": "unknown",
                "version": request.app.state.app_version,
            },
        )
    return JSONResponse(
        content={
            "status": "ready",
            "database": "available",
            "schema": "available",
            "version": request.app.state.app_version,
        }
    )
