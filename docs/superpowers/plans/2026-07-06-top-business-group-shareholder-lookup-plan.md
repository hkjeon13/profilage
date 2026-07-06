# 상위 기업집단 주주 역조회 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공정위 기준 상위 20개 기업집단 corpus를 동기화하고, 최대주주 클릭 시 현재 회사 주주 상세 및 corpus 내 동일명/동일법인 후보를 보여준다.

**Architecture:** 기존 `company_data_groups` 초기화 패턴에 정규화 테이블을 추가하고, `company_shareholders.py`에 FTC 동기화/주주 인덱싱/역조회 서비스를 둔다. API는 `/company/shareholders/search`, `/company/shareholders/sync_top_business_groups`를 추가하고, 프론트는 기존 최대주주 UI를 클릭 가능한 상세 패널로 확장한다.

**Tech Stack:** FastAPI, httpx, psycopg 3, existing static JS/CSS, pytest.

---

### Task 1: 저장소와 설정

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/services/company_store.py`
- Test: `tests/test_company_affiliate_api.py`

- [ ] `BusinessGroupApiSettings`를 추가하고 `BUSINESS_GROUP_SERVICE_KEY` 또는 `EGROUP_SERVICE_KEY`를 읽는다.
- [ ] `PostgresDataGroupStore.initialize()`에 `business_groups`, `business_group_companies`, `shareholder_entities`, `shareholder_holdings`, `shareholder_source_payloads`, `shareholder_sync_runs` 테이블을 추가한다.
- [ ] service key가 없으면 sync API가 503으로 실패하고 기존 프로필 화면은 영향받지 않게 한다.

### Task 2: 주주 corpus 서비스

**Files:**
- Create: `app/services/company_shareholders.py`
- Test: `tests/test_company_affiliate_api.py`

- [ ] OpenAPI 응답에서 item list를 안정적으로 추출하는 helper를 만든다.
- [ ] 기업집단 row와 소속회사 row를 정규화한다.
- [ ] 상위 20개 선택은 공식 순위, 자산총액 순으로 처리하고 둘 다 없으면 명확히 실패한다.
- [ ] DART 최대주주/임원 payload를 주주 엔티티와 보유 내역으로 정규화한다.
- [ ] 이름만 같은 개인은 `low`, 법인등록번호/DART corp code/종목코드가 있으면 `high` confidence로 반환한다.

### Task 3: API

**Files:**
- Modify: `app/api/company.py`
- Test: `tests/test_company_affiliate_api.py`

- [ ] `GET /company/shareholders/search`를 추가한다.
- [ ] `POST /company/shareholders/sync_top_business_groups`를 추가한다.
- [ ] `POST /company/shareholders/index_dart_holdings`를 추가한다.
- [ ] DB가 없거나 corpus가 비어 있을 때 빈 matches를 반환한다.

### Task 4: 프로필 UI

**Files:**
- Modify: `app/static/profile-page-5.js`
- Modify: `app/static/styles.css`
- Modify: `app/static/profile.html`

- [ ] 최대주주 row를 버튼처럼 클릭 가능하게 만든다.
- [ ] 클릭 시 현재 회사 주주 정보와 역조회 후보를 표시하는 패널을 연다.
- [ ] low confidence 후보에는 동명이인 가능성 문구를 표시한다.
- [ ] 법인 주주는 “법인 주주” 문구로 표시한다.

### Task 5: 검증, 커밋, 배포

**Files:**
- Verify all touched files.

- [ ] `pytest tests/test_company_affiliate_api.py -q`를 실행한다.
- [ ] `git diff --check`를 실행한다.
- [ ] 변경사항을 커밋하고 `origin/main`에 push한다.
- [ ] `ssh ai-assistant`의 `/data/psyche/Projects/profilage`에서 pull 및 `docker compose up -d --build api`를 실행한다.
- [ ] 공개 profile 페이지에서 화면이 정상 로딩되는지 확인한다.
