from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Awaitable, Callable, Protocol
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.core.config import get_database_settings


COMPANY_ENTITY_TYPE = "company"
STOCK_ENTITY_TYPE = "stock"

CORP_OUTLINE_GROUP = "corp_outline"
KRX_LISTED_ITEM_GROUP = "krx_listed_item"
AFFILIATE_GROUP = "affiliate"
CONS_SUBS_COMP_GROUP = "cons_subs_comp"
STOCK_PRICE_GROUP = "stock_price"

COMPANY_GROUP_TTLS = {
    CORP_OUTLINE_GROUP: timedelta(days=7),
    KRX_LISTED_ITEM_GROUP: timedelta(days=1),
    AFFILIATE_GROUP: timedelta(days=7),
    CONS_SUBS_COMP_GROUP: timedelta(days=7),
}

KOREA_TZ = ZoneInfo("Asia/Seoul")
KRX_OPEN = time(9, 0)
KRX_CLOSE = time(15, 30)


@dataclass(frozen=True)
class DataGroupRecord:
    payload: dict[str, Any]
    fetched_at: datetime
    expires_at: datetime
    source: str
    stale: bool = False


class DataGroupStore(Protocol):
    async def initialize(self) -> None:
        ...

    async def get_record(
        self,
        *,
        entity_type: str,
        entity_key: str,
        group_name: str,
        allow_stale: bool = False,
    ) -> DataGroupRecord | None:
        ...

    async def upsert_record(
        self,
        *,
        entity_type: str,
        entity_key: str,
        group_name: str,
        source: str,
        payload: dict[str, Any],
        ttl: timedelta | None,
    ) -> DataGroupRecord:
        ...


class PostgresDataGroupStore:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def initialize(self) -> None:
        from psycopg import AsyncConnection

        async with await AsyncConnection.connect(self._database_url) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS company_data_groups (
                        entity_type TEXT NOT NULL,
                        entity_key TEXT NOT NULL,
                        group_name TEXT NOT NULL,
                        source TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        fetched_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (entity_type, entity_key, group_name)
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_company_data_groups_expires_at
                    ON company_data_groups (expires_at)
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shareholder_sync_runs (
                        run_id BIGSERIAL PRIMARY KEY,
                        kind TEXT NOT NULL,
                        status TEXT NOT NULL,
                        designation_month TEXT,
                        row_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
                        error_message TEXT,
                        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        finished_at TIMESTAMPTZ
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS business_groups (
                        designation_month TEXT NOT NULL,
                        group_code TEXT NOT NULL,
                        group_name TEXT NOT NULL,
                        rank INTEGER,
                        asset_amount NUMERIC,
                        same_person_name TEXT,
                        representative_company_name TEXT,
                        company_count INTEGER,
                        source TEXT NOT NULL,
                        fetched_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (designation_month, group_code)
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_business_groups_rank
                    ON business_groups (designation_month, rank)
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS business_group_companies (
                        designation_month TEXT NOT NULL,
                        group_code TEXT NOT NULL,
                        company_name TEXT NOT NULL,
                        legal_registration_number TEXT,
                        business_registration_number TEXT,
                        representative_name TEXT,
                        included_on TEXT,
                        industry_name TEXT,
                        dart_corp_code TEXT,
                        stock_code TEXT,
                        source TEXT NOT NULL,
                        fetched_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (designation_month, group_code, company_name)
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_business_group_companies_identity
                    ON business_group_companies (
                        designation_month,
                        group_code,
                        company_name,
                        COALESCE(legal_registration_number, '')
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_business_group_companies_dart
                    ON business_group_companies (dart_corp_code)
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shareholder_entities (
                        entity_id TEXT PRIMARY KEY,
                        entity_type TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        normalized_name TEXT NOT NULL,
                        legal_registration_number TEXT,
                        dart_corp_code TEXT,
                        stock_code TEXT,
                        confidence_basis TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_shareholder_entities_name
                    ON shareholder_entities (normalized_name)
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shareholder_holdings (
                        entity_id TEXT NOT NULL REFERENCES shareholder_entities(entity_id),
                        held_company_corp_code TEXT,
                        held_company_name TEXT NOT NULL,
                        held_company_group_code TEXT,
                        report_year TEXT NOT NULL,
                        report_code TEXT NOT NULL,
                        relation TEXT,
                        share_class TEXT,
                        share_count NUMERIC,
                        holding_ratio NUMERIC,
                        source_endpoint TEXT NOT NULL,
                        source_receipt_no TEXT,
                        source_fetched_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (
                            entity_id,
                            held_company_name,
                            report_year,
                            report_code
                        )
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_shareholder_holdings_identity
                    ON shareholder_holdings (
                        entity_id,
                        COALESCE(held_company_corp_code, ''),
                        held_company_name,
                        report_year,
                        report_code,
                        COALESCE(share_class, '')
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_shareholder_holdings_company
                    ON shareholder_holdings (held_company_corp_code, held_company_name)
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shareholder_source_payloads (
                        source_key TEXT PRIMARY KEY,
                        source_endpoint TEXT NOT NULL,
                        corp_code TEXT NOT NULL,
                        report_year TEXT NOT NULL,
                        report_code TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        fetched_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            await conn.commit()

    async def get_record(
        self,
        *,
        entity_type: str,
        entity_key: str,
        group_name: str,
        allow_stale: bool = False,
    ) -> DataGroupRecord | None:
        from psycopg import AsyncConnection

        async with await AsyncConnection.connect(self._database_url) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT payload, fetched_at, expires_at, source
                    FROM company_data_groups
                    WHERE entity_type = %s
                      AND entity_key = %s
                      AND group_name = %s
                    """,
                    (entity_type, entity_key, group_name),
                )
                row = await cursor.fetchone()

        if row is None:
            return None

        payload, fetched_at, expires_at, source = row
        now = datetime.now(UTC)
        is_stale = expires_at <= now
        if is_stale and not allow_stale:
            return None

        return DataGroupRecord(
            payload=payload,
            fetched_at=fetched_at,
            expires_at=expires_at,
            source=source,
            stale=is_stale,
        )

    async def upsert_record(
        self,
        *,
        entity_type: str,
        entity_key: str,
        group_name: str,
        source: str,
        payload: dict[str, Any],
        ttl: timedelta | None,
    ) -> DataGroupRecord:
        from psycopg import AsyncConnection
        from psycopg.types.json import Jsonb

        fetched_at = datetime.now(UTC)
        expires_at = (
            datetime.max.replace(tzinfo=UTC)
            if ttl is None
            else fetched_at + ttl
        )
        async with await AsyncConnection.connect(self._database_url) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO company_data_groups (
                        entity_type,
                        entity_key,
                        group_name,
                        source,
                        payload,
                        fetched_at,
                        expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entity_type, entity_key, group_name)
                    DO UPDATE SET
                        source = EXCLUDED.source,
                        payload = EXCLUDED.payload,
                        fetched_at = EXCLUDED.fetched_at,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = now()
                    """,
                    (
                        entity_type,
                        entity_key,
                        group_name,
                        source,
                        Jsonb(payload),
                        fetched_at,
                        expires_at,
                    ),
                )
            await conn.commit()

        return DataGroupRecord(
            payload=payload,
            fetched_at=fetched_at,
            expires_at=expires_at,
            source=source,
        )


_default_store: DataGroupStore | None = None


def get_default_data_group_store() -> DataGroupStore | None:
    global _default_store
    if _default_store is not None:
        return _default_store

    settings = get_database_settings()
    if not settings.database_url:
        return None

    _default_store = PostgresDataGroupStore(settings.database_url)
    return _default_store


def company_group_ttl(group_name: str) -> timedelta:
    return COMPANY_GROUP_TTLS[group_name]


def is_krx_market_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    korea_now = current.astimezone(KOREA_TZ)
    return (
        korea_now.weekday() < 5
        and KRX_OPEN <= korea_now.time().replace(tzinfo=None) <= KRX_CLOSE
    )


def stock_price_ttl(
    exchange: str | None,
    window: str | None,
    now: datetime | None = None,
) -> timedelta:
    normalized_window = (window or "1D").upper()
    is_realtime_window = normalized_window in {"1D", "5D"}
    market_is_open = (exchange or "").upper() == "KRX" and is_krx_market_open(now)

    if normalized_window == "1D":
        return timedelta(minutes=1 if market_is_open else 10)
    if normalized_window == "5D":
        return timedelta(minutes=5 if market_is_open else 30)
    if normalized_window in {"1M", "3M"}:
        return timedelta(minutes=30)
    if normalized_window in {"6M", "YTD"}:
        return timedelta(hours=2)
    if normalized_window == "1Y":
        return timedelta(hours=4)
    if normalized_window in {"5Y", "MAX", "ALL"}:
        return timedelta(days=1)
    if is_realtime_window:
        return timedelta(minutes=5 if market_is_open else 30)
    return timedelta(hours=1)


def stock_entity_key(
    *,
    q: str | None,
    stock_code: str | None,
    exchange: str | None,
    language: str | None,
    window: str | None,
) -> str:
    normalized_exchange = (exchange or "").upper()
    normalized_window = window or ""
    normalized_language = language or ""
    normalized_code = stock_code or q or ""
    return ":".join(
        [
            normalized_exchange or "UNKNOWN",
            normalized_code.replace(":", "_"),
            normalized_language or "default",
            normalized_window or "default",
        ]
    )


def with_group_meta(
    payload: dict[str, Any],
    *,
    source: str,
    group_name: str,
    fetched_at: datetime,
    expires_at: datetime,
    stale: bool = False,
) -> dict[str, Any]:
    ttl_seconds = (
        None
        if expires_at.year >= 9999
        else max(int((expires_at - fetched_at).total_seconds()), 0)
    )
    return {
        **payload,
        "_meta": {
            **payload.get("_meta", {}),
            "source": source,
            "cache_group": group_name,
            "fetched_at": fetched_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "ttl_seconds": ttl_seconds,
            "stale": stale,
        },
    }


async def fetch_with_group_store(
    *,
    store: DataGroupStore | None,
    entity_type: str,
    entity_key: str,
    group_name: str,
    source: str,
    ttl: timedelta | None,
    fetcher: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    if store is None:
        return await fetcher()

    fresh = await store.get_record(
        entity_type=entity_type,
        entity_key=entity_key,
        group_name=group_name,
    )
    if fresh is not None:
        return with_group_meta(
            fresh.payload,
            source=fresh.source,
            group_name=group_name,
            fetched_at=fresh.fetched_at,
            expires_at=fresh.expires_at,
            stale=fresh.stale,
        )

    try:
        payload = await fetcher()
    except HTTPException:
        stale = await store.get_record(
            entity_type=entity_type,
            entity_key=entity_key,
            group_name=group_name,
            allow_stale=True,
        )
        if stale is None:
            raise
        return with_group_meta(
            stale.payload,
            source=stale.source,
            group_name=group_name,
            fetched_at=stale.fetched_at,
            expires_at=stale.expires_at,
            stale=True,
        )

    record = await store.upsert_record(
        entity_type=entity_type,
        entity_key=entity_key,
        group_name=group_name,
        source=source,
        payload=payload,
        ttl=ttl,
    )
    return with_group_meta(
        payload,
        source=record.source,
        group_name=group_name,
        fetched_at=record.fetched_at,
        expires_at=record.expires_at,
        stale=record.stale,
    )
