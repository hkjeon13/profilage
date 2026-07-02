import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_root_serves_company_search_frontend():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Profilage" in response.text
    assert '<body class="is-idle google-like-home">' in response.text
    assert 'class="wordmark"' in response.text
    assert 'class="search-actions"' in response.text
    assert "/api/company/get_corp_outline" in response.text
    assert "/profile?crno=" in response.text


def test_profile_page_serves_company_profile_frontend():
    with TestClient(app) as client:
        response = client.get("/profile")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "기업 프로필" in response.text
    assert "/api/company/get_company_info" in response.text
    assert "/api/company/get_stock_price" in response.text


def test_company_api_is_available_under_api_prefix(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "numOfRows": "1",
                        "pageNo": "1",
                        "totalCount": "1",
                        "items": {
                            "item": {
                                "crno": "1301110006246",
                                "corpNm": "삼성전자(주)",
                            }
                        },
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        app.state.http_transport = transport
        response = client.get(
            "/api/company/get_corp_outline",
            params={"company_name": "삼성", "page": 1, "per_page": 1},
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["params"]["corpNm"] == "삼성"
    assert response.json()["body"]["items"]["item"]["corpNm"] == "삼성전자(주)"


def test_get_affiliate_maps_snake_case_query_to_open_api_parameters(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "numOfRows": "10",
                        "pageNo": "1",
                        "totalCount": "1",
                        "items": {
                            "item": {
                                "basDt": "20260701",
                                "crno": "1101111234567",
                                "afilCmpyNm": "테스트회사",
                                "afilCmpyCrno": "1101117654321",
                                "lstgYn": "Y",
                            }
                        },
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        app.state.http_transport = transport
        response = client.get(
            "/company/get_affiliate",
            params={
                "company_name": "테스트회사",
                "corporate_registration_number": "1101111234567",
                "base_date": "20260701",
                "page": 1,
                "per_page": 10,
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["url"].startswith(
        "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getAffiliate_V2"
    )
    assert captured_request["params"] == {
        "ServiceKey": "decoded-service-key",
        "pageNo": "1",
        "numOfRows": "10",
        "resultType": "json",
        "basDt": "20260701",
        "crno": "1101111234567",
        "afilCmpyNm": "테스트회사",
    }
    assert response.json()["body"]["items"]["item"]["afilCmpyNm"] == "테스트회사"


def test_get_affiliate_requires_company_name_or_corporate_registration_number():
    with TestClient(app) as client:
        response = client.get("/company/get_affiliate")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "company_name or corporate_registration_number is required"
    )


def test_get_cons_subs_comp_maps_snake_case_query_to_open_api_parameters(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "numOfRows": "10",
                        "pageNo": "1",
                        "totalCount": "1",
                        "items": {
                            "item": {
                                "sbrdEnpNm": "테스트종속기업",
                                "sbrdEnpEstbDt": "20200101",
                                "sbrdEnpAdr": "서울특별시",
                                "basDt": "20260701",
                                "crno": "1101111234567",
                            }
                        },
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        app.state.http_transport = transport
        response = client.get(
            "/company/get_cons_subs_comp",
            params={
                "subsidiary_name": "테스트종속기업",
                "corporate_registration_number": "1101111234567",
                "base_date": "20260701",
                "page": 1,
                "per_page": 10,
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["url"].startswith(
        "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getConsSubsComp_V2"
    )
    assert captured_request["params"] == {
        "ServiceKey": "decoded-service-key",
        "pageNo": "1",
        "numOfRows": "10",
        "resultType": "json",
        "basDt": "20260701",
        "crno": "1101111234567",
        "sbrdEnpNm": "테스트종속기업",
    }
    assert response.json()["body"]["items"]["item"]["sbrdEnpNm"] == "테스트종속기업"


def test_get_cons_subs_comp_requires_subsidiary_name_or_corporate_registration_number():
    with TestClient(app) as client:
        response = client.get("/company/get_cons_subs_comp")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "subsidiary_name or corporate_registration_number is required"
    )


def test_get_corp_outline_maps_snake_case_query_to_open_api_parameters(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "numOfRows": "10",
                        "pageNo": "1",
                        "totalCount": "1",
                        "items": {
                            "item": {
                                "crno": "1301110006246",
                                "corpNm": "삼성전자(주)",
                                "corpEnsnNm": "SAMSUNG ELECTRONICS CO.,LTD.",
                                "enpRprFnm": "테스트대표",
                                "bzno": "1234567890",
                            }
                        },
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        app.state.http_transport = transport
        response = client.get(
            "/company/get_corp_outline",
            params={
                "company_name": "삼성전자",
                "corporate_registration_number": "1301110006246",
                "page": 1,
                "per_page": 10,
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["url"].startswith(
        "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2"
    )
    assert captured_request["params"] == {
        "ServiceKey": "decoded-service-key",
        "pageNo": "1",
        "numOfRows": "10",
        "resultType": "json",
        "crno": "1301110006246",
        "corpNm": "삼성전자",
    }
    assert response.json()["body"]["items"]["item"]["corpNm"] == "삼성전자(주)"


def test_get_corp_outline_requires_company_name_or_corporate_registration_number():
    with TestClient(app) as client:
        response = client.get("/company/get_corp_outline")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "company_name or corporate_registration_number is required"
    )


def test_get_krx_listed_item_maps_snake_case_query_to_open_api_parameters(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "numOfRows": 10,
                        "pageNo": 1,
                        "totalCount": 1,
                        "items": {
                            "item": {
                                "basDt": "20260701",
                                "srtnCd": "005930",
                                "isinCd": "KR7005930003",
                                "mrktCtg": "KOSPI",
                                "itmsNm": "삼성전자",
                                "crno": "1301110006246",
                                "corpNm": "삼성전자(주)",
                            }
                        },
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        app.state.http_transport = transport
        response = client.get(
            "/company/get_krx_listed_item",
            params={
                "corporate_registration_number": "1301110006246",
                "company_name": "삼성전자(주)",
                "item_name": "삼성전자",
                "base_date": "20260701",
                "page": 1,
                "per_page": 10,
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["url"].startswith(
        "https://apis.data.go.kr/1160100/service/GetKrxListedInfoService/getItemInfo"
    )
    assert captured_request["params"] == {
        "serviceKey": "decoded-service-key",
        "pageNo": "1",
        "numOfRows": "10",
        "resultType": "json",
        "basDt": "20260701",
        "crno": "1301110006246",
        "corpNm": "삼성전자(주)",
        "itmsNm": "삼성전자",
    }
    assert response.json()["body"]["items"]["item"]["srtnCd"] == "005930"


def test_get_krx_listed_item_requires_a_search_condition():
    with TestClient(app) as client:
        response = client.get("/company/get_krx_listed_item")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "one of corporate_registration_number, company_name, item_name, or isin_code is required"
    )


def test_get_company_info_combines_company_sources_by_corporate_registration_number(
    monkeypatch,
):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_paths.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/getCorpOutline_V2"):
            body = {"items": {"item": {"crno": "1301110006246", "corpNm": "삼성전자(주)"}}}
        elif request.url.path.endswith("/getItemInfo"):
            body = {"items": {"item": {"srtnCd": "005930", "crno": "1301110006246"}}}
        elif request.url.path.endswith("/getAffiliate_V2"):
            body = {"items": {"item": {"afilCmpyNm": "삼성전자(주)", "crno": "1301110006246"}}}
        elif request.url.path.endswith("/getConsSubsComp_V2"):
            body = {"items": {"item": {"sbrdEnpNm": "Samsung Electronics America Inc."}}}
        else:
            body = {}
        body.update({"numOfRows": 10, "pageNo": 1, "totalCount": 1})
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": body,
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        app.state.http_transport = transport
        response = client.get(
            "/company/get_company_info",
            params={"corporate_registration_number": "1301110006246"},
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert [path for path, _ in captured_paths] == [
        "/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2",
        "/1160100/service/GetKrxListedInfoService/getItemInfo",
        "/1160100/service/GetCorpBasicInfoService_V2/getAffiliate_V2",
        "/1160100/service/GetCorpBasicInfoService_V2/getConsSubsComp_V2",
    ]
    assert all(params["crno"] == "1301110006246" for _, params in captured_paths)
    payload = response.json()
    assert payload["corporate_registration_number"] == "1301110006246"
    assert payload["corp_outline"]["body"]["items"]["item"]["corpNm"] == "삼성전자(주)"
    assert payload["krx_listed_item"]["body"]["items"]["item"]["srtnCd"] == "005930"


def test_get_stock_price_maps_query_to_searchapi_google_finance(monkeypatch):
    monkeypatch.setenv("SEARCHAPI_API_KEY", "searchapi-key")

    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "search_parameters": {
                    "engine": "google_finance",
                    "q": "005930:KRX",
                    "hl": "ko",
                    "window": "1M",
                },
                "summary": {
                    "title": "Samsung Electronics Co Ltd",
                    "stock": "005930",
                    "exchange": "KRX",
                    "price": 1234.0,
                    "currency": "KRW",
                },
            },
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        app.state.http_transport = transport
        response = client.get(
            "/company/get_stock_price",
            params={
                "stock_code": "005930",
                "exchange": "KRX",
                "language": "ko",
                "window": "1M",
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["url"].startswith(
        "https://www.searchapi.io/api/v1/search"
    )
    assert captured_request["params"] == {
        "api_key": "searchapi-key",
        "engine": "google_finance",
        "q": "005930:KRX",
        "hl": "ko",
        "window": "1M",
    }
    assert response.json()["summary"]["stock"] == "005930"


def test_get_stock_price_requires_q_or_stock_code():
    with TestClient(app) as client:
        response = client.get("/company/get_stock_price")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "q or stock_code is required"
    )
