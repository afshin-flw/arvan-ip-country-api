import re
from contextvars import ContextVar
from uuid import uuid4

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
request_id_context: ContextVar[str] = ContextVar("request_id", default="unknown")


def valid_request_id(value: str | None) -> bool:
    return value is not None and REQUEST_ID_PATTERN.fullmatch(value) is not None


def request_id_or_new(value: str | None) -> str:
    if value is not None and valid_request_id(value):
        return value
    return str(uuid4())
