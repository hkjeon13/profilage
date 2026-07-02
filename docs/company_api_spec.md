# Company API Specification

## Overview

Profilage의 `/company` API는 기업 검색을 위해 공공데이터포털 금융위원회 OpenAPI와 SearchAPI Google Finance를 내부 endpoint로 감싼 것입니다.

- Local base URL: `http://127.0.0.1:8000`
- Router prefix: `/company`
- OpenAPI key env: `OPEN_API_DECODING_KEY` 우선, 없으면 `OPEN_API_ENCODING_KEY`
- SearchAPI key env: `SEARCHAPI_API_KEY`
- Response policy: 외부 API의 JSON 응답을 가능한 그대로 반환

## Current API List

| API | Source | Main Search Keys | Role |
| --- | --- | --- | --- |
| `GET /company/get_affiliate` | 금융위원회_기업기본정보 `getAffiliate_V2` | `company_name`, `corporate_registration_number` | 계열회사 조회 |
| `GET /company/get_cons_subs_comp` | 금융위원회_기업기본정보 `getConsSubsComp_V2` | `subsidiary_name`, `corporate_registration_number` | 연결대상 종속기업 조회 |
| `GET /company/get_corp_outline` | 금융위원회_기업기본정보 `getCorpOutline_V2` | `company_name`, `corporate_registration_number` | 기업개요 조회 |
| `GET /company/get_krx_listed_item` | 금융위원회_KRX상장종목정보 `getItemInfo` | `corporate_registration_number`, `company_name`, `item_name`, `isin_code` | KRX 상장종목정보 조회 |
| `GET /company/get_company_info` | Internal aggregate | `corporate_registration_number` | 기업개요, 상장종목, 계열회사, 종속기업 통합 조회 |
| `GET /company/get_stock_price` | SearchAPI Google Finance `google_finance` | `q`, `stock_code`, `exchange` | Google Finance 주가 정보 조회 |

## Common Response Shape

공공데이터 원천 API는 대체로 아래 구조를 반환합니다.

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

### `GET /company/get_affiliate`

기업명 또는 법인등록번호 기준으로 계열회사 정보를 조회합니다.

Source:

```text
GET https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getAffiliate_V2
```

| Name | Required | External Param | Description |
| --- | --- | --- | --- |
| `company_name` | conditional | `afilCmpyNm` | 계열회사명 |
| `corporate_registration_number` | conditional | `crno` | 법인등록번호 |
| `base_date` | no | `basDt` | 기준일자, `YYYYMMDD` |
| `page` | no | `pageNo` | 페이지 번호, default `1` |
| `per_page` | no | `numOfRows` | 페이지당 결과 수, default `10`, max `1000` |

`company_name` 또는 `corporate_registration_number` 중 하나는 필수입니다.

Response item fields:

| Field | Meaning |
| --- | --- |
| `basDt` | 기준일자 |
| `crno` | 조회 기준 법인등록번호 |
| `afilCmpyNm` | 계열회사명 |
| `afilCmpyCrno` | 계열회사 법인등록번호 |
| `lstgYn` | 상장 여부 |

Measured example:

```http
GET /company/get_affiliate?company_name=삼성전자&per_page=2
```

```json
{
  "body": {
    "items": {
      "item": [
        {
          "basDt": "20200509",
          "crno": "1101110005953",
          "afilCmpyNm": "삼성전자(주)",
          "afilCmpyCrno": "1301110006246",
          "lstgYn": ""
        },
        {
          "basDt": "20200509",
          "crno": "1101110015762",
          "afilCmpyNm": "삼성전자(주)",
          "afilCmpyCrno": "1301110006246",
          "lstgYn": ""
        }
      ]
    },
    "numOfRows": 2,
    "pageNo": 1,
    "totalCount": 13455
  },
  "header": {
    "resultCode": "00",
    "resultMsg": "NORMAL SERVICE."
  }
}
```

## 2. 연결대상종속기업조회

### `GET /company/get_cons_subs_comp`

법인등록번호 또는 종속기업명 기준으로 연결대상 종속기업 정보를 조회합니다.

Source:

```text
GET https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getConsSubsComp_V2
```

| Name | Required | External Param | Description |
| --- | --- | --- | --- |
| `subsidiary_name` | conditional | `sbrdEnpNm` | 종속기업명 |
| `corporate_registration_number` | conditional | `crno` | 법인등록번호 |
| `base_date` | no | `basDt` | 기준일자, `YYYYMMDD` |
| `page` | no | `pageNo` | 페이지 번호, default `1` |
| `per_page` | no | `numOfRows` | 페이지당 결과 수, default `10`, max `1000` |

`subsidiary_name` 또는 `corporate_registration_number` 중 하나는 필수입니다.

Response item fields:

| Field | Meaning |
| --- | --- |
| `basDt` | 기준일자 |
| `crno` | 법인등록번호 |
| `sbrdEnpNm` | 종속기업명 |
| `sbrdEnpEstbDt` | 종속기업 설립일자 |
| `sbrdEnpAdr` / `sbrdEnpadr` | 종속기업 주소 |
| `sbrdEnpMainBizCtt` | 종속기업 주요 사업 내용 |
| `sbrdEnpLtstEbzyrTastAmt` | 최근 사업연도 총자산 금액 |
| `dntRltBsisCtt` | 지배 관계 근거 내용 |
| `mainSbrdEnpYnCtt` | 주요 종속기업 여부 내용 |

## 3. 기업개요조회

### `GET /company/get_corp_outline`

기업명 또는 법인등록번호 기준으로 기업 개요 정보를 조회합니다.

Source:

```text
GET https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2
```

| Name | Required | External Param | Description |
| --- | --- | --- | --- |
| `company_name` | conditional | `corpNm` | 법인명 |
| `corporate_registration_number` | conditional | `crno` | 법인등록번호 |
| `page` | no | `pageNo` | 페이지 번호, default `1` |
| `per_page` | no | `numOfRows` | 페이지당 결과 수, default `10`, max `1000` |

`company_name` 또는 `corporate_registration_number` 중 하나는 필수입니다.

Main response fields include `crno`, `corpNm`, `corpEnsnNm`, `enpRprFnm`, `bzno`, `enpBsadr`, `enpHmpgUrl`, `enpTlno`, `enpEstbDt`, `enpEmpeCnt`, `fssCorpUnqNo`, `fstOpegDt`, `lastOpegDt`.

Measured Samsung Electronics item:

```json
{
  "crno": "1301110006246",
  "corpNm": "삼성전자(주)",
  "corpEnsnNm": "SAMSUNG ELECTRONICS CO,.LTD",
  "enpPbanCmpyNm": "삼성전자",
  "enpRprFnm": "전영현, 노태문",
  "corpRegMrktDcd": "P",
  "corpRegMrktDcdNm": "유가",
  "bzno": "1248100998",
  "enpBsadr": "경기도 수원시 영통구  삼성로 129 (매탄동)",
  "enpHmpgUrl": "www.samsung.com/sec",
  "enpTlno": "02-2255-0114",
  "enpEstbDt": "19690113",
  "enpEmpeCnt": "128881",
  "fssCorpUnqNo": "00126380"
}
```

## 4. KRX 상장종목정보

### `GET /company/get_krx_listed_item`

법인등록번호, 법인명, 종목명, ISIN 코드 기준으로 KRX 상장종목 정보를 조회합니다.

Source:

```text
GET https://apis.data.go.kr/1160100/service/GetKrxListedInfoService/getItemInfo
```

| Name | Required | External Param | Description |
| --- | --- | --- | --- |
| `corporate_registration_number` | conditional | `crno` | 법인등록번호 |
| `company_name` | conditional | `corpNm` | 법인명 |
| `item_name` | conditional | `itmsNm` | 종목명 |
| `isin_code` | conditional | `isinCd` | ISIN 코드 |
| `base_date` | no | `basDt` | 기준일자, `YYYYMMDD` |
| `page` | no | `pageNo` | 페이지 번호, default `1` |
| `per_page` | no | `numOfRows` | 페이지당 결과 수, default `10`, max `1000` |

`corporate_registration_number`, `company_name`, `item_name`, `isin_code` 중 하나는 필수입니다.

| Field | Meaning |
| --- | --- |
| `basDt` | 기준일자 |
| `srtnCd` | 단축코드 |
| `isinCd` | 국제증권식별번호 |
| `mrktCtg` | 시장구분 |
| `itmsNm` | 종목명 |
| `crno` | 법인등록번호 |
| `corpNm` | 법인명 |

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

## 5. 통합 기업정보

### `GET /company/get_company_info`

법인등록번호 기준으로 기업개요, KRX 상장종목정보, 계열회사, 연결대상 종속기업 정보를 함께 조회합니다.

| Name | Required | Description |
| --- | --- | --- |
| `corporate_registration_number` | yes | 법인등록번호 |
| `page` | no | 각 원천 API에 전달할 페이지 번호, default `1` |
| `per_page` | no | 각 원천 API에 전달할 결과 수, default `10`, max `1000` |

Response keys:

| Key | Description |
| --- | --- |
| `corp_outline` | 기업개요 |
| `krx_listed_item` | KRX 상장종목정보 |
| `affiliate` | 계열회사 |
| `cons_subs_comp` | 연결대상 종속기업 |

## 6. Google Finance 주가정보

### `GET /company/get_stock_price`

SearchAPI의 Google Finance API를 통해 주가 정보를 조회합니다.

Source:

```text
GET https://www.searchapi.io/api/v1/search?engine=google_finance
```

| Name | Required | External Param | Description |
| --- | --- | --- | --- |
| `q` | conditional | `q` | Google Finance query. 예: `005930:KRX`, `TSLA:NASDAQ` |
| `stock_code` | conditional | `q` 구성값 | 종목 코드 |
| `exchange` | no | `q` 구성값 | 거래소 코드. 예: `KRX`, `NASDAQ` |
| `language` | no | `hl` | Google Finance 언어. 예: `ko`, `en` |
| `window` | no | `window` | 차트 기간. 예: `1D`, `5D`, `1M`, `6M`, `YTD`, `1Y`, `5Y`, `MAX` |

`q` 또는 `stock_code` 중 하나는 필수입니다. `stock_code=005930&exchange=KRX`를 넘기면 내부에서 `q=005930:KRX`로 변환합니다.

Measured example:

```http
GET /company/get_stock_price?stock_code=005930&exchange=KRX&language=ko&window=1M
```

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

## Error Responses

필수 검색 조건이 없으면 `400 Bad Request`를 반환합니다.

외부 OpenAPI 또는 SearchAPI 호출 실패/비정상 응답은 `502 Bad Gateway`로 변환합니다.
