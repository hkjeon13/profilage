# Profilage Browser Companion

Chrome의 `확장 프로그램 관리 → 개발자 모드 → 압축해제된 확장 프로그램 로드`에서 이 디렉터리를 선택한다.

서버가 발급한 5분짜리 intent ID와 capture token을 입력하고, 현재 공개 페이지에서 사용자가 직접 선택한 텍스트만 검토 후 전송한다. 쿠키, 로그인 정보, 전체 DOM, 스크린샷은 수집하지 않는다. LinkedIn·Meta·나무위키는 서버 정책에서 거부된다. 일반 도메인은 `PERSON_BROWSER_CAPTURE_ALLOWED_DOMAINS`에 사전 승인된 경우에만 사용할 수 있다.
