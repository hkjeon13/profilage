import os
from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.company_affiliate import (
    CompanyCorpOutlineQuery,
    CompanyCorpOutlineService,
    CompanyInfoQuery,
    CompanyInfoService,
    CompanyStockPriceQuery,
    CompanyStockPriceService,
)
from app.services.company_dart import DartCompanyService
from app.services.company_store import (
    AFFILIATE_GROUP,
    COMPANY_ENTITY_TYPE,
    CONS_SUBS_COMP_GROUP,
    CORP_OUTLINE_GROUP,
    KRX_LISTED_ITEM_GROUP,
    DataGroupRecord,
    is_krx_market_open,
    stock_price_ttl,
)


def dart_corp_code_zip() -> bytes:
    buffer = BytesIO()
    xml = """
    <result>
      <list>
        <corp_code>00126380</corp_code>
        <corp_name>삼성전자</corp_name>
        <corp_eng_name>SAMSUNG ELECTRONICS CO., LTD.</corp_eng_name>
        <stock_code>005930</stock_code>
        <modify_date>20260701</modify_date>
      </list>
    </result>
    """.encode()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return buffer.getvalue()


class FakeJsonCache:
    def __init__(self) -> None:
        self.values = {}
        self.set_calls = []

    async def get_json(self, key):
        return self.values.get(key)

    async def set_json(self, key, value, ttl):
        self.set_calls.append((key, value, ttl))
        self.values[key] = value


class FakeDataGroupStore:
    def __init__(self) -> None:
        self.records = {}
        self.upserts = []

    async def initialize(self):
        return None

    async def get_record(
        self,
        *,
        entity_type,
        entity_key,
        group_name,
        allow_stale=False,
    ):
        record = self.records.get((entity_type, entity_key, group_name))
        if record is None:
            return None
        if record.stale and not allow_stale:
            return None
        return record

    async def upsert_record(
        self,
        *,
        entity_type,
        entity_key,
        group_name,
        source,
        payload,
        ttl,
    ):
        self.upserts.append(
            {
                "entity_type": entity_type,
                "entity_key": entity_key,
                "group_name": group_name,
                "source": source,
                "payload": payload,
                "ttl": ttl,
            }
        )
        record = DataGroupRecord(
            payload=payload,
            fetched_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + ttl,
            source=source,
        )
        self.records[(entity_type, entity_key, group_name)] = record
        return record


def fresh_record(payload):
    return DataGroupRecord(
        payload=payload,
        fetched_at=datetime(2026, 7, 1, tzinfo=UTC),
        expires_at=datetime(2026, 7, 8, tzinfo=UTC),
        source="test",
    )


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
    assert "/app.js?v=google-home-7" in response.text


def test_search_results_status_has_breathing_room():
    with TestClient(app) as client:
        response = client.get("/styles.css")

    assert response.status_code == 200
    assert ".google-like-home:not(.is-idle) .status {\n  margin-top: 36px;" in response.text


def test_search_results_can_restore_query_from_return_url():
    with TestClient(app) as client:
        script_response = client.get("/app.js")

    assert script_response.status_code == 200
    assert 'window.location.search).get("q")' in script_response.text
    assert "searchCompanies(restoredQuery" in script_response.text
    assert 'window.history.replaceState({}, "", nextUrl)' in script_response.text
    assert 'return_q' in script_response.text


def test_profile_page_serves_company_profile_frontend():
    with TestClient(app) as client:
        response = client.get("/profile")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="profile-title"' in response.text
    assert 'id="profile-subtitle"' in response.text
    assert "profile-kicker" not in response.text
    assert '<nav class="top-nav-left">' in response.text
    assert 'class="brand-mark"' in response.text
    assert '<a href="/">검색</a>' in response.text
    assert "top-nav-right" not in response.text
    assert '<a href="/docs">API</a>' not in response.text
    assert '<a href="/openapi.json">OpenAPI</a>' not in response.text
    assert '<a href="/docs">문서</a>' not in response.text
    assert '<a href="/">새 검색</a>' not in response.text
    assert "/api/company/get_company_info" in response.text
    assert "/api/company/get_stock_price" in response.text
    assert "/profile-page-5.js?v=company-profile-14" in response.text


def test_profile_back_link_preserves_return_search_query():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert 'searchParams.get("return_q")' in script_response.text
    assert 'document.querySelector(".back-link")' in script_response.text
    assert 'backLink.href = `/?q=${encodeURIComponent(returnQuery)}`;' in script_response.text


def test_profile_frontend_exposes_card_layout_assets():
    with TestClient(app) as client:
        profile_response = client.get("/profile")
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert profile_response.status_code == 200
    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "company-canvas" in profile_response.text
    assert "company-profile-card" in script_response.text
    assert "company-profile-info-section" in script_response.text
    assert "company-side-panel" not in script_response.text
    assert ".company-background" in style_response.text


def test_profile_overview_groups_company_information_without_relationship_card():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "company-profile-info-section" in script_response.text
    assert "<h3>기업 정보</h3>" in script_response.text
    assert "<h3>핵심 정보</h3>" not in script_response.text
    assert "<h3>관계 회사</h3>" not in script_response.text
    assert "network-row" not in script_response.text
    assert "side-list" not in script_response.text
    assert ".company-profile-info-section" in style_response.text
    assert ".company-summary" in style_response.text
    assert "border-bottom: 1px solid #eef0f6;" in style_response.text
    assert "companySummaryText" in script_response.text
    assert "firstCompanyValue(info.corp_outline" in script_response.text
    assert "DART 공시와 KRX 종목 정보를 한 화면에서 확인할 수 있습니다" not in script_response.text
    assert ".company-facts dd {\n  min-width: 0;\n  margin: 0;\n  color: #111827;\n  font-weight: 500;" in style_response.text
    assert "font-weight: 780;" not in style_response.text


def test_profile_hero_uses_single_arrow_back_action_without_api_cta():
    with TestClient(app) as client:
        response = client.get("/profile")
        style_response = client.get("/styles.css")

    assert response.status_code == 200
    assert style_response.status_code == 200
    assert "API 보기" not in response.text
    assert "primary-action" not in response.text
    assert "profile-search-action" not in response.text
    assert 'class="back-link"' in response.text
    assert 'class="back-link-icon"' in response.text
    assert ".back-link-icon" in style_response.text
    assert ".profile-search-action" not in style_response.text
    assert 'class="profile-identity-row"' in response.text
    assert 'class="profile-title-block"' in response.text
    assert ".profile-identity-row {\n  display: flex;" in style_response.text
    assert "padding: 92px 26px 42px;" in style_response.text
    assert ".company-logo-box {\n  display: grid;\n  width: 70px;" in style_response.text
    assert ".company-logo-box {\n  display: grid;\n  position: absolute;" not in style_response.text
    assert "overflow-wrap: anywhere;" in style_response.text
    assert "@media (max-width: 560px)" in style_response.text
    assert ".profile-page .info-block {\n    padding: 18px;" in style_response.text


def test_profile_frontend_does_not_duplicate_recent_disclosures():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert "renderDartDisclosures(info.dart_disclosures)" in script_response.text
    assert "latest-disclosure" not in script_response.text


def test_profile_disclosures_open_inside_page_viewer():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "data-disclosure-viewer" in script_response.text
    assert "disclosure-viewer-modal" in script_response.text
    assert "disclosure-viewer-frame" in script_response.text
    assert "setupDisclosureViewer()" in script_response.text
    assert 'target="_blank" rel="noreferrer">${text(item.report_nm)}</a>' not in script_response.text
    assert ".disclosure-viewer-modal" in style_response.text
    assert ".disclosure-viewer-frame" in style_response.text
    assert ".company-disclosure-card .block-heading" in style_response.text
    assert ".company-disclosure-card .disclosure-list li" in style_response.text
    assert "border-bottom: 1px solid #eef0f6;" in style_response.text
    assert ".company-disclosure-card .disclosure-list li:last-child" in style_response.text


def test_financial_summary_uses_metric_card_grid():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "financial-summary-heading" in script_response.text
    assert "financial-metrics" in script_response.text
    assert "financial-metric-card" in script_response.text
    assert ".financial-metrics" in style_response.text
    assert ".financial-metric-card" in style_response.text
    assert ".financial-summary-panel[hidden]" in style_response.text
    assert "repeat(auto-fit, minmax(min(100%, 210px), 220px))" in style_response.text
    assert ".company-insight-row .financial-metrics {\n  grid-template-columns: 1fr;" not in style_response.text


def test_financial_summary_more_link_is_in_card_heading():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert '<a class="text-link financial-more-link"' in script_response.text
    assert script_response.text.index('<a class="text-link financial-more-link"') < script_response.text.index('<div class="summary-tabs"')
    assert '<a class="text-link" href="${financialDetailUrl(crno, selected)}">더보기</a>' not in script_response.text


def test_financial_summary_and_disclosures_share_horizontal_row():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "company-insight-row" in script_response.text
    assert "renderCompanyInsightRow(info)" in script_response.text
    assert ".company-insight-row" in style_response.text
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in style_response.text


def test_profile_recent_disclosures_shows_ten_items():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert "slice(0, 10)" in script_response.text
    assert "slice(0, 5)" not in script_response.text


def test_stock_chart_svg_uses_full_card_width():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert 'preserveAspectRatio="none"' in script_response.text


def test_stock_chart_matches_reference_style_structure():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert "stock-range-tabs" in script_response.text
    assert "stock-chart-axis-labels" in script_response.text
    assert "stock-chart-line-primary" in script_response.text
    assert "stock-chart-line-muted" not in script_response.text


def test_stock_chart_uses_date_axis_for_monthly_data():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert "formatChartDate(points[0].date)" in script_response.text
    assert "formatChartDate(points[Math.floor((points.length - 1) / 2)].date)" in script_response.text
    assert "formatChartDate(points.at(-1).date)" in script_response.text
    assert "formatChartTime(points[0].date)" not in script_response.text


def test_stock_card_omits_empty_change_badge():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")

    assert script_response.status_code == 200
    assert "변동 정보 없음" not in script_response.text
    assert "change ? " in script_response.text
    assert 'class="price-meta"' in script_response.text


def test_stock_chart_keeps_endpoint_axis_labels_visible():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        chart_style_response = client.get("/profile-chart-2.css")

    assert script_response.status_code == 200
    assert chart_style_response.status_code == 200
    assert "stock-chart-meta-end" in script_response.text
    assert "visibility: hidden" not in chart_style_response.text


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


@pytest.mark.asyncio
async def test_company_info_service_reuses_fresh_postgres_groups(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    request_count = 0
    store = FakeDataGroupStore()
    crno = "1301110006246"
    store.records = {
        (COMPANY_ENTITY_TYPE, crno, CORP_OUTLINE_GROUP): fresh_record(
            {"body": {"items": {"item": {"crno": crno, "corpNm": "저장회사"}}}}
        ),
        (COMPANY_ENTITY_TYPE, crno, KRX_LISTED_ITEM_GROUP): fresh_record(
            {"body": {"items": {"item": {"crno": crno, "srtnCd": "005930"}}}}
        ),
        (COMPANY_ENTITY_TYPE, crno, AFFILIATE_GROUP): fresh_record(
            {"body": {"items": {"item": {"crno": crno, "afilCmpyNm": "계열회사"}}}}
        ),
        (COMPANY_ENTITY_TYPE, crno, CONS_SUBS_COMP_GROUP): fresh_record(
            {"body": {"items": {"item": {"sbrdEnpNm": "종속회사"}}}}
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(500, json={})

    service = CompanyInfoService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=store,
    )
    payload = await service.fetch(
        CompanyInfoQuery(
            corporate_registration_number=crno,
            page=1,
            per_page=10,
        )
    )

    assert request_count == 0
    assert payload["corp_outline"]["body"]["items"]["item"]["corpNm"] == "저장회사"
    assert payload["krx_listed_item"]["body"]["items"]["item"]["srtnCd"] == "005930"
    assert store.upserts == []


@pytest.mark.asyncio
async def test_company_info_service_upserts_missing_groups(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)
    crno = "1301110006246"
    store = FakeDataGroupStore()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getCorpOutline_V2"):
            body = {"items": {"item": {"crno": crno, "corpNm": "삼성전자(주)"}}}
        elif request.url.path.endswith("/getItemInfo"):
            body = {"items": {"item": {"srtnCd": "005930", "crno": crno}}}
        elif request.url.path.endswith("/getAffiliate_V2"):
            body = {"items": {"item": {"afilCmpyNm": "삼성전자(주)", "crno": crno}}}
        elif request.url.path.endswith("/getConsSubsComp_V2"):
            body = {"items": {"item": {"sbrdEnpNm": "Samsung Electronics America Inc."}}}
        else:
            body = {}
        body.update({"numOfRows": 10, "pageNo": 1, "totalCount": 1})
        return httpx.Response(200, json={"response": {"body": body}})

    service = CompanyInfoService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=store,
    )
    await service.fetch(
        CompanyInfoQuery(
            corporate_registration_number=crno,
            page=1,
            per_page=10,
        )
    )

    upserts = {call["group_name"]: call for call in store.upserts}
    assert set(upserts) == {
        CORP_OUTLINE_GROUP,
        KRX_LISTED_ITEM_GROUP,
        AFFILIATE_GROUP,
        CONS_SUBS_COMP_GROUP,
    }
    assert upserts[CORP_OUTLINE_GROUP]["ttl"].days == 7
    assert upserts[KRX_LISTED_ITEM_GROUP]["ttl"].days == 1
    assert upserts[AFFILIATE_GROUP]["ttl"].days == 7
    assert upserts[CONS_SUBS_COMP_GROUP]["ttl"].days == 7


def test_krx_stock_price_refresh_policy_uses_korea_market_hours():
    market_open = datetime(2026, 7, 2, 1, 0, tzinfo=UTC)
    market_closed = datetime(2026, 7, 2, 8, 0, tzinfo=UTC)

    assert is_krx_market_open(market_open) is True
    assert stock_price_ttl("KRX", market_open).total_seconds() == 300
    assert is_krx_market_open(market_closed) is False
    assert stock_price_ttl("KRX", market_closed).total_seconds() == 3600
    assert stock_price_ttl("NASDAQ", market_open).total_seconds() == 3600


@pytest.mark.asyncio
async def test_open_api_service_reuses_cached_response(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.setenv("CACHE_BYPASS_RATE", "0")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
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

    cache = FakeJsonCache()
    service = CompanyCorpOutlineService(
        transport=httpx.MockTransport(handler),
        cache=cache,
        data_group_store=None,
    )
    query = CompanyCorpOutlineQuery(
        company_name="삼성전자",
        corporate_registration_number=None,
        page=1,
        per_page=10,
    )

    first = await service.fetch(query)
    second = await service.fetch(query)

    assert request_count == 1
    assert second == first
    assert len(cache.set_calls) == 1
    assert cache.set_calls[0][0].startswith("profilage:api:")


@pytest.mark.asyncio
async def test_stock_price_service_reuses_cached_response(monkeypatch):
    monkeypatch.setenv("SEARCHAPI_API_KEY", "searchapi-key")
    monkeypatch.setenv("CACHE_BYPASS_RATE", "0")
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "summary": {
                    "title": "Samsung Electronics Co Ltd",
                    "stock": "005930",
                    "exchange": "KRX",
                    "price": 1234.0,
                }
            },
        )

    cache = FakeJsonCache()
    service = CompanyStockPriceService(
        transport=httpx.MockTransport(handler),
        cache=cache,
        data_group_store=None,
    )
    query = CompanyStockPriceQuery(
        q=None,
        stock_code="005930",
        exchange="KRX",
        language="ko",
        window="1M",
    )

    first = await service.fetch(query)
    second = await service.fetch(query)

    assert request_count == 1
    assert second == first
    assert len(cache.set_calls) == 1
    assert cache.set_calls[0][0].startswith("profilage:api:")


@pytest.mark.asyncio
async def test_open_api_service_can_bypass_cached_response(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.setenv("CACHE_BYPASS_RATE", "1")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "response": {
                    "body": {
                        "items": {
                            "item": {
                                "crno": "1301110006246",
                                "corpNm": f"삼성전자({request_count})",
                            }
                        },
                    },
                }
            },
        )

    cache = FakeJsonCache()
    service = CompanyCorpOutlineService(
        transport=httpx.MockTransport(handler),
        cache=cache,
        data_group_store=None,
    )
    query = CompanyCorpOutlineQuery(
        company_name="삼성전자",
        corporate_registration_number=None,
        page=1,
        per_page=10,
    )

    first = await service.fetch(query)
    second = await service.fetch(query)

    assert request_count == 2
    assert first["body"]["items"]["item"]["corpNm"] == "삼성전자(1)"
    assert second["body"]["items"]["item"]["corpNm"] == "삼성전자(2)"
    assert len(cache.set_calls) == 2


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


def test_get_dart_corp_code_maps_stock_code_to_dart_corp_code(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(200, content=dart_corp_code_zip())

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_corp_code",
            params={"stock_code": "A005930"},
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["params"] == {"crtfc_key": "dart-key"}
    payload = response.json()
    assert payload["match"]["corp_code"] == "00126380"
    assert payload["match"]["stock_code"] == "005930"


def test_get_dart_company_maps_query_to_dart_company_api(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "status": "000",
                "message": "정상",
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "jurir_no": "1301110006246",
            },
        )

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_company",
            params={"corp_code": "00126380"},
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["url"].startswith(
        "https://opendart.fss.or.kr/api/company.json"
    )
    assert captured_request["params"] == {
        "crtfc_key": "dart-key",
        "corp_code": "00126380",
    }
    assert response.json()["jurir_no"] == "1301110006246"


def test_get_dart_disclosures_adds_viewer_url(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "status": "000",
                "message": "정상",
                "page_no": 1,
                "page_count": 10,
                "total_count": 1,
                "list": [
                    {
                        "corp_code": "00126380",
                        "corp_name": "삼성전자",
                        "report_nm": "사업보고서",
                        "rcept_no": "20260331000001",
                        "rcept_dt": "20260331",
                    }
                ],
            },
        )

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_disclosures",
            params={
                "corp_code": "00126380",
                "begin_date": "20260101",
                "page": 1,
                "per_page": 10,
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["params"]["corp_code"] == "00126380"
    assert captured_request["params"]["bgn_de"] == "20260101"
    assert captured_request["params"]["page_no"] == "1"
    assert captured_request["params"]["page_count"] == "10"
    assert response.json()["list"][0]["viewer_url"] == (
        "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260331000001"
    )


def test_get_dart_financial_accounts_maps_query_to_dart_api(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "status": "000",
                "message": "정상",
                "list": [
                    {
                        "account_nm": "매출액",
                        "thstrm_amount": "300000000",
                    }
                ],
            },
        )

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_financial_accounts",
            params={
                "corp_code": "00126380",
                "business_year": "2025",
                "report_code": "11011",
                "fs_division": "CFS",
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert captured_request["params"] == {
        "crtfc_key": "dart-key",
        "corp_code": "00126380",
        "bsns_year": "2025",
        "reprt_code": "11011",
        "fs_div": "CFS",
    }
    assert response.json()["list"][0]["account_nm"] == "매출액"


@pytest.mark.asyncio
async def test_dart_latest_financial_reports_selects_latest_quarter_and_annual(
    monkeypatch,
):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        captured_requests.append(params)
        year = params["bsns_year"]
        report_code = params["reprt_code"]
        if (year, report_code) == ("2026", "11013"):
            items = [
                {
                    "bsns_year": "2026",
                    "reprt_code": "11013",
                    "fs_div": "CFS",
                    "account_nm": "매출액",
                    "thstrm_amount": "100000000",
                }
            ]
        elif (year, report_code) == ("2025", "11011"):
            items = [
                {
                    "bsns_year": "2025",
                    "reprt_code": "11011",
                    "fs_div": "CFS",
                    "account_nm": "매출액",
                    "thstrm_amount": "90000000",
                }
            ]
        else:
            items = []
        return httpx.Response(
            200,
            json={
                "status": "000" if items else "013",
                "message": "정상" if items else "조회된 데이타가 없습니다.",
                "list": items,
            },
        )

    service = DartCompanyService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=FakeDataGroupStore(),
    )

    payload = await service.get_latest_financial_reports(
        corp_code="00126380",
        current_year=2026,
        fs_division="CFS",
    )

    assert payload["quarter"]["selected"] == {
        "business_year": "2026",
        "report_code": "11013",
        "fs_division": "CFS",
        "report_name": "1분기보고서",
    }
    assert payload["quarter"]["accounts"]["list"][0]["thstrm_amount"] == "100000000"
    assert payload["annual"]["selected"] == {
        "business_year": "2025",
        "report_code": "11011",
        "fs_division": "CFS",
        "report_name": "사업보고서",
    }
    assert payload["annual"]["accounts"]["list"][0]["thstrm_amount"] == "90000000"
    assert [request["reprt_code"] for request in captured_requests[:3]] == [
        "11014",
        "11012",
        "11013",
    ]
