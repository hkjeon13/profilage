# Company Data Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기업 프로필에 최대주주, 배당, 감사의견, 재무비율을 우선 추가하고, 주식구조/임직원 등 무거운 DART 정보는 lazy detail로 분리해 첫 화면 속도와 데이터 신뢰도를 함께 지킨다.

**Architecture:** DART 원본 응답을 프론트에서 직접 해석하지 않는다. `DartCompanyService`가 원본 조회와 Postgres 캐시를 담당하고, 새 `CompanyInsightNormalizer`가 화면용 `dart_insights` 요약 객체로 정규화한다. `CompanyInfoService`는 첫 화면에 Phase 1 핵심 요약만 붙이고, 상세/무거운 데이터는 별도 endpoint에서 lazy load한다.

**Tech Stack:** FastAPI, httpx, Python dataclass services, Postgres-backed data group cache, Valkey JSON cache for corp code list, vanilla JavaScript, CSS, pytest.

---

## 핵심 보완 원칙

1. **첫 화면 API 호출 제한**
   - 첫 화면에는 최대주주, 배당, 감사의견, 재무비율만 붙인다.
   - 주식구조, 자기주식, 임원, 직원 현황은 별도 lazy endpoint로 분리한다.

2. **백엔드 정규화 우선**
   - DART 필드명은 API마다 다르므로 프론트에서 `raw.some_field`를 직접 해석하지 않는다.
   - 백엔드는 `dart_insights.ownership`, `dart_insights.dividend`, `dart_insights.audit`, `dart_insights.ratios` 형태로 안정적인 필드명을 제공한다.

3. **엔드포인트와 필드 검증을 구현 전 task로 둔다**
   - OpenDART 개발가이드의 항목명과 실제 endpoint slug, 응답 필드명을 구현 전 표로 고정한다.
   - 샘플 응답 fixture를 테스트에 남겨 이후 필드명 변경/오해를 잡는다.

4. **DART 없음/부분 없음을 정상 상태로 처리**
   - DART 매칭 실패, 비상장/보고서 없음, 특정 API no data는 화면 에러가 아니라 “정보 없음”으로 처리한다.
   - 카드 단위로 숨기거나 빈 상태를 표시한다.

5. **캐시 정책**
   - 최근 6개월 이내 보고서 데이터는 `ttl=1 day`.
   - 6개월 이상 지난 보고서 데이터는 `ttl=None`으로 Postgres에 만료 없이 저장한다.
   - 공시 목록처럼 계속 변하는 목록은 기존 짧은 TTL을 유지한다.

---

## 파일 구조와 책임

- `app/services/company_dart.py`
  - DART 정기보고서 주요정보/재무정보 공통 client를 제공한다.
  - 실제 endpoint slug는 `DART_PERIODIC_ENDPOINTS` 상수로 관리한다.
  - 원본 응답 캐시와 `allow_no_data=True` 처리를 담당한다.

- `app/services/company_insights.py`
  - 새 파일.
  - DART 원본 payload를 프론트 안정 필드로 정규화한다.
  - ownership, dividend, audit, ratios, capital, people normalizer를 둔다.

- `app/services/company_affiliate.py`
  - `CompanyInfoService._fetch_dart_profile()`에서 Phase 1 핵심 insight만 호출해 `dart_insights`로 붙인다.
  - lazy detail endpoint가 필요한 데이터는 첫 화면 응답에 붙이지 않는다.

- `app/main.py`
  - lazy detail endpoint를 추가한다.
  - 예: `/company/get_dart_company_insight_detail?corp_code=...&kind=capital|people`

- `app/static/profile-page-5.js`
  - `renderCompanyInsightCards(info.dart_insights)`를 추가한다.
  - Phase 1 카드는 첫 화면에 렌더링한다.
  - capital/people은 “더보기” 클릭 시 lazy endpoint를 호출해 모달에 표시한다.

- `app/static/styles.css`
  - insight card grid, risk badge, source meta, lazy modal/list 스타일을 추가한다.

- `app/static/profile.html`
  - CSS/JS cache busting 버전을 변경한다.

- `tests/test_company_affiliate_api.py`
  - DART endpoint 매핑 테스트, normalizer 테스트, 통합 응답 테스트, lazy endpoint 테스트, 프론트 정적 테스트를 추가한다.

---

## Phase 0: DART 엔드포인트/필드 검증

### Task 0: Endpoint Registry And Fixtures

**Files:**
- Modify: `app/services/company_dart.py`
- Create: `app/services/company_insights.py`
- Modify: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Write the failing test**

`tests/test_company_affiliate_api.py`에 endpoint registry와 normalizer fixture 테스트를 추가한다.

```python
def test_dart_periodic_endpoint_registry_contains_phase_one_sources():
    from app.services.company_dart import DART_PERIODIC_ENDPOINTS

    assert DART_PERIODIC_ENDPOINTS["major_shareholders"]["group_name"] == "dart_major_shareholders"
    assert DART_PERIODIC_ENDPOINTS["dividends"]["group_name"] == "dart_dividends"
    assert DART_PERIODIC_ENDPOINTS["audit_opinion"]["group_name"] == "dart_audit_opinion"
    assert DART_PERIODIC_ENDPOINTS["financial_ratios"]["group_name"] == "dart_financial_ratios"
    assert DART_PERIODIC_ENDPOINTS["major_shareholders"]["endpoint"].endswith(".json") is False
```

```python
def test_company_insight_normalizer_returns_stable_phase_one_shape():
    from app.services.company_insights import normalize_dart_insights

    payload = normalize_dart_insights(
        {
            "major_shareholders": {
                "status": "000",
                "list": [
                    {
                        "nm": "홍길동",
                        "relate": "본인",
                        "stock_knd": "보통주",
                        "bsis_posesn_stock_co": "1,000",
                        "bsis_posesn_stock_qota_rt": "10.0",
                    }
                ],
            },
            "dividends": {
                "status": "000",
                "list": [
                    {
                        "se": "주당 현금배당금(원)",
                        "thstrm": "1,444",
                        "frmtrm": "1,444",
                    }
                ],
            },
            "audit_opinion": {
                "status": "000",
                "list": [
                    {
                        "bsns_year": "2025",
                        "adtor": "삼일회계법인",
                        "adt_opinion": "적정",
                    }
                ],
            },
            "financial_ratios": {
                "status": "000",
                "list": [
                    {"idx_nm": "부채비율", "idx_val": "30.0"},
                    {"idx_nm": "영업이익률", "idx_val": "15.5"},
                ],
            },
        },
        basis={"business_year": "2025", "report_code": "11011", "report_name": "사업보고서"},
    )

    assert payload["basis"]["business_year"] == "2025"
    assert payload["ownership"]["largest_holder_name"] == "홍길동"
    assert payload["ownership"]["largest_holder_ratio"] == "10.0"
    assert payload["dividend"]["dividend_per_share"] == "1,444"
    assert payload["audit"]["auditor"] == "삼일회계법인"
    assert payload["audit"]["opinion"] == "적정"
    assert payload["ratios"]["items"][0] == {"name": "부채비율", "value": "30.0"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_dart_periodic_endpoint_registry_contains_phase_one_sources tests/test_company_affiliate_api.py::test_company_insight_normalizer_returns_stable_phase_one_shape -q
```

Expected: FAIL because `DART_PERIODIC_ENDPOINTS` and `company_insights.py` do not exist.

- [ ] **Step 3: Implement endpoint registry and normalizer skeleton**

Add to `app/services/company_dart.py`:

```python
DART_PERIODIC_ENDPOINTS = {
    "major_shareholders": {
        "endpoint": "hyslrSttus",
        "group_name": "dart_major_shareholders",
    },
    "minor_shareholders": {
        "endpoint": "mrhlSttus",
        "group_name": "dart_minor_shareholders",
    },
    "dividends": {
        "endpoint": "alotMatter",
        "group_name": "dart_dividends",
    },
    "audit_opinion": {
        "endpoint": "accnutAdtorNmNdAdtOpinion",
        "group_name": "dart_audit_opinion",
    },
    "financial_ratios": {
        "endpoint": "fnlttSinglIndx",
        "group_name": "dart_financial_ratios",
    },
    "total_stock": {
        "endpoint": "stockTotqySttus",
        "group_name": "dart_total_stock",
    },
    "treasury_stock": {
        "endpoint": "tesstkAcqsDspsSttus",
        "group_name": "dart_treasury_stock",
    },
    "executives": {
        "endpoint": "exctvSttus",
        "group_name": "dart_executives",
    },
    "employees": {
        "endpoint": "empSttus",
        "group_name": "dart_employees",
    },
}
```

Create `app/services/company_insights.py`:

```python
from typing import Any


def _items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    item = (payload or {}).get("list", [])
    if isinstance(item, list):
        return [row for row in item if isinstance(row, dict)]
    return [item] if isinstance(item, dict) else []


def _first_value(row: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def normalize_ownership(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    if not rows:
        return None
    first = rows[0]
    return {
        "largest_holder_name": _first_value(first, ["nm", "holder_nm", "stockholdr_nm"]),
        "largest_holder_relation": _first_value(first, ["relate", "relate_nm"]),
        "largest_holder_ratio": _first_value(first, ["bsis_posesn_stock_qota_rt", "posesn_stock_qota_rt", "stock_qota_rt"]),
        "rows": rows,
    }


def normalize_dividend(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    if not rows:
        return None
    dividend_per_share = None
    payout_ratio = None
    for row in rows:
        label = str(row.get("se") or row.get("name") or "")
        if "주당" in label and "배당" in label:
            dividend_per_share = _first_value(row, ["thstrm", "thstrm_amount", "value"])
        if "배당성향" in label:
            payout_ratio = _first_value(row, ["thstrm", "thstrm_amount", "value"])
    return {
        "dividend_per_share": dividend_per_share,
        "payout_ratio": payout_ratio,
        "rows": rows,
    }


def normalize_audit(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    if not rows:
        return None
    first = rows[0]
    return {
        "auditor": _first_value(first, ["adtor", "auditor", "auditor_nm", "account_nm"]),
        "opinion": _first_value(first, ["adt_opinion", "audit_opinion", "opinion"]),
        "rows": rows,
    }


def normalize_ratios(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    wanted = ["부채비율", "영업이익률", "ROE", "ROA", "자기자본이익률", "총자산이익률"]
    items = []
    for label in wanted:
        match = next((row for row in rows if label in str(row.get("idx_nm") or row.get("account_nm") or "")), None)
        if match:
            items.append({
                "name": _first_value(match, ["idx_nm", "account_nm"]),
                "value": _first_value(match, ["idx_val", "thstrm_amount", "value"]),
            })
    return {"items": items, "rows": rows} if items or rows else None


def normalize_dart_insights(raw: dict[str, Any], *, basis: dict[str, Any]) -> dict[str, Any]:
    return {
        "basis": basis,
        "ownership": normalize_ownership(raw.get("major_shareholders")),
        "dividend": normalize_dividend(raw.get("dividends")),
        "audit": normalize_audit(raw.get("audit_opinion")),
        "ratios": normalize_ratios(raw.get("financial_ratios")),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_dart_periodic_endpoint_registry_contains_phase_one_sources tests/test_company_affiliate_api.py::test_company_insight_normalizer_returns_stable_phase_one_shape -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/company_dart.py app/services/company_insights.py tests/test_company_affiliate_api.py
git commit -m "feat: define dart insight normalization"
```

---

## Phase 1: First-Screen Core Insight Cards

### Task 1: DART Periodic Report Client With Stable Cache Policy

**Files:**
- Modify: `app/services/company_dart.py`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_dart_periodic_report_info_maps_query_to_dart_api(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url.copy_with(query=None))
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(200, json={"status": "000", "list": [{"corp_code": "00126380"}]})

    service = DartCompanyService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=FakeDataGroupStore(),
    )

    payload = await service.get_periodic_report_info(
        DartPeriodicReportInfoQuery(
            corp_code="00126380",
            business_year="2025",
            report_code="11011",
            kind="major_shareholders",
        )
    )

    assert payload["list"][0]["corp_code"] == "00126380"
    assert captured_request["url"] == "https://opendart.fss.or.kr/api/hyslrSttus.json"
    assert captured_request["params"] == {
        "crtfc_key": "dart-key",
        "corp_code": "00126380",
        "bsns_year": "2025",
        "reprt_code": "11011",
    }
```

```python
def test_dart_periodic_report_ttl_expires_only_recent_periods():
    assert dart_periodic_report_ttl(
        "2025",
        "11011",
        now=datetime(2026, 7, 4, tzinfo=UTC),
    ) is None
    assert dart_periodic_report_ttl(
        "2026",
        "11013",
        now=datetime(2026, 7, 4, tzinfo=UTC),
    ) == timedelta(days=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_dart_periodic_report_info_maps_query_to_dart_api tests/test_company_affiliate_api.py::test_dart_periodic_report_ttl_expires_only_recent_periods -q
```

Expected: FAIL because `DartPeriodicReportInfoQuery`, `get_periodic_report_info`, or `dart_periodic_report_ttl` is missing.

- [ ] **Step 3: Implement minimal client**

Add to `app/services/company_dart.py`:

```python
@dataclass(frozen=True)
class DartPeriodicReportInfoQuery:
    corp_code: str
    business_year: str
    report_code: str
    kind: str
```

```python
def dart_periodic_report_ttl(
    business_year: str,
    report_code: str,
    *,
    now: datetime | None = None,
) -> timedelta | None:
    current = now or datetime.now(UTC)
    month, day = FINANCIAL_REPORT_PERIOD_END.get(report_code, (12, 31))
    period_end = datetime(int(business_year), month, day, tzinfo=UTC)
    if current - period_end >= DART_FINANCIAL_ACCOUNTS_STABLE_AFTER:
        return None
    return timedelta(days=1)
```

Add to `DartCompanyService`:

```python
async def get_periodic_report_info(
    self,
    query: DartPeriodicReportInfoQuery,
) -> dict[str, Any]:
    config = DART_PERIODIC_ENDPOINTS[query.kind]
    params = {
        "corp_code": query.corp_code,
        "bsns_year": query.business_year,
        "reprt_code": query.report_code,
    }
    return await fetch_with_group_store(
        store=self._data_group_store,
        entity_type=COMPANY_ENTITY_TYPE,
        entity_key=_dart_entity_key(query.corp_code),
        group_name=f"{config['group_name']}:{query.business_year}:{query.report_code}",
        source=f"dart:{config['endpoint']}",
        ttl=dart_periodic_report_ttl(query.business_year, query.report_code),
        fetcher=lambda: self._fetch_json(
            url=f"{DART_BASE_URL}/{config['endpoint']}.json",
            params=params,
            allow_no_data=True,
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_dart_periodic_report_info_maps_query_to_dart_api tests/test_company_affiliate_api.py::test_dart_periodic_report_ttl_expires_only_recent_periods -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/company_dart.py tests/test_company_affiliate_api.py
git commit -m "feat: add dart periodic report client"
```

---

### Task 2: Fetch And Normalize Phase 1 Insights In CompanyInfoService

**Files:**
- Modify: `app/services/company_affiliate.py`
- Modify: `app/services/company_dart.py`
- Modify: `app/services/company_insights.py`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Write the failing integration test**

```python
@pytest.mark.asyncio
async def test_company_info_service_attaches_normalized_dart_insights(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")

    crno = "1301110006246"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/getCorpOutline_V2"):
            body = {"items": {"item": {"crno": crno, "corpNm": "삼성전자(주)"}}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": body}})
        if path.endswith("/getItemInfo"):
            body = {"items": {"item": {"srtnCd": "005930", "crno": crno}}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": body}})
        if path.endswith("/getAffiliate_V2") or path.endswith("/getConsSubsComp_V2"):
            body = {"items": {"item": []}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": body}})
        if path.endswith("/company.json"):
            return httpx.Response(200, json={"status": "000", "corp_code": "00126380", "corp_name": "삼성전자"})
        if path.endswith("/list.json"):
            return httpx.Response(200, json={"status": "000", "list": []})
        if path.endswith("/fnlttSinglAcnt.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"account_nm": "자산총계", "thstrm_amount": "100"}]})
        if path.endswith("/hyslrSttus.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"nm": "삼성생명", "bsis_posesn_stock_qota_rt": "8.51"}]})
        if path.endswith("/alotMatter.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"se": "주당 현금배당금(원)", "thstrm": "1,444"}]})
        if path.endswith("/accnutAdtorNmNdAdtOpinion.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"adtor": "삼일회계법인", "adt_opinion": "적정"}]})
        if path.endswith("/fnlttSinglIndx.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"idx_nm": "부채비율", "idx_val": "30.0"}]})
        raise AssertionError(path)

    service = CompanyInfoService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=FakeDataGroupStore(),
    )

    payload = await service.fetch(CompanyInfoQuery(corporate_registration_number=crno, page=1, per_page=10))

    insights = payload["dart_insights"]
    assert insights["ownership"]["largest_holder_name"] == "삼성생명"
    assert insights["ownership"]["largest_holder_ratio"] == "8.51"
    assert insights["dividend"]["dividend_per_share"] == "1,444"
    assert insights["audit"]["opinion"] == "적정"
    assert insights["ratios"]["items"][0]["name"] == "부채비율"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_company_info_service_attaches_normalized_dart_insights -q
```

Expected: FAIL because `dart_insights` is missing.

- [ ] **Step 3: Implement Phase 1 fetch**

In `company_dart.py`, add wrappers:

```python
async def get_phase_one_insight_sources(
    self,
    *,
    corp_code: str,
    business_year: str,
    report_code: str,
) -> dict[str, Any]:
    return {
        "major_shareholders": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="major_shareholders")
        ),
        "dividends": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="dividends")
        ),
        "audit_opinion": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="audit_opinion")
        ),
        "financial_ratios": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="financial_ratios")
        ),
    }
```

In `CompanyInfoService._fetch_dart_profile()`, after annual financial report selection:

```python
from app.services.company_insights import normalize_dart_insights
```

```python
annual_selected = dart_latest_annual_financial_accounts.get("selected") or {}
dart_insights = None
if annual_selected.get("business_year") and annual_selected.get("report_code"):
    raw_insight_sources = await dart_service.get_phase_one_insight_sources(
        corp_code=corp_code,
        business_year=annual_selected["business_year"],
        report_code=annual_selected["report_code"],
    )
    dart_insights = normalize_dart_insights(
        raw_insight_sources,
        basis={
            "business_year": annual_selected["business_year"],
            "report_code": annual_selected["report_code"],
            "report_name": annual_selected.get("report_name"),
        },
    )
```

Add `"dart_insights": dart_insights` to the return dict.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_company_info_service_attaches_normalized_dart_insights -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/company_affiliate.py app/services/company_dart.py app/services/company_insights.py tests/test_company_affiliate_api.py
git commit -m "feat: attach normalized dart insights"
```

---

### Task 3: Render Phase 1 Insight Cards

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Modify: `app/static/profile.html`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Write the failing frontend test**

```python
def test_profile_frontend_renders_normalized_dart_insight_cards():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")
        profile_response = client.get("/profile")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert profile_response.status_code == 200
    assert "renderCompanyInsightCards" in script_response.text
    assert "insights.ownership" in script_response.text
    assert "insights.dividend" in script_response.text
    assert "insights.audit" in script_response.text
    assert "insights.ratios" in script_response.text
    assert "최대주주" in script_response.text
    assert "주당배당금" in script_response.text
    assert "감사의견" in script_response.text
    assert "재무비율" in script_response.text
    assert ".company-insight-cards" in style_response.text
    assert "/profile-page-5.js?v=company-profile-27" in profile_response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_frontend_renders_normalized_dart_insight_cards -q
```

Expected: FAIL because `renderCompanyInsightCards` is missing.

- [ ] **Step 3: Implement renderer**

Add to `app/static/profile-page-5.js`:

```javascript
function renderInsightMetric(label, value) {
  if (!value) return "";
  return `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function renderCompanyInsightCards(insights) {
  if (!insights) return "";
  const ratioItems = insights.ratios?.items || [];
  const cards = [
    insights.ownership
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>최대주주</h3></div>
          <dl class="compact-metric-grid">
            ${renderInsightMetric("이름", insights.ownership.largest_holder_name)}
            ${renderInsightMetric("지분율", insights.ownership.largest_holder_ratio)}
          </dl>
        </article>
      `
      : "",
    insights.dividend
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>배당</h3></div>
          <dl class="compact-metric-grid">
            ${renderInsightMetric("주당배당금", insights.dividend.dividend_per_share)}
            ${renderInsightMetric("배당성향", insights.dividend.payout_ratio)}
          </dl>
        </article>
      `
      : "",
    insights.audit
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>감사의견</h3></div>
          <dl class="compact-metric-grid">
            ${renderInsightMetric("의견", insights.audit.opinion)}
            ${renderInsightMetric("회계감사인", insights.audit.auditor)}
          </dl>
        </article>
      `
      : "",
    ratioItems.length
      ? `
        <article class="info-block company-insight-card">
          <div class="block-heading"><h3>재무비율</h3></div>
          <dl class="compact-metric-grid">
            ${ratioItems.map((item) => renderInsightMetric(item.name, item.value)).join("")}
          </dl>
        </article>
      `
      : "",
  ].filter(Boolean);
  if (!cards.length) return "";
  return `<section class="company-insight-cards" aria-label="기업 심화 정보">${cards.join("")}</section>`;
}
```

In `renderCompanyDetail()`, place it after `renderCompanyInsightRow(info)`:

```javascript
${renderCompanyInsightCards(info.dart_insights)}
```

- [ ] **Step 4: Add styles**

Add to `app/static/styles.css`:

```css
.company-insight-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.company-insight-card {
  min-width: 0;
}

.compact-metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.compact-metric-grid > div {
  border: 1px solid #eef0f6;
  border-radius: 8px;
  padding: 12px;
}

.compact-metric-grid dt {
  color: #667085;
  font-size: 12px;
  font-weight: 800;
}

.compact-metric-grid dd {
  margin: 6px 0 0;
  color: #101828;
  font-size: 18px;
  font-weight: 850;
}

@media (max-width: 820px) {
  .company-insight-cards,
  .compact-metric-grid {
    grid-template-columns: 1fr;
  }
}
```

Update `app/static/profile.html` cache keys:

```html
<link rel="stylesheet" href="/styles.css?v=company-profile-25" />
<script src="/profile-page-5.js?v=company-profile-27" defer></script>
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
node --check app/static/profile-page-5.js
uv run pytest tests/test_company_affiliate_api.py::test_profile_frontend_renders_normalized_dart_insight_cards -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/static/profile-page-5.js app/static/styles.css app/static/profile.html tests/test_company_affiliate_api.py
git commit -m "feat: render dart insight cards"
```

---

## Phase 2: Lazy Details For Heavy Data

### Task 4: Add Lazy DART Insight Detail Endpoint

**Files:**
- Modify: `app/main.py`
- Modify: `app/services/company_dart.py`
- Modify: `app/services/company_insights.py`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Write the failing endpoint test**

```python
def test_dart_company_insight_detail_endpoint_is_registered():
    with TestClient(app) as client:
        response = client.get(
            "/company/get_dart_company_insight_detail",
            params={"corp_code": "00126380", "business_year": "2025", "report_code": "11011", "kind": "capital"},
        )

    assert response.status_code in (200, 502)
```

```python
@pytest.mark.asyncio
async def test_dart_detail_rejects_unknown_kind(monkeypatch):
    with TestClient(app) as client:
        response = client.get(
            "/company/get_dart_company_insight_detail",
            params={"corp_code": "00126380", "business_year": "2025", "report_code": "11011", "kind": "unknown"},
        )

    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_dart_company_insight_detail_endpoint_is_registered tests/test_company_affiliate_api.py::test_dart_detail_rejects_unknown_kind -q
```

Expected: FAIL because endpoint is missing.

- [ ] **Step 3: Implement endpoint**

Add to `app/main.py`:

```python
@app.get("/company/get_dart_company_insight_detail")
async def get_dart_company_insight_detail(
    corp_code: str,
    business_year: str,
    report_code: str,
    kind: Literal["capital", "people"],
) -> dict[str, Any]:
    service = DartCompanyService()
    if kind == "capital":
        raw = await service.get_company_capital_sources(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
        )
        return normalize_capital_detail(raw)
    raw = await service.get_company_people_sources(
        corp_code=corp_code,
        business_year=business_year,
        report_code=report_code,
    )
    return normalize_people_detail(raw)
```

Add imports:

```python
from typing import Any, Literal
from app.services.company_dart import DartCompanyService
from app.services.company_insights import normalize_capital_detail, normalize_people_detail
```

- [ ] **Step 4: Implement source methods**

Add to `DartCompanyService`:

```python
async def get_company_capital_sources(self, *, corp_code: str, business_year: str, report_code: str) -> dict[str, Any]:
    return {
        "total_stock": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="total_stock")
        ),
        "treasury_stock": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="treasury_stock")
        ),
    }


async def get_company_people_sources(self, *, corp_code: str, business_year: str, report_code: str) -> dict[str, Any]:
    return {
        "executives": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="executives")
        ),
        "employees": await self.get_periodic_report_info(
            DartPeriodicReportInfoQuery(corp_code=corp_code, business_year=business_year, report_code=report_code, kind="employees")
        ),
    }
```

Add to `company_insights.py`:

```python
def normalize_capital_detail(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "capital",
        "total_stock": _items(raw.get("total_stock")),
        "treasury_stock": _items(raw.get("treasury_stock")),
    }


def normalize_people_detail(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "people",
        "executives": _items(raw.get("executives")),
        "employees": _items(raw.get("employees")),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_dart_company_insight_detail_endpoint_is_registered tests/test_company_affiliate_api.py::test_dart_detail_rejects_unknown_kind -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/services/company_dart.py app/services/company_insights.py tests/test_company_affiliate_api.py
git commit -m "feat: add dart insight detail endpoint"
```

---

### Task 5: Add Lazy Detail Buttons And Modal

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Modify: `app/static/profile.html`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Write the failing frontend test**

```python
def test_profile_frontend_exposes_lazy_dart_detail_modal():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert "ensureDartInsightDetailModal" in script_response.text
    assert "openDartInsightDetailModal" in script_response.text
    assert "/api/company/get_dart_company_insight_detail" in script_response.text
    assert "data-dart-insight-detail-kind" in script_response.text
    assert "주식구조 더보기" in script_response.text
    assert "임직원 더보기" in script_response.text
    assert ".dart-insight-detail-modal" in style_response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_frontend_exposes_lazy_dart_detail_modal -q
```

Expected: FAIL because lazy modal code is missing.

- [ ] **Step 3: Add buttons to `renderCompanyInsightCards`**

Use `insights.basis` and `profileDetail.dataset.dartCorpCode` for request params.

```javascript
function renderDartInsightDetailButtons(insights) {
  if (!insights?.basis?.business_year || !insights?.basis?.report_code) return "";
  return `
    <div class="dart-insight-detail-actions">
      <button type="button" data-dart-insight-detail-kind="capital">주식구조 더보기</button>
      <button type="button" data-dart-insight-detail-kind="people">임직원 더보기</button>
    </div>
  `;
}
```

Append `${renderDartInsightDetailButtons(insights)}` inside `renderCompanyInsightCards`.

- [ ] **Step 4: Add lazy modal logic**

```javascript
function ensureDartInsightDetailModal() {
  const existing = document.querySelector(".dart-insight-detail-modal");
  if (existing) return existing;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = `
    <div class="dart-insight-detail-modal" hidden>
      <button type="button" class="dart-insight-detail-backdrop" data-dart-insight-detail-close aria-label="닫기"></button>
      <section class="dart-insight-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="dart-insight-detail-title">
        <div class="dart-insight-detail-header">
          <h3 id="dart-insight-detail-title">상세 정보</h3>
          <button type="button" data-dart-insight-detail-close aria-label="닫기">×</button>
        </div>
        <div class="dart-insight-detail-body" data-dart-insight-detail-body></div>
      </section>
    </div>
  `;
  const modal = wrapper.firstElementChild;
  document.body.appendChild(modal);
  modal.querySelectorAll("[data-dart-insight-detail-close]").forEach((button) => {
    button.addEventListener("click", () => {
      modal.hidden = true;
    });
  });
  return modal;
}

async function openDartInsightDetailModal(button) {
  const kind = button.dataset.dartInsightDetailKind;
  const insights = JSON.parse(button.closest("[data-dart-insight-basis]")?.dataset.dartInsightBasis || "{}");
  const corpCode = profileDetail.dataset.dartCorpCode;
  const modal = ensureDartInsightDetailModal();
  modal.hidden = false;
  modal.querySelector("[data-dart-insight-detail-body]").innerHTML = `<p class="empty-copy">불러오는 중입니다.</p>`;
  const payload = await fetchJson("/api/company/get_dart_company_insight_detail", {
    corp_code: corpCode,
    business_year: insights.business_year,
    report_code: insights.report_code,
    kind,
  });
  modal.querySelector("#dart-insight-detail-title").textContent = kind === "capital" ? "주식 구조" : "임직원";
  modal.querySelector("[data-dart-insight-detail-body]").innerHTML = `<pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
}

function setupDartInsightDetailButtons() {
  document.querySelectorAll("[data-dart-insight-detail-kind]").forEach((button) => {
    if (button.dataset.dartInsightDetailBound === "true") return;
    button.dataset.dartInsightDetailBound = "true";
    button.addEventListener("click", () => {
      openDartInsightDetailModal(button).catch((error) => {
        const modal = ensureDartInsightDetailModal();
        modal.querySelector("[data-dart-insight-detail-body]").innerHTML = `<p class="empty-copy">${escapeHtml(error.message || "상세 정보를 불러오지 못했습니다.")}</p>`;
      });
    });
  });
}
```

Call `setupDartInsightDetailButtons()` after rendering company detail.

- [ ] **Step 5: Add styles and cache bump**

Add modal styles modelled after existing relationship modal, scoped as `.dart-insight-detail-modal`.

Update cache keys:

```html
<link rel="stylesheet" href="/styles.css?v=company-profile-26" />
<script src="/profile-page-5.js?v=company-profile-28" defer></script>
```

- [ ] **Step 6: Verify and commit**

Run:

```bash
node --check app/static/profile-page-5.js
uv run pytest tests/test_company_affiliate_api.py::test_profile_frontend_exposes_lazy_dart_detail_modal -q
```

Commit:

```bash
git add app/static/profile-page-5.js app/static/styles.css app/static/profile.html tests/test_company_affiliate_api.py
git commit -m "feat: add lazy dart insight details"
```

---

## Phase 3: UX, Empty States, Verification, Deployment

### Task 6: Empty States, Source Metadata, And Mobile Density

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Write the failing frontend test**

```python
def test_dart_insight_cards_include_source_and_empty_state_copy():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert "DART 정기보고서" in script_response.text
    assert "정정 공시가 있으면 수치가 바뀔 수 있습니다" in script_response.text
    assert "표시할 심화 정보가 없습니다" in script_response.text
    assert ".company-insight-source" in style_response.text
    assert "@media (max-width: 820px)" in style_response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_dart_insight_cards_include_source_and_empty_state_copy -q
```

Expected: FAIL because metadata copy is missing.

- [ ] **Step 3: Add source metadata**

In `renderCompanyInsightCards`, add:

```javascript
const sourceMeta = insights.basis
  ? `<p class="company-insight-source">출처 DART 정기보고서 · ${escapeHtml(insights.basis.business_year || "")} ${escapeHtml(insights.basis.report_name || "")} · 정정 공시가 있으면 수치가 바뀔 수 있습니다.</p>`
  : `<p class="company-insight-source">출처 DART 정기보고서 · 정정 공시가 있으면 수치가 바뀔 수 있습니다.</p>`;
```

If no cards:

```javascript
return `<article class="info-block company-insight-empty"><p class="empty-copy">표시할 심화 정보가 없습니다.</p></article>`;
```

- [ ] **Step 4: Add styles**

```css
.company-insight-source {
  grid-column: 1 / -1;
  margin: -2px 0 0;
  color: #667085;
  font-size: 12px;
  line-height: 1.5;
}

.company-insight-empty {
  padding: 18px;
}
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
node --check app/static/profile-page-5.js
uv run pytest tests/test_company_affiliate_api.py -q
```

Commit:

```bash
git add app/static/profile-page-5.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "feat: polish dart insight states"
```

---

### Task 7: Final Verification And Deployment

**Files:**
- Modify: `app/static/profile.html`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: Run full local verification**

Run:

```bash
node --check app/static/profile-page-5.js
uv run pytest tests/test_company_affiliate_api.py -q
python3 -m py_compile app/services/company_dart.py app/services/company_affiliate.py app/services/company_insights.py
```

Expected:
- JS syntax check exits 0.
- pytest passes.
- Python compile exits 0.

- [ ] **Step 2: Commit any final cache key or polish change**

```bash
git status --short
git add app/static/profile.html tests/test_company_affiliate_api.py
git commit -m "chore: prepare dart insight release"
```

If no files changed, skip this commit.

- [ ] **Step 3: Push and deploy**

```bash
git push origin main
ssh server-4096 git -C /data/psyche/Projects/profilage fetch origin
ssh server-4096 git -C /data/psyche/Projects/profilage pull --ff-only origin main
ssh server-4096 docker compose -f /data/psyche/Projects/profilage/docker-compose.yml up -d --build api
ssh server-4096 docker compose -f /data/psyche/Projects/profilage/docker-compose.yml ps api
ssh server-4096 curl -fsS http://127.0.0.1:18000/profile
```

Expected:
- Pull is fast-forward.
- `profilage-api` is `Up`.
- `/profile` HTML contains the latest CSS/JS cache keys.

---

## Updated Implementation Priority

1. **Phase 0: Endpoint/field verification and normalizer**
   - Prevents wrong DART field assumptions from leaking into the UI.

2. **Phase 1: First-screen core cards**
   - Maximum shareholder, dividend, audit opinion, financial ratios.
   - These are high-value and compact enough for the profile page.

3. **Phase 2: Lazy detail data**
   - Capital structure, treasury stock, executives, employees.
   - These are useful but too heavy/noisy for first paint.

4. **Phase 3: UX and deployment**
   - Source/basis copy, no-data states, mobile density, release verification.

---

## Self-Review

- Spec coverage: The plan covers the requested useful company information: ownership, dividend, audit, ratios, capital structure, treasury stock, executives, and employees.
- Review feedback applied: The plan no longer attaches all DART APIs to first load, no longer asks the frontend to interpret raw DART field names, and adds an endpoint/field verification phase before feature work.
- Placeholder scan: No `TODO`, `TBD`, or intentionally vague implementation step remains.
- Type consistency: `DartPeriodicReportInfoQuery.kind`, `DART_PERIODIC_ENDPOINTS`, `normalize_dart_insights`, `dart_insights`, and lazy detail kinds `capital|people` are used consistently.
- Scope check: This remains a single feature area because all tasks share the same DART insight pipeline; heavy details are isolated behind lazy endpoints.
