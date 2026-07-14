import pytest
from sqlalchemy.exc import SQLAlchemyError

from ip_country_api.domain.errors import DatabaseUnavailableError
from ip_country_api.domain.ip_validation import validate_public_ip
from ip_country_api.repositories.ip_lookup_repository import PostgreSQLLookupRepository

pytestmark = pytest.mark.unit


class BrokenSessionContext:
    async def __aenter__(self):  # type: ignore[no-untyped-def]
        raise SQLAlchemyError("internal database detail")

    async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
        return False


def broken_factory() -> BrokenSessionContext:
    return BrokenSessionContext()


async def test_database_error_is_translated(metrics) -> None:  # type: ignore[no-untyped-def]
    repository = PostgreSQLLookupRepository(broken_factory, metrics)  # type: ignore[arg-type]
    with pytest.raises(DatabaseUnavailableError) as raised:
        await repository.get(validate_public_ip("8.8.8.8"))
    assert "internal database detail" not in str(raised.value)
