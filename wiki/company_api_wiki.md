# Company API Wiki

## Purpose

Profilage의 기업 검색 API는 공공데이터포털 금융위원회 OpenAPI와 SearchAPI Google Finance를 내부 서비스용 endpoint로 감싼 것입니다.

`corporate_registration_number`인 법인등록번호를 공통 키로 사용하면 기업개요, KRX 상장종목정보, 계열회사, 연결대상 종속기업 정보를 하나의 `company_info`로 구성할 수 있습니다.

## Environment

| Item | Value |
| --- | --- |
| Local base URL | `http://127.0.0.1:8000` |
| Router prefix | `/company` |
| OpenAPI service key | `.env`의 `OPEN_API_DECODING_KEY` 우선, 없으면 `OPEN_API_ENCODING_KEY` |
| SearchAPI key | `.env`의 `SEARCHAPI_API_KEY` |
| Response policy | 원천 API 응답 객체를 가능한 그대로 반환 |

## Current API List

| API | Source | Search Keys | Role |
| --- | --- | --- | --- |
| `GET /company/get_affiliate` | 금융위원회_기업기본정보 `getAffiliate_V2` | `company_name`, `corporate_registration_number` | 계열회사 조회 |
| `GET /company/get_cons_subs_comp` | 금융위원회_기업기본정보 `getConsSubsComp_V2` | `subsidiary_name`, `corporate_registration_number` | 연결대상 종속기업 조회 |
| `GET /company/get_corp_outline` | 금융위원회_기업기본정보 `getCorpOutline_V2` | `company_name`, `corporate_registration_number` | 기업개요 조회 |
| `GET /company/get_krx_listed_item` | 금융위원회_KRX상장종목정보 `getItemInfo` | `corporate_registration_number`, `company_name`, `item_name`, `isin_code` | KRX 상장종목정보 조회 |
| `GET /company/get_company_info` | Internal aggregate | `corporate_registration_number` | 기업개요, 상장종목, 계열회사, 종속기업 통합 조회 |
| `GET /company/get_stock_price` | SearchAPI Google Finance `google_finance` | `q`, `stock_code`, `exchange` | Google Finance 주가 정보 조회 |

## Common Response Shape

공공데이터 원천 API는 대체로 아래 구조입니다.

```json
{
  "header": {
    "resultCode": "00",
    "resultMsg": "NORMAL SERVICE."
  },
  "body": {
    "numOfRows": 10,
    "pageNo": 1,
    "totalCount": 123,
    "items": {
      "item": []
    }
  }
}
```

`items.item`은 결과 수에 따라 객체 하나 또는 배열로 내려올 수 있습니다.

## 1. 계열회사조회

```http
GET /company/get_affiliate
```

기업명 또는 법인등록번호 기준으로 계열회사 정보를 조회합니다.

| Query | External Param | Description |
| --- | --- | --- |
| `company_name` | `afilCmpyNm` | 계열회사명 |
| `corporate_registration_number` | `crno` | 법인등록번호 |
| `base_date` | `basDt` | 기준일자, `YYYYMMDD` |
| `page` | `pageNo` | 페이지 번호 |
| `per_page` | `numOfRows` | 페이지당 결과 수 |

Response fields: `basDt`, `crno`, `afilCmpyNm`, `afilCmpyCrno`, `lstgYn`.

## 2. 연결대상 종속기업조회

```http
GET /company/get_cons_subs_comp
```

법인등록번호 또는 종속기업명 기준으로 연결대상 종속기업 정보를 조회합니다.

| Query | External Param | Description |
| --- | --- | --- |
| `subsidiary_name` | `sbrdEnpNm` | 종속기업명 |
| `corporate_registration_number` | `crno` | 법인등록번호 |
| `base_date` | `basDt` | 기준일자, `YYYYMMDD` |
| `page` | `pageNo` | 페이지 번호 |
| `per_page` | `numOfRows` | 페이지당 결과 수 |

Response fields: `basDt`, `crno`, `sbrdEnpNm`, `sbrdEnpEstbDt`, `sbrdEnpAdr` 또는 `sbrdEnpadr`, `sbrdEnpMainBizCtt`, `sbrdEnpLtstEbzyrTastAmt`, `dntRltBsisCtt`, `mainSbrdEnpYnCtt`.

## 3. 기업개요조회

```http
GET /company/get_corp_outline
```

기업명 또는 법인등록번호 기준으로 기업 개요 정보를 조회합니다.

| Query | External Param | Description |
| --- | --- | --- |
| `company_name` | `corpNm` | 법인명 |
| `corporate_registration_number` | `crno` | 법인등록번호 |
| `page` | `pageNo` | 페이지 번호 |
| `per_page` | `numOfRows` | 페이지당 결과 수 |

Main response fields: `crno`, `corpNm`, `corpEnsnNm`, `enpRprFnm`, `bzno`, `enpBsadr`, `enpHmpgUrl`, `enpTlno`, `enpEstbDt`, `enpEmpeCnt`, `fssCorpUnqNo`.

Measured Samsung Electronics item:

```json
{
  "crno": "1301110006246",
  "corpNm": "삼성전자(주)",
  "corpEnsnNm": "SAMSUNG ELECTRONICS CO,.LTD",
  "enpPbanCmpyNm": "삼성전자",
  "enpRprFnm": "전영현, 노태문",
  "bzno": "1248100998",
  "enpBsadr": "경기도 수원시 영통구  삼성로 129 (매탄동)",
  "enpTlno": "02-2255-0114",
  "enpEstbDt": "19690113",
  "enpEmpeCnt": "128881",
  "fssCorpUnqNo": "00126380"
}
```

## 4. KRX 상장종목정보

```http
GET /company/get_krx_listed_item
```

법인등록번호, 법인명, 종목명, ISIN 코드 기준으로 KRX 상장종목 정보를 조회합니다.

| Query | External Param | Description |
| --- | --- | --- |
| `corporate_registration_number` | `crno` | 법인등록번호 |
| `company_name` | `corpNm` | 법인명 |
| `item_name` | `itmsNm` | 종목명 |
| `isin_code` | `isinCd` | ISIN 코드 |
| `base_date` | `basDt` | 기준일자 |

### KRX Columns

| Field | Meaning |
| --- | --- |
| `basDt` | 기준일자. 해당 상장종목 정보가 집계된 날짜 |
| `srtnCd` | 단축코드. 한국거래소에서 쓰는 종목 단축 코드 |
| `isinCd` | ISIN 코드. 증권을 전 세계적으로 식별하는 12자리 국제증권식별번호 |
| `mrktCtg` | 시장구분. 해당 종목이 상장된 시장 |
| `itmsNm` | 종목명. 거래소에서 표시되는 종목 이름 |
| `crno` | 법인등록번호. 해당 상장종목 발행 법인의 법인등록번호 |
| `corpNm` | 법인명. 법인등록번호에 연결된 회사명 |

Measured example:

```json
{
  "basDt": "20260630",
  "srtnCd": "A005930",
  "isinCd": "KR7005930003",
  "mrktCtg": "KOSPI",
  "itmsNm": "삼성전자",
  "crno": "1301110006246",
  "corpNm": "삼성전자(주)"
}
```

이 한 줄은 “2026년 6월 30일 기준, 법인등록번호 `1301110006246`인 `삼성전자(주)`가 KOSPI에 `삼성전자`라는 종목명으로 상장되어 있고, 거래소 단축코드는 `A005930`, 국제증권식별번호는 `KR7005930003`이다”라는 뜻입니다.

## 5. 통합 기업정보

```http
GET /company/get_company_info
```

법인등록번호 기준으로 현재 연결된 기업 원천 API들을 함께 조회합니다.

| Response Key | Source Endpoint | Description |
| --- | --- | --- |
| `corp_outline` | `/company/get_corp_outline` | 기업개요 |
| `krx_listed_item` | `/company/get_krx_listed_item` | KRX 상장종목정보 |
| `affiliate` | `/company/get_affiliate` | 계열회사 |
| `cons_subs_comp` | `/company/get_cons_subs_comp` | 연결대상 종속기업 |
| `dart_corp_code` | `/company/get_dart_corp_code` | DART 고유번호 매핑. DART 키가 설정된 운영 환경에서 보강 |
| `dart_company` | `/company/get_dart_company` | DART 기업개황. DART 키가 설정된 운영 환경에서 보강 |
| `dart_disclosures` | `/company/get_dart_disclosures` | 최근 DART 공시 목록. DART 키가 설정된 운영 환경에서 보강 |
| `dart_financial_accounts` | `/company/get_dart_financial_accounts` | 최근 사업보고서 주요계정 재무정보. DART 키가 설정된 운영 환경에서 보강 |

Required query: `corporate_registration_number`.

## 6. Google Finance 주가정보

```http
GET /company/get_stock_price
```

SearchAPI의 Google Finance API를 통해 종목 요약 가격, 차트, 관련 뉴스, 재무 정보 등을 조회합니다.

| Query | External Param | Description |
| --- | --- | --- |
| `q` | `q` | Google Finance query. 예: `005930:KRX`, `TSLA:NASDAQ` |
| `stock_code` | `q` 구성값 | 종목 코드 |
| `exchange` | `q` 구성값 | 거래소 코드. 예: `KRX`, `NASDAQ` |
| `language` | `hl` | Google Finance 언어. 예: `ko`, `en` |
| `window` | `window` | 차트 기간. 예: `1D`, `5D`, `1M`, `6M`, `YTD`, `1Y`, `5Y`, `MAX` |

`q` 또는 `stock_code` 중 하나는 필수입니다. `stock_code=005930&exchange=KRX`를 넘기면 내부에서 `q=005930:KRX`로 변환합니다.

Measured example:

```json
{
  "search_parameters": {
    "engine": "google_finance",
    "q": "005930:KRX",
    "hl": "ko",
    "window": "1M"
  },
  "summary": {
    "title": "삼성전자",
    "stock": "005930",
    "exchange": "KRX",
    "price": 314500,
    "currency": "KRW",
    "date": "Jul 01, 06:18:49 PM UTC+09:00"
  }
}
```

## 7. DART 기업/공시/재무정보

금융감독원 OpenDART API를 통해 기업 고유번호, 기업개황, 공시 목록, 단일회사 주요계정 재무정보를 조회합니다.

### DART 고유번호 매핑

```http
GET /company/get_dart_corp_code
```

| Query | Description |
| --- | --- |
| `corporate_registration_number` | 법인등록번호. 종목코드 또는 회사명 후보가 여러 개일 때 기업개황의 `jurir_no`와 비교 |
| `stock_code` | 종목코드. `A005930` 또는 `005930` 모두 허용 |
| `company_name` | 회사명 |

`corporate_registration_number`, `stock_code`, `company_name` 중 하나는 필수입니다.

### DART 기업개황

```http
GET /company/get_dart_company?corp_code=00126380
```

`corp_code` 기준으로 회사명, 영문명, 법인등록번호, 사업자등록번호, 대표자, 업종, 주소 등을 조회합니다.

### DART 공시검색

```http
GET /company/get_dart_disclosures?corp_code=00126380&page=1&per_page=10
```

| Query | Description |
| --- | --- |
| `corp_code` | DART 고유번호 |
| `begin_date` | 시작일자 `YYYYMMDD` |
| `end_date` | 종료일자 `YYYYMMDD` |
| `disclosure_type` | 공시유형 |
| `disclosure_detail_type` | 공시상세유형 |
| `corporation_class` | 법인구분 |
| `page` | 페이지 번호 |
| `per_page` | 페이지 크기 |

각 공시 항목에는 DART 원문 조회용 `viewer_url`을 추가해 반환합니다.

### DART 주요계정 재무정보

```http
GET /company/get_dart_financial_accounts?corp_code=00126380&business_year=2025&report_code=11011&fs_division=CFS
```

| Query | Description |
| --- | --- |
| `corp_code` | DART 고유번호 |
| `business_year` | 사업연도 `YYYY` |
| `report_code` | 보고서 코드. `11011` 사업보고서, `11012` 반기보고서, `11013` 1분기보고서, `11014` 3분기보고서 |
| `fs_division` | `CFS` 연결재무제표, `OFS` 재무제표 |

## 8. 저장/갱신 정책

검색성 응답은 Valkey 캐시를 사용하고, 기업 상세 속성 그룹은 Postgres `company_data_groups`에 저장합니다.

| Group | TTL |
| --- | --- |
| `corp_outline` | 7일 |
| `krx_listed_item` | 1일 |
| `affiliate` | 7일 |
| `cons_subs_comp` | 7일 |
| `dart_company` | 7일 |
| `dart_disclosures` | 1시간 |
| `dart_financial_accounts` | 1일 |
| `stock_price` | KRX 장중 5분, 장외 1시간 |

## Error Responses

필수 검색 조건이 없으면 `400 Bad Request`를 반환합니다. 외부 OpenAPI 또는 SearchAPI 호출 실패/비정상 응답은 `502 Bad Gateway`로 변환합니다.
