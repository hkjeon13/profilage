from fastapi.testclient import TestClient

from app.main import app
from app.services import person_search


SESSION = "0123456789abcdef0123456789abcdef"


def test_person_search_requires_session():
    with TestClient(app) as client:
        response = client.post("/api/person/search", json={"query": "홍길동"})
    assert response.status_code == 422


def test_person_search_returns_session_bound_candidates(monkeypatch):
    async def fake_wiki(query, limit, client):
        return [{
            "display_name": "홍길동", "subtitle": "가상 인물", "roles": [],
            "identity_status": "public_source_found", "source_badges": ["위키백과"],
            "last_verified_at": "2026-07-11", "pages": [{
                "url": "https://ko.wikipedia.org/wiki/test", "domain": "ko.wikipedia.org",
                "title": "홍길동", "page_type": "encyclopedia",
                "display_capability": "direct_link_allowed", "analysis_capability": "server_public",
                "extract": "공개 설명",
            }],
        }]

    async def fake_web(query, limit, client):
        return [{"url": None, "domain": "linkedin.com", "title": None,
                 "page_type": "social_profile_link", "display_capability": "domain_only",
                 "analysis_capability": "external_view_only"}]

    monkeypatch.setattr(person_search, "_wikipedia_candidates", fake_wiki)
    monkeypatch.setattr(person_search, "_searchapi_pages", fake_web)
    person_search.reset_person_store()
    with TestClient(app) as client:
        response = client.post("/api/person/search", headers={"X-Profilage-Session": SESSION},
                               json={"query": "홍길동", "limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["candidate_id"].startswith("cand_")
    assert payload["items"][0]["pages"][1]["domain"] == "linkedin.com"
    assert payload["items"][0]["pages"][1]["open_url"] is None


def test_page_analysis_rejects_social_source(monkeypatch):
    async def fake_owned(candidate_id, source_ref, session_id):
        return {"display_name": "홍길동"}, {
            "url": "https://www.linkedin.com/in/example",
            "analysis_capability": "external_view_only",
        }

    monkeypatch.setattr(person_search, "get_owned_source", fake_owned)
    with TestClient(app) as client:
        response = client.post("/api/person/page-analysis", headers={"X-Profilage-Session": SESSION}, json={
            "candidate_id": "cand_abcdefghijklmnop", "source_ref": "src_abcdefghijklmnop",
        })
    assert response.status_code == 403
    assert "플랫폼 권한" in response.json()["detail"]
