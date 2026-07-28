from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.services import person_search
from app.services import person_page_analysis, person_profile


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


def test_wikipedia_candidates_keep_only_wikidata_humans():
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload

    class Client:
        async def get(self, url, params):
            if url == person_search.WIKIPEDIA_API:
                return Response({"query": {"pages": {
                    "1": {"index": 1, "title": "사람", "extract": "사람 설명", "fullurl": "https://ko.wikipedia.org/wiki/person", "pageprops": {"wikibase_item": "Q1"}},
                    "2": {"index": 2, "title": "기업", "extract": "기업 설명", "fullurl": "https://ko.wikipedia.org/wiki/company", "pageprops": {"wikibase_item": "Q2"}},
                }}})
            return Response({"entities": {
                "Q1": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}},
                "Q2": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q4830453"}}}}]}},
            }})

    import asyncio
    items = asyncio.run(person_search._wikipedia_candidates("검색", 5, Client()))
    assert [item["display_name"] for item in items] == ["사람"]


def test_resolve_materializes_public_profile(monkeypatch):
    monkeypatch.setattr(person_profile, "get_default_data_group_store", lambda: None)
    monkeypatch.setattr(person_profile, "get_openai_settings", lambda required=False: SimpleNamespace(api_key=None, model="test"))
    person_search.reset_person_store()

    async def seed():
        await person_search.get_person_store().set("candidate:cand_abcdefghijklmnop", {
            "candidate_id": "cand_abcdefghijklmnop", "session_id": SESSION,
            "display_name": "홍길동", "subtitle": "공개 인물", "roles": [],
            "last_verified_at": "2026-07-11", "pages": {"src_abcdefghijklmnop": {
                "url": "https://ko.wikipedia.org/wiki/test", "domain": "ko.wikipedia.org",
                "title": "홍길동", "page_type": "encyclopedia", "wikidata_id": "Q123",
                "extract": "홍길동에 대한 공개 설명입니다. " * 10,
                "display_capability": "direct_link_allowed", "analysis_capability": "server_public",
            }},
        }, 1800)

    import asyncio
    asyncio.run(seed())
    with TestClient(app) as client:
        resolved = client.post("/api/person/resolve", headers={"X-Profilage-Session": SESSION}, json={
            "candidate_id": "cand_abcdefghijklmnop", "idempotency_key": "abcdefgh",
        })
        assert resolved.status_code == 200
        person_id = resolved.json()["person_id"]
        profile = client.get(f"/api/person/{person_id}")
        summary = client.get(f"/api/person/{person_id}/summary")
    assert profile.status_code == 200
    assert profile.json()["identifiers"][0]["display_value"] == "Q123"
    assert summary.status_code == 200
    assert summary.json()["summary"]["overview"]


def test_page_intent_job_result_and_delete(monkeypatch):
    person_search.reset_person_store()

    async def seed():
        await person_search.get_person_store().set("candidate:cand_abcdefghijklmnop", {
            "candidate_id": "cand_abcdefghijklmnop", "session_id": SESSION, "display_name": "홍길동",
            "pages": {"src_abcdefghijklmnop": {"url": "https://ko.wikipedia.org/wiki/test",
                "domain": "ko.wikipedia.org", "title": "홍길동", "page_type": "encyclopedia",
                "wikidata_id": "Q123", "extract": "공개 페이지 설명 " * 20,
                "display_capability": "direct_link_allowed", "analysis_capability": "server_public"}},
        }, 1800)

    async def fake_analyze(candidate_id, source_ref, session_id):
        return {"result_id": "par_abcdefghijklmnop", "candidate_id": candidate_id,
                "analysis": {"summary": "요약"}, "evidence": [], "expires_in_seconds": 3600,
                "subject_identity": "Q123", "domain": "ko.wikipedia.org"}

    import asyncio
    asyncio.run(seed())
    monkeypatch.setattr(person_page_analysis, "analyze_page", fake_analyze)
    with TestClient(app) as client:
        intent_response = client.post("/api/person/page-analysis/intents", headers={"X-Profilage-Session": SESSION}, json={
            "subject_ref": {"candidate_id": "cand_abcdefghijklmnop"},
            "source_ref": "src_abcdefghijklmnop", "requested_mode": "server_public",
        })
        assert intent_response.status_code == 200
        intent_id = intent_response.json()["intent_id"]
        job_response = client.post(f"/api/person/page-analysis/intents/{intent_id}/analyze",
                                   headers={"X-Profilage-Session": SESSION})
        assert job_response.status_code == 202
        result_id = job_response.json()["result_id"]
        result_response = client.get(f"/api/person/page-analysis/results/{result_id}",
                                     headers={"X-Profilage-Session": SESSION})
        assert result_response.status_code == 200
        deleted = client.delete(f"/api/person/page-analysis/results/{result_id}",
                                headers={"X-Profilage-Session": SESSION})
        missing = client.get(f"/api/person/page-analysis/results/{result_id}",
                             headers={"X-Profilage-Session": SESSION})
    assert deleted.status_code == 204
    assert missing.status_code == 404


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


def test_page_analysis_uses_trusted_wikimedia_extract(monkeypatch):
    async def fake_owned(candidate_id, source_ref, session_id):
        return {"display_name": "홍길동"}, {
            "url": "https://ko.wikipedia.org/wiki/test", "title": "홍길동",
            "extract": "홍길동은 고전 소설에 등장하는 인물이다. " * 20,
            "analysis_capability": "server_public",
        }

    async def should_not_fetch(url):
        raise AssertionError("Wikimedia extract should be reused")

    monkeypatch.setattr(person_search, "get_owned_source", fake_owned)
    monkeypatch.setattr(person_search, "_fetch_public_page", should_not_fetch)
    monkeypatch.setattr(person_search, "get_openai_settings", lambda required=False: SimpleNamespace(api_key=None))
    person_search.reset_person_store()
    with TestClient(app) as client:
        response = client.post("/api/person/page-analysis", headers={"X-Profilage-Session": SESSION}, json={
            "candidate_id": "cand_abcdefghijklmnop", "source_ref": "src_abcdefghijklmnop",
        })
    assert response.status_code == 200
    assert response.json()["result_id"].startswith("par_")
    assert response.json()["analysis"]["summary"]
