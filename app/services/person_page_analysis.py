from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import os
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from app.services.person_profile import _save_profile, get_person_profile
from app.services.headless_fetch import issue_fetch_ticket
from app.core.config import get_person_search_settings
from app.services.person_search import (
    BLOCKED_CAPTURE_DOMAINS,
    PUBLIC_ANALYSIS_DOMAINS,
    _domain_matches,
    _hostname,
    _opaque,
    analyze_page,
    get_owned_source,
    get_person_store,
)

POLICY_VERSION = "page-analysis-v1"
INTENT_TTL = 300
CAPTURE_TTL = 900
RESULT_TTL = 3600


def _iso_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def _capture_allowed(host: str) -> bool:
    # Browser Companion is intentionally limited to the reviewed public-source registry.
    configured = {item.strip().lower() for item in os.getenv("PERSON_BROWSER_CAPTURE_ALLOWED_DOMAINS", "").split(",") if item.strip()}
    return _domain_matches(host, PUBLIC_ANALYSIS_DOMAINS | configured)


def _headless_allowed(host: str) -> bool:
    configured = {item.strip().lower() for item in os.getenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "").split(",") if item.strip()}
    return bool(get_person_search_settings().headless_enabled and configured and _domain_matches(host, configured))


async def create_intent(candidate_id: str, source_ref: str, session_id: str,
                        purpose_code: str, requested_mode: str) -> dict[str, Any]:
    candidate, source = await get_owned_source(candidate_id, source_ref, session_id)
    url = source.get("url") or ""
    host = _hostname(url)
    capability = source.get("analysis_capability") or "external_view_only"
    reason = None
    capture_token = None
    if not url or _domain_matches(host, BLOCKED_CAPTURE_DOMAINS):
        capability, reason = "external_view_only", "platform_permission_required"
    elif capability == "server_public":
        capability = "server_public"
    elif requested_mode == "browser_selection" and _capture_allowed(host):
        capability = "browser_selection"
    elif requested_mode == "headless" and _headless_allowed(host):
        capability = "server_headless"
    else:
        capability, reason = "policy_review_required", "domain_not_reviewed"
    intent_id = _opaque("pai")
    if capability == "browser_selection":
        capture_token = secrets.token_urlsafe(32)
    intent = {
        "intent_id": intent_id, "candidate_id": candidate_id, "source_ref": source_ref,
        "session_id": session_id, "purpose_code": purpose_code, "capability": capability,
        "capture_token_hash": hashlib.sha256(capture_token.encode()).hexdigest() if capture_token else None,
        "normalized_url_hash": hashlib.sha256(url.encode()).hexdigest(), "state": "issued",
        "created_at": int(time.time()), "expires_at": _iso_after(INTENT_TTL),
        "policy_version": POLICY_VERSION,
        "subject_identity": next((item.get("wikidata_id") for item in candidate.get("pages", {}).values()
                                  if item.get("wikidata_id")), None),
    }
    await get_person_store().set(f"intent:{intent_id}", intent, INTENT_TTL)
    return {"intent_id": intent_id, "capability": capability, "capture_token": capture_token,
            "expires_at": intent["expires_at"], "attach_capability": "requires_recheck",
            "policy_version": POLICY_VERSION, "reason": reason,
            "notice": "현재 페이지 한 건만 분석하며 결과는 1시간 후 삭제됩니다."}


async def analyze_intent(intent_id: str, session_id: str) -> dict[str, Any]:
    store = get_person_store(); intent = await store.get(f"intent:{intent_id}")
    if not intent or intent.get("session_id") != session_id:
        raise KeyError("intent_not_found")
    if intent.get("state") != "issued":
        raise RuntimeError("intent_already_used")
    if intent.get("capability") not in {"server_public", "server_headless"}:
        raise PermissionError("capability_not_allowed")
    intent["state"] = "processing"; await store.set(f"intent:{intent_id}", intent, INTENT_TTL)
    job_id = _opaque("paj")
    job = {"job_id": job_id, "intent_id": intent_id, "session_id": session_id,
           "status": "processing", "created_at": int(time.time()), "deadline_at": _iso_after(600)}
    await store.set(f"job:{job_id}", job, RESULT_TTL)
    if intent.get("capability") == "server_headless":
        _, source = await get_owned_source(intent["candidate_id"], intent["source_ref"], session_id)
        ticket = issue_fetch_ticket(str(source.get("url") or ""), job_id=job_id)
        job.update({"status": "queued", "mode": "headless", "ticket_expires_at": ticket.expires_at})
        intent["state"] = "job_queued"
        await store.set(f"job:{job_id}", job, RESULT_TTL)
        await store.set(f"intent:{intent_id}", intent, INTENT_TTL)
        await store.enqueue("renderer:queue", {
            "job_id": job_id, "intent_id": intent_id, "session_id": session_id,
            "candidate_id": intent["candidate_id"], "subject_identity": intent.get("subject_identity"),
            "source_title": str(source.get("title") or "")[:200], "ticket": ticket.token,
            "deadline": int(time.time()) + 30, "result_ttl": RESULT_TTL,
        })
        return {"job_id": job_id, "job_deadline_at": job["deadline_at"],
                "result_ttl_seconds": RESULT_TTL, "status": "queued"}
    try:
        result = await analyze_page(intent["candidate_id"], intent["source_ref"], session_id)
        result["job_id"] = job_id; result["intent_id"] = intent_id
        await store.set(f"result:{result['result_id']}:{session_id}", result, RESULT_TTL)
        job.update({"status": "result_ready", "result_id": result["result_id"]})
        intent["state"] = "result_ready"
    except Exception:
        job["status"] = "failed"; intent["state"] = "failed"
        await store.set(f"job:{job_id}", job, RESULT_TTL)
        await store.set(f"intent:{intent_id}", intent, INTENT_TTL)
        raise
    await store.set(f"job:{job_id}", job, RESULT_TTL)
    await store.set(f"intent:{intent_id}", intent, INTENT_TTL)
    return {"job_id": job_id, "job_deadline_at": job["deadline_at"],
            "result_ttl_seconds": RESULT_TTL, "status": "result_ready", "result_id": result["result_id"]}


async def capture_selection(intent_id: str, capture_token: str, page: dict[str, Any],
                            blocks: list[dict[str, Any]], user_reviewed: bool) -> dict[str, Any]:
    store = get_person_store(); intent = await store.get(f"intent:{intent_id}")
    if not intent or intent.get("state") != "issued":
        raise KeyError("intent_not_found")
    supplied_hash = hashlib.sha256(capture_token.encode()).hexdigest()
    if not intent.get("capture_token_hash") or not secrets.compare_digest(intent["capture_token_hash"], supplied_hash):
        raise PermissionError("invalid_capture_token")
    if intent.get("capability") != "browser_selection" or not user_reviewed:
        raise PermissionError("capture_not_allowed")
    url = str(page.get("url") or "")
    if hashlib.sha256(url.encode()).hexdigest() != intent.get("normalized_url_hash"):
        raise PermissionError("url_mismatch")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not _capture_allowed((parsed.hostname or "").lower()):
        raise PermissionError("domain_not_allowed")
    if not blocks or len(blocks) > 100:
        raise ValueError("invalid_blocks")
    text = "\n".join(str(block.get("text") or "")[:4000] for block in blocks)[:25000].strip()
    if len(text) < 80:
        raise ValueError("insufficient_content")
    intent["state"] = "result_ready"; intent["capture_token_hash"] = None
    result_id, job_id = _opaque("par"), _opaque("paj")
    result = {
        "result_id": result_id, "job_id": job_id, "intent_id": intent_id,
        "candidate_id": intent["candidate_id"], "page_title": str(page.get("title") or "")[:200],
        "domain": _hostname(url), "source_url": url,
        "analysis": {"summary": text[:700], "topics": [], "observable_communication_features": [],
                     "limitations": ["Browser Companion에서 사용자가 선택한 텍스트만 분석했습니다."]},
        "evidence": [{"quote": text[:450], "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest()}],
        "limitations": ["이 결과는 사용자가 선택한 한 페이지의 일부 텍스트만 기반으로 합니다."],
        "expires_in_seconds": RESULT_TTL,
        "subject_identity": intent.get("subject_identity"),
    }
    job = {"job_id": job_id, "intent_id": intent_id, "session_id": intent["session_id"],
           "status": "result_ready", "result_id": result_id, "created_at": int(time.time())}
    await store.set(f"result:{result_id}:{intent['session_id']}", result, RESULT_TTL)
    await store.set(f"job:{job_id}", job, RESULT_TTL)
    await store.set(f"intent:{intent_id}", intent, INTENT_TTL)
    return {"job_id": job_id, "status": "result_ready", "result_id": result_id,
            "result_ttl_seconds": RESULT_TTL, "capture_purge_at": _iso_after(CAPTURE_TTL)}


async def get_job(job_id: str, session_id: str) -> dict[str, Any]:
    job = await get_person_store().get(f"job:{job_id}")
    if not job or job.get("session_id") != session_id: raise KeyError("job_not_found")
    return job


async def get_result(result_id: str, session_id: str) -> dict[str, Any]:
    result = await get_person_store().get(f"result:{result_id}:{session_id}")
    if not result: raise KeyError("result_not_found")
    return result


async def active_items(session_id: str) -> dict[str, Any]:
    jobs = [item for item in await get_person_store().list_values("job:") if item.get("session_id") == session_id]
    results = []
    for job in jobs:
        if job.get("result_id"):
            result = await get_person_store().get(f"result:{job['result_id']}:{session_id}")
            if result: results.append({"result_id": result["result_id"], "job_id": job["job_id"], "domain": result.get("domain")})
    return {"jobs": jobs, "results": results}


async def delete_item(kind: str, item_id: str, session_id: str) -> None:
    store = get_person_store()
    if kind == "result":
        if not await store.get(f"result:{item_id}:{session_id}"): raise KeyError("not_found")
        await store.delete(f"result:{item_id}:{session_id}")
        return
    item = await store.get(f"{kind}:{item_id}")
    if not item or item.get("session_id") != session_id: raise KeyError("not_found")
    if kind == "job":
        await store.set(f"cancel:{item_id}", {"job_id": item_id, "cancelled_at": int(time.time())}, RESULT_TTL)
    await store.delete(f"{kind}:{item_id}")


async def attach_result(result_id: str, person_id: str, session_id: str) -> dict[str, Any]:
    result = await get_result(result_id, session_id); profile = await get_person_profile(person_id)
    if not profile: raise KeyError("person_not_found")
    qid = next((item.get("display_value") for item in profile.get("identifiers", []) if item.get("kind") == "wikidata"), None)
    if result.get("subject_identity") and result.get("subject_identity") != qid:
        raise PermissionError("identity_mismatch")
    evidence = result.get("evidence", [])
    for item in evidence:
        item["evidence_id"] = _opaque("pevd"); item["source_id"] = _opaque("psrc")
        item["author_match"] = "unverified"
    profile["evidence"] = [*profile.get("evidence", []), *evidence]
    await _save_profile(person_id, profile)
    await get_person_store().delete(f"result:{result_id}:{session_id}")
    return {"status": "attached", "person_id": person_id, "evidence_count": len(evidence)}
