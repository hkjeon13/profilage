# Company Profile Trust Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기업 프로필 화면에 데이터 신뢰도, 주가 상태 피드백, 재무 변화 해석, 공시 탐색성, 관계회사 요약을 단계적으로 추가한다.

**Architecture:** 기존 FastAPI API와 정적 프론트엔드 구조를 유지한다. 백엔드는 기존 aggregate 응답과 SearchAPI/DART 서비스에 최소한의 메타데이터를 추가하고, 프론트는 `profile-page-5.js` 안에서 섹션별 렌더링 함수를 확장한다. 테스트는 현재처럼 `tests/test_company_affiliate_api.py`의 문자열/서비스 회귀 테스트를 중심으로 먼저 실패시키고 구현한다.

**Tech Stack:** FastAPI, httpx, Python dataclass services, Valkey/Postgres-backed data group cache, vanilla JavaScript, CSS, pytest.

---

## 파일 구조와 책임

- `app/services/company_affiliate.py`
  - SearchAPI 주가 응답에 캐시/출처 메타데이터를 붙인다.
  - 기업 통합 응답에 관계회사 요약 계산이 필요할 경우 이 파일의 `CompanyInfoService`에서 만든다.

- `app/services/company_store.py`
  - 이미 존재하는 `DataGroupRecord`의 `fetched_at`, `expires_at`, `source` 정보를 API 응답 `_meta`로 노출할 수 있는 helper를 추가한다.
  - 기간별 주가 TTL 정책은 유지하되 테스트로 고정한다.

- `app/services/company_dart.py`
  - 공시 필터가 필요하면 기존 `DartDisclosureQuery`의 `disclosure_type`, `disclosure_detail_type`, `corporation_class`를 그대로 사용한다.
  - 새 endpoint는 만들지 않고 기존 `/company/get_dart_disclosures` 쿼리를 활용한다.

- `app/static/profile-page-5.js`
  - 주가 탭 loading/error/last updated 표시.
  - 출처/기준일 표시 컴포넌트.
  - 재무 전년 대비 변화 계산 및 렌더링.
  - 공시 필터 UI와 목록 재조회.
  - 관계회사 요약 렌더링.

- `app/static/styles.css`
  - 새 메타 라벨, loading state, delta badge, disclosure filter, relationship summary 스타일.

- `app/static/profile.html`
  - JS/CSS cache busting 버전만 변경한다.

- `tests/test_company_affiliate_api.py`
  - 모든 변경의 회귀 테스트를 추가한다.
  - 서비스 단위 테스트와 정적 자산 문자열 테스트를 섞어 현재 테스트 스타일을 따른다.

---

## 단계별 구현 계획

### Task 1: 주가 기간 탭 상태 피드백과 갱신 시각 표시

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Modify: `app/static/profile.html`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_company_affiliate_api.py`의 주가 차트 테스트 근처에 아래 assertion을 추가한다.

```python
def test_stock_window_tabs_expose_loading_error_and_refresh_metadata():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "is-loading-stock" in script_response.text
    assert "stock-window-status" in script_response.text
    assert "stockUpdatedLabel" in script_response.text
    assert "stock._meta?.fetched_at" in script_response.text
    assert "stock._meta?.expires_at" in script_response.text
    assert "주가 정보를 불러오는 중입니다" in script_response.text
    assert "주가 정보를 불러오지 못했습니다" in script_response.text
    assert ".stock-window-status" in style_response.text
    assert ".company-market-card.is-loading-stock" in style_response.text
    assert "/profile-page-5.js?v=company-profile-19" in client.get("/profile").text
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_stock_window_tabs_expose_loading_error_and_refresh_metadata -q
```

Expected: `stock-window-status` 또는 `stockUpdatedLabel`이 없어서 실패한다.

- [ ] **Step 3: 최소 구현**

`app/static/profile-page-5.js`에 갱신 시각 helper를 추가한다.

```javascript
function formatDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function stockUpdatedLabel(stock) {
  const fetchedAt = formatDateTime(stock?._meta?.fetched_at);
  const expiresAt = formatDateTime(stock?._meta?.expires_at);
  if (fetchedAt && expiresAt) return `갱신 ${fetchedAt} · 캐시 만료 ${expiresAt}`;
  if (fetchedAt) return `갱신 ${fetchedAt}`;
  return "갱신 시각 정보 없음";
}
```

`renderStockChart(stock, activeWindow)` 반환 HTML의 탭 아래에 상태 영역을 넣는다.

```javascript
<p class="stock-window-status" role="status">
  ${escapeHtml(stockUpdatedLabel(stock))}
</p>
```

`setupStockWindowTabs()` 클릭 핸들러에서 loading 문구를 설정한다.

```javascript
const status = card.querySelector(".stock-window-status");
if (status) status.textContent = "주가 정보를 불러오는 중입니다.";
```

실패 catch에서는 기존 에러 문구를 재사용하되 status도 갱신한다.

```javascript
if (status) status.textContent = error.message || "주가 정보를 불러오지 못했습니다.";
```

`app/static/styles.css`에 스타일을 추가한다.

```css
.stock-window-status {
  margin: 8px 0 0;
  color: #667085;
  font-size: 12px;
  line-height: 1.5;
}

.company-market-card.is-loading-stock .stock-chart {
  opacity: 0.55;
}

.stock-chart-error {
  margin: 10px 0 0;
  color: #b42318;
  font-size: 12px;
}
```

`app/static/profile.html`의 script cache busting을 올린다.

```html
<script src="/profile-page-5.js?v=company-profile-19" defer></script>
```

- [ ] **Step 4: 통과 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_stock_window_tabs_expose_loading_error_and_refresh_metadata -q
```

Expected: `1 passed`.

- [ ] **Step 5: 관련 전체 테스트**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected: `45 passed` 이상. 새 테스트 추가 후 개수는 증가한다.

---

### Task 2: API 응답에 출처/캐시 메타데이터 노출

**Files:**
- Modify: `app/services/company_store.py`
- Modify: `app/services/company_affiliate.py`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`FakeDataGroupStore`를 사용하는 주가 서비스 테스트를 추가한다.

```python
@pytest.mark.asyncio
async def test_stock_price_data_group_response_includes_cache_metadata(monkeypatch):
    monkeypatch.setenv("SEARCHAPI_API_KEY", "searchapi-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "search_parameters": {"window": "1D"},
                "summary": {"stock": "005930", "price": 1234.0},
            },
        )

    store = FakeDataGroupStore()
    service = CompanyStockPriceService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=store,
    )

    payload = await service.fetch(
        CompanyStockPriceQuery(
            q=None,
            stock_code="005930",
            exchange="KRX",
            language="ko",
            window="1D",
        )
    )

    assert payload["_meta"]["source"] == "searchapi:google_finance"
    assert payload["_meta"]["cache_group"] == "stock_price"
    assert payload["_meta"]["fetched_at"]
    assert payload["_meta"]["expires_at"]
    assert payload["_meta"]["ttl_seconds"] == 60
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_stock_price_data_group_response_includes_cache_metadata -q
```

Expected: `_meta`가 없어서 실패한다.

- [ ] **Step 3: store helper 구현**

`app/services/company_store.py`에 helper를 추가한다.

```python
def with_group_meta(
    payload: dict[str, Any],
    *,
    source: str,
    group_name: str,
    fetched_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    ttl_seconds = max(int((expires_at - fetched_at).total_seconds()), 0)
    return {
        **payload,
        "_meta": {
            **payload.get("_meta", {}),
            "source": source,
            "cache_group": group_name,
            "fetched_at": fetched_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "ttl_seconds": ttl_seconds,
        },
    }
```

`fetch_with_group_store()`의 fresh/stale/new payload 반환 지점에서 helper를 사용한다.

```python
if fresh is not None:
    return with_group_meta(
        fresh.payload,
        source=fresh.source,
        group_name=group_name,
        fetched_at=fresh.fetched_at,
        expires_at=fresh.expires_at,
    )
```

upsert 이후에는 반환된 record를 사용한다.

```python
record = await store.upsert_record(...)
return with_group_meta(
    payload,
    source=record.source,
    group_name=group_name,
    fetched_at=record.fetched_at,
    expires_at=record.expires_at,
)
```

- [ ] **Step 4: 통과 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_stock_price_data_group_response_includes_cache_metadata -q
```

Expected: `1 passed`.

- [ ] **Step 5: 전체 회귀 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected: 모든 테스트 통과.

---

### Task 3: 섹션별 데이터 출처와 기준일 표시

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_profile_sections_render_source_and_basis_metadata():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderSourceMeta" in script_response.text
    assert "금융위원회 기업기본정보" in script_response.text
    assert "DART" in script_response.text
    assert "SearchAPI Google Finance" in script_response.text
    assert "기준일" in script_response.text
    assert "캐시 만료" in script_response.text
    assert ".source-meta" in style_response.text
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_sections_render_source_and_basis_metadata -q
```

Expected: `renderSourceMeta`가 없어서 실패한다.

- [ ] **Step 3: helper 구현**

`app/static/profile-page-5.js`에 추가한다.

```javascript
function renderSourceMeta(items) {
  const visibleItems = items.filter((item) => item?.value);
  if (!visibleItems.length) return "";
  return `
    <dl class="source-meta">
      ${visibleItems
        .map(
          (item) => `
            <div>
              <dt>${escapeHtml(item.label)}</dt>
              <dd>${escapeHtml(item.value)}</dd>
            </div>
          `,
        )
        .join("")}
    </dl>
  `;
}
```

기업 정보 섹션 아래에 출처를 붙인다.

```javascript
${renderSourceMeta([
  { label: "출처", value: "금융위원회 기업기본정보 · DART" },
  { label: "기준일", value: compactDate(outline.basDt || listed.basDt) },
])}
```

주가 카드에는 SearchAPI 메타를 붙인다.

```javascript
${renderSourceMeta([
  { label: "출처", value: "SearchAPI Google Finance" },
  { label: "캐시 만료", value: formatDateTime(stock?._meta?.expires_at) },
])}
```

- [ ] **Step 4: 스타일 추가**

```css
.source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 14px 0 0;
  color: #667085;
  font-size: 12px;
}

.source-meta div {
  display: inline-flex;
  gap: 4px;
}

.source-meta dt {
  font-weight: 700;
}

.source-meta dd {
  margin: 0;
}
```

- [ ] **Step 5: 테스트 실행**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_sections_render_source_and_basis_metadata -q
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected: 모두 통과.

---

### Task 4: 재무 요약에 전년 대비 변화 배지 추가

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_financial_summary_renders_year_over_year_delta_badges():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "financialDeltaText" in script_response.text
    assert "frmtrm_amount" in script_response.text
    assert "delta-badge" in script_response.text
    assert "is-positive" in script_response.text
    assert "is-negative" in script_response.text
    assert ".delta-badge" in style_response.text
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_financial_summary_renders_year_over_year_delta_badges -q
```

Expected: `financialDeltaText`가 없어서 실패한다.

- [ ] **Step 3: 변화 계산 helper 추가**

```javascript
function financialDelta(item) {
  const current = Number(String(item.thstrm_amount || "").replaceAll(",", ""));
  const previous = Number(String(item.frmtrm_amount || "").replaceAll(",", ""));
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) {
    return null;
  }
  const ratio = ((current - previous) / Math.abs(previous)) * 100;
  return {
    ratio,
    className: ratio >= 0 ? "is-positive" : "is-negative",
  };
}

function financialDeltaText(item) {
  const delta = financialDelta(item);
  if (!delta) return "";
  const sign = delta.ratio > 0 ? "+" : "";
  return `${sign}${delta.ratio.toFixed(1)}% YoY`;
}
```

`renderFinancialSummaryPanel()`의 metric card 안에 배지를 추가한다.

```javascript
${financialDeltaText(item) ? `<span class="delta-badge ${financialDelta(item).className}">${financialDeltaText(item)}</span>` : ""}
```

- [ ] **Step 4: 스타일 추가**

```css
.delta-badge {
  display: inline-flex;
  width: fit-content;
  margin-top: 8px;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 800;
}

.delta-badge.is-positive {
  background: #ecfdf3;
  color: #027a48;
}

.delta-badge.is-negative {
  background: #fef3f2;
  color: #b42318;
}
```

- [ ] **Step 5: 테스트 실행**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_financial_summary_renders_year_over_year_delta_badges -q
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected: 모두 통과.

---

### Task 5: 공시 유형 필터 추가

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_disclosures_page_exposes_disclosure_type_filters():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "DISCLOSURE_FILTERS" in script_response.text
    assert "정기공시" in script_response.text
    assert "주요사항" in script_response.text
    assert "지분공시" in script_response.text
    assert "disclosure_type" in script_response.text
    assert "setupDisclosureFilters" in script_response.text
    assert ".disclosure-filter-tabs" in style_response.text
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosures_page_exposes_disclosure_type_filters -q
```

Expected: `DISCLOSURE_FILTERS`가 없어서 실패한다.

- [ ] **Step 3: 필터 상수와 선택 helper 추가**

```javascript
const DISCLOSURE_FILTERS = [
  ["", "전체"],
  ["A", "정기공시"],
  ["B", "주요사항"],
  ["C", "발행공시"],
  ["D", "지분공시"],
  ["E", "기타공시"],
];

function selectedDisclosureType(searchParams) {
  const requested = searchParams.get("disclosure_type") || "";
  return DISCLOSURE_FILTERS.some(([value]) => value === requested) ? requested : "";
}
```

`renderDisclosuresPage()` 상단에 필터 UI를 추가한다.

```javascript
function renderDisclosureFilters(activeType) {
  return `
    <div class="disclosure-filter-tabs" role="tablist" aria-label="공시 유형">
      ${DISCLOSURE_FILTERS
        .map(
          ([value, label]) => `
            <button type="button" class="${value === activeType ? "is-active" : ""}" data-disclosure-type="${attr(value)}" aria-selected="${value === activeType ? "true" : "false"}">
              ${label}
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}
```

- [ ] **Step 4: 필터 클릭 재조회 구현**

```javascript
function setupDisclosureFilters({ corpCode, crno }) {
  document.querySelectorAll("[data-disclosure-type]").forEach((button) => {
    if (button.dataset.disclosureFilterBound === "true") return;
    button.dataset.disclosureFilterBound = "true";
    button.addEventListener("click", async () => {
      const disclosureType = button.dataset.disclosureType;
      const payload = await fetchJson("/api/company/get_dart_disclosures", {
        corp_code: corpCode,
        disclosure_type: disclosureType,
        page: 1,
        per_page: DISCLOSURE_PAGE_SIZE,
      });
      const nextParams = new URLSearchParams(window.location.search);
      if (disclosureType) nextParams.set("disclosure_type", disclosureType);
      else nextParams.delete("disclosure_type");
      window.history.replaceState({}, "", `${window.location.pathname}?${nextParams.toString()}`);
      renderDisclosuresPage({ disclosures: payload, outline: firstItem({}), crno, activeDisclosureType: disclosureType });
      setupDisclosureViewer();
      setupDisclosureFilters({ corpCode, crno });
    });
  });
}
```

구현 시 `outline`을 잃지 않도록 실제 코드에서는 `renderDisclosuresPage({ disclosures, outline, crno, activeDisclosureType })` 인자를 유지한다.

- [ ] **Step 5: 스타일 추가**

```css
.disclosure-filter-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 14px;
}

.disclosure-filter-tabs button {
  border: 1px solid #e7ebf3;
  border-radius: 999px;
  background: #fff;
  color: #344054;
  cursor: pointer;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 800;
}

.disclosure-filter-tabs button.is-active {
  border-color: #1a73e8;
  background: #eef4ff;
  color: #185abc;
}
```

- [ ] **Step 6: 테스트 실행**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_disclosures_page_exposes_disclosure_type_filters -q
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected: 모두 통과.

---

### Task 6: 관계회사 요약을 작은 카드로 재도입

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_profile_renders_compact_relationship_summary_without_side_panel():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderRelationshipSummary" in script_response.text
    assert "계열회사" in script_response.text
    assert "종속기업" in script_response.text
    assert "상장 관계사" in script_response.text
    assert "company-relationship-summary" in script_response.text
    assert "company-side-panel" not in script_response.text
    assert ".company-relationship-summary" in style_response.text
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_renders_compact_relationship_summary_without_side_panel -q
```

Expected: `renderRelationshipSummary`가 없어서 실패한다.

- [ ] **Step 3: 요약 helper 구현**

```javascript
function countListedRelationships(items) {
  return items.filter((item) => item.lstgYn === "Y" || item.lstgYn === "상장").length;
}

function renderRelationshipSummary(info) {
  const affiliates = normalizeItems(info.affiliate);
  const subsidiaries = normalizeItems(info.cons_subs_comp);
  if (!affiliates.length && !subsidiaries.length) return "";
  const listedCount = countListedRelationships(affiliates);
  return `
    <article class="info-block company-relationship-summary">
      <div class="block-heading">
        <h3>관계회사 요약</h3>
      </div>
      <dl>
        <div><dt>계열회사</dt><dd>${affiliates.length.toLocaleString("ko-KR")}</dd></div>
        <div><dt>종속기업</dt><dd>${subsidiaries.length.toLocaleString("ko-KR")}</dd></div>
        <div><dt>상장 관계사</dt><dd>${listedCount.toLocaleString("ko-KR")}</dd></div>
      </dl>
    </article>
  `;
}
```

`renderCompanyDetail()`에서 주소 카드 위에 배치한다.

```javascript
${renderRelationshipSummary(info)}
```

- [ ] **Step 4: 스타일 추가**

```css
.company-relationship-summary dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.company-relationship-summary div {
  border: 1px solid #eef0f6;
  border-radius: 8px;
  padding: 12px;
}

.company-relationship-summary dt {
  color: #667085;
  font-size: 12px;
  font-weight: 800;
}

.company-relationship-summary dd {
  margin: 6px 0 0;
  color: #101828;
  font-size: 20px;
  font-weight: 850;
}
```

- [ ] **Step 5: 테스트 실행**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_renders_compact_relationship_summary_without_side_panel -q
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected: 모두 통과.

---

### Task 7: 배포 전 검증과 원격 배포

**Files:**
- Modify: `app/static/profile.html`
- Remote deploy target: `/data/psyche/Projects/profilage` on `server-4096`

- [ ] **Step 1: 정적 자산 버전 갱신**

`app/static/profile.html`에서 변경된 JS/CSS 버전을 한 번 더 올린다.

```html
<link rel="stylesheet" href="/styles.css?v=company-profile-20" />
<script src="/profile-page-5.js?v=company-profile-20" defer></script>
```

테스트 기대값도 같은 버전으로 맞춘다.

```python
assert "/styles.css?v=company-profile-20" in response.text
assert "/profile-page-5.js?v=company-profile-20" in response.text
```

- [ ] **Step 2: 전체 테스트 실행**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py -q
python3 -m py_compile app/services/company_affiliate.py app/services/company_store.py app/services/company_dart.py app/api/company.py
```

Expected:

```text
all pytest tests pass
py_compile exits 0
```

- [ ] **Step 3: 원격 백업 생성**

Run:

```bash
ssh server-4096 mkdir -p /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights
ssh server-4096 cp /data/psyche/Projects/profilage/app/static/profile-page-5.js /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights/profile-page-5.js.bak
ssh server-4096 cp /data/psyche/Projects/profilage/app/static/styles.css /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights/styles.css.bak
ssh server-4096 cp /data/psyche/Projects/profilage/app/static/profile.html /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights/profile.html.bak
ssh server-4096 cp /data/psyche/Projects/profilage/app/services/company_affiliate.py /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights/company_affiliate.py.bak
ssh server-4096 cp /data/psyche/Projects/profilage/app/services/company_store.py /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights/company_store.py.bak
ssh server-4096 cp /data/psyche/Projects/profilage/app/services/company_dart.py /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights/company_dart.py.bak
ssh server-4096 cp /data/psyche/Projects/profilage/tests/test_company_affiliate_api.py /data/psyche/Projects/profilage/backups/codex-20260704-trust-insights/test_company_affiliate_api.py.bak
```

Expected: 모든 명령 exit 0.

- [ ] **Step 4: 원격 파일 전송**

Run:

```bash
scp app/static/profile-page-5.js server-4096:/data/psyche/Projects/profilage/app/static/profile-page-5.js
scp app/static/styles.css server-4096:/data/psyche/Projects/profilage/app/static/styles.css
scp app/static/profile.html server-4096:/data/psyche/Projects/profilage/app/static/profile.html
scp app/services/company_affiliate.py server-4096:/data/psyche/Projects/profilage/app/services/company_affiliate.py
scp app/services/company_store.py server-4096:/data/psyche/Projects/profilage/app/services/company_store.py
scp app/services/company_dart.py server-4096:/data/psyche/Projects/profilage/app/services/company_dart.py
scp tests/test_company_affiliate_api.py server-4096:/data/psyche/Projects/profilage/tests/test_company_affiliate_api.py
```

Expected: 모든 전송 exit 0.

- [ ] **Step 5: 원격 문법 확인과 컨테이너 재빌드**

Run:

```bash
ssh server-4096 python3 -m py_compile /data/psyche/Projects/profilage/app/services/company_affiliate.py /data/psyche/Projects/profilage/app/services/company_store.py /data/psyche/Projects/profilage/app/services/company_dart.py /data/psyche/Projects/profilage/app/api/company.py
ssh server-4096 docker compose -f /data/psyche/Projects/profilage/docker-compose.yml --project-directory /data/psyche/Projects/profilage up -d --build api
```

Expected: compile exit 0, `profilage-api` container starts.

- [ ] **Step 6: 라이브 검증**

Run:

```bash
ssh server-4096 "curl -fsS http://127.0.0.1:18000/profile | grep 'profile-page-5.js?v=company-profile-20'"
ssh server-4096 "curl -fsS http://127.0.0.1:18000/profile-page-5.js?v=company-profile-20 | grep 'stock-window-status'"
ssh server-4096 "curl -fsS 'http://127.0.0.1:18000/company/get_stock_price?stock_code=005930&exchange=KRX&language=ko&window=5D' | grep -o '\"window\":\"5D\"' | head -1"
ssh server-4096 docker ps --filter name=profilage-api
```

Expected:

```text
profile-page-5.js?v=company-profile-20
stock-window-status
"window":"5D"
profilage-api Up
```

---

## 구현 순서 추천

1. Task 1과 Task 2를 먼저 구현한다. 사용자 신뢰도와 데이터 메타데이터 기반이 생긴다.
2. Task 3을 구현해 화면에 출처와 기준일을 노출한다.
3. Task 4를 구현해 재무 요약을 숫자 조회에서 변화 해석으로 확장한다.
4. Task 5를 구현해 공시 탐색성을 높인다.
5. Task 6을 구현해 기업 관계 정보를 작은 요약으로 되살린다.
6. Task 7로 검증과 배포를 끝낸다.

## 자체 리뷰

- Spec coverage: 주가 상태 피드백, 출처/기준일, 재무 변화, 공시 필터, 관계회사 요약, 배포 검증을 모두 별도 task로 분리했다.
- Placeholder scan: 미완성 표식이나 막연한 후속 지시를 넣지 않았다.
- Type consistency: `stock_window`, `disclosure_type`, `CompanyStockPriceQuery.window`, `DartDisclosureQuery.disclosure_type` 명칭을 기존 코드와 맞췄다.
- Scope check: 검색 홈, 인증, 데이터베이스 스키마 변경은 포함하지 않았다. 현재 기업 프로필 화면 개선 범위 안에 머문다.
