# B2B Data Platform UX Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Profilage를 "기업 검색 사이트"에서 "전문적이고 신뢰감 있는 B2B 기업 데이터 플랫폼"으로 보이게 만들고, 사용자가 기업을 빠르게 찾고 업무에 바로 활용할 수 있게 한다.

**Architecture:** 현재 프론트엔드는 `app/static/index.html`, `app/static/app.js`, `app/static/profile-page-5.js`, `app/static/compare-page.js`, `app/static/styles.css` 중심의 vanilla JavaScript/CSS 구조다. 서버 API는 이미 금융위원회, DART, SearchAPI, OpenAI 요약을 제공하므로, 이번 계획은 우선 정보 구조, 검색 결과 표현, 상세 페이지 요약 레이어, 데이터 신뢰 표시, 모바일 탐색을 프론트 중심으로 개선한다.

**Tech Stack:** FastAPI static serving, vanilla JavaScript, CSS, existing company APIs, `tests/test_company_affiliate_api.py`, optional in-app browser visual QA.

---

## 1. 감사 요약

### 감사 범위

- 첫 화면: `https://profile.fin-ally.net/`
- 검색 결과: `https://profile.fin-ally.net/?q=롯데`
- 상세 프로필: `/profile?crno=1101113326588&return_q=롯데&stock_window=5D`
- 모바일 상세 프로필
- 비교 화면은 직접적인 주요 범위는 아니지만 CTA와 검색 결과 비교 진입에서는 함께 고려한다.

### 확인된 구조

현재 첫 화면은 Google-like 검색 경험이다.

- 큰 `Profilage` wordmark
- 단일 검색창
- `Profilage 검색`, `대표 기업 보기`
- 검색 후 결과 리스트

현재 상세 페이지는 다음 순서로 렌더링된다.

1. 기업 개요
2. AI 기업 요약
3. 상장 및 주가
4. 재무 요약/최근 공시 row
5. 공시 이벤트 타임라인
6. DART 인사이트 카드
7. 리스크 신호
8. 관계회사 요약
9. 주소

### 핵심 문제

- 첫 화면에서 "기업 검색/조회 사이트"라는 목적이 충분히 선명하지 않다.
- 검색 결과가 업무용 비교 리스트라기보다 일반 링크 리스트에 가깝다.
- 상세 페이지는 데이터가 많아졌지만 정보 위계가 약하다.
- 신뢰 정보를 보여주는 패턴은 있으나 카드마다 표현 밀도와 위치가 완전히 통일되지는 않았다.
- 모바일에서는 카드가 길게 이어져 "요약 → 탐색 → 상세 확인" 흐름이 약하다.

---

## 2. 제품 원칙

### 핵심 사용자

- 비즈니스 종사자
- 영업 담당자
- 투자 담당자
- 마케팅 담당자
- 리서처
- 기업 분석 담당자

### 핵심 사용 시나리오

1. 기업명을 검색한다.
2. 검색 결과에서 원하는 법인을 빠르게 구분한다.
3. 해당 기업의 규모, 업종, 상장 여부, 최근 이슈를 10초 안에 파악한다.
4. 필요하면 재무, 공시, 주주, 관계회사 정보를 더 깊게 확인한다.
5. 두 개 이상의 기업을 비교하거나 공유한다.

### 디자인 방향

- 전문적인
- 신뢰감 있는
- 깔끔한
- 데이터 중심
- 비즈니스 친화적
- 과하게 화려하지 않은
- 빠르게 정보를 찾을 수 있는

### UI 원칙

- 첫 화면은 "검색"보다 "기업 데이터 조회" 목적을 먼저 말한다.
- 상세 페이지 상단 1뷰포트는 executive summary로 쓴다.
- 원천 데이터 단위보다 업무 판단 순서대로 정보를 배치한다.
- 주요 숫자는 카드로, 보조 설명은 작은 metadata로 분리한다.
- 모든 데이터 카드에는 출처와 기준일을 일관되게 둔다.
- 모바일은 전체 정보를 그대로 나열하지 않고 섹션 이동과 접힘을 제공한다.

---

## 3. 목표 정보 구조

### 첫 화면

권장 구조:

1. 헤더
   - 좌측: Profilage
   - 우측: `문서`, `API`, `데이터 문의`
2. 메인 히어로
   - 제목: `기업 정보를 빠르게 찾고 비교하세요`
   - 설명: `금융위원회, DART, 주가 데이터를 기반으로 기업 개요·재무·공시·관계회사를 한 화면에서 확인합니다.`
   - 검색창: `기업명, 종목코드, 법인등록번호로 검색`
3. 예시 검색 칩
   - `삼성전자`
   - `LG전자`
   - `롯데이노베이트`
   - `카카오`
   - `현대자동차`
4. 신뢰 레일
   - `금융위원회 기업기본정보`
   - `DART 공시/재무`
   - `SearchAPI Google Finance`
   - `OpenAI 요약`

### 검색 결과

권장 row 필드:

- 회사명
- 영문명 또는 종목명
- 시장/상장 배지
- 업종
- 지역
- 대표자
- 직원 수
- 설립일
- 데이터 상태 배지: `DART`, `재무`, `주가`
- CTA: `프로필 보기`, `비교 추가`

### 상세 프로필

권장 구조:

1. Hero
   - 회사명, 영문명
   - 시장, 종목코드, 업종, 법인등록번호
   - `비교에 추가`, `공유`, `데이터 문의`
2. Executive Summary
   - AI 기업 요약
   - Key Metrics
   - 최근 이벤트 요약
3. Detail Navigation
   - `요약`, `재무`, `공시`, `주주`, `관계회사`, `기업정보`
4. Detail Cards
   - 상장 및 주가
   - 재무 요약
   - 최근 공시
   - 주주/배당/감사의견
   - 관계회사 요약
   - 주소/기본 정보

---

## 4. 파일 구조와 책임

### 수정 대상

- `app/static/index.html`
  - 첫 화면 문구, CTA, 예시 검색 칩, 신뢰 레일 markup

- `app/static/app.js`
  - 예시 검색 칩 동작
  - 검색 결과 row 렌더링
  - 검색 결과 비교 추가 동작
  - 필터 UI 상태 관리

- `app/static/profile-page-5.js`
  - 상세 페이지 상단 executive summary 구조
  - key metrics 렌더링
  - 데이터 신뢰 metadata 렌더링 정리
  - 모바일 섹션 내비게이션
  - AI 요약 접힘/펼침

- `app/static/compare-page.js`
  - 검색 결과에서 비교 추가한 기업과 기존 비교 페이지 진입 흐름 호환 확인

- `app/static/styles.css`
  - B2B 색상/타입/카드/버튼 스타일
  - 검색 결과 dense row
  - 필터 바
  - 신뢰 배지
  - 상세 페이지 요약 레이어
  - 모바일 sticky section tabs

- `tests/test_company_affiliate_api.py`
  - 정적 HTML/JS/CSS 문자열 테스트
  - 주요 UI contract 확인

### 새 파일 후보

현재는 새 JS/CSS 파일을 만들지 않는다.

이유:

- 기존 앱은 static 파일 수가 적고, 테스트도 기존 파일 기준으로 작성되어 있다.
- 우선 정보 구조 개선이 목적이므로 파일 분리보다 기존 렌더링 흐름 안에서 안정적으로 바꾸는 것이 빠르다.
- 이후 `profile-page-5.js`가 더 커지면 `company-profile-summary.js`, `company-search-results.js`로 분리하는 별도 리팩터링 계획을 세운다.

---

## 5. PR 분리 전략

한 번에 모두 바꾸면 디자인 회귀를 잡기 어렵다. 아래 5개 PR로 나누는 것을 권장한다.

1. **PR 1: 첫 화면 포지셔닝과 신뢰 레일**
2. **PR 2: 검색 결과 dense row와 비교 진입**
3. **PR 3: 상세 페이지 executive summary 재구성**
4. **PR 4: 데이터 신뢰 표시 체계 통일**
5. **PR 5: 모바일 섹션 내비게이션과 CTA 정리**

각 PR은 독립적으로 테스트 가능해야 한다.

---

## 6. PR 1: 첫 화면 포지셔닝과 신뢰 레일

**목표:** 첫 화면에서 "기업 검색/조회 사이트"라는 목적이 즉시 이해되게 한다.

**Files:**

- Modify: `app/static/index.html`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

### Task 1.1: 첫 화면 문구 contract 테스트 추가

- [ ] **Step 1: 실패 테스트를 작성한다.**

`tests/test_company_affiliate_api.py`에 추가:

```python
def test_homepage_positions_as_b2b_company_data_platform():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "기업 정보를 빠르게 찾고 비교하세요" in response.text
    assert "금융위원회, DART, 주가 데이터를 기반" in response.text
    assert "기업명, 종목코드, 법인등록번호로 검색" in response.text
    assert "data-example-query" in response.text
    assert "data-source-rail" in response.text
```

- [ ] **Step 2: 테스트 실패를 확인한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_homepage_positions_as_b2b_company_data_platform -q
```

Expected:

```text
FAILED ... AssertionError
```

### Task 1.2: 첫 화면 markup 교체

- [ ] **Step 1: `app/static/index.html`의 `search-panel` 내부를 아래 구조로 바꾼다.**

```html
<div class="home-kicker">B2B 기업 데이터 플랫폼</div>
<h1 id="page-title" class="home-title">기업 정보를 빠르게 찾고 비교하세요</h1>
<p class="home-subtitle">
  금융위원회, DART, 주가 데이터를 기반으로 기업 개요·재무·공시·관계회사를 한 화면에서 확인합니다.
</p>
<form class="search-form" id="search-form">
  <label class="visually-hidden" for="company-query">기업명, 종목코드, 법인등록번호</label>
  <input
    id="company-query"
    name="company-query"
    type="search"
    autocomplete="off"
    placeholder="기업명, 종목코드, 법인등록번호로 검색"
    minlength="1"
  />
  <button class="search-submit" type="submit">검색</button>
</form>
<div class="example-query-list" aria-label="예시 기업">
  <button type="button" data-example-query="삼성전자">삼성전자</button>
  <button type="button" data-example-query="LG전자">LG전자</button>
  <button type="button" data-example-query="롯데이노베이트">롯데이노베이트</button>
  <button type="button" data-example-query="카카오">카카오</button>
  <button type="button" data-example-query="현대자동차">현대자동차</button>
</div>
<div class="source-rail" data-source-rail aria-label="데이터 출처">
  <span>금융위원회 기업기본정보</span>
  <span>DART 공시/재무</span>
  <span>SearchAPI Google Finance</span>
  <span>OpenAI 요약</span>
</div>
<p class="status" id="search-status" role="status"></p>
```

- [ ] **Step 2: 기존 `.wordmark`, `.search-actions` 의존 CSS를 유지하되 새 클래스 스타일을 추가한다.**

`app/static/styles.css`에 추가:

```css
.home-kicker {
  margin-bottom: 12px;
  color: #175cd3;
  font-size: 13px;
  font-weight: 850;
}

.home-title {
  max-width: 760px;
  margin: 0;
  color: #101828;
  font-size: clamp(34px, 5vw, 58px);
  font-weight: 850;
  line-height: 1.12;
  letter-spacing: 0;
  text-align: center;
}

.home-subtitle {
  max-width: 680px;
  margin: 18px 0 28px;
  color: #667085;
  font-size: 17px;
  line-height: 1.65;
  text-align: center;
}

.example-query-list,
.source-rail {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.example-query-list {
  margin-top: 16px;
}

.example-query-list button {
  min-height: 32px;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  background: #ffffff;
  color: #344054;
  padding: 0 12px;
  font-size: 13px;
  font-weight: 750;
  cursor: pointer;
}

.source-rail {
  margin-top: 20px;
  color: #667085;
  font-size: 12px;
  font-weight: 750;
}

.source-rail span {
  border: 1px solid #eaecf0;
  border-radius: 999px;
  background: #f8fafc;
  padding: 7px 10px;
}
```

### Task 1.3: 예시 검색 칩 동작 추가

- [ ] **Step 1: `app/static/app.js`에 예시 버튼 이벤트를 추가한다.**

```javascript
document.querySelectorAll("[data-example-query]").forEach((button) => {
  button.addEventListener("click", () => {
    searchCompanies(button.dataset.exampleQuery || "");
  });
});
```

- [ ] **Step 2: 테스트를 통과시킨다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_homepage_positions_as_b2b_company_data_platform -q
node --check app/static/app.js
```

Expected:

```text
1 passed
```

---

## 7. PR 2: 검색 결과 dense row와 비교 진입

**목표:** 검색 결과를 B2B 업무자가 빠르게 비교할 수 있는 리스트로 만든다.

**Files:**

- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

### Task 2.1: 검색 결과 UI contract 테스트 추가

- [ ] **Step 1: 실패 테스트를 작성한다.**

```python
def test_search_results_render_dense_business_rows():
    with TestClient(app) as client:
        script_response = client.get("/app.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "result-card-main" in script_response.text
    assert "result-meta-grid" in script_response.text
    assert "data-result-compare-add" in script_response.text
    assert ".result-card-main" in style_response.text
    assert ".result-meta-grid" in style_response.text
    assert ".result-data-badges" in style_response.text
```

- [ ] **Step 2: 실패를 확인한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_search_results_render_dense_business_rows -q
```

Expected:

```text
FAILED ... AssertionError
```

### Task 2.2: 결과 row markup 확장

- [ ] **Step 1: `renderResults(items)`의 `link.innerHTML`을 아래 구조로 바꾼다.**

```javascript
link.innerHTML = `
  <div class="result-card-main">
    <div>
      <strong>${text(displayName)}</strong>
      <span class="result-subtitle">${text(company.corpEnsnNm || company.listedItemName || company.enpRprFnm, "보조 정보 없음")}</span>
    </div>
    <div class="result-actions">
      <span class="result-market-badge">${company.isListed ? text(market, "상장") : "비상장/확인 필요"}</span>
      <button type="button" data-result-compare-add="${text(company.crno)}" data-result-name="${text(displayName)}">비교 추가</button>
    </div>
  </div>
  <div class="result-meta-grid">
    <span><b>법인등록번호</b>${text(company.crno)}</span>
    <span><b>업종</b>${text(company.enpMainBizNm || company.itmsNm, "정보 없음")}</span>
    <span><b>대표자</b>${text(company.enpRprFnm, "정보 없음")}</span>
    <span><b>직원 수</b>${text(company.enpEmpeCnt, "정보 없음")}</span>
  </div>
  <div class="result-data-badges">
    <span>${company.isListed ? "주가 가능" : "주가 미제공"}</span>
    <span>기본정보</span>
  </div>
`;
```

- [ ] **Step 2: 링크 안 버튼 클릭이 프로필 이동을 트리거하지 않도록 이벤트를 추가한다.**

```javascript
function setupResultCompareButtons() {
  document.querySelectorAll("[data-result-compare-add]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const existing = JSON.parse(localStorage.getItem("profilage.compareCompanies") || "[]");
      const next = [
        ...existing.filter((item) => item.crno !== button.dataset.resultCompareAdd),
        {
          crno: button.dataset.resultCompareAdd,
          name: button.dataset.resultName,
        },
      ].slice(0, 4);
      localStorage.setItem("profilage.compareCompanies", JSON.stringify(next));
      button.textContent = "추가됨";
      button.disabled = true;
    });
  });
}
```

- [ ] **Step 3: `renderResults(items)` 마지막에 `setupResultCompareButtons();`를 호출한다.**

```javascript
resultList.appendChild(fragment);
setupResultCompareButtons();
```

### Task 2.3: dense row 스타일 추가

- [ ] **Step 1: 결과 카드 스타일을 업무용 list row로 조정한다.**

```css
.result-card {
  display: grid;
  gap: 10px;
  border: 1px solid #eaecf0;
  border-radius: 8px;
  background: #ffffff;
  padding: 16px;
}

.result-list {
  gap: 10px;
}

.result-card-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.result-subtitle {
  margin-top: 2px;
}

.result-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.result-market-badge,
.result-data-badges span {
  display: inline-flex;
  min-height: 26px;
  align-items: center;
  border-radius: 999px;
  background: #f2f4f7;
  color: #344054;
  padding: 0 9px;
  font-size: 12px;
  font-weight: 800;
}

.result-actions button {
  min-height: 28px;
  border: 1px solid #d8e5ff;
  border-radius: 8px;
  background: #f6f9ff;
  color: #175cd3;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 850;
  cursor: pointer;
}

.result-meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px 12px;
}

.result-meta-grid span {
  color: #344054;
  font-size: 13px;
  line-height: 1.45;
}

.result-meta-grid b {
  display: block;
  color: #667085;
  font-size: 11px;
  font-weight: 850;
}

.result-data-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
```

- [ ] **Step 2: 모바일에서는 meta grid를 2열 또는 1열로 줄인다.**

```css
@media (max-width: 720px) {
  .result-card-main {
    flex-direction: column;
  }

  .result-actions {
    justify-content: flex-start;
  }

  .result-meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 420px) {
  .result-meta-grid {
    grid-template-columns: 1fr;
  }
}
```

### Task 2.4: 테스트와 문법 검사

- [ ] **Step 1: 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_search_results_render_dense_business_rows -q
node --check app/static/app.js
git diff --check
```

Expected:

```text
1 passed
```

---

## 8. PR 3: 상세 페이지 executive summary 재구성

**목표:** 상세 페이지 상단에서 기업 판단에 필요한 핵심 정보를 먼저 보여준다.

**Files:**

- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

### Task 3.1: 상세 요약 레이어 contract 테스트 추가

- [ ] **Step 1: 실패 테스트를 작성한다.**

```python
def test_profile_exposes_executive_summary_layer():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderExecutiveSummary" in script_response.text
    assert "renderKeyMetricStrip" in script_response.text
    assert "executive-summary-block" in script_response.text
    assert "key-metric-strip" in script_response.text
    assert ".executive-summary-block" in style_response.text
    assert ".key-metric-strip" in style_response.text
```

- [ ] **Step 2: 실패를 확인한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_exposes_executive_summary_layer -q
```

Expected:

```text
FAILED ... AssertionError
```

### Task 3.2: Key Metrics 계산 함수 추가

- [ ] **Step 1: `profile-page-5.js`에 핵심 지표 helper를 추가한다.**

```javascript
function preferredFinancialValue(info, accountNames) {
  const rows = info?.dart_financial_accounts?.list || [];
  const match = rows.find((row) => accountNames.includes(row.account_nm));
  return match?.thstrm_amount || "";
}

function renderKeyMetricStrip({ info, outline, listed }) {
  const metrics = [
    ["시장", listed.mrktCtg || outline.corpRegMrktDcdNm],
    ["직원 수", formatNumber(outline.enpEmpeCnt)],
    ["설립일", compactDate(outline.enpEstbDt)],
    ["매출액", formatKoreanCurrency(preferredFinancialValue(info, ["매출액"]))],
    ["영업이익", formatKoreanCurrency(preferredFinancialValue(info, ["영업이익"]))],
    ["자산총계", formatKoreanCurrency(preferredFinancialValue(info, ["자산총계"]))],
  ];
  return `
    <section class="key-metric-strip" aria-label="핵심 지표">
      ${metrics
        .map(
          ([label, value]) => `
            <div>
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(text(value, "-"))}</strong>
            </div>
          `,
        )
        .join("")}
    </section>
  `;
}
```

`formatKoreanCurrency`가 이미 존재하면 그대로 사용한다. 존재하지 않으면 아래 함수를 추가한다.

```javascript
function formatKoreanCurrency(value) {
  const numeric = Number(String(value || "").replaceAll(",", ""));
  if (!Number.isFinite(numeric) || numeric === 0) return "";
  if (Math.abs(numeric) >= 1000000000000) return `${(numeric / 1000000000000).toFixed(1)}조`;
  if (Math.abs(numeric) >= 100000000) return `${Math.round(numeric / 100000000).toLocaleString("ko-KR")}억`;
  return numeric.toLocaleString("ko-KR");
}
```

### Task 3.3: Executive Summary 렌더러 추가

- [ ] **Step 1: `renderExecutiveSummary`를 추가한다.**

```javascript
function renderExecutiveSummary({ info, outline, listed }) {
  return `
    <article class="info-block executive-summary-block">
      <div class="block-heading">
        <h3>요약</h3>
        <span class="summary-status-pill">업무용 핵심 정보</span>
      </div>
      ${renderCompanyProfileSummaryCard()}
      ${renderKeyMetricStrip({ info, outline, listed })}
      ${renderSourceMeta([
        { label: "출처", value: "금융위원회 기업기본정보 · DART · SearchAPI" },
        { label: "기준", value: compactDate(outline.basDt || listed.basDt) },
      ])}
    </article>
  `;
}
```

- [ ] **Step 2: `renderCompanyDetail`에서 기업 개요 뒤가 아니라 상단 요약 영역에 배치한다.**

기존:

```javascript
${renderCompanyProfileSummaryCard()}
${renderCompanyStockCard(...)}
```

변경:

```javascript
${renderExecutiveSummary({ info, outline, listed })}
${renderCompanyStockCard(...)}
```

주의:

- `renderExecutiveSummary` 내부에서 `renderCompanyProfileSummaryCard()`를 호출하므로 중복 렌더링하지 않는다.
- `loadCompanyProfileSummary(crno)`는 그대로 유지한다.

### Task 3.4: Executive Summary 스타일 추가

- [ ] **Step 1: 스타일을 추가한다.**

```css
.executive-summary-block {
  display: grid;
  gap: 16px;
}

.executive-summary-block .company-ai-summary-card {
  border: 1px solid #eaecf0;
  box-shadow: none;
  padding: 16px;
}

.key-metric-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.key-metric-strip div {
  display: grid;
  gap: 5px;
  border: 1px solid #eaecf0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px;
}

.key-metric-strip span {
  color: #667085;
  font-size: 12px;
  font-weight: 850;
}

.key-metric-strip strong {
  color: #101828;
  font-size: 16px;
  font-weight: 850;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 2: 모바일 2열/1열 규칙을 추가한다.**

```css
@media (max-width: 720px) {
  .key-metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 420px) {
  .key-metric-strip {
    grid-template-columns: 1fr;
  }
}
```

### Task 3.5: 테스트와 문법 검사

- [ ] **Step 1: 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_exposes_executive_summary_layer -q
node --check app/static/profile-page-5.js
git diff --check
```

Expected:

```text
1 passed
```

---

## 9. PR 4: 데이터 신뢰 표시 체계 통일

**목표:** 모든 주요 카드에서 출처, 기준일, 갱신 상태를 같은 패턴으로 보여준다.

**Files:**

- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

### Task 4.1: trust meta contract 테스트 추가

- [ ] **Step 1: 실패 테스트를 작성한다.**

```python
def test_profile_uses_consistent_data_trust_meta():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderDataTrustMeta" in script_response.text
    assert "data-trust-meta" in script_response.text
    assert "data-trust-badge" in script_response.text
    assert ".data-trust-meta" in style_response.text
    assert ".data-trust-badge" in style_response.text
```

- [ ] **Step 2: 실패를 확인한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_uses_consistent_data_trust_meta -q
```

Expected:

```text
FAILED ... AssertionError
```

### Task 4.2: trust meta helper 추가

- [ ] **Step 1: `profile-page-5.js`에 helper를 추가한다.**

```javascript
function renderDataTrustMeta(items, status = "확인됨") {
  const visibleItems = items.filter((item) => item?.value);
  if (!visibleItems.length) return "";
  return `
    <div class="data-trust-meta">
      <span class="data-trust-badge">${escapeHtml(status)}</span>
      <dl>
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
    </div>
  `;
}
```

- [ ] **Step 2: 신규/주요 카드부터 `renderDataTrustMeta`를 적용한다.**

대상:

- 기업 개요 카드
- AI 요약/Executive Summary 카드
- 상장 및 주가 카드
- 재무 요약 카드
- 최근 공시 카드
- 관계회사 요약 카드

상장 및 주가 카드 예:

```javascript
${renderDataTrustMeta(
  [
    { label: "출처", value: "SearchAPI Google Finance" },
    { label: "캐시 만료", value: formatDateTime(stock?._meta?.expires_at) },
  ],
  hasListedStock ? "주가 제공" : "부분 제공",
)}
```

### Task 4.3: trust meta 스타일 추가

- [ ] **Step 1: 스타일을 추가한다.**

```css
.data-trust-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-top: 14px;
  border-top: 1px solid #eef0f6;
  padding-top: 12px;
}

.data-trust-badge {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  border-radius: 999px;
  background: #ecfdf5;
  color: #08734f;
  padding: 0 9px;
  font-size: 12px;
  font-weight: 850;
}

.data-trust-meta dl {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 0;
  color: #667085;
  font-size: 12px;
}

.data-trust-meta div {
  display: inline-flex;
  gap: 4px;
}

.data-trust-meta dt {
  font-weight: 850;
}

.data-trust-meta dd {
  margin: 0;
}
```

### Task 4.4: 테스트와 문법 검사

- [ ] **Step 1: 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_uses_consistent_data_trust_meta -q
node --check app/static/profile-page-5.js
git diff --check
```

Expected:

```text
1 passed
```

---

## 10. PR 5: 모바일 섹션 내비게이션과 CTA 정리

**목표:** 모바일에서 긴 상세 페이지를 업무용으로 탐색하기 쉽게 만든다.

**Files:**

- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

### Task 5.1: 모바일 섹션 nav contract 테스트 추가

- [ ] **Step 1: 실패 테스트를 작성한다.**

```python
def test_profile_exposes_mobile_section_navigation():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderProfileSectionNav" in script_response.text
    assert "profile-section-nav" in script_response.text
    assert "data-profile-section" in script_response.text
    assert ".profile-section-nav" in style_response.text
    assert "position: sticky;" in style_response.text
```

- [ ] **Step 2: 실패를 확인한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_exposes_mobile_section_navigation -q
```

Expected:

```text
FAILED ... AssertionError
```

### Task 5.2: 섹션 nav 렌더러 추가

- [ ] **Step 1: `profile-page-5.js`에 렌더러를 추가한다.**

```javascript
function renderProfileSectionNav() {
  const sections = [
    ["summary", "요약"],
    ["market", "주가"],
    ["financials", "재무"],
    ["disclosures", "공시"],
    ["relationships", "관계회사"],
    ["basic", "기업정보"],
  ];
  return `
    <nav class="profile-section-nav" aria-label="프로필 섹션">
      ${sections
        .map(
          ([id, label]) => `
            <a href="#section-${id}" data-profile-section="${id}">${label}</a>
          `,
        )
        .join("")}
    </nav>
  `;
}
```

- [ ] **Step 2: `renderCompanyDetail`에서 hero 아래, 카드 목록 위에 삽입한다.**

```javascript
${renderProfileSectionNav()}
```

- [ ] **Step 3: 주요 카드에 id를 붙인다.**

예:

```html
<article id="section-summary" class="info-block executive-summary-block">
```

```html
<article id="section-market" class="info-block company-market-card ...">
```

관계회사 요약은 `section-relationships`, 기업 개요는 `section-basic`을 사용한다.

### Task 5.3: sticky nav 스타일 추가

- [ ] **Step 1: 기본 스타일을 추가한다.**

```css
.profile-section-nav {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  gap: 6px;
  overflow-x: auto;
  border: 1px solid #eaecf0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  padding: 8px;
  backdrop-filter: blur(8px);
}

.profile-section-nav a {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  color: #344054;
  padding: 0 11px;
  font-size: 13px;
  font-weight: 850;
  white-space: nowrap;
  text-decoration: none;
}

.profile-section-nav a:hover,
.profile-section-nav a:focus-visible {
  background: #f2f4f7;
  color: #175cd3;
}
```

- [ ] **Step 2: 데스크톱에서는 nav가 과하게 보이지 않도록 폭을 맞춘다.**

```css
@media (min-width: 900px) {
  .profile-section-nav {
    top: 12px;
  }
}
```

### Task 5.4: AI 요약 모바일 접힘

- [ ] **Step 1: AI 요약 카드에 접힘 class를 추가한다.**

`renderCompanyProfileSummaryCard()`의 article class:

```html
<article class="info-block company-ai-summary-card is-collapsed-mobile" data-company-profile-summary-card>
```

- [ ] **Step 2: 요약 완료 후 `더보기` 버튼을 표시한다.**

`renderCompanyProfileSummaryPayload(payload)` 하단:

```html
<button type="button" class="company-ai-summary-more" data-company-ai-summary-more>요약 더보기</button>
```

- [ ] **Step 3: 버튼 이벤트를 추가한다.**

```javascript
function setupCompanyAiSummaryMore() {
  document.querySelectorAll("[data-company-ai-summary-more]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
      const card = button.closest(".company-ai-summary-card");
      card?.classList.remove("is-collapsed-mobile");
      button.remove();
    });
  });
}
```

`loadCompanyProfileSummary` 성공 후 호출:

```javascript
setupCompanyAiSummaryMore();
```

- [ ] **Step 4: 모바일 접힘 스타일을 추가한다.**

```css
@media (max-width: 560px) {
  .company-ai-summary-card.is-collapsed-mobile .company-ai-summary-body {
    max-height: 190px;
    overflow: hidden;
  }

  .company-ai-summary-more {
    min-height: 34px;
    border: 1px solid #d8e5ff;
    border-radius: 8px;
    background: #f6f9ff;
    color: #175cd3;
    padding: 0 12px;
    font-weight: 850;
  }
}
```

### Task 5.5: 테스트와 문법 검사

- [ ] **Step 1: 테스트를 실행한다.**

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py::test_profile_exposes_mobile_section_navigation -q
node --check app/static/profile-page-5.js
git diff --check
```

Expected:

```text
1 passed
```

---

## 11. CTA 체계

### 첫 화면 CTA

Primary:

- `기업 검색하기`

Secondary:

- `예시 기업 보기`
- `API 문서 보기`

### 검색 결과 CTA

Primary:

- `프로필 보기`

Secondary:

- `비교 추가`

### 상세 페이지 CTA

Primary:

- `비교에 추가`

Secondary:

- `공유`
- `API로 연동하기`
- `데이터 문의`

### 유료/문의 CTA

도입 위치:

- 첫 화면 하단 source rail 근처
- 상세 페이지 trust meta 아래
- 비교 화면 toolbar 아래

추천 문구:

- `팀용 데이터 도입 문의`
- `API 사용 문의`
- `기업 데이터 자동화 상담`
- `대량 조회 플랜 문의`

---

## 12. 시각 스타일 권장값

### 컬러

```css
:root {
  --bg: #f8fafc;
  --panel: #ffffff;
  --text: #101828;
  --muted: #667085;
  --line: #eaecf0;
  --accent: #175cd3;
  --accent-strong: #1849a9;
  --positive: #08734f;
  --warning: #b54708;
}
```

### 타입

- 본문: 현재 system/Inter 유지
- H1: 34~58px
- 카드 제목: 17~20px
- 메타 라벨: 11~12px, 800 이상
- 숫자 지표: 16~28px, 850

### 카드

- radius: 8px 유지
- shadow: 약하게 줄이고 border 중심
- 카드 안 카드 중첩은 최소화
- 반복 item 카드만 배경 `#f8fafc`

### 버튼

- Primary: solid blue
- Secondary: outline blue
- Tertiary: ghost/transparent
- 위험/삭제: 텍스트 또는 icon only

---

## 13. QA 체크리스트

### 데스크톱

- [ ] 첫 화면에서 서비스 목적이 3초 안에 이해된다.
- [ ] 검색창 placeholder가 검색 가능한 키를 말한다.
- [ ] 예시 검색 칩 클릭으로 검색이 실행된다.
- [ ] 검색 결과에서 회사명, 시장, 업종, 대표자, 직원 수를 한눈에 볼 수 있다.
- [ ] 검색 결과에서 비교 추가가 프로필 이동과 충돌하지 않는다.
- [ ] 상세 페이지 첫 viewport 안에 회사명, 요약, key metrics가 보인다.
- [ ] 모든 주요 카드에 출처/기준일/상태가 있다.
- [ ] 비교 CTA와 문의/API CTA가 서로 경쟁하지 않는다.

### 모바일

- [ ] 검색창이 화면 너비 안에서 잘리지 않는다.
- [ ] 검색 결과 row가 390px 폭에서 overflow 없이 보인다.
- [ ] 상세 페이지 섹션 nav가 sticky로 동작한다.
- [ ] AI 요약이 너무 길게 첫 화면을 밀어내지 않는다.
- [ ] 주요 CTA가 한 줄 compact 또는 full-width로 자연스럽게 보인다.
- [ ] 차트 tooltip과 모달이 viewport 밖으로 잘리지 않는다.

### 접근성

- [ ] 검색창 label이 유지된다.
- [ ] 예시 검색 칩은 button이다.
- [ ] 필터는 tablist 또는 button group으로 keyboard 접근 가능하다.
- [ ] 데이터 상태는 색상만이 아니라 텍스트로도 표현된다.
- [ ] sticky nav link는 focus-visible 상태가 있다.
- [ ] modal/tooltip은 모바일에서 터치로 열고 닫을 수 있다.

---

## 14. 검증 명령

각 PR 공통 검증:

```bash
uv run pytest tests/test_company_affiliate_api.py -q
python3 -m py_compile app/api/company.py app/services/company_profile_summary.py app/services/company_disclosure_summary.py
node --check app/static/app.js
node --check app/static/profile-page-5.js
node --check app/static/compare-page.js
git diff --check
```

배포 전 smoke test:

```bash
curl -I https://profile.fin-ally.net/
curl -I https://profile.fin-ally.net/profile?crno=1101113326588
```

원격 배포:

```bash
git push origin main
ssh server-4096 "cd /data/psyche/Projects/profilage && git fetch origin && git pull --ff-only"
ssh server-4096 "cd /data/psyche/Projects/profilage && docker compose up -d --build"
ssh server-4096 "cd /data/psyche/Projects/profilage && docker compose ps"
```

---

## 15. 실행 우선순위

### P0: 복잡도 감소와 목적 명확화

- PR 1: 첫 화면 포지셔닝
- PR 3: 상세 페이지 executive summary
- PR 4: 데이터 신뢰 표시 체계

이유:

- 사용자가 가장 먼저 체감한다.
- 현재 "복잡해 보임" 문제의 핵심은 데이터 양이 아니라 정보 위계다.

### P1: 업무용 검색/비교 강화

- PR 2: 검색 결과 dense row
- 검색 결과 비교 추가
- 필터 바 1차 도입

이유:

- B2B 사용자는 결과 비교와 후보 압축이 중요하다.

### P2: 모바일과 전환 CTA

- PR 5: 모바일 섹션 내비게이션
- 문의/API/팀용 데이터 CTA
- 저장/최근 조회/공유 흐름

이유:

- 모바일 업무 사용성을 높이고, 장기적으로 수익화/문의 전환으로 연결한다.

---

## 16. 성공 기준

### 정성 기준

- 첫 화면에서 기업 데이터 조회 목적이 즉시 이해된다.
- 상세 페이지가 "데이터 덩어리"가 아니라 "업무용 요약 보고서"처럼 보인다.
- 데이터 출처와 기준일이 사용자의 신뢰를 높인다.
- 모바일에서 긴 페이지를 헤매지 않는다.

### 정량 기준

측정이 가능해지면 아래 지표를 본다.

- 검색 실행률
- 검색 결과 클릭률
- 검색 결과에서 비교 추가율
- 상세 페이지 내 `재무`, `공시`, `관계회사` 섹션 도달률
- 비교 페이지 진입률
- 공유 링크 복사율
- 데이터/API 문의 클릭률

---

## 17. Self-Review

### Spec coverage

- 첫 화면 목적 명확화: PR 1에서 처리한다.
- 검색창/필터 구조: PR 1, PR 2에서 처리한다.
- 검색 결과 비교 가능성: PR 2에서 처리한다.
- 상세 페이지 정보 구조: PR 3에서 처리한다.
- 데이터 신뢰 표현: PR 4에서 처리한다.
- 전문적이고 깔끔한 B2B 분위기: PR 1~5의 컬러/카드/버튼 원칙에 반영한다.
- 모바일 UX: PR 5에서 처리한다.
- CTA: 섹션 11과 PR 5에서 처리한다.

### Placeholder scan

- 이 계획은 실행 가능한 파일 경로, 테스트, 코드 조각, 검증 명령을 포함한다.
- 구현 중 새 데이터가 필요한 필터는 별도 API 확장 전에 현재 응답 필드 기반으로 시작한다.

### Scope check

- 이 계획은 프론트 UX 개선이 중심이다.
- 백엔드 데이터 모델 확장, 계정/결제, CRM 연동은 포함하지 않는다.
- 필터의 서버 사이드 검색 최적화는 검색 UX 1차 적용 이후 별도 계획으로 분리한다.
