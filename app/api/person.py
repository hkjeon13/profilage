import re

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.person_search import analyze_page, search_people
from app.services.person_profile import (
    get_person_profile,
    get_person_summary,
    resolve_candidate,
    submit_rights_request,
)
from app.services.person_page_analysis import (
    active_items,
    analyze_intent,
    attach_result,
    capture_selection,
    create_intent,
    delete_item,
    get_job,
    get_result,
)
from app.api.rate_limit import enforce_summary_rate_limit
from app.core.config import get_app_settings

router = APIRouter(prefix="/person", tags=["person"])
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


class PersonSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=10, ge=1, le=20)
    purpose_code: str = Field(default="business_research", pattern=r"^[a-z_]{3,40}$")


class PageAnalysisRequest(BaseModel):
    candidate_id: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")
    source_ref: str = Field(pattern=r"^src_[A-Za-z0-9_-]+$")
    purpose_code: str = Field(default="business_research", pattern=r"^[a-z_]{3,40}$")


class ResolveRequest(BaseModel):
    candidate_id: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")
    purpose_code: str = Field(default="business_research", pattern=r"^[a-z_]{3,40}$")
    idempotency_key: str = Field(min_length=8, max_length=100)


class CorrectionRequest(BaseModel):
    kind: str = Field(pattern=r"^(correction|deletion|search_exclusion)$")
    detail: str = Field(min_length=3, max_length=1000)


class SubjectRef(BaseModel):
    candidate_id: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")


class IntentRequest(BaseModel):
    subject_ref: SubjectRef
    source_ref: str = Field(pattern=r"^src_[A-Za-z0-9_-]+$")
    purpose_code: str = Field(default="business_research", pattern=r"^[a-z_]{3,40}$")
    requested_mode: str = Field(default="server_public", pattern=r"^(server_public|browser_selection|headless)$")


class CapturePage(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    title: str = Field(default="", max_length=200)
    lang: str = Field(default="", max_length=20)
    captured_at: str | None = None


class CaptureBlock(BaseModel):
    client_block_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="main_text", max_length=40)
    text: str = Field(min_length=1, max_length=4000)
    locator: str | None = Field(default=None, max_length=500)


class CaptureRequest(BaseModel):
    intent_id: str = Field(pattern=r"^pai_[A-Za-z0-9_-]+$")
    page: CapturePage
    capture_mode: str = Field(pattern=r"^selection$")
    blocks: list[CaptureBlock] = Field(min_length=1, max_length=100)
    content_hash: str | None = Field(default=None, max_length=100)
    user_reviewed: bool


class AttachRequest(BaseModel):
    person_id: str = Field(pattern=r"^per_[a-f0-9]{24}$")
    purpose_code: str = Field(default="business_research", pattern=r"^[a-z_]{3,40}$")
    idempotency_key: str = Field(min_length=8, max_length=100)


class SourceReviewRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    purpose_code: str = Field(default="business_research", pattern=r"^[a-z_]{3,40}$")


def require_session(x_profilage_session: str = Header(alias="X-Profilage-Session")) -> str:
    if not SESSION_RE.fullmatch(x_profilage_session):
        raise HTTPException(status_code=400, detail="유효한 검색 세션이 필요합니다.")
    return x_profilage_session


@router.post("/search")
async def person_search(payload: PersonSearchRequest, request: Request, session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    enforce_summary_rate_limit(request, limit=get_app_settings().summary_rate_limit_per_minute)
    query = " ".join(payload.query.split())
    try:
        return await search_people(query, payload.limit, session_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="인물 검색 제공자 응답을 확인하지 못했습니다.") from exc


@router.post("/page-analysis")
async def person_page_analysis(payload: PageAnalysisRequest, request: Request, session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    enforce_summary_rate_limit(request, limit=max(get_app_settings().summary_rate_limit_per_minute // 2, 3))
    try:
        return await analyze_page(payload.candidate_id, payload.source_ref, session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="검색 후보 또는 출처가 만료되었습니다.") from exc
    except PermissionError as exc:
        reason = str(exc)
        detail = "플랫폼 권한이 없어 링크만 제공합니다." if "platform" in reason else "아직 분석이 승인되지 않은 도메인입니다."
        raise HTTPException(status_code=403, detail=detail) from exc
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail="페이지 본문을 안전하게 분석할 수 없습니다.") from exc


@router.post("/resolve")
async def person_resolve(payload: ResolveRequest, request: Request,
                         session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    enforce_summary_rate_limit(request, limit=get_app_settings().summary_rate_limit_per_minute)
    try:
        return await resolve_candidate(payload.candidate_id, session_id, payload.purpose_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="검색 후보가 만료되었거나 이미 사용되었습니다.") from exc


@router.get("/{person_id}")
async def person_profile(person_id: str):
    if not re.fullmatch(r"per_[a-f0-9]{24}", person_id):
        raise HTTPException(status_code=404, detail="인물 프로필을 찾을 수 없습니다.")
    profile = await get_person_profile(person_id)
    if not profile:
        raise HTTPException(status_code=404, detail="인물 프로필을 찾을 수 없습니다.")
    return profile


@router.get("/{person_id}/sources")
async def person_sources(person_id: str):
    profile = await get_person_profile(person_id)
    if not profile:
        raise HTTPException(status_code=404, detail="인물 프로필을 찾을 수 없습니다.")
    return {"person_id": person_id, "items": profile.get("sources", [])}


@router.get("/{person_id}/summary")
async def person_summary(person_id: str, request: Request):
    enforce_summary_rate_limit(request, limit=get_app_settings().summary_rate_limit_per_minute)
    try:
        return await get_person_summary(person_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="인물 프로필을 찾을 수 없습니다.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="인물 요약을 생성하지 못했습니다.") from exc


@router.post("/{person_id}/refresh")
async def person_refresh(person_id: str, request: Request):
    enforce_summary_rate_limit(request, limit=max(get_app_settings().summary_rate_limit_per_minute // 3, 2))
    try:
        return await get_person_summary(person_id, refresh=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="인물 프로필을 찾을 수 없습니다.") from exc


@router.post("/{person_id}/correction", status_code=202)
async def person_correction(person_id: str, payload: CorrectionRequest,
                            session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    try:
        return await submit_rights_request(person_id, payload.kind, payload.detail, session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="인물 프로필을 찾을 수 없습니다.") from exc


@router.post("/page-analysis/intents")
async def page_intent(payload: IntentRequest, session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    try:
        return await create_intent(payload.subject_ref.candidate_id, payload.source_ref, session_id,
                                   payload.purpose_code, payload.requested_mode)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="검색 후보 또는 출처가 만료되었습니다.") from exc


@router.post("/page-analysis/intents/{intent_id}/analyze", status_code=202)
async def page_intent_analyze(intent_id: str, session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    try:
        return await analyze_intent(intent_id, session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="분석 요청이 만료되었습니다.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="이미 사용된 분석 요청입니다.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="이 출처에는 해당 분석 방식을 사용할 수 없습니다.") from exc


@router.post("/page-analysis/captures", status_code=202)
async def page_capture(payload: CaptureRequest, authorization: str = Header(alias="Authorization")):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "capture" or not token:
        raise HTTPException(status_code=401, detail="유효한 capture token이 필요합니다.")
    try:
        return await capture_selection(payload.intent_id, token, payload.page.model_dump(),
                                       [item.model_dump() for item in payload.blocks], payload.user_reviewed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="분석 요청이 만료되었습니다.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="페이지 선택 내용을 수락할 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="선택한 페이지 내용이 분석 기준을 충족하지 않습니다.") from exc


@router.get("/page-analysis/jobs/{job_id}")
async def page_job(job_id: str, session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    try: return await get_job(job_id, session_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다.") from exc


@router.get("/page-analysis/results/{result_id}")
async def page_result(result_id: str, session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    try: return await get_result(result_id, session_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail="분석 결과가 만료되었거나 삭제되었습니다.") from exc


@router.get("/page-analysis/active")
async def page_active(session_id: str = Header(alias="X-Profilage-Session")):
    return await active_items(require_session(session_id))


@router.post("/page-analysis/source-review-requests", status_code=202)
async def source_review(payload: SourceReviewRequest,
                        session_id: str = Header(alias="X-Profilage-Session")):
    from app.services.person_search import _opaque, get_person_store
    import time
    session_id = require_session(session_id)
    request_id = _opaque("psr")
    await get_person_store().set(f"source-review:{request_id}", {
        "request_id": request_id, "domain": payload.domain.lower(), "purpose_code": payload.purpose_code,
        "session_id": session_id, "status": "received", "created_at": int(time.time()),
    }, 30 * 86400)
    return {"request_id": request_id, "status": "received"}


@router.post("/page-analysis/results/{result_id}/attach")
async def page_attach(result_id: str, payload: AttachRequest,
                      session_id: str = Header(alias="X-Profilage-Session")):
    session_id = require_session(session_id)
    try: return await attach_result(result_id, payload.person_id, session_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail="프로필 또는 분석 결과를 찾을 수 없습니다.") from exc
    except PermissionError as exc: raise HTTPException(status_code=403, detail="인물 연결을 확인할 수 없어 프로필에 반영하지 않았습니다.") from exc


@router.delete("/page-analysis/intents/{intent_id}", status_code=204)
async def delete_intent(intent_id: str, session_id: str = Header(alias="X-Profilage-Session")):
    try: await delete_item("intent", intent_id, require_session(session_id))
    except KeyError as exc: raise HTTPException(status_code=404, detail="분석 요청을 찾을 수 없습니다.") from exc


@router.delete("/page-analysis/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, session_id: str = Header(alias="X-Profilage-Session")):
    try: await delete_item("job", job_id, require_session(session_id))
    except KeyError as exc: raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다.") from exc


@router.delete("/page-analysis/results/{result_id}", status_code=204)
async def delete_result(result_id: str, session_id: str = Header(alias="X-Profilage-Session")):
    try: await delete_item("result", result_id, require_session(session_id))
    except KeyError as exc: raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.") from exc
