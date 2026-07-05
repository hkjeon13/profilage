import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
import httpx

from app.core.config import get_openai_settings
from app.services.company_disclosure_summary import OPENAI_RESPONSES_URL
from app.services.company_store import COMPANY_ENTITY_TYPE, DataGroupStore


COMPANY_PROFILE_SUMMARY_PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class CompanyProfileSummaryQuery:
    corporate_registration_number: str
    profile_payload: dict[str, Any]


def company_profile_summary_group_name(model: str) -> str:
    safe_model = model.replace(":", "_").replace("/", "_")
    return (
        f"company_profile_summary:{safe_model}:"
        f"{COMPANY_PROFILE_SUMMARY_PROMPT_VERSION}"
    )


def _string_list(value: Any, *, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def normalize_company_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    headline = str(payload.get("headline") or "").strip()
    return {
        "headline": headline,
        "bullets": _string_list(payload.get("bullets"), limit=5),
        "watch_points": _string_list(payload.get("watch_points"), limit=5),
        "data_basis": _string_list(payload.get("data_basis"), limit=5),
        "limitations": _string_list(payload.get("limitations"), limit=3),
    }


def _first_openapi_item(payload: dict[str, Any] | None) -> dict[str, Any]:
    items = _openapi_items(payload)
    return items[0] if items else {}


def _openapi_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if isinstance(items, dict):
        item = items.get("item")
        if isinstance(item, list):
            return [row for row in item if isinstance(row, dict)]
        return [item] if isinstance(item, dict) else []
    body = payload.get("body")
    if isinstance(body, dict):
        return _openapi_items(body)
    raw_list = payload.get("list")
    if isinstance(raw_list, list):
        return [row for row in raw_list if isinstance(row, dict)]
    return []


def _financial_accounts_sample(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("list")
    if not isinstance(rows, list):
        return []
    preferred = {"자산총계", "부채총계", "자본총계", "매출액", "영업이익", "당기순이익"}
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        account_name = row.get("account_nm")
        if account_name in preferred:
            result.append(
                {
                    "account_nm": account_name,
                    "thstrm_amount": row.get("thstrm_amount"),
                    "thstrm_nm": row.get("thstrm_nm"),
                }
            )
    return result[:8]


def build_company_summary_source(profile_payload: dict[str, Any]) -> dict[str, Any]:
    outline = _first_openapi_item(profile_payload.get("corp_outline"))
    listed = _first_openapi_item(profile_payload.get("krx_listed_item"))
    dart_company = profile_payload.get("dart_company") or {}
    dart_corp_code = profile_payload.get("dart_corp_code") or {}
    annual = profile_payload.get("dart_latest_annual_financial_accounts") or {}
    quarter = profile_payload.get("dart_latest_quarter_financial_accounts") or {}
    insights = profile_payload.get("dart_insights") or {}
    disclosures = profile_payload.get("dart_disclosures") or {}

    return {
        "basic": {
            "name": outline.get("corpNm") or dart_company.get("corp_name"),
            "english_name": outline.get("corpEnsnNm") or dart_company.get("corp_name_eng"),
            "representative": outline.get("enpRprFnm") or dart_company.get("ceo_nm"),
            "market": listed.get("mrktCtg") or outline.get("corpRegMrktDcdNm"),
            "stock_code": listed.get("srtnCd") or dart_company.get("stock_code"),
            "industry": outline.get("enpMainBizNm") or listed.get("itmsNm"),
            "established_on": outline.get("enpEstbDt") or dart_company.get("est_dt"),
            "employee_count": outline.get("enpEmpeCnt"),
            "address": outline.get("enpBsadr") or dart_company.get("adres"),
        },
        "dart": {
            "corp_code": (dart_corp_code.get("match") or {}).get("corp_code")
            or dart_company.get("corp_code"),
            "recent_disclosures": [
                {
                    "date": item.get("rcept_dt"),
                    "title": item.get("report_nm"),
                    "submitter": item.get("flr_nm"),
                }
                for item in disclosures.get("list", [])
                if isinstance(item, dict)
            ][:5],
            "annual_basis": annual.get("selected"),
            "quarter_basis": quarter.get("selected"),
            "financial_accounts": _financial_accounts_sample(
                (quarter.get("accounts") or {})
                if isinstance(quarter.get("accounts"), dict)
                else profile_payload.get("dart_financial_accounts")
            ),
            "insights": insights,
        },
        "relationships": {
            "affiliate_count": len(_openapi_items(profile_payload.get("affiliate"))),
            "subsidiary_count": len(
                _openapi_items(profile_payload.get("cons_subs_comp"))
            ),
        },
        "risk_signals": profile_payload.get("risk_signals") or {},
        "disclosure_events": profile_payload.get("disclosure_events") or [],
    }


def company_summary_fingerprint(profile_payload: dict[str, Any]) -> str:
    explicit = profile_payload.get("fingerprint")
    if isinstance(explicit, str) and explicit:
        return explicit
    source = build_company_summary_source(profile_payload)
    serialized = json.dumps(source, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def build_company_summary_prompt(
    *,
    source: dict[str, Any],
    max_chars: int,
) -> str:
    clipped = json.dumps(source, ensure_ascii=False, sort_keys=True, default=str)[
        :max_chars
    ]
    return (
        "다음 기업 프로필 데이터를 바탕으로 한국어 기업 요약을 작성하세요. "
        "제공된 데이터에 없는 내용을 추측하지 말고, 투자 판단을 단정하지 마세요. "
        "비상장/주가 없음처럼 빠진 데이터는 한계 또는 확인할 점으로 다루세요. "
        "JSON만 반환하세요. JSON schema는 "
        '{"headline":"한줄 요약","bullets":["핵심 포인트"],'
        '"watch_points":["확인할 점"],"data_basis":["데이터 기준"],'
        '"limitations":["한계"]} 입니다.\n\n'
        f"기업 프로필 데이터:\n{clipped}"
    )


def _extract_openai_text(payload: dict[str, Any]) -> str:
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise HTTPException(status_code=502, detail="OpenAI summary response was empty")


async def summarize_company_profile_with_openai(
    *,
    source: dict[str, Any],
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    settings = get_openai_settings(required=True)
    request_payload = {
        "model": settings.model,
        "input": build_company_summary_prompt(
            source=source,
            max_chars=settings.max_chars,
        ),
        "text": {"format": {"type": "json_object"}},
    }
    try:
        async with httpx.AsyncClient(transport=transport, timeout=60.0) as client:
            response = await client.post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {settings.api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI request failed with status {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="OpenAI request failed") from exc

    try:
        summary_json = json.loads(_extract_openai_text(response.json()))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="OpenAI returned invalid company summary JSON",
        ) from exc

    return {
        "summary": normalize_company_summary_payload(summary_json),
        "model": settings.model,
        "prompt_version": COMPANY_PROFILE_SUMMARY_PROMPT_VERSION,
    }


class CompanyProfileSummaryService:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        data_group_store: DataGroupStore | None = None,
    ) -> None:
        self._transport = transport
        self._data_group_store = data_group_store

    async def fetch(self, query: CompanyProfileSummaryQuery) -> dict[str, Any]:
        try:
            settings = get_openai_settings(required=True)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY is not configured",
            ) from exc

        fingerprint = company_summary_fingerprint(query.profile_payload)
        group_name = company_profile_summary_group_name(settings.model)

        if self._data_group_store is not None:
            cached = await self._data_group_store.get_record(
                entity_type=COMPANY_ENTITY_TYPE,
                entity_key=query.corporate_registration_number,
                group_name=group_name,
            )
            if cached is not None and cached.payload.get("fingerprint") == fingerprint:
                return {**cached.payload, "cached": True}

        source = build_company_summary_source(query.profile_payload)
        summary_payload = await summarize_company_profile_with_openai(
            source=source,
            transport=self._transport,
        )
        payload = {
            "corporate_registration_number": query.corporate_registration_number,
            "summary": summary_payload["summary"],
            "fingerprint": fingerprint,
            "model": summary_payload["model"],
            "prompt_version": summary_payload["prompt_version"],
            "cached": False,
        }

        if self._data_group_store is not None:
            await self._data_group_store.upsert_record(
                entity_type=COMPANY_ENTITY_TYPE,
                entity_key=query.corporate_registration_number,
                group_name=group_name,
                source="openai:responses",
                payload=payload,
                ttl=None,
            )
        return payload
