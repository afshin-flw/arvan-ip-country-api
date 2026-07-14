import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ip_country_api.domain.errors import AppError
from ip_country_api.observability.request_context import request_id_context

logger = structlog.get_logger()


def _envelope(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message, "request_id": request_id_context.get()}}


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    logger.warning("request_failed", error_type=exc.code)
    return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message))


async def validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_envelope("INVALID_IP", "The request must contain one valid IP address."),
    )


async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    # Keep the event deliberately bounded. Arbitrary exception text and traceback
    # content can include driver or upstream details and therefore are not logged.
    logger.error("unexpected_request_failure", error_type="INTERNAL_ERROR")
    return JSONResponse(
        status_code=500,
        content=_envelope("INTERNAL_ERROR", "An unexpected error occurred."),
    )
