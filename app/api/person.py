import re

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.person_search import analyze_page, search_people
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
