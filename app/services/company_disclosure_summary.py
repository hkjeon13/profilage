import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

from fastapi import HTTPException
import httpx

from app.core.config import get_openai_settings
from app.services.company_store import (
    COMPANY_ENTITY_TYPE,
    DataGroupStore,
    fetch_with_group_store,
)


DART_DISCLOSURE_TEXT_GROUP = "dart_disclosure_text"
DART_DISCLOSURE_SUMMARY_PROMPT_VERSION = "v2"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DART_VIEWER_DOCUMENT_LIMIT = 12


@dataclass(frozen=True)
class DisclosureSummaryQuery:
    receipt_no: str
    viewer_url: str
    title: str | None


@dataclass(frozen=True)
class DartViewerDocumentRef:
    rcp_no: str
    dcm_no: str
    ele_id: str | None
    offset: str | None
    length: str | None
    dtd: str


def validate_dart_viewer_url(viewer_url: str) -> bool:
    parsed = urlparse(viewer_url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.endswith(
        "dart.fss.or.kr"
    )


def disclosure_text_entity_key(receipt_no: str) -> str:
    return receipt_no.strip()


def disclosure_summary_group_name(model: str) -> str:
    safe_model = model.replace(":", "_").replace("/", "_")
    return (
        f"dart_disclosure_summary:{safe_model}:"
        f"{DART_DISCLOSURE_SUMMARY_PROMPT_VERSION}"
    )


def extract_disclosure_text(html_text: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text)
    cleaned = re.sub(r"(?is)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?is)</(p|div|h[1-6]|tr|li|table)>", "\n", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)
    return cleaned.strip()


def _script_value(value: str | None) -> str | None:
    if value is None:
        return None
    return html.unescape(value).strip()


def _document_ref_key(ref: DartViewerDocumentRef) -> tuple[str, str, str | None]:
    return (ref.rcp_no, ref.dcm_no, ref.ele_id)


def extract_dart_viewer_document_refs(html_text: str) -> list[DartViewerDocumentRef]:
    refs: list[DartViewerDocumentRef] = []
    seen: set[tuple[str, str, str | None]] = set()

    for block in re.findall(
        r"(?is)var\s+node1\s*=\s*\{\};(.*?)treeData\.push\(node1\);",
        html_text,
    ):
        values = {
            key: _script_value(value)
            for key, value in re.findall(
                r"""node1\[['"]([^'"]+)['"]\]\s*=\s*"([^"]*)";""",
                block,
            )
        }
        rcp_no = values.get("rcpNo")
        dcm_no = values.get("dcmNo")
        dtd = values.get("dtd")
        if not rcp_no or not dcm_no or not dtd:
            continue
        ref = DartViewerDocumentRef(
            rcp_no=rcp_no,
            dcm_no=dcm_no,
            ele_id=values.get("eleId"),
            offset=values.get("offset"),
            length=values.get("length"),
            dtd=dtd,
        )
        key = _document_ref_key(ref)
        if key not in seen:
            refs.append(ref)
            seen.add(key)

    if refs:
        return refs[:DART_VIEWER_DOCUMENT_LIMIT]

    for match in re.findall(
        r"""viewDoc\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]+)"\s*,\s*"([^"]*)"\s*\)""",
        html_text,
    ):
        ref = DartViewerDocumentRef(
            rcp_no=_script_value(match[0]) or "",
            dcm_no=_script_value(match[1]) or "",
            ele_id=_script_value(match[2]),
            offset=_script_value(match[3]),
            length=_script_value(match[4]),
            dtd=_script_value(match[5]) or "",
        )
        if not ref.rcp_no or not ref.dcm_no or not ref.dtd:
            continue
        key = _document_ref_key(ref)
        if key not in seen:
            refs.append(ref)
            seen.add(key)

    return refs[:DART_VIEWER_DOCUMENT_LIMIT]


def dart_viewer_document_url(viewer_url: str, ref: DartViewerDocumentRef) -> str:
    base_url = urljoin(viewer_url, "/report/viewer.do")
    params = [
        ("rcpNo", ref.rcp_no),
        ("dcmNo", ref.dcm_no),
        ("dtd", ref.dtd),
    ]
    if ref.ele_id:
        params.append(("eleId", ref.ele_id))
    if ref.offset:
        params.append(("offset", ref.offset))
    if ref.length:
        params.append(("length", ref.length))
    return str(httpx.URL(base_url, params=params))


def _string_list(value: Any, *, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def normalize_summary_payload(payload: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "bullets": _string_list(payload.get("bullets"), limit=5),
        "risks": _string_list(payload.get("risks"), limit=5),
        "changes": _string_list(payload.get("changes"), limit=5),
        "limitations": _string_list(payload.get("limitations"), limit=3),
    }


def build_disclosure_summary_prompt(
    *,
    title: str | None,
    text: str,
    max_chars: int,
) -> str:
    clipped = text[:max_chars]
    return (
        "다음 DART 공시 원문을 한국어로 요약하세요. "
        "원문에 없는 내용을 추측하지 말고, 투자 판단을 단정하지 마세요. "
        "JSON만 반환하세요. JSON schema는 "
        '{"bullets":["핵심 요약"],"risks":["리스크/확인사항"],'
        '"changes":["변동사항"],"limitations":["한계"]} 입니다.\n\n'
        f"공시 제목: {title or '제목 정보 없음'}\n"
        f"원문:\n{clipped}"
    )


def _extract_openai_text(payload: dict[str, Any]) -> str:
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise HTTPException(status_code=502, detail="OpenAI summary response was empty")


async def summarize_with_openai(
    *,
    title: str | None,
    text: str,
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    settings = get_openai_settings(required=True)
    prompt = build_disclosure_summary_prompt(
        title=title,
        text=text,
        max_chars=settings.max_chars,
    )
    request_payload = {
        "model": settings.model,
        "input": prompt,
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
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="OpenAI returned invalid summary JSON",
        ) from exc

    return {
        "summary": normalize_summary_payload(summary_json),
        "model": settings.model,
        "prompt_version": DART_DISCLOSURE_SUMMARY_PROMPT_VERSION,
    }


class DisclosureSummaryService:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        data_group_store: DataGroupStore | None = None,
    ) -> None:
        self._transport = transport
        self._data_group_store = data_group_store

    async def _fetch_disclosure_text(
        self,
        query: DisclosureSummaryQuery,
    ) -> dict[str, Any]:
        if not validate_dart_viewer_url(query.viewer_url):
            raise HTTPException(status_code=400, detail="DART viewer_url is required")
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=30.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                response = await client.get(query.viewer_url)
                response.raise_for_status()
                viewer_html = response.text
                document_refs = extract_dart_viewer_document_refs(viewer_html)
                document_texts = []
                for ref in document_refs:
                    document_response = await client.get(
                        dart_viewer_document_url(query.viewer_url, ref)
                    )
                    document_response.raise_for_status()
                    document_text = extract_disclosure_text(document_response.text)
                    if document_text:
                        document_texts.append(document_text)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "DART disclosure request failed with status "
                    f"{exc.response.status_code}"
                ),
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail="DART disclosure request failed",
            ) from exc

        text = "\n\n".join(document_texts).strip()
        if not text:
            text = extract_disclosure_text(viewer_html)
        if not text:
            raise HTTPException(status_code=502, detail="DART disclosure text was empty")
        return {"receipt_no": query.receipt_no, "title": query.title, "text": text}

    async def fetch(self, query: DisclosureSummaryQuery) -> dict[str, Any]:
        try:
            settings = get_openai_settings(required=True)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY is not configured",
            ) from exc

        entity_key = disclosure_text_entity_key(query.receipt_no)
        summary_group = disclosure_summary_group_name(settings.model)

        if self._data_group_store is not None:
            cached = await self._data_group_store.get_record(
                entity_type=COMPANY_ENTITY_TYPE,
                entity_key=entity_key,
                group_name=summary_group,
            )
            if cached is not None:
                return {**cached.payload, "cached": True}

        if self._data_group_store is not None:
            text_payload = await fetch_with_group_store(
                store=self._data_group_store,
                entity_type=COMPANY_ENTITY_TYPE,
                entity_key=entity_key,
                group_name=DART_DISCLOSURE_TEXT_GROUP,
                source="dart:viewer",
                ttl=None,
                fetcher=lambda: self._fetch_disclosure_text(query),
            )
        else:
            text_payload = await self._fetch_disclosure_text(query)

        summary_payload = await summarize_with_openai(
            title=query.title,
            text=text_payload["text"],
            transport=self._transport,
        )
        payload = {
            "receipt_no": query.receipt_no,
            "title": query.title,
            "summary": summary_payload["summary"],
            "model": summary_payload["model"],
            "prompt_version": summary_payload["prompt_version"],
            "cached": False,
        }

        if self._data_group_store is not None:
            await self._data_group_store.upsert_record(
                entity_type=COMPANY_ENTITY_TYPE,
                entity_key=entity_key,
                group_name=summary_group,
                source="openai:responses",
                payload=payload,
                ttl=None,
            )
        return payload
