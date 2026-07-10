# Profilage 보안 개선 계획

작성일: 2026-07-10  
대상: `profile.fin-ally.net` 배포본 및 `/Users/psyche/PycharmProjects/profilage`

## 요약

현재 즉시 확인된 핵심 위험은 앱 로직의 원격 코드 실행이나 SQL injection보다, 운영 표면이 과하게 공개되어 있다는 점이다. 우선순위는 다음 순서로 둔다.

1. GitHub 토큰 노출 제거 및 회전
2. 관리자성/비용성 API 인증 적용
3. 프로덕션 API 문서와 OpenAPI 스키마 비공개
4. CSP 및 기본 보안 헤더 강화
5. 외부 XML 파서 hardening
6. Docker 실행 권한과 포트 노출 축소

## 1. GitHub 토큰 노출 제거

### 문제

로컬과 원격 서버의 git origin URL이 `https://user:token@github.com/...` 형태로 설정되어 있다. 이 토큰은 쉘 히스토리, 프로세스 출력, 로그, 스크린샷 등에 노출될 수 있다.

### 조치

- GitHub에서 해당 토큰을 즉시 revoke 또는 rotate한다.
- 로컬과 원격 서버 모두 origin을 SSH URL로 교체한다.

```bash
git remote set-url origin git@github.com:hkjeon13/profilage.git
ssh ai-assistant 'cd /data/psyche/Projects/profilage && git remote set-url origin git@github.com:hkjeon13/profilage.git'
```

### 검증

```bash
git remote get-url origin
ssh ai-assistant 'cd /data/psyche/Projects/profilage && git remote get-url origin'
```

출력에 토큰이나 비밀번호가 없어야 한다.

## 2. 인증 없는 비용/관리 API 보호

### 문제

다음 API는 인증 없이 공개되어 있다.

- `GET /company/get_dart_disclosure_summary`
- `GET /company/get_company_profile_summary`
- `POST /company/shareholders/sync_top_business_groups`
- `POST /company/shareholders/index_dart_holdings`
- 동일한 `/api/company/...` prefix 경로

공시/프로필 요약 API는 OpenAI 호출 비용을 유발할 수 있고, 주주 동기화/색인 API는 DB write와 외부 API 호출을 수행한다.

### 조치

- 관리자성 POST API는 필수 인증으로 전환한다.
- 요약 API는 최소한 rate limit을 적용하고, 가능하면 세션/서버 측 allowlist 또는 API key를 둔다.
- 캐시된 요약 조회와 신규 생성 요청을 분리한다.
  - 예: `GET /summary/{receipt_no}`는 공개 가능
  - `POST /summary/generate`는 인증/레이트리밋 필수
- Cloudflare WAF 또는 reverse proxy에서 `/company/shareholders/*` POST를 제한한다.

### 구현 후보

- 기존 `has_valid_full_response_jwt()`와 별개로 `require_admin_jwt()`를 만든다.
- `PROFILAGE_ADMIN_JWT_SECRET` 또는 `PROFILAGE_ADMIN_API_KEY`를 사용한다.
- 실패 시 `401`, 권한 부족 시 `403`을 반환한다.

### 검증

```bash
curl -i -X POST 'https://profile.fin-ally.net/company/shareholders/sync_top_business_groups'
```

인증 없이 `401` 또는 `403`이어야 한다.

## 3. 프로덕션 API 문서 비공개

### 문제

프로덕션에서 `/docs`와 `/openapi.json`이 `200`으로 노출된다. 내부성 POST API와 전체 파라미터가 공개된다.

### 조치

- 프로덕션 환경에서는 FastAPI docs를 끈다.

```python
app = FastAPI(
    title="Profilage API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
```

- 개발 환경에서만 열고 싶다면 `APP_ENV` 또는 `ENABLE_API_DOCS`로 분기한다.

### 검증

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://profile.fin-ally.net/docs
curl -s -o /dev/null -w '%{http_code}\n' https://profile.fin-ally.net/openapi.json
```

프로덕션에서는 `404`가 나와야 한다.

## 4. CSP 및 보안 헤더 강화

### 문제

현재 CSP가 지나치게 완화되어 있다.

```text
default-src * 'unsafe-inline' 'unsafe-eval'
```

또한 다음 헤더가 누락되어 있다.

- `Strict-Transport-Security`
- `X-Content-Type-Options`
- `X-Frame-Options` 또는 CSP `frame-ancestors`
- `Referrer-Policy`
- `Permissions-Policy`

### 조치

- 앱 또는 reverse proxy에서 기본 보안 헤더를 추가한다.
- CSP는 실제 사용 도메인만 허용하도록 줄인다.
- 가능하면 inline script/style을 제거하고 nonce 기반 CSP로 전환한다.

### 1차 권장 헤더

```text
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: blob:; connect-src 'self' https://profile.fin-ally.net; frame-ancestors 'none'; base-uri 'self'; object-src 'none'
```

현재 프론트가 inline script/style에 의존할 수 있으므로, CSP는 단계적으로 조인다.

### 검증

```bash
curl -sS -D - -o /dev/null https://profile.fin-ally.net/ | grep -Ei 'content-security-policy|strict-transport-security|x-content-type-options|referrer-policy|permissions-policy'
```

## 5. 외부 XML 파싱 hardening

### 문제

외부 API 응답 XML을 `xml.etree.ElementTree.fromstring()`으로 파싱한다.

- `app/services/company_dart.py`
- `app/services/company_shareholders.py`

### 조치

- `defusedxml.ElementTree`로 교체한다.
- DART zip 응답은 압축 해제 전후 크기 제한을 둔다.
- XML/ZIP 파싱 실패는 내부 예외를 노출하지 않고 `502`로 표준화한다.

### 구현 후보

```python
from defusedxml import ElementTree
```

`pyproject.toml`과 Docker 설치 의존성에 `defusedxml`을 추가한다.

### 검증

```bash
python3 -m bandit -r app -q
pytest
```

XML 관련 Bandit 경고가 사라져야 한다.

## 6. Docker 실행 권한 및 포트 노출 축소

### 문제

API 컨테이너가 root 사용자로 실행되고, root filesystem이 writable이다. compose는 API를 `0.0.0.0:18000`에 bind한다.

현재 외부에서 `profile.fin-ally.net:18000` 직접 접근은 timeout이지만, 방화벽/네트워크 설정 변경 시 reverse proxy를 우회할 수 있다.

### 조치

- Dockerfile에 non-root user를 추가한다.
- compose에 `read_only: true`, `tmpfs`, `security_opt`, `cap_drop`을 검토한다.
- API 포트는 reverse proxy가 같은 호스트에 있다면 `127.0.0.1:${API_PORT:-18000}:8000`으로 제한한다.

### 구현 후보

```yaml
ports:
  - "127.0.0.1:${API_PORT:-18000}:8000"
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
```

### 검증

```bash
ssh ai-assistant 'cd /data/psyche/Projects/profilage && docker compose ps'
curl --max-time 4 -I http://profile.fin-ally.net:18000/ || true
```

외부 직접 접근은 계속 실패해야 한다.

## 7. 추가 권장 사항

- `/company/*` 조회성 API에도 IP 기반 rate limit을 둔다.
- OpenAI 요약 요청에는 일별/분당 쿼터와 사용자 단위 중복 방지를 둔다.
- 에러 응답에서 외부 API 원문 일부를 그대로 노출하는 부분을 줄인다.
- `viewer_url`은 현재 fetch에 쓰이지 않으므로 API 파라미터에서 제거하거나 optional로 바꾼다.
- 배포 파이프라인에 `bandit`, `pip-audit`, `pytest`를 최소 게이트로 추가한다.

## 권장 작업 순서

### Phase 0: 즉시 조치

- GitHub 토큰 rotate
- 로컬/원격 git remote를 SSH URL로 변경

### Phase 1: 공개 표면 축소

- 관리자 POST API 인증 적용
- `/docs`, `/openapi.json` 프로덕션 비공개
- 요약 생성 API rate limit 적용

### Phase 2: 브라우저 방어선 강화

- 보안 헤더 추가
- CSP를 현재 프론트 호환 범위에서 1차 강화
- inline script/style 제거 계획 수립

### Phase 3: 파서/컨테이너 hardening

- `defusedxml` 적용
- ZIP/XML 크기 제한
- non-root Docker 실행
- host port bind를 loopback으로 제한

## 완료 기준

- 인증 없는 관리자성 POST 요청이 실패한다.
- 프로덕션 `/docs`, `/openapi.json`이 비공개다.
- 공개 응답에 기본 보안 헤더가 포함된다.
- `bandit -r app -q`에서 XML 파싱 경고가 제거된다.
- git remote URL에 토큰이 없다.
- 원격 배포 후 `profile.fin-ally.net` 정상 동작이 확인된다.
