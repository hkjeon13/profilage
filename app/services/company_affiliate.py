from dataclasses import dataclass
import hashlib
import json
from typing import Any

from fastapi import HTTPException
import httpx

from app.core.config import (
    get_cache_settings,
    get_open_api_settings,
    get_searchapi_api_key,
)
from app.services.cache import JsonCache, get_default_cache


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


class OpenApiCompanyService:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        cache: JsonCache | None = None,
    ) -> None:
        self._transport = transport
        self._cache = cache if cache is not None else get_default_cache()

    def _cache_key(self, *, endpoint_url: str, params: dict[str, Any]) -> str:
        normalized = {
            "endpoint_url": endpoint_url,
            "params": sorted((key, str(value)) for key, value in params.items()),
        }
        digest = hashlib.sha256(
            json.dumps(normalized, ensure_ascii=False).encode()
        ).hexdigest()
        return f"profilage:api:{digest}"

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
        cached = await self._cache.get_json(cache_key)
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

        return await self._fetch(
            endpoint_url=OPEN_API_GET_CORP_OUTLINE_URL,
            params=params,
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

        return await self._fetch(
            endpoint_url=OPEN_API_GET_KRX_LISTED_ITEM_URL,
            params=params,
            service_key_param_name="serviceKey",
        )


class CompanyInfoService(OpenApiCompanyService):
    async def fetch(self, query: CompanyInfoQuery) -> dict[str, Any]:
        corp_outline_service = CompanyCorpOutlineService(
            transport=self._transport,
            cache=self._cache,
        )
        krx_listed_item_service = CompanyKrxListedItemService(
            transport=self._transport,
            cache=self._cache,
        )
        affiliate_service = CompanyAffiliateService(
            transport=self._transport,
            cache=self._cache,
        )
        cons_subs_comp_service = CompanyConsSubsCompService(
            transport=self._transport,
            cache=self._cache,
        )

        corp_outline = await corp_outline_service.fetch(
            CompanyCorpOutlineQuery(
                company_name=None,
                corporate_registration_number=query.corporate_registration_number,
                page=query.page,
                per_page=query.per_page,
            )
        )
        krx_listed_item = await krx_listed_item_service.fetch(
            CompanyKrxListedItemQuery(
                corporate_registration_number=query.corporate_registration_number,
                company_name=None,
                item_name=None,
                isin_code=None,
                base_date=None,
                page=query.page,
                per_page=query.per_page,
            )
        )
        affiliate = await affiliate_service.fetch(
            CompanyAffiliateQuery(
                company_name=None,
                corporate_registration_number=query.corporate_registration_number,
                base_date=None,
                page=query.page,
                per_page=query.per_page,
            )
        )
        cons_subs_comp = await cons_subs_comp_service.fetch(
            CompanyConsSubsCompQuery(
                subsidiary_name=None,
                corporate_registration_number=query.corporate_registration_number,
                base_date=None,
                page=query.page,
                per_page=query.per_page,
            )
        )

        return {
            "corporate_registration_number": query.corporate_registration_number,
            "corp_outline": corp_outline,
            "krx_listed_item": krx_listed_item,
            "affiliate": affiliate,
            "cons_subs_comp": cons_subs_comp,
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

        cache_params = {key: value for key, value in params.items() if key != "api_key"}
        cache_key = self._cache_key(
            endpoint_url=SEARCHAPI_SEARCH_URL,
            params=cache_params,
        )
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cached

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
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="SearchAPI returned a non-JSON response",
            ) from exc

        await self._cache.set_json(
            cache_key,
            payload,
            get_cache_settings().ttl_seconds,
        )
        return payload
