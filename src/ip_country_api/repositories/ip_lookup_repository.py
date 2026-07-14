from datetime import UTC, datetime
from ipaddress import ip_address
from time import perf_counter
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ip_country_api.database.models import IPLookupCache
from ip_country_api.domain.errors import DatabaseUnavailableError
from ip_country_api.domain.models import CacheRecord, IPAddress
from ip_country_api.observability.metrics import ApplicationMetrics


class LookupRepository(Protocol):
    async def get(self, ip: IPAddress) -> CacheRecord | None: ...

    async def upsert(self, record: CacheRecord) -> None: ...


class PostgreSQLLookupRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        metrics: ApplicationMetrics,
    ) -> None:
        self._session_factory = session_factory
        self._metrics = metrics

    async def get(self, ip: IPAddress) -> CacheRecord | None:
        started = perf_counter()
        try:
            async with self._session_factory() as session:
                row = await session.scalar(
                    select(IPLookupCache).where(IPLookupCache.ip_address == str(ip))
                )
        except (DBAPIError, SQLAlchemyError) as exc:
            self._metrics.database_error("read", "unavailable")
            raise DatabaseUnavailableError from exc
        finally:
            self._metrics.database_operation("read", perf_counter() - started)

        if row is None:
            return None
        return CacheRecord(
            ip=ip_address(str(row.ip_address)),
            country_code=row.country_code,
            country_name=row.country_name,
            provider=row.provider,
            fetched_at=_utc(row.fetched_at),
            expires_at=_utc(row.expires_at),
        )

    async def upsert(self, record: CacheRecord) -> None:
        started = perf_counter()
        now = datetime.now(UTC)
        statement = insert(IPLookupCache).values(
            ip_address=str(record.ip),
            country_code=record.country_code,
            country_name=record.country_name,
            provider=record.provider,
            fetched_at=record.fetched_at,
            expires_at=record.expires_at,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[IPLookupCache.ip_address],
            set_={
                "country_code": statement.excluded.country_code,
                "country_name": statement.excluded.country_name,
                "provider": statement.excluded.provider,
                "fetched_at": statement.excluded.fetched_at,
                "expires_at": statement.excluded.expires_at,
                "updated_at": now,
            },
        )
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(statement)
        except (DBAPIError, SQLAlchemyError) as exc:
            self._metrics.database_error("upsert", "unavailable")
            raise DatabaseUnavailableError from exc
        finally:
            self._metrics.database_operation("upsert", perf_counter() - started)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
