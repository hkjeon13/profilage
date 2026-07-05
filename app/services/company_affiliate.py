from dataclasses import dataclass
import hashlib
import json
import random
from typing import Any, Awaitable, Callable

from fastapi import HTTPException
import httpx

from app.core.config import (
    get_dart_api_key,
    get_cache_settings,
    get_open_api_settings,
    get_searchapi_api_key,
)
from app.services.cache import JsonCache, get_default_cache
from app.services.company_dart import (
    DartCompanyQuery,
    DartCompanyService,
    DartCorpCodeQuery,
    DartDisclosureQuery,
)
from app.services.company_insights import normalize_dart_insights
from app.services.company_store import (
    AFFILIATE_GROUP,
    COMPANY_ENTITY_TYPE,
    CONS_SUBS_COMP_GROUP,
    CORP_OUTLINE_GROUP,
    KRX_LISTED_ITEM_GROUP,
    STOCK_ENTITY_TYPE,
    STOCK_PRICE_GROUP,
    DataGroupStore,
    company_group_ttl,
    fetch_with_group_store,
    get_default_data_group_store,
    stock_entity_key,
    stock_price_ttl,
)


OPEN_API_BASE_URL = (
    "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2"
)

OPEN_API_GET_AFFILIATE_URL = f"{OPEN_API_BASE_URL}/getAffiliate_V2"
OPEN_API_GET_CONS_SUBS_COMP_URL = f"{OPEN_API_BASE_URL}/getConsSubsComp_V2"
OPEN_API_GET_CORP_OUTLINE_URL = f"{OPEN_API_BASE_URL}/getCorpOutline_V2"
OPEN_API_GET_KRX_LISTED_ITEM_URL = (
    "https://apis.data.go.kr/1160100/service/"
    "GetKrxListedInfoService/getItemInfo"
)
SEARCHAPI_SEARCH_URL = "https://www.searchapi.io/api/v1/search"
DATA_GROUP_STORE_UNSET = object()


def _first_openapi_item(payload: dict[str, Any]) -> dict[str, Any]:
    item = payload.get("body", {}).get("items", {}).get("item")
    if isinstance(item, list):
        return item[0] if item else {}
    return item if isinstance(item, dict) else {}


def _has_openapi_items(payload: dict[str, Any]) -> bool:
    item = payload.get("body", {}).get("items", {}).get("item")
    if isinstance(item, list):
        return bool(item)
    return isinstance(item, dict) and bool(item)


def _case_relaxed_candidates(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            item
            for item in (value, value.upper(), value.lower())
            if item.strip()
        )
    )


def _empty_openapi_payload(*, source: str, detail: str | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {"source": source, "status": "unavailable"}
    if detail:
        meta["detail"] = detail
    return {
        "body": {
            "numOfRows": 0,
            "pageNo": 1,
            "totalCount": 0,
            "items": {},
        },
        "_meta": meta,
    }


def _unavailable_payload(*, source: str, detail: str | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {"source": source, "status": "unavailable"}
    if detail:
        meta["detail"] = detail
    return {"_meta": meta}


@dataclass(frozen=True)
class CompanyAffiliateQuery:
    company_name: str | None
    corporate_registration_number: str | None
    base_date: str | None
    page: int
    per_page: int


@dataclass(frozen=True)
class CompanyConsSubsCompQuery:
    subsidiary_name: str | None
    corporate_registration_number: str | None
    base_date: str | None
    page: int
    per_page: int


@dataclass(frozen=True)
class CompanyCorpOutlineQuery:
    company_name: str | None
    corporate_registration_number: str | None
    page: int
    per_page: int


@dataclass(frozen=True)
class CompanyKrxListedItemQuery:
    corporate_registration_number: str | None
    company_name: str | None
    item_name: str | None
    isin_code: str | None
    base_date: str | None
    page: int
    per_page: int


@dataclass(frozen=True)
class CompanyInfoQuery:
    corporate_registration_number: str
    page: int
    per_page: int


@dataclass(frozen=True)
class CompanyStockPriceQuery:
    q: str | None
    stock_code: str | None
    exchange: str | None
    language: str | None
    window: str | None
    corporate_registration_number: str | None = None


class OpenApiCompanyService:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        cache: JsonCache | None = None,
        data_group_store: DataGroupStore | None | object = DATA_GROUP_STORE_UNSET,
    ) -> None:
        self._transport = transport
        self._cache = cache if cache is not None else get_default_cache()
        self._data_group_store = (
            get_default_data_group_store()
            if data_group_store is DATA_GROUP_STORE_UNSET
            else data_group_store
        )

    def _cache_key(self, *, endpoint_url: str, params: dict[str, Any]) -> str:
        normalized = {
            "endpoint_url": endpoint_url,
            "params": sorted((key, str(value)) for key, value in params.items()),
        }
        digest = hashlib.sha256(
            json.dumps(normalized, ensure_ascii=False).encode()
        ).hexdigest()
        return f"profilage:api:{digest}"

    async def _get_cached_json(self, cache_key: str) -> Any | None:
        if random.random() < get_cache_settings().bypass_rate:
            return None
        return await self._cache.get_json(cache_key)

    async def _fetch(
        self,
        *,
        endpoint_url: str,
        params: dict[str, Any],
        service_key_param_name: str = "ServiceKey",
    ) -> dict[str, Any]:
        settings = get_open_api_settings()
        url = endpoint_url

        if settings.service_key_is_encoded:
            url = f"{url}?{service_key_param_name}={settings.service_key}"
        else:
            params[service_key_param_name] = settings.service_key

        cache_params = {
            key: value
            for key, value in params.items()
            if key != service_key_param_name
        }
        cache_key = self._cache_key(endpoint_url=endpoint_url, params=cache_params)
        cached = await self._get_cached_json(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=30.0,
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"OpenAPI request failed with status {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail="OpenAPI request failed",
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="OpenAPI returned a non-JSON response",
            ) from exc

        result = payload.get("response", payload)
        await self._cache.set_json(
            cache_key,
            result,
            get_cache_settings().ttl_seconds,
        )
        return result

    async def _fetch_with_case_relaxed_fallback(
        self,
        *,
        endpoint_url: str,
        params: dict[str, Any],
        search_param_names: list[str],
        service_key_param_name: str = "ServiceKey",
    ) -> dict[str, Any]:
        result = await self._fetch(
            endpoint_url=endpoint_url,
            params=params.copy(),
            service_key_param_name=service_key_param_name,
        )
        if _has_openapi_items(result):
            return result

        for param_name in search_param_names:
            original = params.get(param_name)
            if not isinstance(original, str) or not original:
                continue
            for candidate in _case_relaxed_candidates(original)[1:]:
                fallback_params = params.copy()
                fallback_params[param_name] = candidate
                fallback = await self._fetch(
                    endpoint_url=endpoint_url,
                    params=fallback_params,
                    service_key_param_name=service_key_param_name,
                )
                if _has_openapi_items(fallback):
                    return fallback

        return result


class CompanyAffiliateService(OpenApiCompanyService):
    async def fetch(self, query: CompanyAffiliateQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageNo": str(query.page),
            "numOfRows": str(query.per_page),
            "resultType": "json",
        }

        if query.base_date:
            params["basDt"] = query.base_date
        if query.corporate_registration_number:
            params["crno"] = query.corporate_registration_number
        if query.company_name:
            params["afilCmpyNm"] = query.company_name

        return await self._fetch(
            endpoint_url=OPEN_API_GET_AFFILIATE_URL,
            params=params,
        )


class CompanyConsSubsCompService(OpenApiCompanyService):
    async def fetch(self, query: CompanyConsSubsCompQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageNo": str(query.page),
            "numOfRows": str(query.per_page),
            "resultType": "json",
        }

        if query.base_date:
            params["basDt"] = query.base_date
        if query.corporate_registration_number:
            params["crno"] = query.corporate_registration_number
        if query.subsidiary_name:
            params["sbrdEnpNm"] = query.subsidiary_name

        return await self._fetch(
            endpoint_url=OPEN_API_GET_CONS_SUBS_COMP_URL,
            params=params,
        )


class CompanyCorpOutlineService(OpenApiCompanyService):
    async def fetch(self, query: CompanyCorpOutlineQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageNo": str(query.page),
            "numOfRows": str(query.per_page),
            "resultType": "json",
        }

        if query.corporate_registration_number:
            params["crno"] = query.corporate_registration_number
        if query.company_name:
            params["corpNm"] = query.company_name

        return await self._fetch_with_case_relaxed_fallback(
            endpoint_url=OPEN_API_GET_CORP_OUTLINE_URL,
            params=params,
            search_param_names=["corpNm"],
        )


class CompanyKrxListedItemService(OpenApiCompanyService):
    async def fetch(self, query: CompanyKrxListedItemQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageNo": str(query.page),
            "numOfRows": str(query.per_page),
            "resultType": "json",
        }

        if query.base_date:
            params["basDt"] = query.base_date
        if query.corporate_registration_number:
            params["crno"] = query.corporate_registration_number
        if query.company_name:
            params["corpNm"] = query.company_name
        if query.item_name:
            params["itmsNm"] = query.item_name
        if query.isin_code:
            params["isinCd"] = query.isin_code

        return await self._fetch_with_case_relaxed_fallback(
            endpoint_url=OPEN_API_GET_KRX_LISTED_ITEM_URL,
            params=params,
            search_param_names=["corpNm", "itmsNm"],
            service_key_param_name="serviceKey",
        )


class CompanyInfoService(OpenApiCompanyService):
    async def _fetch_optional_company_group(
        self,
        *,
        crno: str,
        group_name: str,
        source: str,
        fetcher: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        try:
            return await fetch_with_group_store(
                store=self._data_group_store,
                entity_type=COMPANY_ENTITY_TYPE,
                entity_key=crno,
                group_name=group_name,
                source=source,
                ttl=company_group_ttl(group_name),
                fetcher=fetcher,
            )
        except HTTPException as exc:
            return _empty_openapi_payload(source=source, detail=str(exc.detail))

    async def fetch(self, query: CompanyInfoQuery) -> dict[str, Any]:
        corp_outline_service = CompanyCorpOutlineService(
            transport=self._transport,
            cache=self._cache,
            data_group_store=self._data_group_store,
        )
        krx_listed_item_service = CompanyKrxListedItemService(
            transport=self._transport,
            cache=self._cache,
            data_group_store=self._data_group_store,
        )
        affiliate_service = CompanyAffiliateService(
            transport=self._transport,
            cache=self._cache,
            data_group_store=self._data_group_store,
        )
        cons_subs_comp_service = CompanyConsSubsCompService(
            transport=self._transport,
            cache=self._cache,
            data_group_store=self._data_group_store,
        )

        crno = query.corporate_registration_number
        corp_outline = await fetch_with_group_store(
            store=self._data_group_store,
            entity_type=COMPANY_ENTITY_TYPE,
            entity_key=crno,
            group_name=CORP_OUTLINE_GROUP,
            source="openapi:getCorpOutline_V2",
            ttl=company_group_ttl(CORP_OUTLINE_GROUP),
            fetcher=lambda: corp_outline_service.fetch(
                CompanyCorpOutlineQuery(
                    company_name=None,
                    corporate_registration_number=crno,
                    page=query.page,
                    per_page=query.per_page,
                )
            ),
        )
        krx_listed_item = await self._fetch_optional_company_group(
            crno=crno,
            group_name=KRX_LISTED_ITEM_GROUP,
            source="openapi:getItemInfo",
            fetcher=lambda: krx_listed_item_service.fetch(
                CompanyKrxListedItemQuery(
                    corporate_registration_number=crno,
                    company_name=None,
                    item_name=None,
                    isin_code=None,
                    base_date=None,
                    page=query.page,
                    per_page=query.per_page,
                )
            ),
        )
        affiliate = await self._fetch_optional_company_group(
            crno=crno,
            group_name=AFFILIATE_GROUP,
            source="openapi:getAffiliate_V2",
            fetcher=lambda: affiliate_service.fetch(
                CompanyAffiliateQuery(
                    company_name=None,
                    corporate_registration_number=crno,
                    base_date=None,
                    page=query.page,
                    per_page=query.per_page,
                )
            ),
        )
        cons_subs_comp = await self._fetch_optional_company_group(
            crno=crno,
            group_name=CONS_SUBS_COMP_GROUP,
            source="openapi:getConsSubsComp_V2",
            fetcher=lambda: cons_subs_comp_service.fetch(
                CompanyConsSubsCompQuery(
                    subsidiary_name=None,
                    corporate_registration_number=crno,
                    base_date=None,
                    page=query.page,
                    per_page=query.per_page,
                )
            ),
        )

        return {
            "corporate_registration_number": crno,
            "corp_outline": corp_outline,
            "krx_listed_item": krx_listed_item,
            "affiliate": affiliate,
            "cons_subs_comp": cons_subs_comp,
            **await self._fetch_optional_dart_profile(crno, corp_outline, krx_listed_item),
        }

    async def _fetch_optional_dart_profile(
        self,
        crno: str,
        corp_outline: dict[str, Any],
        krx_listed_item: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return await self._fetch_dart_profile(crno, corp_outline, krx_listed_item)
        except HTTPException as exc:
            return {
                "dart_corp_code": _unavailable_payload(
                    source="dart",
                    detail=str(exc.detail),
                )
            }

    async def _fetch_dart_profile(
        self,
        crno: str,
        corp_outline: dict[str, Any],
        krx_listed_item: dict[str, Any],
    ) -> dict[str, Any]:
        if not get_dart_api_key(required=False):
            return {}

        outline_item = _first_openapi_item(corp_outline)
        listed_item = _first_openapi_item(krx_listed_item)
        stock_code = (listed_item.get("srtnCd") or "").replace("A", "", 1)
        company_name = outline_item.get("corpNm") or listed_item.get("corpNm")
        dart_service = DartCompanyService(
            transport=self._transport,
            data_group_store=self._data_group_store,
        )
        corp_code_payload = await dart_service.find_corp_code(
            DartCorpCodeQuery(
                corporate_registration_number=crno,
                stock_code=stock_code or None,
                company_name=company_name,
            )
        )
        corp_code = corp_code_payload.get("match", {}).get("corp_code")
        if not corp_code:
            return {"dart_corp_code": corp_code_payload}

        dart_company = await dart_service.get_company(
            query=DartCompanyQuery(corp_code=corp_code)
        )
        dart_disclosures = await dart_service.get_disclosures(
            DartDisclosureQuery(
                corp_code=corp_code,
                begin_date=None,
                end_date=None,
                disclosure_type=None,
                disclosure_detail_type=None,
                corporation_class=None,
                page=1,
                per_page=5,
            )
        )
        dart_financial_reports = await dart_service.get_latest_financial_reports(
            corp_code=corp_code,
            fs_division="CFS",
        )
        dart_latest_quarter_financial_accounts = dart_financial_reports["quarter"]
        dart_latest_annual_financial_accounts = dart_financial_reports["annual"]
        dart_financial_accounts = (
            dart_latest_quarter_financial_accounts["accounts"]
            if dart_latest_quarter_financial_accounts["accounts"].get("list")
            else dart_latest_annual_financial_accounts["accounts"]
        )
        annual_selected = dart_latest_annual_financial_accounts.get("selected") or {}
        dart_insights = None
        if annual_selected.get("business_year") and annual_selected.get("report_code"):
            raw_insight_sources = await dart_service.get_phase_one_insight_sources(
                corp_code=corp_code,
                business_year=annual_selected["business_year"],
                report_code=annual_selected["report_code"],
            )
            dart_insights = normalize_dart_insights(
                raw_insight_sources,
                basis={
                    "business_year": annual_selected["business_year"],
                    "report_code": annual_selected["report_code"],
                    "report_name": annual_selected.get("report_name"),
                    "fs_division": annual_selected.get("fs_division"),
                },
            )
        return {
            "dart_corp_code": corp_code_payload,
            "dart_company": dart_company,
            "dart_disclosures": dart_disclosures,
            "dart_financial_accounts": dart_financial_accounts,
            "dart_latest_quarter_financial_accounts": dart_latest_quarter_financial_accounts,
            "dart_latest_annual_financial_accounts": dart_latest_annual_financial_accounts,
            "dart_insights": dart_insights,
        }


class CompanyStockPriceService(OpenApiCompanyService):
    async def fetch(self, query: CompanyStockPriceQuery) -> dict[str, Any]:
        api_key = get_searchapi_api_key()
        q = query.q
        if not q and query.stock_code:
            q = query.stock_code
            if query.exchange:
                q = f"{q}:{query.exchange}"

        params: dict[str, Any] = {
            "api_key": api_key,
            "engine": "google_finance",
            "q": q,
        }

        if query.language:
            params["hl"] = query.language
        if query.window:
            params["window"] = query.window

        async def fetch_searchapi() -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=30.0,
                ) as client:
                    response = await client.get(SEARCHAPI_SEARCH_URL, params=params)
                    response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "SearchAPI request failed with status "
                        f"{exc.response.status_code}"
                    ),
                ) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="SearchAPI request failed",
                ) from exc

            try:
                return response.json()
            except ValueError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="SearchAPI returned a non-JSON response",
                ) from exc

        if self._data_group_store is not None:
            return await fetch_with_group_store(
                store=self._data_group_store,
                entity_type=STOCK_ENTITY_TYPE,
                entity_key=stock_entity_key(
                    q=q,
                    stock_code=query.stock_code,
                    exchange=query.exchange,
                    language=query.language,
                    window=query.window,
                ),
                group_name=STOCK_PRICE_GROUP,
                source="searchapi:google_finance",
                ttl=stock_price_ttl(query.exchange, query.window),
                fetcher=fetch_searchapi,
            )

        cache_params = {key: value for key, value in params.items() if key != "api_key"}
        cache_key = self._cache_key(
            endpoint_url=SEARCHAPI_SEARCH_URL,
            params=cache_params,
        )
        cached = await self._get_cached_json(cache_key)
        if cached is not None:
            return cached

        payload = await fetch_searchapi()
        await self._cache.set_json(
            cache_key,
            payload,
            int(stock_price_ttl(query.exchange, query.window).total_seconds()),
        )
        return payload
