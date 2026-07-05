# Company Feature Opportunities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DART, 금융위원회 기업기본정보, SearchAPI Google Finance를 이용해 기업 프로필과 비교 화면의 해석력을 높이고, 데이터가 부족한 기업도 부분 정보를 안정적으로 보여준다.

**Architecture:** 현재 API는 `app/api/company.py`가 라우팅하고 `app/services/company_affiliate.py`, `app/services/company_dart.py`, `app/services/company_store.py`, `app/services/company_insights.py`가 데이터 조회/캐시/정규화를 담당한다. 프론트엔드는 `app/static/profile-page-5.js`, `app/static/compare-page.js`, `app/static/styles.css` 중심으로 확장한다. 기능은 즉시 구현 가능한 규칙 기반 기능을 먼저 만들고, 원문 파싱/뉴스/LLM/시가총액 같은 추가 의존 기능은 별도 단계로 분리한다.

**Tech Stack:** FastAPI, Python service layer, Postgres-backed cache/store, vanilla JavaScript frontend, CSS, DART OpenAPI, 금융위원회 기업기본정보 API, SearchAPI Google Finance.

---

## 1. 현재 데이터 소스와 실제 가능 범위

### DART

현재 코드에서 사용 중이거나 확장 가능한 DART 범위:

- 기업 고유번호 조회
- DART 회사 개황
- 최근 공시 목록
- 재무제표 계정
- 최근 정기보고서 기준 재무 요약
- 최대 10개년 재무 추이
- 주요주주
- 소액주주
- 배당
- 감사의견
- 재무비율
- 주식 총수
- 자기주식
- 임원
- 직원

주의할 점:

- 공시 목록과 viewer 링크는 있으나, 공시 원문 본문을 안정적으로 수집/파싱하는 계층은 아직 없다.
- 최대주주 변동, 임원 변동, 배당 중단/급감 같은 변화 탐지는 단일 보고서만으로는 부족하다.
- 변화 탐지를 하려면 다년도 DART 조회 또는 조회 결과의 히스토리 저장이 필요하다.

### 금융위원회 기업기본정보

현재 활용 범위:

- 기업 개요
- 법인등록번호, 사업자등록번호
- 대표자, 설립일, 직원 수, 주소, 업종
- 상장 정보
- 계열회사
- 종속기업

주의할 점:

- 비상장 기업은 KRX/SearchAPI 주가 정보가 없을 수 있다.
- DART 고유번호가 없거나 정기보고서가 없는 기업도 기본정보는 표시해야 한다.
- 관계회사 수 변화 추적은 현재 목록만으로는 불가능하며, 별도 스냅샷 저장이 필요하다.

### SearchAPI Google Finance

현재 활용 범위:

- 현재가
- 기간별 주가 그래프
- 기간별 수익률 계산 기반 데이터
- 주가 캐시 TTL 관리

현재 TTL 정책:

- `1D`: KRX 장중 1분, 장외 10분
- `5D`: KRX 장중 5분, 장외 30분
- `1M`, `3M`: 30분
- `6M`, `YTD`: 2시간
- `1Y`: 4시간
- `5Y`, `MAX`, `ALL`: 1일

주의할 점:

- SearchAPI 일반 검색/뉴스 검색은 현재 Google Finance 주가 조회와 별도 연동이다.
- 뉴스 요약을 하려면 SearchAPI engine 확장 또는 별도 뉴스 API가 필요하다.
- 시가총액, PER, PBR은 현재 파서에서 안정적으로 제공된다고 보기 어렵다.

---

## 2. 기능 분류 원칙

### 바로 구현 가능한 기능

현재 API와 저장 구조를 크게 바꾸지 않고 구현한다.

- 공시 이벤트 타임라인
- 주가 차트 공시 마커
- 규칙 기반 재무 요약
- 비교 페이지 요약
- 기간별 주가 수익률 요약
- 비상장/부분 데이터 graceful degradation

### 선행 작업 후 구현 가능한 기능

추가 조회, 스냅샷 저장, 원문 파싱, 외부 데이터가 필요하다.

- 최대주주 변동 탐지
- 임원 변동 탐지
- 배당 중단/급감 탐지
- 관계회사 수 변화 추적
- 공시 원문 LLM 요약
- 뉴스/이슈 요약
- 자동 동종업계 비교
- PER/PBR/시가총액 기반 밸류에이션 비교

---

## 3. 우선순위 로드맵

### 1순위: 비상장/부분 데이터 표시 안정화

이유:

- 현재 사용자가 이미 비상장 또는 주가 정보가 없는 기업에서 실패 화면을 경험했다.
- 데이터 소스 일부가 실패해도 기업 기본정보, 관계회사, DART 가능 정보는 보여주는 것이 서비스 신뢰도를 높인다.
- 이후 모든 기능의 공통 전제다.

완료 기준:

- 금융위원회 기본정보만 있는 기업도 프로필 화면이 열린다.
- 주가 카드는 `상장/주가 정보를 찾을 수 없습니다` 같은 부분 상태로 표시된다.
- DART 정보가 없으면 DART 기반 카드만 숨기거나 안내 문구를 표시한다.

### 2순위: 공시 이벤트 타임라인

이유:

- DART 공시 목록은 이미 있다.
- 이벤트 분류가 있어야 주가 차트 마커와 리스크 카드가 안정적으로 확장된다.

완료 기준:

- 공시 제목과 유형을 규칙 기반으로 `정기보고서`, `지분/최대주주`, `임원`, `자본`, `배당`, `감사/회계`, `기타`로 분류한다.
- 프로필 화면에 최근 이벤트 타임라인을 표시한다.
- 공시 상세 링크 또는 기존 viewer 모달로 연결한다.

### 3순위: 주가 차트 공시 이벤트 마커

이유:

- DART 공시 날짜와 SearchAPI 주가 포인트를 결합하면 체감 가치가 크다.
- LLM 없이 구현 가능하다.

완료 기준:

- 주가 차트 위에 주요 공시 마커를 표시한다.
- 마커 클릭 또는 hover 시 공시 제목, 일자, 분류를 보여준다.
- 공시일이 비거래일이면 가장 가까운 다음 거래일 포인트에 매핑한다.
- 장마감 후 공시는 다음 거래일 이벤트로 표시하는 정책을 둔다.

### 4순위: 규칙 기반 위험 신호 카드

이유:

- 숫자를 해석하기 어려운 사용자를 도와준다.
- 단일 보고서로 가능한 신호와 히스토리가 필요한 신호를 분리할 수 있다.

바로 가능한 신호:

- 부채비율이 높은 경우
- 영업이익률이 낮거나 음수인 경우
- ROE/ROA가 낮거나 음수인 경우
- 감사의견이 적정이 아닌 경우
- 관계회사/종속기업 수가 일정 기준 이상인 경우

히스토리 필요 신호:

- 부채비율 급증
- 영업이익 적자 전환
- 당기순이익 적자 전환
- 최대주주 변동
- 주요 임원 변동
- 배당 중단 또는 급감
- 관계회사 수 변화

완료 기준:

- `현재 데이터 기준`과 `과거 비교 기준` 신호를 UI에서 구분한다.
- 과거 비교 데이터가 없으면 해당 신호를 계산하지 않는다.

### 5순위: 비교 페이지 종합 요약

이유:

- 비교 기능이 이미 있으므로 자연스럽게 확장 가능하다.
- 사용자가 수치표를 전부 읽지 않아도 차이를 파악할 수 있다.

완료 기준:

- 규모, 수익성, 안정성, 성장성, 주가 흐름, 공시 리스크 기준으로 비교 요약을 표시한다.
- 각 요약 문구는 어떤 수치에서 나온 것인지 간단한 근거를 함께 보여준다.
- 비상장 기업이 포함된 비교에서는 주가 기준을 제외하고 비교한다.

### 6순위: 관계회사 네트워크 고도화

이유:

- 계열회사와 종속기업의 차이가 사용자에게 헷갈린다.
- 현재는 수와 목록 중심이므로 그룹핑과 설명을 추가하면 이해도가 높아진다.

바로 가능한 기능:

- 계열회사 목록
- 종속기업 목록
- 상장 관계사만 보기
- 국가 또는 주소 기준 그룹
- 업종 기준 그룹
- 계열회사/종속기업 용어 툴팁

히스토리 필요 기능:

- 관계회사 수 변화 추적
- 새로 추가/제외된 관계회사 표시

---

## 4. 구현 작업 계획

### Task 1: 부분 데이터 프로필 정책 정리

**Files:**

- Modify: `app/services/company_affiliate.py`
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 실패 조건을 데이터 소스별 부분 상태로 나누는 테스트를 추가한다.**

검증할 케이스:

- 금융위원회 기본정보는 성공한다.
- KRX 상장 정보는 없다.
- DART 고유번호 또는 정기보고서는 없다.
- API 응답은 실패가 아니라 `partial` 상태와 사용 가능한 섹션을 반환한다.

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py -q
```

Expected:

- 신규 테스트는 구현 전 실패한다.
- 구현 후 전체 테스트가 통과한다.

- [ ] **Step 2: 서비스 응답에 부분 상태 메타데이터를 추가한다.**

권장 응답 필드:

```json
{
  "availability": {
    "basic": "available",
    "listed": "missing",
    "stock": "missing",
    "dart": "missing",
    "financial": "missing"
  },
  "warnings": [
    "상장 정보를 찾을 수 없습니다.",
    "DART 정기보고서를 찾을 수 없습니다."
  ]
}
```

- [ ] **Step 3: 프론트엔드에서 섹션별 placeholder를 표시한다.**

표시 정책:

- 기본정보가 있으면 프로필 Hero와 기업 개요는 표시한다.
- 주가 정보가 없으면 주가 카드에 안내 문구를 표시한다.
- DART 정보가 없으면 공시/재무/위험 신호 카드를 숨기거나 안내 상태로 표시한다.

- [ ] **Step 4: 커밋한다.**

```bash
git add app/services/company_affiliate.py app/static/profile-page-5.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "fix: show partial company profiles"
```

### Task 2: 공시 이벤트 분류기 추가

**Files:**

- Create: `app/services/company_disclosure_events.py`
- Modify: `app/services/company_affiliate.py`
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 공시 제목 분류 테스트를 추가한다.**

분류 규칙:

- `사업보고서`, `반기보고서`, `분기보고서`: `periodic`
- `최대주주`, `주식등의대량보유상황보고서`, `임원ㆍ주요주주`: `ownership`
- `임원`, `대표이사`, `사외이사`: `executive`
- `유상증자`, `무상증자`, `전환사채`, `신주인수권`: `capital`
- `배당`, `현금ㆍ현물배당`: `dividend`
- `감사`, `회계`, `감사보고서`: `audit`
- 그 외: `other`

Run:

```bash
uv run pytest tests/test_company_affiliate_api.py -q
```

- [ ] **Step 2: `company_disclosure_events.py`에 순수 함수로 분류기를 구현한다.**

권장 함수:

```python
def classify_disclosure_event(report_name: str) -> str:
    ...

def normalize_disclosure_events(disclosures: list[dict]) -> list[dict]:
    ...
```

- [ ] **Step 3: 기업 프로필 응답에 `disclosure_events`를 추가한다.**

각 이벤트 필드:

```json
{
  "date": "20260701",
  "title": "임원ㆍ주요주주특정증권등소유상황보고서",
  "category": "ownership",
  "corp_name": "삼성전자",
  "receipt_no": "20260701000000",
  "viewer_url": "..."
}
```

- [ ] **Step 4: 프로필 화면에 타임라인을 표시한다.**

UI 정책:

- 최근 10개 이벤트를 기본 표시한다.
- 카테고리 배지를 표시한다.
- 클릭 시 기존 공시 viewer 모달을 연다.

- [ ] **Step 5: 커밋한다.**

```bash
git add app/services/company_disclosure_events.py app/services/company_affiliate.py app/static/profile-page-5.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "feat: add disclosure event timeline"
```

### Task 3: 주가 차트 공시 마커 추가

**Files:**

- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 차트 마커 매핑 테스트를 추가한다.**

검증할 정책:

- 공시일과 같은 거래일 포인트가 있으면 해당 포인트에 매핑한다.
- 공시일이 비거래일이면 다음 거래일 포인트에 매핑한다.
- 차트 범위 밖 공시는 마커에서 제외한다.

- [ ] **Step 2: 프론트엔드에 날짜 매핑 함수를 추가한다.**

권장 함수:

```javascript
function mapDisclosureEventsToPricePoints(events, pricePoints) {
  return events
    .map((event) => {
      const point = findSameOrNextTradingPoint(event.date, pricePoints);
      if (!point) return null;
      return { ...event, x: point.x, y: point.y, price: point.price };
    })
    .filter(Boolean);
}
```

- [ ] **Step 3: 마커 UI를 추가한다.**

표시 정책:

- 모든 공시가 아니라 `periodic`, `ownership`, `capital`, `dividend`, `audit`만 기본 표시한다.
- 마커 tooltip은 모바일에서 차트 영역을 벗어나지 않도록 좌우 위치를 보정한다.
- 마커 클릭 시 공시 viewer 모달을 연다.

- [ ] **Step 4: 커밋한다.**

```bash
git add app/static/profile-page-5.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "feat: show disclosure markers on stock chart"
```

### Task 4: 규칙 기반 위험 신호 카드 추가

**Files:**

- Modify: `app/services/company_insights.py`
- Modify: `app/services/company_affiliate.py`
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 단일 보고서 기준 위험 신호 테스트를 추가한다.**

검증할 신호:

- 부채비율이 200% 이상이면 `debt_high`
- 영업이익률이 0% 미만이면 `operating_margin_negative`
- ROE가 0% 미만이면 `roe_negative`
- 감사의견이 `적정`이 아니면 `audit_opinion_warning`
- 계열회사와 종속기업 합계가 50개 이상이면 `complex_group_structure`

- [ ] **Step 2: 히스토리 필요 신호는 계산하지 않고 `requires_history`로 분류한다.**

대상:

- `debt_ratio_surge`
- `operating_loss_turnaround`
- `net_loss_turnaround`
- `major_shareholder_changed`
- `executive_changed`
- `dividend_cut_or_stopped`
- `affiliate_count_changed`

- [ ] **Step 3: 위험 신호 카드를 렌더링한다.**

UI 정책:

- 현재 계산 가능한 신호만 카드에 표시한다.
- 히스토리가 필요한 신호는 카드 하단 설명에 `과거 보고서 비교가 쌓이면 표시됩니다`로 안내한다.

- [ ] **Step 4: 커밋한다.**

```bash
git add app/services/company_insights.py app/services/company_affiliate.py app/static/profile-page-5.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "feat: add rule based company risk signals"
```

### Task 5: 비교 페이지 종합 요약 추가

**Files:**

- Modify: `app/static/compare-page.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 비교 요약 렌더링 테스트를 추가한다.**

검증할 항목:

- 자산/매출/영업이익이 큰 기업을 규모 우위로 표시한다.
- 부채비율이 낮은 기업을 안정성 우위로 표시한다.
- 영업이익률/ROE가 높은 기업을 수익성 우위로 표시한다.
- 주가 데이터가 없는 기업이 있으면 주가 흐름 요약을 생략한다.

- [ ] **Step 2: 비교 요약 계산 함수를 추가한다.**

권장 함수:

```javascript
function buildCompareSummary(companies, rows) {
  return {
    scale: summarizeScale(companies, rows),
    profitability: summarizeProfitability(companies, rows),
    stability: summarizeStability(companies, rows),
    stock: summarizeStockIfAvailable(companies),
  };
}
```

- [ ] **Step 3: 비교 페이지 상단에 요약 영역을 표시한다.**

UI 정책:

- 표보다 위, 선택 기업 컨트롤 아래에 둔다.
- 각 요약에는 근거 수치를 함께 표시한다.
- 모바일에서는 1열 카드가 아니라 조밀한 리스트 형태로 표시한다.

- [ ] **Step 4: 커밋한다.**

```bash
git add app/static/compare-page.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "feat: summarize company comparisons"
```

### Task 6: 관계회사 UX 고도화

**Files:**

- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_company_affiliate_api.py`

- [ ] **Step 1: 계열회사/종속기업 설명 툴팁 테스트를 추가한다.**

툴팁 문구:

- 계열회사: `같은 기업집단에 속한 회사입니다. 지분으로 직접 지배하지 않아도 같은 그룹으로 묶일 수 있습니다.`
- 종속기업: `현재 회사가 지배력을 가진 회사입니다. 보통 연결재무제표 작성 대상입니다.`

- [ ] **Step 2: 관계회사 목록에 필터를 추가한다.**

필터:

- 전체
- 상장 관계사
- 비상장 관계사
- 국내
- 해외

- [ ] **Step 3: 변화 추적은 후속 단계로 명시한다.**

UI에는 현재 수 변화 추적을 표시하지 않는다. 이 기능은 별도 `company_relationship_snapshots` 같은 히스토리 저장 구조가 생긴 뒤 구현한다.

- [ ] **Step 4: 커밋한다.**

```bash
git add app/static/profile-page-5.js app/static/styles.css tests/test_company_affiliate_api.py
git commit -m "feat: improve related company browsing"
```

---

## 5. 후속 확장 계획

### A. 히스토리 저장 기반 변화 탐지

필요한 저장 정책:

- DART 주요주주/임원/배당/재무비율 조회 결과를 보고서 기준으로 보존한다.
- 금융위원회 계열회사/종속기업 목록을 조회일 기준 스냅샷으로 보존한다.
- 같은 보고서 또는 같은 조회일 데이터는 중복 저장하지 않는다.

가능해지는 기능:

- 최대주주 변동
- 임원 변동
- 배당 중단 또는 급감
- 관계회사 수 변화
- 부채비율/영업이익률 급변 탐지

### B. 공시 원문 파싱과 LLM 요약

필요한 선행 작업:

- DART viewer URL에서 원문 HTML 또는 문서 본문을 가져온다.
- 본문에서 표, 제목, 주석, 본문 텍스트를 구분한다.
- 원문 저장/캐시 정책을 만든다.
- LLM 입력 길이 제한에 맞게 섹션별 요약 파이프라인을 둔다.

가능해지는 기능:

- 정기보고서 핵심 요약
- 사업 위험 요약
- 재무 주석 요약
- 최대주주/임원 변경 의미 요약

### C. 뉴스/이슈 요약

필요한 선행 작업:

- SearchAPI 일반 검색 또는 뉴스 검색 engine을 별도 연동한다.
- 중복 기사 제거 기준을 둔다.
- 날짜, 언론사, 제목, URL, 요약문을 저장한다.
- LLM 요약은 같은 이슈 묶음 단위로 수행한다.

가능해지는 기능:

- 최근 뉴스 요약
- 긍정/부정 이슈 분리
- 공시와 뉴스 시점 비교
- 주가 급변일 주변 뉴스 확인

### D. 밸류에이션/동종업계 자동 비교

필요한 데이터:

- KRX 상장사 전체 목록
- 업종 코드
- 시가총액
- 상장주식수
- EPS
- BPS
- PER
- PBR

권장 방향:

- 자동 동종업계 비교보다 사용자가 직접 기업을 선택하는 비교를 먼저 고도화한다.
- 자동 peer 추천은 KRX/업종/시가총액 데이터가 확보된 뒤 별도 기능으로 만든다.

---

## 6. 검증 체크리스트

- [ ] 비상장 기업 프로필에서 전체 실패 화면이 나오지 않는다.
- [ ] 상장 기업은 기존 주가/재무/공시/관계회사 기능이 유지된다.
- [ ] 공시 이벤트 분류가 한국어 공시 제목에서 안정적으로 동작한다.
- [ ] 주가 차트 마커 tooltip이 모바일에서 잘리지 않는다.
- [ ] 위험 신호는 계산 근거가 있는 경우에만 표시된다.
- [ ] 비교 페이지는 2개 이상 기업에서 모바일 가로 스크롤이 깨지지 않는다.
- [ ] 관계회사 툴팁 클릭이 모달 열기와 충돌하지 않는다.
- [ ] `uv run pytest tests/test_company_affiliate_api.py -q`가 통과한다.

---

## 7. 구현 순서 요약

1. 부분 데이터 프로필 정책 정리
2. 공시 이벤트 타임라인
3. 주가 차트 공시 마커
4. 규칙 기반 위험 신호 카드
5. 비교 페이지 종합 요약
6. 관계회사 UX 고도화
7. 히스토리 저장 기반 변화 탐지
8. 공시 원문 파싱과 LLM 요약
9. 뉴스/이슈 요약
10. 밸류에이션/동종업계 자동 비교

단기적으로는 LLM 없이도 충분히 유용한 기능을 만들 수 있다. 먼저 부분 데이터 표시와 공시 이벤트 구조화를 끝내면, 이후 주가 마커와 위험 신호 카드가 훨씬 안정적으로 붙는다.
