from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from io import BytesIO
import json
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

from fastapi import HTTPException
import httpx

from app.core.config import get_dart_api_key
from app.services.cache import JsonCache, get_default_cache
from app.services.company_store import (
    COMPANY_ENTITY_TYPE,
    DataGroupStore,
    fetch_with_group_store,
    get_default_data_group_store,
)


DART_BASE_URL = "https://opendart.fss.or.kr/api"
DART_CORP_CODE_URL = f"{DART_BASE_URL}/corpCode.xml"
DART_COMPANY_URL = f"{DART_BASE_URL}/company.json"
DART_DISCLOSURE_LIST_URL = f"{DART_BASE_URL}/list.json"
DART_FINANCIAL_ACCOUNT_URL = f"{DART_BASE_URL}/fnlttSinglAcnt.json"
DART_VIEWER_BASE_URL = "https://dart.fss.or.kr/dsaf001/main.do"

DART_CORP_CODE_GROUP = "dart_corp_code"
DART_COMPANY_GROUP = "dart_company"
DART_DISCLOSURES_GROUP = "dart_disclosures"
DART_FINANCIAL_ACCOUNTS_GROUP = "dart_financial_accounts"

DART_CORP_CODE_TTL = timedelta(days=7)
DART_COMPANY_TTL = timedelta(days=7)
DART_DISCLOSURES_TTL = timedelta(hours=1)
DART_FINANCIAL_ACCOUNTS_TTL = timedelta(days=1)
NO_DATA_STATUS = "013"
SUCCESS_STATUS = "000"
FINANCIAL_REPORT_NAMES = {
    "11011": "사업보고서",
    "11012": "반기보고서",
    "11013": "1분기보고서",
    "11014": "3분기보고서",
}


@dataclass(frozen=True)
class DartCorpCodeQuery:
    corporate_registration_number: str | None
    stock_code: str | None
    company_name: str | None


@dataclass(frozen=True)
class DartCompanyQuery:
    corp_code: str


@dataclass(frozen=True)
class DartDisclosureQuery:
    corp_code: str | None
    begin_date: str | None
    end_date: str | None
    disclosure_type: str | None
    disclosure_detail_type: str | None
    corporation_class: str | None
    page: int
    per_page: int


@dataclass(frozen=True)
class DartFinancialAccountsQuery:
    corp_code: str
    business_year: str
    report_code: str
    fs_division: str | None


def _viewer_url(receipt_number: str | None) -> str | None:
    if not receipt_number:
        return None
    return f"{DART_VIEWER_BASE_URL}?rcpNo={receipt_number}"


def _normalize_stock_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper()
    if normalized.startswith("A") and len(normalized) == 7:
        normalized = normalized[1:]
    return normalized.zfill(6) if normalized.isdigit() else normalized


def _normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    return (
        value.replace("주식회사", "")
        .replace("(주)", "")
        .replace("㈜", "")
        .replace(" ", "")
        .strip()
    )


def _dart_entity_key(corp_code: str) -> str:
    return f"dart:{corp_code}"


def _ensure_success(payload: dict[str, Any], *, allow_no_data: bool = False) -> dict[str, Any]:
    status = payload.get("status")
    if status in (None, SUCCESS_STATUS):
        return payload
    if allow_no_data and status == NO_DATA_STATUS:
        payload = dict(payload)
        payload.setdefault("list", [])
        return payload
    raise HTTPException(
        status_code=502,
        detail=f"DART request failed with status {status}: {payload.get('message', '')}",
    )


class DartCompanyService:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        cache: JsonCache | None = None,
        data_group_store: DataGroupStore | None = None,
    ) -> None:
        self._transport = transport
        self._cache = cache if cache is not None else get_default_cache()
        self._data_group_store = (
            data_group_store
            if data_group_store is not None
            else get_default_data_group_store()
        )

    async def _fetch_json(
        self,
        *,
        url: str,
        params: dict[str, Any],
        allow_no_data: bool = False,
    ) -> dict[str, Any]:
        api_key = get_dart_api_key()
        request_params = {"crtfc_key": api_key, **params}
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=30.0,
            ) as client:
                response = await client.get(url, params=request_params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"DART request failed with status {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="DART request failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="DART returned a non-JSON response",
            ) from exc
        return _ensure_success(payload, allow_no_data=allow_no_data)

    async def _fetch_corp_code_rows(self) -> list[dict[str, str]]:
        cached = await self._cache.get_json("profilage:dart:corp_codes")
        if cached is not None:
            return cached

        api_key = get_dart_api_key()
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=30.0,
            ) as client:
                response = await client.get(
                    DART_CORP_CODE_URL,
                    params={"crtfc_key": api_key},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"DART corp code request failed with status {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail="DART corp code request failed",
            ) from exc

        try:
            with ZipFile(BytesIO(response.content)) as archive:
                xml_name = archive.namelist()[0]
                root = ElementTree.fromstring(archive.read(xml_name))
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="DART corp code response could not be parsed",
            ) from exc

        rows = [
            {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "corp_eng_name": (item.findtext("corp_eng_name") or "").strip(),
                "stock_code": (item.findtext("stock_code") or "").strip(),
                "modify_date": (item.findtext("modify_date") or "").strip(),
            }
            for item in root.findall("list")
        ]
        await self._cache.set_json(
            "profilage:dart:corp_codes",
            rows,
            int(DART_CORP_CODE_TTL.total_seconds()),
        )
        return rows

    async def find_corp_code(self, query: DartCorpCodeQuery) -> dict[str, Any]:
        rows = await self._fetch_corp_code_rows()
        stock_code = _normalize_stock_code(query.stock_code)
        jurir_no = (query.corporate_registration_number or "").strip()
        company_name = _normalize_name(query.company_name)

        candidates = rows
        if stock_code:
            candidates = [row for row in rows if row["stock_code"] == stock_code]
        elif company_name:
            candidates = [
                row
                for row in rows
                if _normalize_name(row["corp_name"]) == company_name
            ]

        if jurir_no and len(candidates) != 1:
            company_matches = []
            for row in candidates[:20]:
                company = await self.get_company(DartCompanyQuery(row["corp_code"]))
                if company.get("jurir_no") == jurir_no:
                    company_matches.append(row)
            candidates = company_matches

        return {
            "status": SUCCESS_STATUS if candidates else NO_DATA_STATUS,
            "message": "정상" if candidates else "조회된 데이타가 없습니다.",
            "matches": candidates,
            "match": candidates[0] if candidates else None,
        }

    async def get_company(self, query: DartCompanyQuery) -> dict[str, Any]:
        return await fetch_with_group_store(
            store=self._data_group_store,
            entity_type=COMPANY_ENTITY_TYPE,
            entity_key=_dart_entity_key(query.corp_code),
            group_name=DART_COMPANY_GROUP,
            source="dart:company",
            ttl=DART_COMPANY_TTL,
            fetcher=lambda: self._fetch_json(
                url=DART_COMPANY_URL,
                params={"corp_code": query.corp_code},
            ),
        )

    async def get_disclosures(self, query: DartDisclosureQuery) -> dict[str, Any]:
        begin_date = query.begin_date
        if not begin_date and not query.end_date:
            begin_date = (datetime.now(UTC) - timedelta(days=365)).strftime("%Y%m%d")

        params: dict[str, Any] = {
            "page_no": str(query.page),
            "page_count": str(query.per_page),
            "sort": "date",
            "sort_mth": "desc",
        }
        if query.corp_code:
            params["corp_code"] = query.corp_code
        if begin_date:
            params["bgn_de"] = begin_date
        if query.end_date:
            params["end_de"] = query.end_date
        if query.disclosure_type:
            params["pblntf_ty"] = query.disclosure_type
        if query.disclosure_detail_type:
            params["pblntf_detail_ty"] = query.disclosure_detail_type
        if query.corporation_class:
            params["corp_cls"] = query.corporation_class

        digest = hashlib.sha256(
            json.dumps(sorted(params.items()), ensure_ascii=False).encode()
        ).hexdigest()
        entity_key = f"{_dart_entity_key(query.corp_code or 'all')}:list:{digest}"

        payload = await fetch_with_group_store(
            store=self._data_group_store,
            entity_type=COMPANY_ENTITY_TYPE,
            entity_key=entity_key,
            group_name=DART_DISCLOSURES_GROUP,
            source="dart:list",
            ttl=DART_DISCLOSURES_TTL,
            fetcher=lambda: self._fetch_json(
                url=DART_DISCLOSURE_LIST_URL,
                params=params,
                allow_no_data=True,
            ),
        )
        payload = dict(payload)
        payload["list"] = [
            {**item, "viewer_url": _viewer_url(item.get("rcept_no"))}
            for item in payload.get("list", [])
        ]
        return payload

    async def get_financial_accounts(
        self,
        query: DartFinancialAccountsQuery,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "corp_code": query.corp_code,
            "bsns_year": query.business_year,
            "reprt_code": query.report_code,
        }
        if query.fs_division:
            params["fs_div"] = query.fs_division

        payload = await fetch_with_group_store(
            store=self._data_group_store,
            entity_type=COMPANY_ENTITY_TYPE,
            entity_key=_dart_entity_key(query.corp_code),
            group_name=f"{DART_FINANCIAL_ACCOUNTS_GROUP}:{query.business_year}:{query.report_code}:{query.fs_division or 'all'}",
            source="dart:fnlttSinglAcnt",
            ttl=DART_FINANCIAL_ACCOUNTS_TTL,
            fetcher=lambda: self._fetch_json(
                url=DART_FINANCIAL_ACCOUNT_URL,
                params=params,
                allow_no_data=True,
            ),
        )
        if not query.fs_division:
            return payload

        payload = dict(payload)
        payload["list"] = [
            item
            for item in payload.get("list", [])
            if item.get("fs_div") in (None, query.fs_division)
        ]
        return payload

    async def get_latest_financial_reports(
        self,
        *,
        corp_code: str,
        current_year: int | None = None,
        fs_division: str = "CFS",
    ) -> dict[str, Any]:
        year = current_year or datetime.now(UTC).year
        quarter_candidates = [
            (str(year), "11014"),
            (str(year), "11012"),
            (str(year), "11013"),
            (str(year - 1), "11014"),
            (str(year - 1), "11012"),
            (str(year - 1), "11013"),
        ]
        annual_candidates = [
            (str(candidate_year), "11011")
            for candidate_year in range(year, year - 6, -1)
        ]

        async def first_available(
            candidates: list[tuple[str, str]],
        ) -> dict[str, Any] | None:
            for business_year, report_code in candidates:
                accounts = await self.get_financial_accounts(
                    DartFinancialAccountsQuery(
                        corp_code=corp_code,
                        business_year=business_year,
                        report_code=report_code,
                        fs_division=fs_division,
                    )
                )
                if accounts.get("list"):
                    return {
                        "selected": {
                            "business_year": business_year,
                            "report_code": report_code,
                            "fs_division": fs_division,
                            "report_name": FINANCIAL_REPORT_NAMES.get(
                                report_code,
                                report_code,
                            ),
                        },
                        "accounts": accounts,
                    }
            return None

        empty_report = {
            "selected": None,
            "accounts": {
                "status": NO_DATA_STATUS,
                "message": "조회된 데이타가 없습니다.",
                "list": [],
            },
        }
        return {
            "quarter": await first_available(quarter_candidates) or empty_report,
            "annual": await first_available(annual_candidates) or empty_report,
        }
