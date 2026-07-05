# DART Disclosure LLM Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DART 공시 원문을 추출하고 OpenAI LLM으로 요약해, 프로필/공시 화면에서 사용자가 공시 핵심 내용을 빠르게 확인할 수 있게 만든다.

**Architecture:** 새 기능은 `app/services/company_disclosure_summary.py`에 원문 추출, 텍스트 정리, OpenAI 요약 호출, 캐시 키 생성을 모은다. API는 `app/api/company.py`에 `GET /api/company/get_dart_disclosure_summary`를 추가하고, 저장은 기존 `company_data_groups` 기반 `fetch_with_group_store` 패턴을 재사용한다. 프론트는 `app/static/profile-page-5.js`와 `app/static/styles.css`에 요약 버튼/모달을 추가하되, 기존 DART viewer 모달과 독립적으로 동작하게 한다.

**Tech Stack:** FastAPI, httpx, Postgres-backed `DataGroupStore`, vanilla JavaScript, CSS, DART viewer HTML, OpenAI Responses API-compatible HTTP call.

---

## PR 분리 전략

이 기능은 한 PR에 모두 넣으면 리뷰 범위가 커진다. 아래처럼 4개 PR로 나누면 각 PR이 독립적으로 테스트 가능하다.

1. **PR 1: 설정/원문 추출 기반**
2. **PR 2: OpenAI 요약 서비스와 캐시**
3. **PR 3: API 엔드포인트**
4. **PR 4: 프론트 요약 UI**

선행 PR이 배포되지 않아도 다음 PR의 테스트는 mock으로 검증한다. 실제 OpenAI 호출 smoke test는 PR 3 이후 원격 서버에서 수행한다.

---

## 사전 결정

### 환경변수

원격 서버에는 `/data/psyche/Projects/profilage/.env`에 `OPENAI_API_KEY`가 있다. 앱 코드는 키 값을 읽거나 출력하지 않고, `os.environ`에 올라온 값만 사용한다.

추가 환경변수:

- `OPENAI_API_KEY`: 필수. 요약 요청 시에만 필요하다.
- `OPENAI_MODEL`: 선택. 기본값은 `gpt-4.1-mini`.
- `OPENAI_SUMMARY_MAX_CHARS`: 선택. 기본값은 `18000`.

### 캐시 정책

기존 `company_data_groups`를 재사용한다.

엔티티:

- `entity_type`: `company`
- `entity_key`: `receipt_no`
- `group_name`: `dart_disclosure_text` 또는 `dart_disclosure_summary:<model>:<prompt_version>`
- `ttl`: `None`

이유:

- DART 접수번호 기준 공시 원문은 거의 변하지 않는다.
- 프롬프트나 모델이 바뀌면 같은 원문이라도 요약 결과가 달라질 수 있으므로 `group_name`에 모델과 프롬프트 버전을 포함한다.

### LLM 안전 원칙

프롬프트는 다음 원칙을 강제한다.

- 원문에 없는 내용을 추측하지 않는다.
- 투자 판단을 단정하지 않는다.
- 불확실한 내용은 `원문에서 확인되지 않음`으로 표시한다.
- 요약은 한국어로 작성한다.
- 응답은 JSON 형태로만 받는다.

---

## PR 1: 설정/원문 추출 기반

**목표:** OpenAI 설정 함수와 DART viewer HTML 텍스트 추출기를 추가한다. 이 PR은 OpenAI API를 호출하지 않는다.

**Files:**

- Modify: `app/core/config.py`
- Create: `app/services/company_disclosure_summary.py`
- Test: `tests/test_company_affiliate_api.py`

### Task 1.1: OpenAI 설정 함수 추가

- [ ] **Step 1: 설정 테스트를 추가한다.**

`tests/test_company_affiliate_api.py`에 추가:

```python
def test_openai_settings_are_optional_until_summary_request(monkeypatch):
    from app.core.config import get_openai_settings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    settings = get_openai_settings(required=False)

    assert settings.api_key is None
    assert settings.model == "gpt-4.1-mini"
    assert settings.max_chars == 18000
```

- [ ] **Step 2: 실패 확인 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_openai_settings_are_optional_until_summary_request -q
```

Expected:

```text
FAILED ... ImportError 또는 AttributeError
```

- [ ] **Step 3: `app/core/config.py`에 설정을 추가한다.**

추가할 코드:

```python
@dataclass(frozen=True)
class OpenAiSettings:
    api_key: str | None
    model: str
    max_chars: int


def get_openai_settings(*, required: bool = True) -> OpenAiSettings:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if required and not api_key:
        raise RuntimeError("OPENAI_API_KEY must be configured")

    return OpenAiSettings(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        max_chars=int(os.getenv("OPENAI_SUMMARY_MAX_CHARS", "18000")),
    )
```

- [ ] **Step 4: 테스트를 다시 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_openai_settings_are_optional_until_summary_request -q
```

Expected:

```text
1 passed
```

### Task 1.2: DART viewer URL 검증과 텍스트 추출기 추가

- [ ] **Step 1: URL/HTML 정리 테스트를 추가한다.**

`tests/test_company_affiliate_api.py`에 추가:

```python
def test_disclosure_text_extractor_accepts_only_dart_viewer_urls():
    from app.services.company_disclosure_summary import disclosure_text_entity_key, validate_dart_viewer_url

    assert validate_dart_viewer_url("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000")
    assert disclosure_text_entity_key("20260701000000") == "20260701000000"
    assert not validate_dart_viewer_url("https://example.com/dsaf001/main.do?rcpNo=20260701000000")


def test_disclosure_html_to_text_removes_scripts_and_compacts_text():
    from app.services.company_disclosure_summary import extract_disclosure_text

    html = """
    <html>
      <head><script>alert('x')</script><style>body { color:red }</style></head>
      <body>
        <h1>분기보고서</h1>
        <p>매출액은 증가했습니다.</p>
        <p>영업이익은 감소했습니다.</p>
      </body>
    </html>
    """

    text = extract_disclosure_text(html)

    assert "alert" not in text
    assert "color:red" not in text
    assert "분기보고서" in text
    assert "매출액은 증가했습니다." in text
    assert "영업이익은 감소했습니다." in text
```

- [ ] **Step 2: 실패 확인 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosure_text_extractor_accepts_only_dart_viewer_urls tests/test_company_affiliate_api.py::test_disclosure_html_to_text_removes_scripts_and_compacts_text -q
```

Expected:

```text
FAILED ... ModuleNotFoundError
```

- [ ] **Step 3: `app/services/company_disclosure_summary.py`를 생성한다.**

구현:

```python
import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

DART_DISCLOSURE_TEXT_GROUP = "dart_disclosure_text"
DART_DISCLOSURE_SUMMARY_PROMPT_VERSION = "v1"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


@dataclass(frozen=True)
class DisclosureSummaryQuery:
    receipt_no: str
    viewer_url: str
    title: str | None


def validate_dart_viewer_url(viewer_url: str) -> bool:
    parsed = urlparse(viewer_url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.endswith("dart.fss.or.kr")


def disclosure_text_entity_key(receipt_no: str) -> str:
    return receipt_no.strip()


def disclosure_summary_group_name(model: str) -> str:
    safe_model = model.replace(":", "_").replace("/", "_")
    return f"dart_disclosure_summary:{safe_model}:{DART_DISCLOSURE_SUMMARY_PROMPT_VERSION}"


def extract_disclosure_text(html_text: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html_text)
    cleaned = re.sub(r"(?is)<br\\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?is)</(p|div|h[1-6]|tr|li|table)>", "\n", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \\t\\r\\f\\v]+", " ", cleaned)
    cleaned = re.sub(r"\\n\\s*\\n+", "\n", cleaned)
    return cleaned.strip()
```

- [ ] **Step 4: 테스트를 다시 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosure_text_extractor_accepts_only_dart_viewer_urls tests/test_company_affiliate_api.py::test_disclosure_html_to_text_removes_scripts_and_compacts_text -q
```

Expected:

```text
2 passed
```

### Task 1.3: PR 1 검증과 커밋

- [ ] **Step 1: 문법과 테스트를 실행한다.**

Run:

```bash
python3 -m py_compile app/core/config.py app/services/company_disclosure_summary.py
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected:

```text
전체 테스트 통과
```

- [ ] **Step 2: 커밋한다.**

```bash
git add app/core/config.py app/services/company_disclosure_summary.py tests/test_company_affiliate_api.py
git commit -m "feat: add dart disclosure text extraction foundation"
```

---

## PR 2: OpenAI 요약 서비스와 캐시

**목표:** DART viewer HTML을 가져와 텍스트를 캐시하고, OpenAI로 JSON 요약을 생성해 캐시한다. API 엔드포인트는 아직 추가하지 않는다.

**Files:**

- Modify: `app/services/company_disclosure_summary.py`
- Modify: `app/services/company_store.py`
- Test: `tests/test_company_affiliate_api.py`

### Task 2.1: 요약 프롬프트와 JSON 정규화 추가

- [ ] **Step 1: JSON 정규화 테스트를 추가한다.**

```python
def test_disclosure_summary_normalizer_returns_stable_shape():
    from app.services.company_disclosure_summary import normalize_summary_payload

    payload = normalize_summary_payload(
        {
            "bullets": ["핵심 1", "핵심 2"],
            "risks": ["리스크 1"],
            "changes": ["변동 1"],
        }
    )

    assert payload == {
        "bullets": ["핵심 1", "핵심 2"],
        "risks": ["리스크 1"],
        "changes": ["변동 1"],
        "limitations": [],
    }
```

- [ ] **Step 2: 실패 확인 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosure_summary_normalizer_returns_stable_shape -q
```

Expected:

```text
FAILED ... ImportError 또는 AttributeError
```

- [ ] **Step 3: 정규화 함수를 구현한다.**

`company_disclosure_summary.py`에 추가:

```python
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


def build_disclosure_summary_prompt(*, title: str | None, text: str, max_chars: int) -> str:
    clipped = text[:max_chars]
    return (
        "다음 DART 공시 원문을 한국어로 요약하세요. "
        "원문에 없는 내용을 추측하지 말고, 투자 판단을 단정하지 마세요. "
        "JSON만 반환하세요. JSON schema는 "
        '{"bullets":["핵심 요약"],"risks":["리스크/확인사항"],"changes":["변동사항"],"limitations":["한계"]} 입니다.\\n\\n'
        f"공시 제목: {title or '제목 정보 없음'}\\n"
        f"원문:\\n{clipped}"
    )
```

- [ ] **Step 4: 테스트를 다시 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosure_summary_normalizer_returns_stable_shape -q
```

Expected:

```text
1 passed
```

### Task 2.2: OpenAI 호출 함수 추가

- [ ] **Step 1: OpenAI mock 호출 테스트를 추가한다.**

```python
@pytest.mark.asyncio
async def test_openai_summary_client_parses_response_json(monkeypatch):
    from app.services.company_disclosure_summary import summarize_with_openai

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openai.com"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"bullets":["요약"],"risks":["위험"],"changes":["변동"],"limitations":[]}',
                            }
                        ]
                    }
                ]
            },
        )

    payload = await summarize_with_openai(
        title="분기보고서",
        text="매출액은 증가했습니다.",
        transport=httpx.MockTransport(handler),
    )

    assert payload["summary"]["bullets"] == ["요약"]
    assert payload["summary"]["risks"] == ["위험"]
    assert payload["model"] == "gpt-test"
```

- [ ] **Step 2: 실패 확인 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_openai_summary_client_parses_response_json -q
```

Expected:

```text
FAILED ... ImportError 또는 AttributeError
```

- [ ] **Step 3: OpenAI 호출 함수를 구현한다.**

`company_disclosure_summary.py`에 추가:

```python
import json
from app.core.config import get_openai_settings


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
        raise HTTPException(status_code=502, detail="OpenAI returned invalid summary JSON") from exc

    return {
        "summary": normalize_summary_payload(summary_json),
        "model": settings.model,
        "prompt_version": DART_DISCLOSURE_SUMMARY_PROMPT_VERSION,
    }
```

- [ ] **Step 4: 테스트를 다시 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_openai_summary_client_parses_response_json -q
```

Expected:

```text
1 passed
```

### Task 2.3: 원문/요약 캐시 오케스트레이션 추가

- [ ] **Step 1: 캐시 hit 테스트를 추가한다.**

```python
@pytest.mark.asyncio
async def test_disclosure_summary_service_reuses_cached_summary(monkeypatch):
    from app.services.company_disclosure_summary import DisclosureSummaryQuery, DisclosureSummaryService

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    store = FakeDataGroupStore()
    service = DisclosureSummaryService(
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        data_group_store=store,
    )
    store.records[
        ("company", "20260701000000", "dart_disclosure_summary:gpt-4.1-mini:v1")
    ] = fresh_record(
        {
            "receipt_no": "20260701000000",
            "title": "분기보고서",
            "summary": {"bullets": ["cached"], "risks": [], "changes": [], "limitations": []},
            "model": "gpt-4.1-mini",
            "prompt_version": "v1",
        }
    )

    payload = await service.fetch(
        DisclosureSummaryQuery(
            receipt_no="20260701000000",
            viewer_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000",
            title="분기보고서",
        )
    )

    assert payload["summary"]["bullets"] == ["cached"]
```

- [ ] **Step 2: 실패 확인 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosure_summary_service_reuses_cached_summary -q
```

Expected:

```text
FAILED ... ImportError 또는 AttributeError
```

- [ ] **Step 3: `DisclosureSummaryService`를 구현한다.**

구현 요점:

- `viewer_url`이 DART 도메인이 아니면 400
- `data_group_store`가 있으면 summary 캐시를 먼저 확인
- summary 캐시 miss면 text 캐시 확인
- text 캐시 miss면 DART viewer HTML fetch 후 텍스트 추출
- summary 생성 후 summary 캐시에 저장

핵심 코드 형태:

```python
from app.services.company_store import COMPANY_ENTITY_TYPE, DataGroupStore, fetch_with_group_store


class DisclosureSummaryService:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        data_group_store: DataGroupStore | None = None,
    ) -> None:
        self._transport = transport
        self._data_group_store = data_group_store

    async def _fetch_disclosure_text(self, query: DisclosureSummaryQuery) -> dict[str, Any]:
        if not validate_dart_viewer_url(query.viewer_url):
            raise HTTPException(status_code=400, detail="DART viewer_url is required")
        async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
            response = await client.get(query.viewer_url)
            response.raise_for_status()
        text = extract_disclosure_text(response.text)
        if not text:
            raise HTTPException(status_code=502, detail="DART disclosure text was empty")
        return {"receipt_no": query.receipt_no, "title": query.title, "text": text}

    async def fetch(self, query: DisclosureSummaryQuery) -> dict[str, Any]:
        from app.core.config import get_openai_settings

        settings = get_openai_settings(required=True)
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
```

- [ ] **Step 4: 테스트를 다시 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosure_summary_service_reuses_cached_summary -q
```

Expected:

```text
1 passed
```

### Task 2.4: PR 2 검증과 커밋

- [ ] **Step 1: 전체 테스트를 실행한다.**

Run:

```bash
python3 -m py_compile app/services/company_disclosure_summary.py
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected:

```text
전체 테스트 통과
```

- [ ] **Step 2: 커밋한다.**

```bash
git add app/services/company_disclosure_summary.py tests/test_company_affiliate_api.py
git commit -m "feat: summarize dart disclosures with openai"
```

---

## PR 3: 요약 API 엔드포인트

**목표:** 프론트가 호출할 수 있는 `GET /api/company/get_dart_disclosure_summary`를 추가한다.

**Files:**

- Modify: `app/api/company.py`
- Test: `tests/test_company_affiliate_api.py`

### Task 3.1: API 엔드포인트 추가

- [ ] **Step 1: API 테스트를 추가한다.**

```python
def test_get_dart_disclosure_summary_endpoint_uses_service_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with TestClient(app) as client:
        response = client.get(
            "/company/get_dart_disclosure_summary",
            params={
                "receipt_no": "20260701000000",
                "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000",
                "title": "분기보고서",
            },
        )

    assert response.status_code in {200, 502}
```

이 테스트는 첫 작성 직후 실제 외부 호출을 막기 위해 Step 3에서 mock transport 방식으로 고친다.

- [ ] **Step 2: 실패 확인 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_get_dart_disclosure_summary_endpoint_uses_service_cache -q
```

Expected:

```text
FAILED ... 404 Not Found
```

- [ ] **Step 3: API 테스트를 mock transport 기반으로 완성한다.**

최종 테스트:

```python
def test_get_dart_disclosure_summary_endpoint_uses_service_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dart.fss.or.kr":
            return httpx.Response(200, text="<html><body><p>매출액은 증가했습니다.</p></body></html>")
        if request.url.host == "api.openai.com":
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": '{"bullets":["매출 증가"],"risks":[],"changes":[],"limitations":[]}',
                                }
                            ]
                        }
                    ]
                },
            )
        raise AssertionError(str(request.url))

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_disclosure_summary",
            params={
                "receipt_no": "20260701000000",
                "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000",
                "title": "분기보고서",
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    payload = response.json()
    assert payload["receipt_no"] == "20260701000000"
    assert payload["summary"]["bullets"] == ["매출 증가"]
```

- [ ] **Step 4: 엔드포인트를 구현한다.**

`app/api/company.py`에 import:

```python
from app.services.company_disclosure_summary import (
    DisclosureSummaryQuery,
    DisclosureSummaryService,
)
from app.services.company_store import get_default_data_group_store
```

라우트 추가:

```python
@router.get("/get_dart_disclosure_summary")
async def get_dart_disclosure_summary(
    request: Request,
    receipt_no: Annotated[str, Query(description="DART 접수번호")],
    viewer_url: Annotated[str, Query(description="DART viewer URL")],
    title: Annotated[str | None, Query(description="공시 제목")] = None,
):
    service = DisclosureSummaryService(
        transport=getattr(request.app.state, "http_transport", None),
        data_group_store=get_default_data_group_store(),
    )
    return await service.fetch(
        DisclosureSummaryQuery(
            receipt_no=receipt_no,
            viewer_url=viewer_url,
            title=title,
        )
    )
```

- [ ] **Step 5: 테스트를 다시 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_get_dart_disclosure_summary_endpoint_uses_service_cache -q
```

Expected:

```text
1 passed
```

### Task 3.2: 설정 없음 에러 테스트 추가

- [ ] **Step 1: 키가 없을 때 500이 아닌 명확한 오류를 반환하도록 테스트한다.**

```python
def test_get_dart_disclosure_summary_requires_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with TestClient(app) as client:
        response = client.get(
            "/company/get_dart_disclosure_summary",
            params={
                "receipt_no": "20260701000000",
                "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000",
                "title": "분기보고서",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured"
```

- [ ] **Step 2: 서비스 또는 API에서 RuntimeError를 HTTPException으로 변환한다.**

`DisclosureSummaryService.fetch()`에서 설정 로드 부분을 다음처럼 감싼다.

```python
try:
    settings = get_openai_settings(required=True)
except RuntimeError as exc:
    raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured") from exc
```

- [ ] **Step 3: 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_get_dart_disclosure_summary_requires_openai_key -q
```

Expected:

```text
1 passed
```

### Task 3.3: PR 3 검증과 커밋

- [ ] **Step 1: 전체 테스트를 실행한다.**

Run:

```bash
python3 -m py_compile app/api/company.py app/services/company_disclosure_summary.py
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected:

```text
전체 테스트 통과
```

- [ ] **Step 2: 커밋한다.**

```bash
git add app/api/company.py app/services/company_disclosure_summary.py tests/test_company_affiliate_api.py
git commit -m "feat: expose dart disclosure summary api"
```

---

## PR 4: 프론트 요약 UI

**목표:** 최근 공시, 공시 이벤트 타임라인, 공시 더보기 화면에서 요약 버튼을 제공하고, 요약 모달에서 LLM 결과를 보여준다.

**Files:**

- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

### Task 4.1: 정적 UI 계약 테스트 추가

- [ ] **Step 1: 프론트 정적 테스트를 추가한다.**

```python
def test_profile_frontend_exposes_disclosure_summary_modal():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "summaryUrl" in script_response.text
    assert "data-disclosure-summary" in script_response.text
    assert "ensureDisclosureSummaryModal" in script_response.text
    assert "공시 요약" in script_response.text
    assert ".disclosure-summary-modal" in style_response.text
    assert ".disclosure-summary-button" in style_response.text
```

- [ ] **Step 2: 실패 확인 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_frontend_exposes_disclosure_summary_modal -q
```

Expected:

```text
FAILED
```

### Task 4.2: 요약 버튼 렌더링 추가

- [ ] **Step 1: `profile-page-5.js` 상단에 API URL을 추가한다.**

```javascript
const summaryUrl = "/api/company/get_dart_disclosure_summary";
```

- [ ] **Step 2: 공시 요약 버튼 렌더링 함수를 추가한다.**

```javascript
function renderDisclosureSummaryButton(item) {
  const viewerUrl = text(item.viewer_url, "");
  const receiptNo = text(item.rcept_no || item.receipt_no, "");
  const title = text(item.report_nm || item.title, "");
  if (!viewerUrl || viewerUrl === "#" || !receiptNo) return "";
  return `
    <button
      type="button"
      class="disclosure-summary-button"
      data-disclosure-summary
      data-disclosure-receipt-no="${attr(receiptNo)}"
      data-disclosure-viewer-url="${attr(viewerUrl)}"
      data-disclosure-title="${attr(title)}"
    >요약</button>
  `;
}
```

- [ ] **Step 3: 기존 공시 리스트 렌더링에 버튼을 붙인다.**

대상 함수:

- `disclosureListItemsHtml`
- `renderDartDisclosures`
- `renderDisclosureEventTimeline`

각 공시 제목 영역 근처에 `${renderDisclosureSummaryButton(item)}`를 추가한다.

### Task 4.3: 요약 모달과 API 호출 추가

- [ ] **Step 1: 모달 생성 함수를 추가한다.**

```javascript
function ensureDisclosureSummaryModal() {
  const existing = document.querySelector(".disclosure-summary-modal");
  if (existing) return existing;
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div class="disclosure-summary-modal" hidden>
        <button type="button" class="disclosure-summary-backdrop" data-disclosure-summary-close aria-label="닫기"></button>
        <section class="disclosure-summary-dialog" role="dialog" aria-modal="true" aria-labelledby="disclosure-summary-title">
          <header class="disclosure-summary-header">
            <div>
              <p id="disclosure-summary-meta">DART 공시</p>
              <h2 id="disclosure-summary-title">공시 요약</h2>
            </div>
            <button type="button" class="disclosure-summary-close" data-disclosure-summary-close>닫기</button>
          </header>
          <div class="disclosure-summary-body" data-disclosure-summary-body></div>
        </section>
      </div>
    `,
  );
  const modal = document.querySelector(".disclosure-summary-modal");
  modal.querySelectorAll("[data-disclosure-summary-close]").forEach((button) => {
    button.addEventListener("click", closeDisclosureSummaryModal);
  });
  return modal;
}
```

- [ ] **Step 2: 요약 응답 렌더링 함수를 추가한다.**

```javascript
function renderDisclosureSummaryPayload(payload) {
  const summary = payload?.summary || {};
  const section = (title, items) => `
    <section>
      <h3>${escapeHtml(title)}</h3>
      ${
        items?.length
          ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
          : `<p class="empty-copy">표시할 내용이 없습니다.</p>`
      }
    </section>
  `;
  return `
    ${section("핵심 요약", summary.bullets || [])}
    ${section("리스크/확인사항", summary.risks || [])}
    ${section("변동사항", summary.changes || [])}
    ${section("한계", summary.limitations || [])}
    <p class="disclosure-summary-source">OpenAI 요약 · 원문에 없는 내용은 포함하지 않도록 생성됩니다.</p>
  `;
}
```

- [ ] **Step 3: 버튼 이벤트를 추가한다.**

```javascript
async function openDisclosureSummary(button) {
  const modal = ensureDisclosureSummaryModal();
  modal.hidden = false;
  document.body.classList.add("has-disclosure-summary-open");
  modal.querySelector("#disclosure-summary-title").textContent = button.dataset.disclosureTitle || "공시 요약";
  modal.querySelector("[data-disclosure-summary-body]").innerHTML = `<p class="empty-copy">요약을 생성하는 중입니다.</p>`;
  try {
    const payload = await fetchJson(summaryUrl, {
      receipt_no: button.dataset.disclosureReceiptNo,
      viewer_url: button.dataset.disclosureViewerUrl,
      title: button.dataset.disclosureTitle,
    });
    modal.querySelector("[data-disclosure-summary-body]").innerHTML = renderDisclosureSummaryPayload(payload);
  } catch (error) {
    modal.querySelector("[data-disclosure-summary-body]").innerHTML = `<p class="empty-copy">${escapeHtml(error.message || "요약을 생성하지 못했습니다.")}</p>`;
  }
}

function closeDisclosureSummaryModal() {
  const modal = document.querySelector(".disclosure-summary-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("has-disclosure-summary-open");
}

function setupDisclosureSummaryButtons() {
  ensureDisclosureSummaryModal();
  document.querySelectorAll("[data-disclosure-summary]").forEach((button) => {
    if (button.dataset.disclosureSummaryBound === "true") return;
    button.dataset.disclosureSummaryBound = "true";
    button.addEventListener("click", () => openDisclosureSummary(button));
  });
}
```

- [ ] **Step 4: 기존 setup 흐름에 `setupDisclosureSummaryButtons()`를 추가한다.**

추가 위치:

- `renderCompanyDetail()` 마지막 setup 블록
- `appendDisclosureItems()`
- `renderDisclosuresPage()` 이후 setup 흐름
- `setupDisclosureFilters()`로 리스트를 다시 그린 직후

### Task 4.4: 요약 모달 CSS 추가

- [ ] **Step 1: `styles.css`에 모달과 버튼 스타일을 추가한다.**

```css
.disclosure-summary-button {
  border: 0;
  background: transparent;
  color: #1a73e8;
  cursor: pointer;
  padding: 0;
  font: inherit;
  font-size: 12px;
  font-weight: 850;
}

.disclosure-summary-modal[hidden] {
  display: none;
}

.disclosure-summary-modal {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  padding: 20px;
}

.disclosure-summary-backdrop {
  position: absolute;
  inset: 0;
  border: 0;
  background: rgb(15 23 42 / 42%);
}

.disclosure-summary-dialog {
  position: relative;
  width: min(720px, 100%);
  max-height: min(760px, calc(100vh - 40px));
  overflow: auto;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 24px 80px rgb(15 23 42 / 22%);
}

.disclosure-summary-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid #eef0f6;
  padding: 18px 20px;
}

.disclosure-summary-body {
  display: grid;
  gap: 16px;
  padding: 18px 20px 22px;
}

.disclosure-summary-body h3 {
  margin: 0 0 8px;
  color: #101828;
  font-size: 15px;
}

.disclosure-summary-body ul {
  margin: 0;
  padding-left: 18px;
  color: #344054;
  line-height: 1.55;
}

.disclosure-summary-source {
  margin: 0;
  color: #667085;
  font-size: 12px;
}
```

- [ ] **Step 2: 모바일 스타일을 추가한다.**

```css
@media (max-width: 820px) {
  .disclosure-summary-modal {
    align-items: end;
    padding: 14px;
  }

  .disclosure-summary-dialog {
    max-height: calc(100vh - 28px);
    border-radius: 10px;
  }
}
```

### Task 4.5: PR 4 검증과 커밋

- [ ] **Step 1: 문법과 테스트를 실행한다.**

Run:

```bash
node --check app/static/profile-page-5.js
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected:

```text
전체 테스트 통과
```

- [ ] **Step 2: 커밋한다.**

```bash
git add app/static/profile-page-5.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "feat: add dart disclosure summary ui"
```

---

## 배포 후 Smoke Test

원격 서버에는 `/data/psyche/Projects/profilage/.env`에 `OPENAI_API_KEY`가 있다고 했으므로, 배포 후 아래를 확인한다.

- [ ] 원격 서버에서 최신 코드 pull
- [ ] 서비스 재시작
- [ ] `OPENAI_API_KEY`가 로그에 출력되지 않는지 확인
- [ ] 실제 공시 하나에서 요약 버튼 클릭
- [ ] 첫 요청은 생성 시간이 걸리고, 두 번째 요청은 캐시로 빠르게 반환되는지 확인
- [ ] OpenAI 장애 또는 키 누락 시 UI에 실패 문구가 표시되는지 확인

원격 smoke test 예:

```bash
curl -G "https://profile.fin-ally.net/api/company/get_dart_disclosure_summary" \
  --data-urlencode "receipt_no=20260701000000" \
  --data-urlencode "viewer_url=https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000" \
  --data-urlencode "title=분기보고서"
```

응답 확인:

```json
{
  "receipt_no": "20260701000000",
  "summary": {
    "bullets": ["..."],
    "risks": ["..."],
    "changes": ["..."],
    "limitations": ["..."]
  },
  "model": "gpt-4.1-mini",
  "prompt_version": "v1"
}
```

---

## 리스크와 보완책

- DART viewer HTML 구조가 바뀌면 텍스트 추출 품질이 낮아질 수 있다. 보완책은 추출 실패 시 원문 링크를 안내하고, 추출 텍스트 길이를 테스트 fixture로 계속 보강하는 것이다.
- LLM 응답이 JSON이 아닐 수 있다. 보완책은 JSON parse 실패 시 502를 반환하고 UI에서 실패 문구를 보여주는 것이다.
- 요약 비용이 늘어날 수 있다. 보완책은 `receipt_no + model + prompt_version` 캐시를 강제하고 같은 공시를 재요약하지 않는 것이다.
- 원격 서버의 `.env`에 키가 있어도 서비스 프로세스가 `.env`를 로드하지 못하면 요약이 실패한다. 보완책은 `get_openai_settings(required=False)`로 설정 상태를 확인하는 헬스 체크성 테스트를 추가하는 것이다.

---

## 전체 완료 기준

- [ ] 공시 요약 API가 mock OpenAI 응답으로 테스트 통과
- [ ] DART viewer URL 도메인 검증으로 외부 임의 URL fetch 방지
- [ ] 요약 결과가 기존 `company_data_groups`에 캐시됨
- [ ] 프로필 최근 공시, 공시 이벤트, 공시 더보기에서 요약 버튼이 보임
- [ ] 요약 모달이 모바일에서 잘리지 않음
- [ ] OpenAI 키가 없으면 명확한 실패 문구를 표시
- [ ] 원격 서버에서 실제 OpenAI 키로 smoke test 성공
