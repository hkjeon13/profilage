from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import re
import time
from typing import Any

import httpx

from app.core.config import get_openai_settings
from app.services.company_store import get_default_data_group_store
from app.services.person_search import get_person_store, _opaque

PERSON_ENTITY_TYPE = "person"
PERSON_PROFILE_GROUP = "person_profile"
PERSON_SUMMARY_GROUP = "person_summary"
PUBLIC_PROFILE_TTL = timedelta(days=90)


def _public_person_id(wikidata_id: str) -> str:
    digest = hashlib.sha256(f"wikidata:{wikidata_id}".encode()).hexdigest()[:24]
    return f"per_{digest}"


def _public_source(source_ref: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": f"psrc_{hashlib.sha256(source_ref.encode()).hexdigest()[:20]}",
        "source_ref": source_ref,
        "domain": source.get("domain"),
        "title": source.get("title"),
        "source_type": source.get("page_type"),
        "open_url": source.get("url") if source.get("display_capability") == "direct_link_allowed" else None,
        "display_capability": source.get("display_capability"),
        "analysis_capability": source.get("analysis_capability"),
        "wikidata_id": source.get("wikidata_id"),
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def _save_profile(person_id: str, payload: dict[str, Any]) -> None:
    store = get_default_data_group_store()
    if store is not None:
        await store.upsert_record(entity_type=PERSON_ENTITY_TYPE, entity_key=person_id,
                                  group_name=PERSON_PROFILE_GROUP, source="person:resolve",
                                  payload=payload, ttl=PUBLIC_PROFILE_TTL)
    else:
        await get_person_store().set(f"profile:{person_id}", payload, int(PUBLIC_PROFILE_TTL.total_seconds()))


async def get_person_profile(person_id: str) -> dict[str, Any] | None:
    store = get_default_data_group_store()
    if store is not None:
        record = await store.get_record(entity_type=PERSON_ENTITY_TYPE, entity_key=person_id,
                                        group_name=PERSON_PROFILE_GROUP)
        return record.payload if record else None
    return await get_person_store().get(f"profile:{person_id}")


async def resolve_candidate(candidate_id: str, session_id: str, purpose_code: str) -> dict[str, Any]:
    candidate = await get_person_store().get(f"candidate:{candidate_id}")
    if not candidate or candidate.get("session_id") != session_id:
        raise KeyError("candidate_not_found")
    if purpose_code != "business_research":
        return {"status": "not_materialized", "policy_mode": "discovery_only", "reason": "processing_basis_required"}
    source_items = list((candidate.get("pages") or {}).items())
    qid = next((source.get("wikidata_id") for _, source in source_items if source.get("wikidata_id")), None)
    if not qid:
        return {"status": "not_materialized", "policy_mode": "discovery_only", "reason": "public_role_not_verified"}
    person_id = _public_person_id(str(qid))
    sources = [_public_source(ref, source) for ref, source in source_items]
    evidence = [{
        "evidence_id": f"pevd_{hashlib.sha256((ref + str(source.get('extract', ''))).encode()).hexdigest()[:20]}",
        "source_id": _public_source(ref, source)["source_id"],
        "text": re.sub(r"\s+", " ", str(source.get("extract") or ""))[:1200],
        "author_match": "reference_source",
    } for ref, source in source_items if source.get("extract")]
    profile = {
        "person_id": person_id, "display_name": candidate.get("display_name"),
        "subtitle": candidate.get("subtitle"), "roles": candidate.get("roles", []),
        "policy_mode": "public_role", "visibility": "public", "status": "active",
        "identifiers": [{"kind": "wikidata", "display_value": qid}],
        "sources": sources, "evidence": evidence,
        "processing_basis": {"purpose_code": purpose_code, "basis_type": "public_information_business_research",
                             "policy_version": "public-role-v1"},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_verified_at": candidate.get("last_verified_at"),
    }
    await _save_profile(person_id, profile)
    await get_person_store().delete(f"candidate:{candidate_id}")
    return {"status": "materialized", "person_id": person_id, "policy_mode": "public_role",
            "access": "public", "href": f"/person/profile?person_id={person_id}"}


async def get_person_summary(person_id: str, *, refresh: bool = False) -> dict[str, Any]:
    profile = await get_person_profile(person_id)
    if not profile:
        raise KeyError("person_not_found")
    fingerprint = hashlib.sha256(json.dumps({"evidence": profile.get("evidence"), "sources": profile.get("sources")},
                                           ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    data_store = get_default_data_group_store()
    if data_store is not None and not refresh:
        cached = await data_store.get_record(entity_type=PERSON_ENTITY_TYPE, entity_key=person_id,
                                             group_name=PERSON_SUMMARY_GROUP)
        if cached and cached.payload.get("fingerprint") == fingerprint:
            return {**cached.payload, "cached": True}
    evidence_text = "\n".join(item.get("text", "") for item in profile.get("evidence", []))[:16000]
    settings = get_openai_settings(required=False)
    if settings.api_key and evidence_text:
        prompt = (
            "다음 공개 근거만으로 인물 프로필 요약 JSON을 한국어로 작성하세요. 민감정보, 성격, 능력, 숨은 의도는 추론하지 마세요. "
            "JSON 키: headline, overview, verified_facts(배열), public_topics(배열), limitations(배열), evidence_ids(배열). "
            f"인물: {profile.get('display_name')}\n근거:\n{evidence_text}"
        )
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers={
                "Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
                json={"model": settings.model, "input": prompt, "text": {"format": {"type": "json_object"}}})
            response.raise_for_status()
            raw = response.json(); output_text = raw.get("output_text") or "".join(
                part.get("text", "") for output in raw.get("output", []) for part in output.get("content", [])
                if part.get("type") == "output_text")
            summary = json.loads(output_text)
    else:
        summary = {"headline": profile.get("subtitle"), "overview": evidence_text[:700],
                   "verified_facts": [], "public_topics": [],
                   "limitations": ["공개 근거가 제한적이어서 확인 가능한 설명만 표시합니다."],
                   "evidence_ids": [item.get("evidence_id") for item in profile.get("evidence", [])]}
    payload = {"person_id": person_id, "summary": summary, "fingerprint": fingerprint,
               "model": settings.model if settings.api_key else None, "prompt_version": "person-summary-v1",
               "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cached": False}
    if data_store is not None:
        await data_store.upsert_record(entity_type=PERSON_ENTITY_TYPE, entity_key=person_id,
                                       group_name=PERSON_SUMMARY_GROUP, source="openai:responses",
                                       payload=payload, ttl=PUBLIC_PROFILE_TTL)
    return payload


async def submit_rights_request(person_id: str, kind: str, detail: str, session_id: str) -> dict[str, Any]:
    if not await get_person_profile(person_id):
        raise KeyError("person_not_found")
    request_id = _opaque("prr")
    await get_person_store().set(f"rights:{request_id}", {
        "request_id": request_id, "person_id": person_id, "kind": kind,
        "detail": detail[:1000], "status": "received", "session_id": session_id,
        "created_at": int(time.time()),
    }, 30 * 86400)
    return {"request_id": request_id, "status": "received"}
