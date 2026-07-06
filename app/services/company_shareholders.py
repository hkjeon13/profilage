from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Any

from fastapi import HTTPException
import httpx

from app.core.config import get_business_group_api_settings, get_database_settings
from app.services.company_dart import (
    DartCompanyService,
    DartCorpCodeQuery,
    DartPeriodicReportInfoQuery,
)


BUSINESS_GROUP_SOURCE = "ftc:business_group_portal"
SHAREHOLDER_SOURCE = "dart:hyslrSttus"
CORPORATION_SUFFIXES = (
    "주식회사",
    "(주)",
    "㈜",
    "유한회사",
    "합자회사",
    "합명회사",
    "사단법인",
    "재단법인",
)


@dataclass(frozen=True)
class BusinessGroupSyncResult:
    designation_month: str
    groups: int
    companies: int


def _items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    body_items = ((payload.get("response") or {}).get("body") or {}).get("items")
    if isinstance(body_items, dict):
        item = body_items.get("item")
        if isinstance(item, list):
            return [row for row in item if isinstance(row, dict)]
        if isinstance(item, dict):
            return [item]
    if isinstance(body_items, list):
        return [row for row in body_items if isinstance(row, dict)]
    item = (((payload.get("body") or {}).get("items") or {}).get("item"))
    if isinstance(item, list):
        return [row for row in item if isinstance(row, dict)]
    if isinstance(item, dict):
        return [item]
    if isinstance(payload.get("list"), list):
        return [row for row in payload["list"] if isinstance(row, dict)]
    return []


def _first_value(row: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    cleaned = str(value).replace(",", "").replace("%", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_shareholder_name(name: str | None) -> str:
    normalized = "".join(str(name or "").split()).lower()
    for suffix in CORPORATION_SUFFIXES:
        normalized = normalized.replace(suffix.lower(), "")
    return normalized


def classify_shareholder(
    *,
    name: str | None,
    legal_registration_number: str | None = None,
    dart_corp_code: str | None = None,
    stock_code: str | None = None,
    executive_match: bool = False,
) -> str:
    if legal_registration_number or dart_corp_code or stock_code:
        return "corporation"
    if any(suffix in str(name or "") for suffix in CORPORATION_SUFFIXES):
        return "corporation"
    if executive_match:
        return "individual"
    if name:
        return "individual"
    return "unknown"


def entity_confidence(entity_type: str, durable_identifier: bool) -> str:
    if durable_identifier:
        return "high"
    if entity_type == "corporation":
        return "medium"
    return "low"


def shareholder_entity_id(
    *,
    name: str,
    legal_registration_number: str | None = None,
    dart_corp_code: str | None = None,
    stock_code: str | None = None,
) -> str:
    durable = legal_registration_number or dart_corp_code or stock_code
    basis = durable or normalize_shareholder_name(name)
    digest = hashlib.sha1(str(basis).encode("utf-8")).hexdigest()[:16]
    return f"sh_{digest}"


def normalize_business_group(row: dict[str, Any]) -> dict[str, Any]:
    group_code = _first_value(row, ["entrprsgrpCode", "bzentyGrpCd", "grpCode", "group_code"])
    group_name = _first_value(row, ["entrprsgrpNm", "bzentyGrpNm", "grpNm", "group_name"])
    rank = _number(_first_value(row, ["rank", "ord", "assetsRank", "assetRank", "ordr"]))
    asset_amount = _number(
        _first_value(row, ["assetsTotamt", "assetTotamt", "assetAmount", "totAssets"])
    )
    if not group_code and group_name:
        group_code = normalize_shareholder_name(group_name)
    if not group_code or not group_name:
        raise ValueError("business group row requires code and name")
    return {
        "group_code": group_code,
        "group_name": group_name,
        "rank": int(rank) if rank is not None else None,
        "asset_amount": asset_amount,
        "same_person_name": _first_value(row, ["samePersonNm", "unityNm", "indvdlNm"]),
        "representative_company_name": _first_value(
            row, ["reprsntCmpyNm", "rprsCmpyNm", "representativeCompanyName"]
        ),
        "company_count": int(_number(_first_value(row, ["affltsCo", "companyCount", "cmpyCnt"])) or 0)
        or None,
    }


def normalize_business_group_company(
    row: dict[str, Any],
    *,
    group_code: str,
) -> dict[str, Any]:
    company_name = _first_value(row, ["corpNm", "cmpyNm", "afilCmpyNm", "company_name"])
    if not company_name:
        raise ValueError("business group company row requires company name")
    return {
        "group_code": group_code,
        "company_name": company_name,
        "legal_registration_number": _first_value(row, ["jurirNo", "crno", "corpRegNo"]),
        "business_registration_number": _first_value(row, ["bizrNo", "bzno", "businessNumber"]),
        "representative_name": _first_value(row, ["rprsntvNm", "ceoNm", "representativeName"]),
        "included_on": _first_value(row, ["incDate", "includedOn", "afilDt"]),
        "industry_name": _first_value(row, ["indutyNm", "industryName", "mainBizNm"]),
        "dart_corp_code": _first_value(row, ["corpCode", "dartCorpCode"]),
        "stock_code": _first_value(row, ["stockCode", "srtnCd"]),
    }


def select_top_business_groups(
    rows: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    normalized = [normalize_business_group(row) for row in rows]
    if any(group["rank"] is not None for group in normalized):
        return sorted(
            normalized,
            key=lambda group: (
                group["rank"] if group["rank"] is not None else 999999,
                group["group_name"],
            ),
        )[:limit]
    if any(group["asset_amount"] is not None for group in normalized):
        return sorted(
            normalized,
            key=lambda group: (
                -(group["asset_amount"] or 0),
                group["group_name"],
            ),
        )[:limit]
    raise ValueError("official rank or asset amount is required to select top groups")


def normalize_holding_rows(
    *,
    shareholder_payload: dict[str, Any] | None,
    executives_payload: dict[str, Any] | None,
    held_company_name: str,
    held_company_corp_code: str | None,
    held_company_group_code: str | None,
    report_year: str,
    report_code: str,
) -> list[dict[str, Any]]:
    executive_names = {
        normalize_shareholder_name(_first_value(row, ["nm", "name"]))
        for row in _items(executives_payload)
    }
    holdings = []
    for row in _items(shareholder_payload):
        name = _first_value(row, ["nm", "holder_nm", "stockholdr_nm"])
        if not name or name in {"계", "합계", "소계", "총계"}:
            continue
        ratio = _number(
            _first_value(row, ["bsis_posesn_stock_qota_rt", "posesn_stock_qota_rt", "stock_qota_rt"])
        )
        normalized_name = normalize_shareholder_name(name)
        entity_type = classify_shareholder(
            name=name,
            executive_match=normalized_name in executive_names,
        )
        confidence = entity_confidence(entity_type, durable_identifier=False)
        entity_id = shareholder_entity_id(name=name)
        holdings.append(
            {
                "entity": {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "display_name": name,
                    "normalized_name": normalized_name,
                    "legal_registration_number": None,
                    "dart_corp_code": None,
                    "stock_code": None,
                    "confidence_basis": confidence,
                },
                "holding": {
                    "entity_id": entity_id,
                    "held_company_corp_code": held_company_corp_code,
                    "held_company_name": held_company_name,
                    "held_company_group_code": held_company_group_code,
                    "report_year": report_year,
                    "report_code": report_code,
                    "relation": _first_value(row, ["relate", "relate_nm"]),
                    "share_class": _first_value(row, ["stock_knd", "stockKnd"]),
                    "share_count": _number(
                        _first_value(
                            row,
                            [
                                "bsis_posesn_stock_co",
                                "trmend_posesn_stock_co",
                                "posesn_stock_co",
                            ],
                        )
                    ),
                    "holding_ratio": ratio,
                    "source_endpoint": SHAREHOLDER_SOURCE,
                    "source_receipt_no": _first_value(row, ["rcept_no", "rceptNo"]),
                },
            }
        )
    return holdings


class BusinessGroupShareholderService:
    def __init__(
        self,
        *,
        database_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._database_url = database_url if database_url is not None else get_database_settings().database_url
        self._transport = transport

    async def search(
        self,
        *,
        name: str,
        corp_code: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        normalized_name = normalize_shareholder_name(name)
        if not self._database_url or not normalized_name:
            return {
                "query": {"name": name, "normalized_name": normalized_name, "corp_code": corp_code},
                "matches": [],
                "corpus": {"available": False},
            }

        from psycopg import AsyncConnection
        from psycopg.rows import dict_row

        async with await AsyncConnection.connect(self._database_url, row_factory=dict_row) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        se.entity_id,
                        se.entity_type,
                        se.display_name,
                        se.normalized_name,
                        se.confidence_basis,
                        sh.held_company_corp_code,
                        sh.held_company_name,
                        sh.held_company_group_code,
                        bg.group_name,
                        sh.report_year,
                        sh.report_code,
                        sh.relation,
                        sh.share_class,
                        sh.share_count,
                        sh.holding_ratio,
                        sh.source_endpoint,
                        sh.source_receipt_no,
                        sh.source_fetched_at
                    FROM shareholder_entities se
                    JOIN shareholder_holdings sh ON sh.entity_id = se.entity_id
                    LEFT JOIN business_groups bg
                      ON bg.group_code = sh.held_company_group_code
                     AND bg.designation_month = (
                        SELECT MAX(designation_month) FROM business_groups
                     )
                    WHERE se.normalized_name = %s
                      AND (%s::text IS NULL OR sh.held_company_corp_code IS DISTINCT FROM %s::text)
                    ORDER BY
                        CASE se.confidence_basis
                            WHEN 'high' THEN 1
                            WHEN 'medium' THEN 2
                            ELSE 3
                        END,
                        sh.holding_ratio DESC NULLS LAST,
                        sh.held_company_name
                    LIMIT %s
                    """,
                    (normalized_name, corp_code, corp_code, limit),
                )
                rows = await cursor.fetchall()

        return {
            "query": {"name": name, "normalized_name": normalized_name, "corp_code": corp_code},
            "matches": [self._public_match(row) for row in rows],
            "corpus": {"available": True},
        }

    async def sync_top_business_groups(self, *, designation_month: str | None = None) -> BusinessGroupSyncResult:
        if not self._database_url:
            raise HTTPException(status_code=503, detail="DATABASE_URL must be configured")

        settings = get_business_group_api_settings()
        if not settings.service_key:
            raise HTTPException(status_code=503, detail="BUSINESS_GROUP_SERVICE_KEY must be configured")

        active_month = designation_month or datetime.now(UTC).strftime("%Y%m")
        group_payload = await self._fetch_business_group_api(settings.groups_path, active_month)
        rank_payload = await self._fetch_business_group_api(settings.asset_ranks_path, active_month)
        group_rows = _items(rank_payload) or _items(group_payload)
        groups = select_top_business_groups(group_rows, limit=20)
        companies = []
        for group in groups:
            company_payload = await self._fetch_business_group_api(
                settings.companies_path,
                active_month,
                group_code=group["group_code"],
                group_name=group["group_name"],
            )
            companies.extend(
                normalize_business_group_company(row, group_code=group["group_code"])
                for row in _items(company_payload)
            )
        await self._store_groups_and_companies(
            designation_month=active_month,
            groups=groups,
            companies=companies,
        )
        return BusinessGroupSyncResult(
            designation_month=active_month,
            groups=len(groups),
            companies=len(companies),
        )

    async def index_dart_holdings(
        self,
        *,
        report_year: str,
        report_code: str = "11011",
        limit: int = 200,
    ) -> dict[str, Any]:
        if not self._database_url:
            raise HTTPException(status_code=503, detail="DATABASE_URL must be configured")

        companies = await self._latest_group_companies(limit=limit)
        dart_service = DartCompanyService(transport=self._transport)
        indexed = 0
        skipped = 0
        holdings_total = 0
        for company in companies:
            corp_code = company.get("dart_corp_code") or await self._resolve_dart_corp_code(
                dart_service=dart_service,
                company=company,
            )
            if not corp_code:
                skipped += 1
                continue
            shareholder_payload = await dart_service.get_periodic_report_info(
                DartPeriodicReportInfoQuery(
                    corp_code=corp_code,
                    business_year=report_year,
                    report_code=report_code,
                    kind="major_shareholders",
                )
            )
            people_payload = await dart_service.get_company_people_sources(
                corp_code=corp_code,
                business_year=report_year,
                report_code=report_code,
            )
            normalized = normalize_holding_rows(
                shareholder_payload=shareholder_payload,
                executives_payload=people_payload.get("executives"),
                held_company_name=company["company_name"],
                held_company_corp_code=corp_code,
                held_company_group_code=company.get("group_code"),
                report_year=report_year,
                report_code=report_code,
            )
            await self._store_holding_rows(normalized)
            indexed += 1
            holdings_total += len(normalized)
        return {
            "report_year": report_year,
            "report_code": report_code,
            "indexed_companies": indexed,
            "skipped_companies": skipped,
            "holdings": holdings_total,
        }

    async def _fetch_business_group_api(
        self,
        path: str,
        designation_month: str,
        *,
        group_code: str | None = None,
        group_name: str | None = None,
    ) -> dict[str, Any]:
        settings = get_business_group_api_settings()
        params: dict[str, Any] = {
            "serviceKey": settings.service_key,
            "resultType": "json",
            "pageNo": 1,
            "numOfRows": 1000,
            "presentnYear": designation_month[:4],
        }
        if len(designation_month) >= 6:
            params["presentnMonth"] = designation_month[4:6]
        if group_code:
            params["entrprsgrpCode"] = group_code
            params["bzentyGrpCd"] = group_code
        if group_name:
            params["entrprsgrpNm"] = group_name
            params["bzentyGrpNm"] = group_name

        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                response = await client.get(f"{settings.base_url}{path}", params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"business group API failed with status {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="business group API request failed") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="business group API returned non-JSON") from exc

    async def _latest_group_companies(self, *, limit: int) -> list[dict[str, Any]]:
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row

        async with await AsyncConnection.connect(self._database_url, row_factory=dict_row) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        designation_month,
                        group_code,
                        company_name,
                        legal_registration_number,
                        dart_corp_code,
                        stock_code
                    FROM business_group_companies
                    WHERE designation_month = (
                        SELECT MAX(designation_month) FROM business_group_companies
                    )
                    ORDER BY group_code, company_name
                    LIMIT %s
                    """,
                    (limit,),
                )
                return await cursor.fetchall()

    async def _resolve_dart_corp_code(
        self,
        *,
        dart_service: DartCompanyService,
        company: dict[str, Any],
    ) -> str | None:
        payload = await dart_service.find_corp_code(
            DartCorpCodeQuery(
                corporate_registration_number=company.get("legal_registration_number"),
                stock_code=company.get("stock_code"),
                company_name=company.get("company_name"),
            )
        )
        corp_code = (payload.get("match") or {}).get("corp_code")
        if corp_code:
            await self._update_company_dart_corp_code(company=company, corp_code=corp_code)
        return corp_code

    async def _update_company_dart_corp_code(
        self,
        *,
        company: dict[str, Any],
        corp_code: str,
    ) -> None:
        from psycopg import AsyncConnection

        async with await AsyncConnection.connect(self._database_url) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE business_group_companies
                    SET dart_corp_code = %s
                    WHERE designation_month = %s
                      AND group_code = %s
                      AND company_name = %s
                    """,
                    (
                        corp_code,
                        company["designation_month"],
                        company["group_code"],
                        company["company_name"],
                    ),
                )
            await conn.commit()

    async def _store_holding_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        from psycopg import AsyncConnection

        fetched_at = datetime.now(UTC)
        async with await AsyncConnection.connect(self._database_url) as conn:
            async with conn.cursor() as cursor:
                for row in rows:
                    entity = row["entity"]
                    holding = row["holding"]
                    await cursor.execute(
                        """
                        INSERT INTO shareholder_entities (
                            entity_id,
                            entity_type,
                            display_name,
                            normalized_name,
                            legal_registration_number,
                            dart_corp_code,
                            stock_code,
                            confidence_basis
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (entity_id)
                        DO UPDATE SET
                            entity_type = EXCLUDED.entity_type,
                            display_name = EXCLUDED.display_name,
                            normalized_name = EXCLUDED.normalized_name,
                            confidence_basis = EXCLUDED.confidence_basis,
                            updated_at = now()
                        """,
                        (
                            entity["entity_id"],
                            entity["entity_type"],
                            entity["display_name"],
                            entity["normalized_name"],
                            entity.get("legal_registration_number"),
                            entity.get("dart_corp_code"),
                            entity.get("stock_code"),
                            entity.get("confidence_basis"),
                        ),
                    )
                    await cursor.execute(
                        """
                        INSERT INTO shareholder_holdings (
                            entity_id,
                            held_company_corp_code,
                            held_company_name,
                            held_company_group_code,
                            report_year,
                            report_code,
                            relation,
                            share_class,
                            share_count,
                            holding_ratio,
                            source_endpoint,
                            source_receipt_no,
                            source_fetched_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (entity_id, held_company_name, report_year, report_code)
                        DO UPDATE SET
                            held_company_corp_code = EXCLUDED.held_company_corp_code,
                            held_company_group_code = EXCLUDED.held_company_group_code,
                            relation = EXCLUDED.relation,
                            share_class = EXCLUDED.share_class,
                            share_count = EXCLUDED.share_count,
                            holding_ratio = EXCLUDED.holding_ratio,
                            source_endpoint = EXCLUDED.source_endpoint,
                            source_receipt_no = EXCLUDED.source_receipt_no,
                            source_fetched_at = EXCLUDED.source_fetched_at
                        """,
                        (
                            holding["entity_id"],
                            holding.get("held_company_corp_code"),
                            holding["held_company_name"],
                            holding.get("held_company_group_code"),
                            holding["report_year"],
                            holding["report_code"],
                            holding.get("relation"),
                            holding.get("share_class"),
                            holding.get("share_count"),
                            holding.get("holding_ratio"),
                            holding["source_endpoint"],
                            holding.get("source_receipt_no"),
                            fetched_at,
                        ),
                    )
            await conn.commit()

    async def _store_groups_and_companies(
        self,
        *,
        designation_month: str,
        groups: list[dict[str, Any]],
        companies: list[dict[str, Any]],
    ) -> None:
        from psycopg import AsyncConnection

        fetched_at = datetime.now(UTC)
        async with await AsyncConnection.connect(self._database_url) as conn:
            async with conn.cursor() as cursor:
                for group in groups:
                    await cursor.execute(
                        """
                        INSERT INTO business_groups (
                            designation_month,
                            group_code,
                            group_name,
                            rank,
                            asset_amount,
                            same_person_name,
                            representative_company_name,
                            company_count,
                            source,
                            fetched_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (designation_month, group_code)
                        DO UPDATE SET
                            group_name = EXCLUDED.group_name,
                            rank = EXCLUDED.rank,
                            asset_amount = EXCLUDED.asset_amount,
                            same_person_name = EXCLUDED.same_person_name,
                            representative_company_name = EXCLUDED.representative_company_name,
                            company_count = EXCLUDED.company_count,
                            source = EXCLUDED.source,
                            fetched_at = EXCLUDED.fetched_at
                        """,
                        (
                            designation_month,
                            group["group_code"],
                            group["group_name"],
                            group.get("rank"),
                            group.get("asset_amount"),
                            group.get("same_person_name"),
                            group.get("representative_company_name"),
                            group.get("company_count"),
                            BUSINESS_GROUP_SOURCE,
                            fetched_at,
                        ),
                    )
                for company in companies:
                    await cursor.execute(
                        """
                        INSERT INTO business_group_companies (
                            designation_month,
                            group_code,
                            company_name,
                            legal_registration_number,
                            business_registration_number,
                            representative_name,
                            included_on,
                            industry_name,
                            dart_corp_code,
                            stock_code,
                            source,
                            fetched_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (designation_month, group_code, company_name)
                        DO UPDATE SET
                            legal_registration_number = EXCLUDED.legal_registration_number,
                            business_registration_number = EXCLUDED.business_registration_number,
                            representative_name = EXCLUDED.representative_name,
                            included_on = EXCLUDED.included_on,
                            industry_name = EXCLUDED.industry_name,
                            dart_corp_code = EXCLUDED.dart_corp_code,
                            stock_code = EXCLUDED.stock_code,
                            source = EXCLUDED.source,
                            fetched_at = EXCLUDED.fetched_at
                        """,
                        (
                            designation_month,
                            company["group_code"],
                            company["company_name"],
                            company.get("legal_registration_number"),
                            company.get("business_registration_number"),
                            company.get("representative_name"),
                            company.get("included_on"),
                            company.get("industry_name"),
                            company.get("dart_corp_code"),
                            company.get("stock_code"),
                            BUSINESS_GROUP_SOURCE,
                            fetched_at,
                        ),
                    )
            await conn.commit()

    def _public_match(self, row: dict[str, Any]) -> dict[str, Any]:
        confidence = row.get("confidence_basis") or "low"
        return {
            "entity_id": row.get("entity_id"),
            "entity_type": row.get("entity_type") or "unknown",
            "display_name": row.get("display_name"),
            "confidence": confidence,
            "same_name_warning": confidence == "low",
            "holding": {
                "company_name": row.get("held_company_name"),
                "corp_code": row.get("held_company_corp_code"),
                "group_code": row.get("held_company_group_code"),
                "group_name": row.get("group_name"),
                "report_year": row.get("report_year"),
                "report_code": row.get("report_code"),
                "relation": row.get("relation"),
                "share_class": row.get("share_class"),
                "share_count": str(row.get("share_count")) if row.get("share_count") is not None else None,
                "holding_ratio": str(row.get("holding_ratio")) if row.get("holding_ratio") is not None else None,
                "source_endpoint": row.get("source_endpoint"),
                "source_receipt_no": row.get("source_receipt_no"),
                "source_fetched_at": (
                    row["source_fetched_at"].isoformat()
                    if row.get("source_fetched_at") is not None
                    else None
                ),
            },
        }
