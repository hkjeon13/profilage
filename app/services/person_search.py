from __future__ import annotations

import asyncio
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
import re
import secrets
import socket
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import (
    get_cache_settings,
    get_openai_settings,
    get_person_search_settings,
    get_searchapi_api_key,
)

WIKIPEDIA_API = "https://ko.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"
BLOCKED_SOCIAL_DOMAINS = {
    "linkedin.com", "www.linkedin.com", "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com", "threads.net", "www.threads.net",
}
BLOCKED_CAPTURE_DOMAINS = BLOCKED_SOCIAL_DOMAINS | {"namu.wiki", "www.namu.wiki"}
PUBLIC_ANALYSIS_DOMAINS = {
    "wikipedia.org", "ko.wikipedia.org", "en.wikipedia.org", "wikimedia.org",
    "wikidata.org", "www.wikidata.org",
}


def _opaque(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(18)}"


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _domain_matches(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


class EphemeralPersonStore:
    def __init__(self) -> None:
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._redis = None
        url = get_person_search_settings().ephemeral_valkey_url or get_cache_settings().valkey_url
        if url:
            from redis import asyncio as redis
            self._redis = redis.from_url(url, decode_responses=True)

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        if self._redis is not None:
            await self._redis.set(f"person:{key}", json.dumps(value, ensure_ascii=False), ex=ttl)
            return
        self._memory[key] = (time.monotonic() + ttl, value)

    async def get(self, key: str) -> dict[str, Any] | None:
        if self._redis is not None:
            raw = await self._redis.get(f"person:{key}")
            return json.loads(raw) if raw else None
        stored = self._memory.get(key)
        if not stored or stored[0] <= time.monotonic():
            self._memory.pop(key, None)
            return None
        return stored[1]

    async def delete(self, key: str) -> None:
        if self._redis is not None:
            await self._redis.delete(f"person:{key}")
        self._memory.pop(key, None)

    async def list_values(self, prefix: str) -> list[dict[str, Any]]:
        if self._redis is not None:
            keys = await self._redis.keys(f"person:{prefix}*")
            if not keys:
                return []
            values = await self._redis.mget(keys)
            return [json.loads(value) for value in values if value]
        now = time.monotonic()
        return [value for key, (expires, value) in self._memory.items()
                if key.startswith(prefix) and expires > now]

    async def enqueue(self, queue: str, value: dict[str, Any]) -> None:
        if self._redis is None:
            raise RuntimeError("ephemeral_valkey_required")
        await self._redis.rpush(f"person:{queue}", json.dumps(value, ensure_ascii=False))


_store: EphemeralPersonStore | None = None


def get_person_store() -> EphemeralPersonStore:
    global _store
    if _store is None:
        _store = EphemeralPersonStore()
    return _store


def reset_person_store() -> None:
    global _store
    _store = None


async def _wikipedia_candidates(query: str, limit: int, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(WIKIPEDIA_API, params={
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrlimit": min(limit, 10), "prop": "pageprops|extracts|info",
        "exintro": 1, "explaintext": 1, "inprop": "url", "format": "json", "origin": "*",
    })
    response.raise_for_status()
    pages = list(response.json().get("query", {}).get("pages", {}).values())
    pages.sort(key=lambda page: page.get("index", 999))
    qids = [str((page.get("pageprops") or {}).get("wikibase_item") or "") for page in pages]
    qids = [qid for qid in qids if qid]
    human_qids: set[str] = set()
    if qids:
        entity_response = await client.get(WIKIDATA_API, params={
            "action": "wbgetentities", "ids": "|".join(qids), "props": "claims", "format": "json", "origin": "*",
        })
        entity_response.raise_for_status()
        for qid, entity in entity_response.json().get("entities", {}).items():
            instances = (entity.get("claims") or {}).get("P31", [])
            if any(str((((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id")) == "Q5"
                   for claim in instances):
                human_qids.add(qid)
    items = []
    for page in pages:
        qid = str((page.get("pageprops") or {}).get("wikibase_item") or "")
        if qid not in human_qids:
            continue
        title = str(page.get("title") or "").strip()
        if not title:
            continue
        extract = re.sub(r"\s+", " ", str(page.get("extract") or "")).strip()
        url = page.get("fullurl") or f"https://ko.wikipedia.org/wiki/{title.replace(' ', '_')}"
        items.append({
            "display_name": title,
            "subtitle": extract[:150] or "위키백과 검색 결과",
            "roles": [],
            "identity_status": "public_source_found",
            "source_badges": ["위키백과"],
            "last_verified_at": time.strftime("%Y-%m-%d", time.gmtime()),
            "pages": [{
                "url": url, "domain": "ko.wikipedia.org", "title": title,
                "page_type": "encyclopedia", "display_capability": "direct_link_allowed",
                "analysis_capability": "server_public", "extract": extract,
                "wikidata_id": qid,
            }],
        })
    return items


async def _searchapi_pages(query: str, limit: int, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(SEARCHAPI_URL, params={
        "engine": "google", "q": f'"{query}" 인물 프로필 OR 인터뷰 OR 소개',
        "gl": "kr", "hl": "ko", "num": min(limit * 2, 20), "api_key": get_searchapi_api_key(),
    })
    response.raise_for_status()
    pages = []
    for item in response.json().get("organic_results", []):
        url = str(item.get("link") or "")
        host = _hostname(url)
        if not host:
            continue
        blocked = _domain_matches(host, BLOCKED_SOCIAL_DOMAINS)
        headless_domains = {value.strip().lower() for value in os.getenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "").split(",") if value.strip()}
        headless_allowed = bool(get_person_search_settings().headless_enabled and _domain_matches(host, headless_domains))
        pages.append({
            "url": None if blocked else url,
            "domain": host.removeprefix("www."),
            "title": None if blocked else str(item.get("title") or "")[:180],
            "page_type": "social_profile_link" if blocked else "public_web",
            "display_capability": "domain_only" if blocked else "direct_link_allowed",
            "analysis_capability": "external_view_only" if blocked else ("server_headless" if headless_allowed else "policy_review_required"),
        })
    return pages


async def search_people(query: str, limit: int, session_id: str) -> dict[str, Any]:
    settings = get_person_search_settings()
    limit = min(max(limit, 1), settings.search_limit)
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=False,
                                headers={"User-Agent": "Profilage/1.0 person-research"}) as client:
        wiki_result, web_result = await asyncio.gather(
            _wikipedia_candidates(query, limit, client),
            _searchapi_pages(query, limit, client),
            return_exceptions=True,
        )
    candidates = wiki_result if isinstance(wiki_result, list) else []
    web_pages = web_result if isinstance(web_result, list) else []
    partial = not isinstance(wiki_result, list) or not isinstance(web_result, list)
    if not candidates and web_pages:
        candidates = [{
            "display_name": query.split()[0], "subtitle": "공개 웹 후보 — 동일인 확인 필요",
            "roles": [], "identity_status": "needs_confirmation", "source_badges": ["웹 검색"],
            "last_verified_at": time.strftime("%Y-%m-%d", time.gmtime()), "pages": web_pages[:5],
        }]
    elif candidates and web_pages:
        candidates[0]["pages"].extend(web_pages[:5])
        candidates[0]["source_badges"].append("웹 검색")

    store = get_person_store()
    public_items = []
    for candidate in candidates[:limit]:
        candidate_id = _opaque("cand")
        pages = []
        stored_pages = {}
        for page in candidate.pop("pages", []):
            source_ref = _opaque("src")
            stored_pages[source_ref] = page
            pages.append({"source_ref": source_ref, **{k: v for k, v in page.items() if k not in {"url", "extract"}},
                          "open_url": page.get("url")})
        stored = {**candidate, "candidate_id": candidate_id, "session_id": session_id,
                  "pages": stored_pages, "created_at": int(time.time())}
        await store.set(f"candidate:{candidate_id}", stored, settings.candidate_ttl_seconds)
        public_items.append({"type": "person", "candidate_id": candidate_id, **candidate, "href": None, "pages": pages})
    notices = ["동명이인 여부와 소속·직책을 확인해 주세요."]
    if partial:
        notices.append("일부 외부 출처가 응답하지 않아 확인 가능한 결과만 표시합니다.")
    return {"query": {"text": query, "type": "person"}, "items": public_items,
            "partial": partial, "notices": notices}


async def get_owned_source(candidate_id: str, source_ref: str, session_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = await get_person_store().get(f"candidate:{candidate_id}")
    if not candidate or not secrets.compare_digest(str(candidate.get("session_id", "")), session_id):
        raise KeyError("candidate_not_found")
    source = candidate.get("pages", {}).get(source_ref)
    if not source:
        raise KeyError("source_not_found")
    return candidate, source


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}: self.skip += 1
        if tag == "title": self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip: self.skip -= 1
        if tag == "title": self._in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip: return
        clean = re.sub(r"\s+", " ", data).strip()
        if clean:
            if self._in_title: self.title += clean
            self.parts.append(clean)


async def _public_address(host: str) -> None:
    loop = asyncio.get_running_loop()
    records = await loop.run_in_executor(None, lambda: socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        if not address.is_global:
            raise ValueError("private_network_blocked")


async def _fetch_public_page(url: str) -> tuple[str, str, str]:
    settings = get_person_search_settings()
    current = url
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=False,
                                headers={"User-Agent": "Profilage/1.0 page-analysis"}) as client:
        for _ in range(4):
            parsed = urlparse(current)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("https_required")
            await _public_address(parsed.hostname)
            response = await client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                target = response.headers.get("location")
                if not target: raise ValueError("invalid_redirect")
                current = urljoin(current, target)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "text/plain" not in content_type:
                raise ValueError("unsupported_content_type")
            raw = response.content[:settings.max_page_bytes + 1]
            if len(raw) > settings.max_page_bytes: raise ValueError("page_too_large")
            parser = _TextExtractor(); parser.feed(raw.decode(response.encoding or "utf-8", errors="replace"))
            return current, parser.title[:200], "\n".join(parser.parts)[:18000]
    raise ValueError("too_many_redirects")


async def analyze_page(candidate_id: str, source_ref: str, session_id: str) -> dict[str, Any]:
    candidate, source = await get_owned_source(candidate_id, source_ref, session_id)
    url = source.get("url")
    host = _hostname(url or "")
    if not url or _domain_matches(host, BLOCKED_CAPTURE_DOMAINS):
        raise PermissionError("platform_permission_required")
    if source.get("analysis_capability") == "policy_review_required" and not _domain_matches(host, PUBLIC_ANALYSIS_DOMAINS):
        raise PermissionError("domain_not_reviewed")
    trusted_extract = str(source.get("extract") or "").strip()
    if trusted_extract and _domain_matches(host, PUBLIC_ANALYSIS_DOMAINS):
        final_url, title, content = url, str(source.get("title") or ""), trusted_extract
    else:
        final_url, title, content = await _fetch_public_page(url)
    if len(content) < 80:
        raise ValueError("insufficient_page_content")
    evidence = content[:9000]
    summary = None
    settings = get_openai_settings(required=False)
    if settings.api_key:
        prompt = (
            "다음 공개 페이지 한 건만 근거로 한국어 JSON을 작성하세요. 추측, 성격/능력 진단, 민감정보 추론은 금지합니다. "
            "키는 summary(3문장 이내), topics(문자열 배열), observable_communication_features(문자열 배열), limitations(문자열 배열)입니다. "
            f"대상 후보: {candidate.get('display_name')}\n페이지: {title}\n본문:\n{evidence}"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers={
                "Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}, json={
                "model": settings.model, "input": prompt, "text": {"format": {"type": "json_object"}},
            })
            response.raise_for_status()
            payload = response.json()
            output_text = payload.get("output_text")
            if not output_text:
                output_text = "".join(part.get("text", "") for item in payload.get("output", [])
                                      for part in item.get("content", []) if part.get("type") == "output_text")
            summary = json.loads(output_text)
    if summary is None:
        summary = {"summary": evidence[:500], "topics": [], "observable_communication_features": [],
                   "limitations": ["LLM 요약을 사용할 수 없어 본문 일부만 표시합니다."]}
    result_id = _opaque("par")
    result = {"result_id": result_id, "candidate_id": candidate_id, "page_title": title or source.get("title"),
              "domain": _hostname(final_url), "source_url": final_url, "analysis": summary,
              "evidence": [{"quote": re.sub(r"\s+", " ", evidence[:450]), "content_hash": "sha256:" + hashlib.sha256(evidence.encode()).hexdigest()}],
              "limitations": ["이 결과는 사용자가 선택한 한 페이지에만 기반하며, 이 인물 전체를 대표하지 않습니다."],
              "expires_in_seconds": get_person_search_settings().analysis_ttl_seconds}
    result["subject_identity"] = next((item.get("wikidata_id") for item in candidate.get("pages", {}).values()
                                       if item.get("wikidata_id")), None)
    await get_person_store().set(f"result:{result_id}:{session_id}", result, get_person_search_settings().analysis_ttl_seconds)
    return result
