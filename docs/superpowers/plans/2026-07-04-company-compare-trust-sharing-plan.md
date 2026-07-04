# 기업 비교 신뢰도 및 공유 기능 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기업 비교 페이지에서 각 기업의 재무 수치 기준을 명확히 보여주고, 현재 비교 조합을 URL로 쉽게 공유할 수 있게 만든다.

**Architecture:** 기존 FastAPI 정적 페이지 구조와 vanilla JavaScript 렌더링 구조를 유지한다. 백엔드 API는 새로 만들지 않고, `compare-page.js`가 이미 로드한 `get_company_info` 응답의 DART 기준 정보를 컬럼 헤더에 표시한다. 공유 링크는 localStorage가 아닌 현재 비교 목록의 `crno` URL 파라미터를 기준으로 만든다.

**Tech Stack:** FastAPI static page route, vanilla JavaScript, CSS, pytest.

---

## 핵심 원칙

1. **비교 수치의 기준을 숨기지 않는다**
   - 같은 화면에서 비교하더라도 기업별 보고서 기준이 다를 수 있다.
   - 각 기업 컬럼에 `2025 사업보고서 · 연결`처럼 기준 정보를 표시한다.

2. **공유 링크는 URL만으로 재현 가능해야 한다**
   - localStorage에 저장된 비교함은 개인 브라우저 상태다.
   - 공유 링크는 반드시 `/compare?crno=...&crno=...` 형태로 현재 비교 대상만 포함해야 한다.

3. **기존 비교 UX를 깨지 않는다**
   - `기업 추가`, `×` 삭제, 모바일 가로 스크롤 비교표는 유지한다.
   - 새 기능은 비교 페이지 상단 툴바와 표 헤더에만 최소한으로 추가한다.

4. **부분 데이터는 정상 상태로 처리한다**
   - DART 기준 정보가 없으면 `기준 정보 없음`을 표시한다.
   - clipboard API가 실패해도 사용자에게 공유 URL을 확인할 수 있는 fallback을 제공한다.

---

## 구현 범위

### 포함

- 기업별 기준 보고서 표시
- 공유 링크 복사 버튼
- URL/localStorage 정합성 정리
- 공유 URL 중복 제거 및 최대 5개 제한
- `report_code`, `fs_division` fallback 처리
- 모바일 레이아웃 보강
- 정적 자산/동작 회귀 테스트
- 캐시 버전 갱신 및 배포

### 제외

- LLM 요약
- 자동 동종업계 peer 추천
- 비교 기업 검색 모달
- 백엔드 비교 전용 API
- 로그인 기반 저장 비교함

---

## 파일 구조와 책임

- `app/static/compare-page.js`
  - 기업별 기준 label 생성.
  - 공유 URL 생성.
  - clipboard 복사 및 fallback 처리.
  - 비교표 헤더에 기준 정보와 `×` 삭제 버튼을 함께 렌더링.

- `app/static/styles.css`
  - 컬럼 기준 텍스트 스타일.
  - 공유 버튼 스타일.
  - 모바일에서 툴바/헤더 요소가 깨지지 않도록 보강.

- `app/static/compare.html`
  - `compare-page.js` cache busting 버전 갱신.
  - CSS cache busting 버전 갱신.

- `app/static/profile.html`
  - 공통 CSS cache busting 버전 갱신.

- `tests/test_company_affiliate_api.py`
  - 비교 페이지 정적 자산 테스트 확장.
  - 신규 함수/문구/CSS selector 존재 검증.

---

## 데이터 설계

### 기준 정보 입력 후보

`loadCompany(crno)`는 현재 다음 정보를 가지고 있다.

```javascript
{
  crno,
  name,
  subtitle,
  values,
  financialValues,
  ratioValues,
  basis:
    info.dart_latest_annual_financial_accounts?.selected ||
    info.dart_insights?.basis ||
    null,
}
```

이 구조를 유지하고, `basisLabel(company)` helper에서 표시용 텍스트로 변환한다.

### 기준 표시 우선순위

1. `company.basis.business_year`
2. `company.basis.report_name`
3. `company.basis.report_code` 또는 `company.basis.reportCode`를 보고서명 fallback으로 사용
4. `company.basis.fs_division` 또는 `company.basis.fsDivision`
5. 없으면 `기준 정보 없음`

### 기준 정보 fallback 주의점

현재 `loadCompany(crno)`의 `basis`는 아래 우선순위로 선택한다.

```javascript
basis:
  info.dart_latest_annual_financial_accounts?.selected ||
  info.dart_insights?.basis ||
  null
```

`dart_latest_annual_financial_accounts.selected`에는 현재 `fs_division`이 포함된다. 반면 `dart_insights.basis`는 현재 백엔드에서 `business_year`, `report_code`, `report_name`만 내려주며 `fs_division`은 포함하지 않는다. 따라서 fallback으로 `dart_insights.basis`를 쓰는 경우에는 `연결/별도`가 표시되지 않을 수 있다.

구현 시 선택지는 둘 중 하나다.

1. **프론트만 보완:** `fs_division`이 없으면 보고서 기준만 표시한다. 예: `2025 사업보고서`
2. **백엔드도 보완:** `CompanyInfoService`가 `dart_insights.basis`를 만들 때 `fs_division: annual_selected.get("fs_division")`도 포함한다.

이 계획에서는 작은 범위를 유지하기 위해 **프론트 fallback을 기본 구현**으로 하고, 백엔드 `fs_division` 보강은 선택 작업으로 둔다.

### 표시 예시

- `2025 사업보고서 · 연결`
- `2026 1분기보고서 · 연결`
- `2025 사업보고서`
- `기준 정보 없음`

### 연결/별도 label 매핑

```javascript
const financialStatementLabels = {
  CFS: "연결",
  OFS: "별도",
};
```

### 보고서명 fallback 매핑

`report_name`이 없을 때 `report_code`만으로도 사용자에게 읽히는 문구를 만들기 위해 아래 매핑을 사용한다.

```javascript
const financialReportLabels = {
  "11011": "사업보고서",
  "11012": "반기보고서",
  "11013": "1분기보고서",
  "11014": "3분기보고서",
};
```

---

## UI 설계

### 비교 페이지 상단 툴바

현재:

```text
선택한 기업 2개
재무 수치는 최근 사업보고서 또는 DART 정기보고서 기준입니다...
[기업 추가]
```

변경 후:

```text
선택한 기업 2개
재무 수치는 각 컬럼의 기준 보고서 기준입니다...
[공유 링크 복사] [기업 추가]
```

버튼 동작:

- `공유 링크 복사`
  - 현재 비교 중인 기업 `crno`만 URL에 담는다.
  - 성공 시 1.5초 동안 `복사됨` 표시.
  - 실패 시 버튼 아래 상태 문구에 공유 URL 표시.

- `기업 추가`
  - 기존처럼 `/`로 이동한다.

### 비교표 헤더

현재:

```text
항목 | LG전자(주) [×] | 삼성전자(주) [×]
```

변경 후:

```text
항목 | LG전자(주) [×]
     | 2025 사업보고서 · 연결

항목 | 삼성전자(주) [×]
     | 2025 사업보고서 · 연결
```

HTML 구조 예시:

```html
<span class="compare-column-head">
  <span>
    <span class="compare-column-name">삼성전자(주)</span>
    <span class="compare-column-basis">2025 사업보고서 · 연결</span>
  </span>
  <button class="compare-remove-button">×</button>
</span>
```

### 모바일

- 툴바는 기존처럼 세로 배치.
- 공유 버튼과 기업 추가 버튼은 전체 폭으로 표시.
- 표 헤더의 기업명/기준/삭제 버튼은 줄바꿈되어도 겹치지 않아야 한다.
- 비교표는 계속 `.compare-table-wrap` 내부에서만 가로 스크롤된다.

---

## 함수 설계

### `basisLabel(company)`

역할:

- 회사 객체의 `basis`를 사람이 읽는 기준 문구로 변환한다.

Pseudo-code:

```javascript
function basisLabel(company) {
  const basis = company?.basis || {};
  const year = basis.business_year || basis.businessYear;
  const reportCode = basis.report_code || basis.reportCode;
  const report = basis.report_name || basis.reportName || financialReportLabels[reportCode];
  const fsDivision = basis.fs_division || basis.fsDivision;
  const statement = financialStatementLabels[fsDivision] || "";
  const parts = [year, report].filter(Boolean);
  const head = parts.join(" ");
  if (head && statement) return `${head} · ${statement}`;
  if (head) return head;
  if (statement) return statement;
  return "기준 정보 없음";
}
```

### `compareShareUrl(companies)`

역할:

- 현재 렌더링된 회사 목록을 URL 공유 링크로 만든다.
- localStorage 항목은 사용하지 않는다.

Pseudo-code:

```javascript
function compareShareUrl(companies) {
  const endpoint = new URL("/compare", window.location.origin);
  Array.from(new Set(companies.map((company) => company.crno).filter(Boolean)))
    .slice(0, MAX_COMPARE_COMPANIES)
    .forEach((crno) => endpoint.searchParams.append("crno", crno));
  return endpoint.toString();
}
```

### `shareCompareLink(button, companies)`

역할:

- 공유 URL을 clipboard에 복사한다.
- 성공/실패 상태를 사용자에게 보여준다.

Pseudo-code:

```javascript
async function shareCompareLink(button, companies) {
  const url = compareShareUrl(companies);
  try {
    await navigator.clipboard.writeText(url);
    button.textContent = "복사됨";
    setTimeout(() => {
      button.textContent = "공유 링크 복사";
    }, 1500);
  } catch {
    const status = document.querySelector("[data-compare-share-status]");
    if (status) {
      status.textContent = `공유 링크를 복사하지 못했습니다. 아래 링크를 길게 눌러 복사해주세요: ${url}`;
    }
  }
}
```

### `setupCompareShareButton(companies)`

역할:

- 공유 버튼 이벤트를 바인딩한다.
- `renderComparePage(companies)` 호출 이후 실행한다.

Pseudo-code:

```javascript
function setupCompareShareButton(companies) {
  const button = document.querySelector("[data-compare-share]");
  if (!button) return;
  button.addEventListener("click", () => shareCompareLink(button, companies));
}
```

---

## 단계별 구현 계획

### Task 1: 실패 테스트 작성

**Files:**
- Modify: `tests/test_company_affiliate_api.py`

- [ ] `test_compare_page_serves_company_compare_frontend`에 아래 assertion을 추가한다.

```python
assert "basisLabel" in script_response.text
assert "financialReportLabels" in script_response.text
assert "financialStatementLabels" in script_response.text
assert "compareShareUrl" in script_response.text
assert "shareCompareLink" in script_response.text
assert "setupCompareShareButton" in script_response.text
assert "new Set(companies.map((company) => company.crno)" in script_response.text
assert "공유 링크 복사" in script_response.text
assert "복사됨" in script_response.text
assert "공유 링크를 복사하지 못했습니다" in script_response.text
assert "data-compare-share" in script_response.text
assert "data-compare-share-status" in script_response.text
assert ".compare-column-basis" in style_response.text
assert ".compare-share-button" in style_response.text
```

- [ ] cache busting 기대값을 미리 올린다.

```python
assert "/styles.css?v=company-profile-37" in response.text
assert "/compare-page.js?v=company-compare-5" in response.text
```

- [ ] RED 확인.

```bash
uv run pytest tests/test_company_affiliate_api.py::test_compare_page_serves_company_compare_frontend -q
```

Expected: `basisLabel`, `compareShareUrl`, cache version 등으로 실패한다.

---

### Task 2: 기업별 기준 label 구현

**Files:**
- Modify: `app/static/compare-page.js`

- [ ] `financialStatementLabels` 상수를 추가한다.

```javascript
const financialStatementLabels = {
  CFS: "연결",
  OFS: "별도",
};
```

- [ ] `financialReportLabels` 상수를 추가한다.

```javascript
const financialReportLabels = {
  "11011": "사업보고서",
  "11012": "반기보고서",
  "11013": "1분기보고서",
  "11014": "3분기보고서",
};
```

- [ ] `basisLabel(company)` helper를 추가한다.
- [ ] `basisLabel(company)`는 아래 fallback을 모두 처리한다.
  - `business_year` 또는 `businessYear`
  - `report_name` 또는 `reportName`
  - `report_code` 또는 `reportCode`
  - `fs_division` 또는 `fsDivision`
  - `fs_division`이 없으면 연결/별도 표시 없이 보고서 기준만 표시
- [ ] `renderCompareTable(companies)`의 `<th>` 렌더링을 변경한다.

변경 전:

```javascript
<span>${escapeHtml(company.name)}</span>
<button ...>×</button>
```

변경 후:

```javascript
<span class="compare-column-title">
  <span class="compare-column-name">${escapeHtml(company.name)}</span>
  <span class="compare-column-basis">${escapeHtml(basisLabel(company))}</span>
</span>
<button ...>×</button>
```

- [ ] 삭제 버튼의 접근성 label은 유지한다.

```html
aria-label="${attr(company.name)} 비교에서 삭제"
```

---

### Task 3: 공유 링크 복사 구현

**Files:**
- Modify: `app/static/compare-page.js`

- [ ] `compareShareUrl(companies)`를 추가한다.
- [ ] `compareShareUrl(companies)`는 `Array.from(new Set(...))`으로 `crno`를 중복 제거한다.
- [ ] `compareShareUrl(companies)`는 최대 `MAX_COMPARE_COMPANIES`개까지만 URL에 포함한다.
- [ ] `compareShareUrl(companies)`는 localStorage를 참조하지 않고 인자로 받은 `companies`만 사용한다.
- [ ] `shareCompareLink(button, companies)`를 추가한다.
- [ ] `shareCompareLink(button, companies)` fallback 문구는 긴 URL이 모바일에서 밀리지 않도록 `compare-share-status` 영역에 표시한다.
- [ ] `setupCompareShareButton(companies)`를 추가한다.
- [ ] `renderComparePage(companies)`의 toolbar에 공유 버튼과 상태 영역을 추가한다.

Toolbar 예시:

```javascript
<div class="compare-toolbar-actions">
  <button type="button" class="compare-share-button" data-compare-share>공유 링크 복사</button>
  <a class="primary-link-button" href="/">기업 추가</a>
</div>
<p class="compare-share-status" data-compare-share-status role="status"></p>
```

- [ ] `renderComparePage(companies)` 끝에서 `setupCompareShareButton(companies)`를 호출한다.

```javascript
setupCompareRemoveButtons();
setupCompareShareButton(companies);
```

---

### Task 4: 스타일 구현

**Files:**
- Modify: `app/static/styles.css`

- [ ] 컬럼 헤더 내부 구조 스타일 추가.

```css
.compare-column-title {
  display: inline-grid;
  gap: 3px;
  min-width: 0;
}

.compare-column-name {
  color: #344054;
  font-weight: 850;
}

.compare-column-basis {
  color: #667085;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
```

- [ ] 공유 버튼 스타일 추가.

```css
.compare-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.compare-share-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  border: 1px solid #d8e5ff;
  border-radius: 8px;
  background: #fff;
  color: #1a73e8;
  padding: 0 11px;
  font-size: 13px;
  font-weight: 850;
  cursor: pointer;
}

.compare-share-status {
  margin: 8px 0 0;
  color: #667085;
  font-size: 12px;
  overflow-wrap: anywhere;
}
```

- [ ] 모바일 보강.

```css
@media (max-width: 560px) {
  .compare-toolbar-actions {
    width: 100%;
    flex-direction: column;
  }

  .compare-share-button {
    width: 100%;
  }

  .compare-column-head {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}
```

---

### Task 4.5: 선택 작업 - `dart_insights.basis.fs_division` 보강

**Files:**
- Optional Modify: `app/services/company_affiliate.py`
- Optional Test: `tests/test_company_affiliate_api.py`

이 작업은 필수는 아니지만, 기준 표시의 일관성을 더 높인다.

- [ ] `CompanyInfoService._fetch_dart_profile()`에서 `normalize_dart_insights(... basis=...)` 호출 시 `fs_division`을 추가한다.

```python
basis={
    "business_year": annual_selected["business_year"],
    "report_code": annual_selected["report_code"],
    "report_name": annual_selected.get("report_name"),
    "fs_division": annual_selected.get("fs_division"),
}
```

- [ ] normalizer 테스트에서 `payload["basis"]["fs_division"] == "CFS"`를 확인한다.

이 선택 작업을 하지 않더라도 프론트 `basisLabel()` fallback 때문에 기능은 정상 동작해야 한다.

---

### Task 5: 캐시 버전 갱신

**Files:**
- Modify: `app/static/compare.html`
- Modify: `app/static/profile.html`
- Modify: `tests/test_company_affiliate_api.py`

- [ ] `compare.html`의 CSS 버전 변경.

```html
<link rel="stylesheet" href="/styles.css?v=company-profile-37" />
```

- [ ] `compare.html`의 JS 버전 변경.

```html
<script src="/compare-page.js?v=company-compare-5" defer></script>
```

- [ ] `profile.html`의 공통 CSS 버전 변경.

```html
<link rel="stylesheet" href="/styles.css?v=company-profile-37" />
```

- [ ] 테스트의 버전 문자열도 동일하게 갱신한다.

---

### Task 6: 검증

**Commands:**

```bash
node --check app/static/compare-page.js
```

```bash
uv run pytest tests/test_company_affiliate_api.py::test_compare_page_serves_company_compare_frontend -q
```

```bash
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected:

- `node --check` exits 0.
- 단일 비교 페이지 테스트 통과.
- 전체 테스트 통과. 현재 기준 예상: `73 passed`.

---

### Task 7: 커밋/푸시

**Commands:**

```bash
git status --short --branch
git add app/static/compare-page.js app/static/styles.css app/static/compare.html app/static/profile.html tests/test_company_affiliate_api.py
git commit -m "feat: show compare basis and share link"
git push origin main
```

---

### Task 8: 원격 서버 배포

**Commands:**

```bash
ssh server-4096 git -C /data/psyche/Projects/profilage fetch origin
ssh server-4096 git -C /data/psyche/Projects/profilage pull --ff-only origin main
ssh server-4096 docker compose -f /data/psyche/Projects/profilage/docker-compose.yml up -d --build api
```

**Verification:**

```bash
ssh server-4096 docker compose -f /data/psyche/Projects/profilage/docker-compose.yml ps api
ssh server-4096 curl -fsS http://127.0.0.1:18000/compare
ssh server-4096 curl -fsS http://127.0.0.1:18000/profile
```

Expected:

- `profilage-api` status is `Up`.
- `/compare` contains:
  - `/styles.css?v=company-profile-37`
  - `/compare-page.js?v=company-compare-5`
- `/profile` contains:
  - `/styles.css?v=company-profile-37`

---

## Acceptance Criteria

- [ ] 비교표 각 기업 컬럼에서 기업명 아래 기준 보고서를 볼 수 있다.
- [ ] 기준 정보가 없으면 `기준 정보 없음`이 표시된다.
- [ ] `report_name`이 없고 `report_code`만 있어도 보고서명이 표시된다.
- [ ] `fs_division`이 없으면 연결/별도 없이 보고서 기준만 표시된다.
- [ ] `공유 링크 복사` 버튼이 현재 비교 대상 `crno`만 포함한 URL을 복사한다.
- [ ] 공유 링크에서 중복 `crno`는 제거된다.
- [ ] 공유 링크에는 최대 5개 기업만 포함된다.
- [ ] 공유 링크 생성은 localStorage를 참조하지 않는다.
- [ ] 복사 성공 시 버튼 문구가 잠시 `복사됨`으로 바뀐다.
- [ ] 복사 실패 시 사용자가 URL을 확인할 수 있는 fallback 문구가 표시된다.
- [ ] 기업 삭제 후 공유 링크에는 삭제된 기업이 포함되지 않는다.
- [ ] 모바일에서 공유/추가 버튼이 겹치지 않는다.
- [ ] 비교표 가로 스크롤 동작은 유지된다.
- [ ] 전체 테스트가 통과한다.

---

## Risk And Mitigation

### Clipboard API 제한

- **Risk:** 일부 브라우저/환경에서 `navigator.clipboard`가 HTTPS 또는 권한 문제로 실패할 수 있다.
- **Mitigation:** 실패 시 `data-compare-share-status` 영역에 공유 URL을 표시한다.

### 기준 정보 필드 불일치

- **Risk:** `selected`와 `basis`의 필드명이 다를 수 있다.
- **Mitigation:** `business_year/businessYear`, `report_name/reportName`, `fs_division/fsDivision`을 모두 처리한다.

### URL과 localStorage 불일치

- **Risk:** URL에는 삭제됐지만 localStorage에 남아 다시 나타날 수 있다.
- **Mitigation:** 삭제 시 localStorage에서도 동일 `crno`를 제거한다. 공유 링크는 렌더링된 `companies`만 사용한다.

### 모바일 헤더 압축

- **Risk:** 기업명이 긴 경우 기준 텍스트와 `×` 버튼이 겹칠 수 있다.
- **Mitigation:** `.compare-column-title`은 grid, `.compare-column-head`는 flex-wrap 또는 align-start로 보강한다.

---

## Future Extensions

- 비교 페이지 내부 검색/추가 모달
- 선택 지표만 보기
- 2개 기업 비교 시 차이값 컬럼
- 기준 보고서가 다른 기업이 섞인 경우 상단 경고 배지
- CSV 다운로드
