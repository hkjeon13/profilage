import os
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
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
from app.services.company_dart import (
    DART_PERIODIC_ENDPOINTS,
    DartPeriodicReportInfoQuery,
    DartFinancialAccountsQuery,
    DartCompanyService,
    dart_financial_accounts_ttl,
    dart_periodic_report_ttl,
)
from app.services.company_disclosure_events import (
    classify_disclosure_event,
    normalize_disclosure_events,
)
from app.services.company_insights import (
    normalize_company_risk_signals,
    normalize_dart_insights,
)
from app.services.company_shareholders import (
    classify_shareholder,
    normalize_business_group_company,
    normalize_holding_rows,
    select_top_business_groups,
)
from app.services.company_store import (
    AFFILIATE_GROUP,
    COMPANY_ENTITY_TYPE,
    CONS_SUBS_COMP_GROUP,
    CORP_OUTLINE_GROUP,
    KRX_LISTED_ITEM_GROUP,
    STOCK_PRICE_GROUP,
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
            expires_at=(
                datetime.max.replace(tzinfo=UTC)
                if ttl is None
                else datetime.now(UTC) + ttl
            ),
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


def hs256_jwt(payload, secret="test-secret"):
    def encode_part(value):
        raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = encode_part({"alg": "HS256", "typ": "JWT"})
    body = encode_part(payload)
    signing_input = f"{header}.{body}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{body}.{encoded_signature}"


def test_root_serves_company_search_frontend():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Profilage" in response.text
    assert '<body class="is-idle google-like-home">' in response.text
    assert 'class="home-title"' in response.text
    assert 'class="example-query-list"' in response.text
    assert "/api/company/get_corp_outline" in response.text
    assert "/profile?crno=" in response.text
    assert "/styles.css?v=google-home-9" in response.text
    assert "/app.js?v=google-home-11" in response.text


def test_search_results_status_has_breathing_room():
    with TestClient(app) as client:
        response = client.get("/styles.css")

    assert response.status_code == 200
    assert ".google-like-home:not(.is-idle) .status {\n  margin-top: 36px;" in response.text
    assert ".detail-panel {\n  min-height: 360px;" in response.text
    assert ".result-list,\n.detail-panel {\n  min-height: 360px;" not in response.text


def test_search_results_can_restore_query_from_return_url():
    with TestClient(app) as client:
        script_response = client.get("/app.js")

    assert script_response.status_code == 200
    assert 'window.location.search).get("q")' in script_response.text
    assert "searchCompanies(restoredQuery" in script_response.text
    assert 'window.history.replaceState({}, "", nextUrl)' in script_response.text
    assert 'return_q' in script_response.text
    assert "loadCompanySearchResults" in script_response.text
    assert "caseInsensitiveQueryCandidates" not in script_response.text
    assert "searchCompaniesWithCaseFallback" not in script_response.text


def test_homepage_positions_as_b2b_company_data_platform():
    with TestClient(app) as client:
        response = client.get("/")
        script_response = client.get("/app.js")
        style_response = client.get("/styles.css")

    assert response.status_code == 200
    assert "기업 정보를 빠르게 찾고 비교하세요" in response.text
    assert "금융위원회, DART, 주가 데이터를 기반" in response.text
    assert "기업명, 종목코드, 법인등록번호로 검색" in response.text
    assert "data-example-query" in response.text
    assert "data-source-rail" in response.text
    assert "B2B 기업 데이터 플랫폼" in response.text
    assert "인물명" not in response.text
    assert "[data-example-query]" in script_response.text
    assert ".home-title" in style_response.text
    assert ".source-rail" in style_response.text


def test_search_results_render_dense_business_rows_with_entity_type():
    with TestClient(app) as client:
        script_response = client.get("/app.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "result-card-main" in script_response.text
    assert "result-meta-grid" in script_response.text
    assert "data-result-compare-add" in script_response.text
    assert "entity-type-badge" in script_response.text
    assert "setupResultCompareButtons" in script_response.text
    assert ".result-card-main" in style_response.text
    assert ".result-meta-grid" in style_response.text
    assert ".result-data-badges" in style_response.text
    assert ".entity-type-badge" in style_response.text


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
    assert "/styles.css?v=company-profile-46" in response.text
    assert "/profile-chart-2.css?v=interactive-9" in response.text
    assert "/api/company/get_company_info" in response.text
    assert "/api/company/get_stock_price" in response.text
    assert "/profile-page-5.js?v=company-profile-44" in response.text


def test_compare_page_serves_company_compare_frontend():
    with TestClient(app) as client:
        response = client.get("/compare")
        script_response = client.get("/compare-page.js")
        style_response = client.get("/styles.css")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="compare-root"' in response.text
    assert "/styles.css?v=company-profile-45" in response.text
    assert "/compare-page.js?v=company-compare-6" in response.text
    assert "/api/company/get_company_info" in response.text
    assert "COMPARE_STORAGE_KEY" in script_response.text
    assert "renderCompareTable" in script_response.text
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
    assert "removeCompanyFromCompare" in script_response.text
    assert "data-compare-remove" in script_response.text
    assert "setupCompareRemoveButtons" in script_response.text
    assert "compareUrlForCrnos" in script_response.text
    assert ">×</button>" in script_response.text
    assert "compare-best" in script_response.text
    assert "renderCompareSummary" in script_response.text
    assert "buildCompareSummary" in script_response.text
    assert "종합 요약" in script_response.text
    assert ".compare-summary-list" in style_response.text
    assert "renderCompanyChips" not in script_response.text
    assert "compare-company-chips" not in script_response.text
    assert "최소 2개 기업을 선택하면 비교표가 표시됩니다" in script_response.text
    assert ".compare-table" in style_response.text
    assert ".compare-best" in style_response.text
    assert ".compare-table tbody tr:last-child th,\n.compare-table tbody tr:last-child td" in style_response.text
    assert ".compare-remove-button" in style_response.text
    assert ".compare-column-head" in style_response.text
    assert ".compare-column-basis" in style_response.text
    assert ".compare-share-button" in style_response.text
    assert "border-radius: 50%;" in style_response.text
    remove_button_rule = style_response.text.split(
        ".compare-remove-button {", 1
    )[1].split("}", 1)[0]
    assert "background: transparent;" in remove_button_rule
    assert "background: #f2f4f7" not in remove_button_rule
    assert ".compare-company-chips" not in style_response.text
    assert ".compare-table-wrap {\n  overflow-x: auto;" in style_response.text
    assert ".compare-toolbar {\n    align-items: stretch;\n    flex-direction: column;" in style_response.text
    assert ".compare-table {\n    min-width: 560px;" in style_response.text


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
    assert 'class="homepage-icon-link"' in script_response.text
    assert 'aria-label="홈페이지"' in script_response.text
    assert 'target="_blank" rel="noreferrer">홈페이지</a>' not in script_response.text
    assert "info.dart_company || {}" in script_response.text
    company_info_section = script_response.text.split(
        '<section class="company-profile-info-section"', 1
    )[1].split("</section>", 1)[0]
    assert "직원 수" in company_info_section
    assert "전화번호" in company_info_section
    assert "DART 고유번호" not in company_info_section
    assert "FSS 고유번호" not in company_info_section
    assert "단축코드" not in company_info_section
    assert "ISIN" not in company_info_section
    assert "최초 영업일" in company_info_section
    assert "최종 영업일" in company_info_section
    assert "<dt>주소</dt>" in company_info_section
    assert 'class="company-address-card"' not in script_response.text
    assert "outline.enpTlno || dartCompany.phn_no" in script_response.text
    assert 'text(outline.enpBsadr, "주소 정보 없음")' in script_response.text
    assert "function validIndustryName" in script_response.text
    assert 'text(industry, "정보 없음")' in script_response.text
    assert 'text(outline.enpMainBizNm || listed.itmsNm, "정보 없음")' not in script_response.text
    assert "outline.enpEmpeCnt" in script_response.text
    assert "dartCompany.corp_code" in script_response.text
    assert ".homepage-icon-link" in style_response.text
    assert ".block-heading .homepage-icon-link {\n  display: inline-flex;\n  width: auto;" in style_response.text
    homepage_link_rule = style_response.text.split(
        ".block-heading .homepage-icon-link {", 1
    )[1].split("}", 1)[0]
    assert "border:" not in homepage_link_rule
    assert "background:" not in homepage_link_rule


def test_profile_frontend_can_add_company_to_compare_list():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        profile_response = client.get("/profile")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert profile_response.status_code == 200
    assert style_response.status_code == 200
    assert "COMPARE_STORAGE_KEY" in script_response.text
    assert "addCompanyToCompare" in script_response.text
    assert "setupCompareActions" in script_response.text
    assert "data-compare-add" in script_response.text
    assert "비교에 추가" in script_response.text
    assert "/profile-page-5.js?v=company-profile-44" in profile_response.text
    assert ".block-heading .homepage-icon-link:hover {\n  color: #185abc;\n}" in style_response.text
    assert ".company-facts dd {\n  min-width: 0;\n  margin: 0;\n  color: #111827;\n  font-weight: 500;" in style_response.text
    assert ".profile-heading-actions {\n    align-items: center;\n    flex-direction: row;" in style_response.text
    assert ".profile-heading-actions .compare-add-button,\n  .profile-heading-actions .compare-link-button {\n    width: auto;" in style_response.text
    assert "font-weight: 780;" not in style_response.text


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
    assert "preferredFinancialValue" in script_response.text
    assert ".executive-summary-block" in style_response.text
    assert ".key-metric-strip" in style_response.text


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
    assert "공개 데이터 기반" in script_response.text


def test_profile_exposes_mobile_section_navigation():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderProfileSectionNav" in script_response.text
    assert "profile-section-nav" in script_response.text
    assert "data-profile-section" in script_response.text
    assert "setupCompanyAiSummaryMore" in script_response.text
    assert ".profile-section-nav" in style_response.text
    assert "position: sticky;" in style_response.text


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
    assert ".company-insight-row .financial-metrics {\n    grid-template-columns: 1fr;" in style_response.text
    assert "    width: 100%;" in style_response.text
    assert "    justify-items: stretch;" in style_response.text
    assert "justify-content: stretch;" in style_response.text
    assert ".company-insight-row .financial-metric-card {\n    width: 100%;" in style_response.text


def test_financial_summary_cards_open_trend_modal_with_account_checks():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")
        profile_response = client.get("/profile")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert profile_response.status_code == 200
    assert "ensureFinancialTrendModal" in script_response.text
    assert "setupFinancialTrendCards" in script_response.text
    assert "renderFinancialTrendChart" in script_response.text
    assert "data-financial-trend-account" in script_response.text
    assert "data-financial-trend-payload" in script_response.text
    assert "/api/company/get_dart_financial_trends" in script_response.text
    assert "financial-trend-account-check" in script_response.text
    assert ".financial-trend-modal" in style_response.text
    assert ".financial-trend-chart" in style_response.text
    assert "/profile-page-5.js?v=company-profile-44" in profile_response.text


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


def test_disclosures_page_loads_more_items_on_scroll():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "setupInfiniteDisclosureScroll" in script_response.text
    assert "IntersectionObserver" in script_response.text
    assert 'data-disclosure-list="true"' in script_response.text
    assert 'data-disclosure-sentinel="true"' in script_response.text
    assert 'data-disclosure-count="true"' in script_response.text
    assert "appendDisclosureItems" in script_response.text
    assert "page: nextPage" in script_response.text
    assert "per_page: DISCLOSURE_PAGE_SIZE" in script_response.text
    assert "total_count" in script_response.text
    assert ".disclosure-load-status" in style_response.text


def test_disclosures_page_exposes_disclosure_type_filters():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "DISCLOSURE_FILTERS" in script_response.text
    assert "정기공시" in script_response.text
    assert "주요사항" in script_response.text
    assert "지분공시" in script_response.text
    assert "disclosure_type" in script_response.text
    assert "selectedDisclosureType" in script_response.text
    assert "setupDisclosureFilters" in script_response.text
    assert ".disclosure-filter-tabs" in style_response.text


def test_disclosures_page_uses_flat_list_layout():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert 'class="info-block full disclosure-subpage-card"' in script_response.text
    assert ".profile-page .disclosure-subpage-card {" in style_response.text
    assert "box-shadow: none;" in style_response.text
    assert ".disclosure-subpage-card .disclosure-list-large {" in style_response.text
    assert "gap: 0;" in style_response.text
    assert ".disclosure-subpage-card .disclosure-list-large li {" in style_response.text
    assert "padding: 16px 22px;" in style_response.text
    assert "border-bottom: 1px solid #eef0f6;" in style_response.text


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
    assert 'STOCK_WINDOWS = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]' in script_response.text
    assert 'data-stock-window="${rangeLabel}"' in script_response.text
    assert "setupStockWindowTabs" in script_response.text
    assert "fetchJson(stockUrl" in script_response.text
    assert "window: nextWindow" in script_response.text
    assert "stock_window" in script_response.text
    assert "stock-chart-axis-labels" in script_response.text
    assert "stock-chart-line-primary" in script_response.text
    assert "stock-chart-line-muted" not in script_response.text
    assert "renderCompanyStockCard" in script_response.text
    assert "refreshCompanyStockCard" in script_response.text
    assert "stockLoading" in script_response.text
    assert "renderCompanyDetail({" in script_response.text
    assert "refreshCompanyStockCard({" in script_response.text


def test_stock_window_tabs_expose_loading_error_and_refresh_metadata():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")
        profile_response = client.get("/profile")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert profile_response.status_code == 200
    assert "is-loading-stock" in script_response.text
    assert "stock-window-status" in script_response.text
    assert "stockUpdatedLabel" in script_response.text
    assert "stock?._meta?.fetched_at" in script_response.text
    assert "stock?._meta?.expires_at" in script_response.text
    assert "주가 정보를 불러오는 중입니다" in script_response.text
    assert "주가 정보를 불러오지 못했습니다" in script_response.text
    assert ".stock-window-status" in style_response.text
    assert ".company-market-card.is-loading-stock" in style_response.text
    assert "/profile-page-5.js?v=company-profile-44" in profile_response.text


def test_profile_sections_render_source_and_basis_metadata():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderSourceMeta" in script_response.text
    assert "금융위원회 기업기본정보" in script_response.text
    assert "DART" in script_response.text
    assert "SearchAPI Google Finance" in script_response.text
    assert "기준일" in script_response.text
    assert "캐시 만료" in script_response.text
    assert ".source-meta" in style_response.text


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


def test_stock_chart_uses_wide_mobile_aspect_ratio():
    with TestClient(app) as client:
        chart_style_response = client.get("/profile-chart-2.css")

    assert chart_style_response.status_code == 200
    assert "@media (max-width: 820px)" in chart_style_response.text
    assert ".stock-chart svg {\n    height: 156px;" in chart_style_response.text
    assert ".stock-chart-axis-labels {\n    height: 156px;" in chart_style_response.text


def test_stock_chart_tooltip_stays_inside_mobile_chart_bounds():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        chart_style_response = client.get("/profile-chart-2.css")

    assert script_response.status_code == 200
    assert chart_style_response.status_code == 200
    assert "function getTooltipLeftPercent" in script_response.text
    assert "tooltip.offsetWidth / 2 + 8" in script_response.text
    assert "chartPixelWidth - tooltipHalfWidth" in script_response.text
    assert "tooltip.style.left = `${tooltipPosition}%`;" in script_response.text
    assert "transform: translate(-50%, -50%);" in chart_style_response.text


def test_stock_chart_point_marker_is_hidden_from_default_chart_view():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        chart_style_response = client.get("/profile-chart-2.css")

    assert script_response.status_code == 200
    assert chart_style_response.status_code == 200
    assert 'chart.classList.toggle("is-inspecting", revealMarker);' not in script_response.text
    assert "updateStockChartSelection(chart, points.at(-1));" in script_response.text
    assert "updateStockChartSelection(chart, nearest);" in script_response.text
    dot_rule = chart_style_response.text.split(".stock-chart-dot {", 1)[1].split("}", 1)[0]
    assert "opacity: 0;" in dot_rule
    assert "transition: opacity 120ms ease;" in dot_rule
    assert "display: none;" in dot_rule


def test_stock_chart_tooltip_is_compact_on_mobile():
    with TestClient(app) as client:
        chart_style_response = client.get("/profile-chart-2.css")
        profile_response = client.get("/profile")

    assert chart_style_response.status_code == 200
    assert profile_response.status_code == 200
    assert "@media (max-width: 560px)" in chart_style_response.text
    assert ".stock-chart-tooltip {\n    min-width: 104px;" in chart_style_response.text
    assert "padding: 8px 9px;" in chart_style_response.text
    assert ".stock-chart-tooltip strong {\n    font-size: 13px;" in chart_style_response.text
    assert ".stock-chart-tooltip span {\n    margin-top: 3px;\n    font-size: 11px;" in chart_style_response.text
    assert "/profile-chart-2.css?v=interactive-9" in profile_response.text


def test_profile_mobile_layout_prevents_horizontal_overflow():
    with TestClient(app) as client:
        style_response = client.get("/styles.css")
        chart_style_response = client.get("/profile-chart-2.css")

    assert style_response.status_code == 200
    assert chart_style_response.status_code == 200
    assert ".profile-layout {\n  display: grid;\n  min-width: 0;" in style_response.text
    assert ".profile-page .detail-panel {\n  min-width: 0;" in style_response.text
    assert ".company-main-column {\n  display: grid;\n  min-width: 0;" in style_response.text
    assert ".profile-page .info-block {\n  min-width: 0;" in style_response.text
    assert "overflow-wrap: anywhere;" in style_response.text
    assert ".stock-range-tabs {\n  display: flex;\n  flex-wrap: wrap;" in chart_style_response.text
    assert "max-width: 100%;" in chart_style_response.text


def test_financial_summary_renders_delta_badges_with_correct_comparison_basis():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "financialDeltaText" in script_response.text
    assert "financialDeltaBasis" in script_response.text
    assert "yoy_amount" in script_response.text
    assert "frmtrm_amount" in script_response.text
    assert "전년 동기" in script_response.text
    assert "전기 대비" not in script_response.text
    assert "YoY" not in script_response.text
    assert "delta-badge" in script_response.text
    assert "is-positive" in script_response.text
    assert "is-negative" in script_response.text
    assert ".delta-badge" in style_response.text


def test_profile_renders_compact_relationship_summary_without_side_panel():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderRelationshipSummary" in script_response.text
    assert "계열회사" in script_response.text
    assert "종속기업" in script_response.text
    assert "상장 관계사" in script_response.text
    assert "company-relationship-summary" in script_response.text
    assert "company-side-panel" not in script_response.text
    assert ".company-relationship-summary" in style_response.text


def test_relationship_summary_cards_open_company_list_modal():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")
        profile_response = client.get("/profile")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert profile_response.status_code == 200
    assert "ensureRelationshipListModal" in script_response.text
    assert "setupRelationshipSummaryCards" in script_response.text
    assert "renderRelationshipListItems" in script_response.text
    assert "data-relationship-list-type" in script_response.text
    assert "data-relationship-list-payload" in script_response.text
    assert "afilCmpyNm" in script_response.text
    assert "sbrdEnpNm" in script_response.text
    assert "relationship-list-modal" in script_response.text
    assert ".relationship-list-modal" in style_response.text
    assert ".relationship-list-items" in style_response.text
    assert "/styles.css?v=company-profile-46" in profile_response.text
    assert "/profile-page-5.js?v=company-profile-44" in profile_response.text


def test_relationship_summary_terms_have_tooltips():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "relationshipTermDescription" in script_response.text
    assert "같은 기업집단에 속한 회사" in script_response.text
    assert "현재 회사가 지배하는 회사" in script_response.text
    assert "data-relationship-tooltip" in script_response.text
    assert "relationship-summary-help" in script_response.text
    assert "data-relationship-help" in script_response.text
    assert "toggleRelationshipTooltip" in script_response.text
    assert "event.stopPropagation();" in script_response.text
    assert 'event.target.closest("[data-relationship-help]")' in script_response.text
    assert ".relationship-summary-help" in style_response.text
    assert ".relationship-summary-tooltip" in style_response.text
    assert ".relationship-summary-card.is-tooltip-open .relationship-summary-tooltip" in style_response.text
    wrapper_rule = style_response.text.split(
        ".company-relationship-summary .relationship-summary-grid > div {", 1
    )[1].split("}", 1)[0]
    assert "overflow: hidden" not in wrapper_rule
    assert "overflow: visible;" in wrapper_rule
    active_rule = style_response.text.split(
        ".relationship-summary-card:hover,\n.relationship-summary-card:focus-visible {", 1
    )[1].split("}", 1)[0]
    assert "z-index: 2;" in active_rule


def test_profile_frontend_renders_normalized_dart_insight_cards():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")
        profile_response = client.get("/profile")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert profile_response.status_code == 200
    assert "renderCompanyInsightCards" in script_response.text
    assert "insights.ownership" in script_response.text
    assert "insights.dividend" in script_response.text
    assert "insights.audit" in script_response.text
    assert "insights.ratios" in script_response.text
    assert "renderOwnershipStackedBar" in script_response.text
    assert "setupShareholderDetailButtons" in script_response.text
    assert "shareholderSearchUrl" in script_response.text
    assert "상위 20개 기업집단 내 보유 후보" in script_response.text
    assert "ownership-bar-segment" in script_response.text
    assert "ownership-holder-button" in script_response.text
    assert "isOwnershipTotalHolder" in script_response.text
    assert "Number(b.ratio_number) - Number(a.ratio_number)" in script_response.text
    assert "기타 주주" in script_response.text
    assert "최대주주" in script_response.text
    assert "주당배당금" in script_response.text
    assert "감사의견" in script_response.text
    assert "재무비율" in script_response.text
    assert ".company-insight-cards" in style_response.text
    assert ".ownership-stacked-bar" in style_response.text
    assert ".ownership-bar-segment" in style_response.text
    assert ".shareholder-detail-modal" in style_response.text
    assert "/styles.css?v=company-profile-46" in profile_response.text
    assert "/profile-page-5.js?v=company-profile-44" in profile_response.text


def test_profile_frontend_exposes_lazy_dart_detail_modal():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "ensureDartInsightDetailModal" in script_response.text
    assert "openDartInsightDetailModal" in script_response.text
    assert "/api/company/get_dart_company_insight_detail" in script_response.text
    assert "data-dart-insight-detail-kind" in script_response.text
    assert "주식구조 더보기" in script_response.text
    assert "임직원 더보기" in script_response.text
    assert ".dart-insight-detail-modal" in style_response.text


def test_dart_detail_modal_formats_rows_with_human_labels():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "formatDartInsightDetailField" in script_response.text
    assert "renderDartInsightDetailMeta" in script_response.text
    assert "직위" in script_response.text
    assert "담당업무" in script_response.text
    assert "주식수" in script_response.text
    assert "entries.map(([key, value])" not in script_response.text
    assert "Object.entries(row)" not in script_response.text
    assert ".dart-insight-detail-meta" in style_response.text


def test_dart_insight_cards_include_source_and_empty_state_copy():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "DART 정기보고서" in script_response.text
    assert "정정 공시가 있으면 수치가 바뀔 수 있습니다" in script_response.text
    assert "표시할 심화 정보가 없습니다" in script_response.text
    assert ".company-insight-source" in style_response.text
    assert "@media (max-width: 820px)" in style_response.text


def test_profile_frontend_exposes_disclosure_events_and_risk_signals():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderDisclosureEventTimeline" in script_response.text
    assert "mapDisclosureEventsToPricePoints" in script_response.text
    assert "data-disclosure-event-marker" not in script_response.text
    assert 'class="disclosure-event-title-row"' in script_response.text
    assert 'class="disclosure-title-row"' in script_response.text
    assert 'class="disclosure-title-cell"' in script_response.text
    assert "renderRiskSignalCards" in script_response.text
    assert "상장/주가 정보를 찾을 수 없습니다" in script_response.text
    assert "renderRelationshipFilters" in script_response.text
    assert "data-relationship-filter" in script_response.text
    assert ".disclosure-event-timeline" in style_response.text
    assert "grid-template-columns: 76px 84px minmax(0, 1fr);" in style_response.text
    assert "justify-content: center;" in style_response.text
    assert "grid-template-columns: minmax(0, 1fr) auto;" in style_response.text
    assert ".disclosure-title-row" in style_response.text
    assert ".disclosure-list .disclosure-title-row" in style_response.text
    assert ".disclosure-event-title-row" in style_response.text
    assert ".stock-chart-event-marker" not in style_response.text
    assert ".company-risk-card" in style_response.text
    assert ".relationship-list-filters" in style_response.text


def test_profile_frontend_exposes_disclosure_summary_modal():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "summaryUrl" in script_response.text
    assert "data-disclosure-summary" in script_response.text
    assert "ensureDisclosureSummaryModal" in script_response.text
    assert "공시 요약" in script_response.text
    assert "renderDisclosureSummaryLoading" in script_response.text
    assert "요약을 생성하는 중입니다" in script_response.text
    assert ".disclosure-summary-modal" in style_response.text
    assert ".disclosure-summary-button" in style_response.text
    assert ".disclosure-summary-loading-card" in style_response.text
    assert "@keyframes disclosure-summary-glow" in style_response.text


def test_dart_periodic_endpoint_registry_contains_phase_one_sources():
    assert DART_PERIODIC_ENDPOINTS["major_shareholders"]["group_name"] == "dart_major_shareholders"
    assert DART_PERIODIC_ENDPOINTS["dividends"]["group_name"] == "dart_dividends"
    assert DART_PERIODIC_ENDPOINTS["audit_opinion"]["group_name"] == "dart_audit_opinion"
    assert DART_PERIODIC_ENDPOINTS["financial_ratios"]["group_name"] == "dart_financial_ratios"
    assert DART_PERIODIC_ENDPOINTS["major_shareholders"]["endpoint"].endswith(".json") is False


def test_business_group_selector_uses_official_rank_or_assets():
    ranked = select_top_business_groups(
        [
            {"unityGrupCode": "A", "unityGrupNm": "A그룹", "rn": "2"},
            {"unityGrupCode": "B", "unityGrupNm": "B그룹", "rn": "1"},
        ],
        limit=1,
    )
    assert ranked[0]["group_name"] == "B그룹"

    by_asset = select_top_business_groups(
        [
            {"unityGrupCode": "A", "unityGrupNm": "A그룹", "assetAmount": "10,000"},
            {"unityGrupCode": "B", "unityGrupNm": "B그룹", "assetAmount": "20,000"},
        ],
        limit=1,
    )
    assert by_asset[0]["group_name"] == "B그룹"

    with pytest.raises(ValueError, match="official rank or asset amount"):
        select_top_business_groups(
            [{"unityGrupCode": "A", "unityGrupNm": "A그룹"}],
            limit=1,
        )


def test_business_group_company_normalizer_keeps_identity_fields():
    normalized = normalize_business_group_company(
        {
            "afilCmpyNm": "삼성전자",
            "jurirNo": "1301110006246",
            "bizrNo": "1248100998",
            "repreNm": "전영현",
            "stockCode": "005930",
        },
        group_code="samsung",
    )

    assert normalized["group_code"] == "samsung"
    assert normalized["company_name"] == "삼성전자"
    assert normalized["legal_registration_number"] == "1301110006246"
    assert normalized["stock_code"] == "005930"


def test_shareholder_holding_normalizer_marks_name_only_matches_low_confidence():
    rows = normalize_holding_rows(
        shareholder_payload={
            "list": [
                {"nm": "계", "bsis_posesn_stock_qota_rt": "30.0"},
                {
                    "nm": "홍길동",
                    "relate": "본인",
                    "stock_knd": "보통주",
                    "bsis_posesn_stock_co": "1,000",
                    "bsis_posesn_stock_qota_rt": "10.5",
                },
            ],
        },
        executives_payload={"list": [{"nm": "홍길동", "ofcps": "대표이사"}]},
        held_company_name="테스트회사",
        held_company_corp_code="00123456",
        held_company_group_code="test-group",
        report_year="2025",
        report_code="11011",
    )

    assert len(rows) == 1
    assert rows[0]["entity"]["entity_type"] == "individual"
    assert rows[0]["entity"]["confidence_basis"] == "low"
    assert rows[0]["holding"]["holding_ratio"] == 10.5
    assert rows[0]["holding"]["share_count"] == 1000


def test_shareholder_classifier_detects_corporations():
    assert classify_shareholder(name="삼성물산(주)") == "corporation"
    assert classify_shareholder(name="삼성물산", dart_corp_code="00123456") == "corporation"
    assert classify_shareholder(name="홍길동", executive_match=True) == "individual"


def test_shareholder_search_api_degrades_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        response = client.get("/company/shareholders/search", params={"name": "홍길동"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["matches"] == []
    assert payload["corpus"]["available"] is False


def test_shareholder_api_exposes_sync_and_index_routes():
    with TestClient(app) as client:
        routes = set(client.get("/openapi.json").json()["paths"])

    assert "/company/shareholders/search" in routes
    assert "/company/shareholders/sync_top_business_groups" in routes
    assert "/company/shareholders/index_dart_holdings" in routes


def test_company_insight_normalizer_returns_stable_phase_one_shape():
    payload = normalize_dart_insights(
        {
            "major_shareholders": {
                "status": "000",
                "list": [
                    {
                        "nm": "계",
                        "bsis_posesn_stock_qota_rt": "31.0",
                    },
                    {
                        "nm": "홍길동",
                        "relate": "본인",
                        "stock_knd": "보통주",
                        "bsis_posesn_stock_co": "1,000",
                        "bsis_posesn_stock_qota_rt": "10.0",
                    },
                    {
                        "nm": "특수관계인",
                        "relate": "계열회사",
                        "bsis_posesn_stock_qota_rt": "5.5",
                    },
                    {
                        "nm": "더큰주주",
                        "relate": "계열회사",
                        "bsis_posesn_stock_qota_rt": "15.5",
                    },
                ],
            },
            "dividends": {
                "status": "000",
                "list": [
                    {
                        "se": "주당 현금배당금(원)",
                        "thstrm": "1,444",
                        "frmtrm": "1,444",
                    }
                ],
            },
            "audit_opinion": {
                "status": "000",
                "list": [
                    {
                        "bsns_year": "2025",
                        "adtor": "삼일회계법인",
                        "adt_opinion": "적정",
                    }
                ],
            },
            "financial_ratios": {
                "status": "000",
                "list": [
                    {"idx_nm": "부채비율", "idx_val": "30.0"},
                    {"idx_nm": "영업이익률", "idx_val": "15.5"},
                ],
            },
        },
        basis={
            "business_year": "2025",
            "report_code": "11011",
            "report_name": "사업보고서",
            "fs_division": "CFS",
        },
    )

    assert payload["basis"]["business_year"] == "2025"
    assert payload["basis"]["fs_division"] == "CFS"
    assert payload["ownership"]["largest_holder_name"] == "더큰주주"
    assert payload["ownership"]["largest_holder_ratio"] == "15.5"
    assert [holder["name"] for holder in payload["ownership"]["holders"]] == [
        "더큰주주",
        "홍길동",
        "특수관계인",
    ]
    assert payload["ownership"]["holders"][0] == {
        "name": "더큰주주",
        "relation": "계열회사",
        "ratio": "15.5",
        "ratio_number": 15.5,
    }
    assert payload["ownership"]["holders"][1]["ratio_number"] == 10.0
    assert payload["ownership"]["holders"][2]["ratio_number"] == 5.5
    assert payload["dividend"]["dividend_per_share"] == "1,444"
    assert payload["audit"]["auditor"] == "삼일회계법인"
    assert payload["audit"]["opinion"] == "적정"
    assert payload["ratios"]["items"][0] == {"name": "부채비율", "value": "30.0"}


def test_disclosure_event_normalizer_classifies_common_dart_titles():
    assert classify_disclosure_event("분기보고서 (2026.03)") == "periodic"
    assert classify_disclosure_event("임원ㆍ주요주주특정증권등소유상황보고서") == "ownership"
    assert classify_disclosure_event("대표이사변경") == "executive"
    assert classify_disclosure_event("유상증자결정") == "capital"
    assert classify_disclosure_event("현금ㆍ현물배당결정") == "dividend"
    assert classify_disclosure_event("감사보고서제출") == "audit"

    events = normalize_disclosure_events(
        {
            "list": [
                {
                    "rcept_dt": "20260701",
                    "report_nm": "임원ㆍ주요주주특정증권등소유상황보고서",
                    "corp_name": "삼성전자",
                    "rcept_no": "20260701000000",
                    "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do",
                }
            ]
        }
    )

    assert events[0] == {
        "date": "20260701",
        "title": "임원ㆍ주요주주특정증권등소유상황보고서",
        "category": "ownership",
        "category_label": "지분/최대주주",
        "corp_name": "삼성전자",
        "receipt_no": "20260701000000",
        "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do",
    }


def test_company_risk_signal_normalizer_separates_current_and_history_signals():
    payload = normalize_company_risk_signals(
        insights={
            "ratios": {
                "items": [
                    {"name": "부채비율", "value": "230.5"},
                    {"name": "영업이익률", "value": "-2.1"},
                    {"name": "ROE", "value": "-1.2"},
                ]
            },
            "audit": {"opinion": "한정"},
        },
        affiliate_count=40,
        subsidiary_count=12,
    )

    codes = {signal["code"] for signal in payload["signals"]}
    history_codes = {signal["code"] for signal in payload["requires_history"]}
    assert {"debt_high", "operating_margin_negative", "roe_negative", "audit_opinion_warning", "complex_group_structure"} <= codes
    assert {"major_shareholder_changed", "dividend_cut_or_stopped", "affiliate_count_changed"} <= history_codes


def test_openai_settings_are_optional_until_summary_request(monkeypatch):
    from app.core.config import get_openai_settings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_SUMMARY_MAX_CHARS", raising=False)

    settings = get_openai_settings(required=False)

    assert settings.api_key is None
    assert settings.model == "gpt-4.1-mini"
    assert settings.max_chars == 18000


def test_disclosure_text_extractor_accepts_only_dart_viewer_urls():
    from app.services.company_disclosure_summary import (
        disclosure_text_entity_key,
        validate_dart_viewer_url,
    )

    assert validate_dart_viewer_url(
        "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000"
    )
    assert disclosure_text_entity_key("20260701000000") == "20260701000000"
    assert not validate_dart_viewer_url(
        "https://example.com/dsaf001/main.do?rcpNo=20260701000000"
    )


def test_disclosure_html_to_text_removes_scripts_and_compacts_text():
    from app.services.company_disclosure_summary import extract_disclosure_text

    html = """
    <html>
      <head><script>alert('x')</script><style>body { color:red }</style></head>
      <body>
        <h1>분기보고서</h1>
        <p>매출액은 증가했습니다.</p>
        <p>영업이익은 감소했습니다.</p>
      </body>
    </html>
    """

    text = extract_disclosure_text(html)

    assert "alert" not in text
    assert "color:red" not in text
    assert "분기보고서" in text
    assert "매출액은 증가했습니다." in text
    assert "영업이익은 감소했습니다." in text


def test_disclosure_summary_normalizer_returns_stable_shape():
    from app.services.company_disclosure_summary import normalize_summary_payload

    payload = normalize_summary_payload(
        {
            "bullets": ["핵심 1", "핵심 2"],
            "risks": ["리스크 1"],
            "changes": ["변동 1"],
        }
    )

    assert payload == {
        "bullets": ["핵심 1", "핵심 2"],
        "risks": ["리스크 1"],
        "changes": ["변동 1"],
        "limitations": [],
    }


def test_company_profile_summary_normalizer_returns_stable_shape():
    from app.services.company_profile_summary import normalize_company_summary_payload

    payload = normalize_company_summary_payload(
        {
            "headline": "롯데이노베이트는 IT 서비스 기업입니다.",
            "bullets": ["공시 기반 요약", "재무 기반 요약"],
            "watch_points": ["확인 필요"],
            "data_basis": ["DART", "금융위원회"],
        }
    )

    assert payload == {
        "headline": "롯데이노베이트는 IT 서비스 기업입니다.",
        "bullets": ["공시 기반 요약", "재무 기반 요약"],
        "watch_points": ["확인 필요"],
        "data_basis": ["DART", "금융위원회"],
        "limitations": [],
    }


@pytest.mark.asyncio
async def test_openai_summary_client_parses_response_json(monkeypatch):
    from app.services.company_disclosure_summary import summarize_with_openai

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openai.com"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"bullets":["요약"],"risks":["위험"],"changes":["변동"],"limitations":[]}',
                            }
                        ]
                    }
                ]
            },
        )

    payload = await summarize_with_openai(
        title="분기보고서",
        text="매출액은 증가했습니다.",
        transport=httpx.MockTransport(handler),
    )

    assert payload["summary"]["bullets"] == ["요약"]
    assert payload["summary"]["risks"] == ["위험"]
    assert payload["model"] == "gpt-test"


@pytest.mark.asyncio
async def test_disclosure_summary_service_reuses_cached_summary(monkeypatch):
    from app.services.company_disclosure_summary import (
        DisclosureSummaryQuery,
        DisclosureSummaryService,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    store = FakeDataGroupStore()
    service = DisclosureSummaryService(
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        data_group_store=store,
    )
    store.records[
        ("company", "20260701000000", "dart_disclosure_summary:gpt-4.1-mini:v1")
    ] = fresh_record(
        {
            "receipt_no": "20260701000000",
            "title": "분기보고서",
            "summary": {
                "bullets": ["cached"],
                "risks": [],
                "changes": [],
                "limitations": [],
            },
            "model": "gpt-4.1-mini",
            "prompt_version": "v1",
        }
    )

    payload = await service.fetch(
        DisclosureSummaryQuery(
            receipt_no="20260701000000",
            viewer_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000",
            title="분기보고서",
        )
    )

    assert payload["summary"]["bullets"] == ["cached"]


@pytest.mark.asyncio
async def test_company_profile_summary_service_reuses_cached_summary(monkeypatch):
    from app.services.company_profile_summary import (
        COMPANY_PROFILE_SUMMARY_PROMPT_VERSION,
        CompanyProfileSummaryQuery,
        CompanyProfileSummaryService,
        company_profile_summary_group_name,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    store = FakeDataGroupStore()
    group_name = company_profile_summary_group_name("gpt-test")
    store.records[("company", "1101113326588", group_name)] = fresh_record(
        {
            "corporate_registration_number": "1101113326588",
            "summary": {
                "headline": "cached headline",
                "bullets": ["cached bullet"],
                "watch_points": [],
                "data_basis": ["cached basis"],
                "limitations": [],
            },
            "fingerprint": "stable",
            "model": "gpt-test",
            "prompt_version": COMPANY_PROFILE_SUMMARY_PROMPT_VERSION,
        }
    )
    service = CompanyProfileSummaryService(
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        data_group_store=store,
    )

    payload = await service.fetch(
        CompanyProfileSummaryQuery(
            corporate_registration_number="1101113326588",
            profile_payload={"fingerprint": "stable"},
        )
    )

    assert payload["summary"]["headline"] == "cached headline"
    assert payload["cached"] is True


def test_profile_frontend_exposes_async_company_profile_summary_card():
    with TestClient(app) as client:
        script_response = client.get("/profile-page-5.js")
        style_response = client.get("/styles.css")

    assert script_response.status_code == 200
    assert style_response.status_code == 200
    assert "renderCompanyProfileSummaryCard" in script_response.text
    assert "loadCompanyProfileSummary" in script_response.text
    assert "/api/company/get_company_profile_summary" in script_response.text
    assert "company-ai-summary-card" in script_response.text
    assert ".company-ai-summary-card" in style_response.text
    assert ".company-ai-summary-skeleton" in style_response.text


@pytest.mark.asyncio
async def test_dart_periodic_report_info_maps_query_to_dart_api(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url.copy_with(query=None))
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(200, json={"status": "000", "list": [{"corp_code": "00126380"}]})

    service = DartCompanyService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=FakeDataGroupStore(),
    )

    payload = await service.get_periodic_report_info(
        DartPeriodicReportInfoQuery(
            corp_code="00126380",
            business_year="2025",
            report_code="11011",
            kind="major_shareholders",
        )
    )

    assert payload["list"][0]["corp_code"] == "00126380"
    assert captured_request["url"] == "https://opendart.fss.or.kr/api/hyslrSttus.json"
    assert captured_request["params"] == {
        "crtfc_key": "dart-key",
        "corp_code": "00126380",
        "bsns_year": "2025",
        "reprt_code": "11011",
    }


def test_dart_periodic_report_ttl_expires_only_recent_periods():
    assert dart_periodic_report_ttl(
        "2025",
        "11011",
        now=datetime(2026, 7, 4, tzinfo=UTC),
    ) is None
    assert dart_periodic_report_ttl(
        "2026",
        "11013",
        now=datetime(2026, 7, 4, tzinfo=UTC),
    ) == timedelta(days=1)


@pytest.mark.asyncio
async def test_dart_financial_ratio_report_includes_required_index_class(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["params"] = dict(request.url.params)
        return httpx.Response(200, json={"status": "000", "list": [{"idx_nm": "부채비율", "idx_val": "30.0"}]})

    service = DartCompanyService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=FakeDataGroupStore(),
    )

    await service.get_periodic_report_info(
        DartPeriodicReportInfoQuery(
            corp_code="00126380",
            business_year="2025",
            report_code="11011",
            kind="financial_ratios",
            idx_cl_code="M220000",
        )
    )

    assert captured_request["params"]["idx_cl_code"] == "M220000"


@pytest.mark.asyncio
async def test_company_info_service_attaches_normalized_dart_insights(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")

    crno = "1301110006246"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/getCorpOutline_V2"):
            body = {"items": {"item": {"crno": crno, "corpNm": "삼성전자(주)"}}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": body}})
        if path.endswith("/getItemInfo"):
            body = {"items": {"item": {"srtnCd": "005930", "crno": crno}}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": body}})
        if path.endswith("/getAffiliate_V2") or path.endswith("/getConsSubsComp_V2"):
            body = {"items": {"item": []}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": body}})
        if path.endswith("/corpCode.xml"):
            return httpx.Response(200, content=dart_corp_code_zip())
        if path.endswith("/company.json"):
            return httpx.Response(200, json={"status": "000", "corp_code": "00126380", "corp_name": "삼성전자"})
        if path.endswith("/list.json"):
            return httpx.Response(
                200,
                json={
                    "status": "000",
                    "list": [
                        {
                            "rcept_dt": "20260701",
                            "report_nm": "임원ㆍ주요주주특정증권등소유상황보고서",
                            "corp_name": "삼성전자",
                            "rcept_no": "20260701000000",
                            "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do",
                        }
                    ],
                },
            )
        if path.endswith("/fnlttSinglAcnt.json"):
            return httpx.Response(
                200,
                json={
                    "status": "000",
                    "list": [
                        {
                            "fs_div": "CFS",
                            "sj_div": "BS",
                            "account_nm": "자산총계",
                            "thstrm_amount": "100",
                        }
                    ],
                },
            )
        if path.endswith("/hyslrSttus.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"nm": "삼성생명", "bsis_posesn_stock_qota_rt": "8.51"}]})
        if path.endswith("/alotMatter.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"se": "주당 현금배당금(원)", "thstrm": "1,444"}]})
        if path.endswith("/accnutAdtorNmNdAdtOpinion.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"adtor": "삼일회계법인", "adt_opinion": "적정"}]})
        if path.endswith("/fnlttSinglIndx.json"):
            return httpx.Response(200, json={"status": "000", "list": [{"idx_nm": "부채비율", "idx_val": "30.0"}]})
        raise AssertionError(path)

    service = CompanyInfoService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=FakeDataGroupStore(),
    )

    payload = await service.fetch(
        CompanyInfoQuery(corporate_registration_number=crno, page=1, per_page=10)
    )

    insights = payload["dart_insights"]
    assert insights["ownership"]["largest_holder_name"] == "삼성생명"
    assert insights["ownership"]["largest_holder_ratio"] == "8.51"
    assert insights["dividend"]["dividend_per_share"] == "1,444"
    assert insights["audit"]["opinion"] == "적정"
    assert insights["ratios"]["items"][0]["name"] == "부채비율"
    assert payload["availability"]["sections"]["basic"] == "available"
    assert payload["availability"]["sections"]["dart"] == "available"
    assert payload["disclosure_events"][0]["category"] == "ownership"
    assert "requires_history" in payload["risk_signals"]


def test_get_dart_company_insight_detail_returns_capital_detail(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stockTotqySttus.json"):
            return httpx.Response(
                200,
                json={
                    "status": "000",
                    "list": [
                        {
                            "corp_code": "00126380",
                            "rcept_no": "20260331000001",
                            "stock_code": "005930",
                            "se": "보통주",
                            "istc_totqy": "5,969,782,550",
                        }
                    ],
                },
            )
        if request.url.path.endswith("/tesstkAcqsDspsSttus.json"):
            return httpx.Response(
                200,
                json={
                    "status": "000",
                    "list": [
                        {
                            "corp_code": "00126380",
                            "rcept_no": "20260331000001",
                            "stock_code": "005930",
                            "stock_knd": "보통주",
                            "trmend_qy": "100",
                        }
                    ],
                },
            )
        raise AssertionError(request.url.path)

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_company_insight_detail",
            params={
                "corp_code": "00126380",
                "business_year": "2025",
                "report_code": "11011",
                "kind": "capital",
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "capital"
    assert payload["total_stock"][0]["istc_totqy"] == "5,969,782,550"
    assert "corp_code" not in payload["total_stock"][0]
    assert "rcept_no" not in payload["total_stock"][0]
    assert "stock_code" not in payload["total_stock"][0]
    assert payload["treasury_stock"][0]["trmend_qy"] == "100"
    assert "corp_code" not in payload["treasury_stock"][0]


def test_get_dart_company_insight_detail_rejects_unknown_kind():
    with TestClient(app) as client:
        response = client.get(
            "/company/get_dart_company_insight_detail",
            params={
                "corp_code": "00126380",
                "business_year": "2025",
                "report_code": "11011",
                "kind": "unknown",
            },
        )

    assert response.status_code == 422


def test_get_dart_disclosure_summary_endpoint_uses_service_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dart.fss.or.kr":
            return httpx.Response(
                200,
                text="<html><body><p>매출액은 증가했습니다.</p></body></html>",
            )
        if request.url.host == "api.openai.com":
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": '{"bullets":["매출 증가"],"risks":[],"changes":[],"limitations":[]}',
                                }
                            ]
                        }
                    ]
                },
            )
        raise AssertionError(str(request.url))

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_disclosure_summary",
            params={
                "receipt_no": "20260701000000",
                "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000",
                "title": "분기보고서",
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    payload = response.json()
    assert payload["receipt_no"] == "20260701000000"
    assert payload["summary"]["bullets"] == ["매출 증가"]
    assert "model" not in payload
    assert "prompt_version" not in payload
    assert "cached" not in payload


def test_get_dart_disclosure_summary_requires_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with TestClient(app) as client:
        response = client.get(
            "/company/get_dart_disclosure_summary",
            params={
                "receipt_no": "20260701000000",
                "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260701000000",
                "title": "분기보고서",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured"


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
    assert response.json()["items"][0]["corpNm"] == "삼성전자(주)"


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
    payload = response.json()
    assert payload["items"][0]["afilCmpyNm"] == "테스트회사"
    assert payload["items"][0]["name"] == "테스트회사"
    assert "body" not in payload


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
    payload = response.json()
    assert payload["items"][0]["sbrdEnpNm"] == "테스트종속기업"
    assert payload["items"][0]["name"] == "테스트종속기업"
    assert "body" not in payload


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
    payload = response.json()
    assert payload["items"][0]["corpNm"] == "삼성전자(주)"
    assert payload["items"][0]["enpRprFnm"] == "테스트대표"
    assert "body" not in payload


def test_get_corp_outline_returns_raw_payload_with_valid_jwt(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.setenv("PROFILAGE_JWT_SECRET", "test-secret")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
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
                                "enpFxno": "031-000-0000",
                            }
                        },
                    },
                }
            },
        )

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_corp_outline",
            params={"company_name": "삼성전자", "page": 1, "per_page": 10},
            headers={
                "Authorization": (
                    "Bearer "
                    + hs256_jwt({"sub": "tester", "exp": 4102444800})
                )
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    payload = response.json()
    assert payload["body"]["items"]["item"]["corpNm"] == "삼성전자(주)"
    assert payload["body"]["items"]["item"]["enpFxno"] == "031-000-0000"


def test_get_corp_outline_retries_company_name_without_case_sensitivity(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_params = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        captured_params.append(params)
        item = (
            {
                "crno": "1101112487050",
                "corpNm": "LG전자(주)",
            }
            if params.get("corpNm") == "LG전자"
            else None
        )
        body = {
            "numOfRows": "10",
            "pageNo": "1",
            "totalCount": "1" if item else "0",
        }
        if item:
            body["items"] = {"item": item}
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
            "/company/get_corp_outline",
            params={"company_name": "lg전자", "page": 1, "per_page": 10},
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert [params["corpNm"] for params in captured_params] == ["lg전자", "LG전자"]
    assert response.json()["items"][0]["corpNm"] == "LG전자(주)"


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
    payload = response.json()
    assert payload["items"][0]["srtnCd"] == "005930"
    assert payload["items"][0]["itmsNm"] == "삼성전자"
    assert "body" not in payload


def test_get_krx_listed_item_retries_item_name_without_case_sensitivity(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)

    captured_params = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        captured_params.append(params)
        item = (
            {
                "srtnCd": "066570",
                "itmsNm": "LG전자",
                "crno": "1101112487050",
                "corpNm": "LG전자(주)",
            }
            if params.get("itmsNm") == "LG전자"
            else None
        )
        body = {
            "numOfRows": "10",
            "pageNo": "1",
            "totalCount": "1" if item else "0",
        }
        if item:
            body["items"] = {"item": item}
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
            "/company/get_krx_listed_item",
            params={"item_name": "lg전자", "page": 1, "per_page": 10},
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert [params["itmsNm"] for params in captured_params] == ["lg전자", "LG전자"]
    assert response.json()["items"][0]["itmsNm"] == "LG전자"


def test_get_krx_listed_item_requires_a_search_condition():
    with TestClient(app) as client:
        response = client.get("/company/get_krx_listed_item")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "one of corporate_registration_number, company_name, item_name, or isin_code is required"
    )


def test_get_company_info_returns_compact_frontend_payload_without_jwt(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)
    monkeypatch.delenv("DART_API_KEY", raising=False)

    crno = "1301110006246"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getCorpOutline_V2"):
            body = {
                "items": {
                    "item": {
                        "crno": crno,
                        "corpNm": "삼성전자(주)",
                        "corpEnsnNm": "SAMSUNG ELECTRONICS CO.,LTD",
                        "enpRprFnm": "전영현, 노태문",
                        "corpRegMrktDcdNm": "KOSPI",
                        "enpMainBizNm": "이동전화기 제조업",
                        "enpEstbDt": "19690113",
                        "enpEmpeCnt": "128881",
                        "enpTlno": "02-2255-0114",
                        "bzno": "1248100998",
                        "enpBsadr": "경기도 수원시 영통구 삼성로 129",
                        "enpHmpgUrl": "https://www.samsung.com/sec/",
                        "basDt": "20260701",
                    }
                }
            }
        elif request.url.path.endswith("/getItemInfo"):
            body = {
                "items": {
                    "item": {
                        "srtnCd": "005930",
                        "crno": crno,
                        "itmsNm": "삼성전자",
                        "mrktCtg": "KOSPI",
                    }
                }
            }
        elif request.url.path.endswith("/getAffiliate_V2"):
            body = {
                "items": {
                    "item": [
                        {"afilCmpyNm": "삼성디스플레이", "lstgYn": "N"},
                        {"afilCmpyNm": "삼성물산", "lstgYn": "Y"},
                    ]
                }
            }
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

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_company_info",
            params={"corporate_registration_number": crno},
        )
        del app.state.http_transport

    assert response.status_code == 200
    payload = response.json()
    assert payload["corporate_registration_number"] == crno
    assert payload["company"]["name"] == "삼성전자(주)"
    assert payload["company"]["employee_count"] == "128881"
    assert payload["listing"]["short_code"] == "005930"
    assert payload["listing"]["is_listed"] is True
    assert payload["relationships"]["affiliate_count"] == 2
    assert payload["relationships"]["subsidiary_count"] == 1
    assert payload["relationships"]["listed_affiliate_count"] == 1
    assert payload["relationships"]["affiliates"][0]["name"] == "삼성디스플레이"
    assert payload["availability"]["sections"]["basic"] == "available"
    assert "corp_outline" not in payload
    assert "krx_listed_item" not in payload
    assert "dart_insights" not in payload


def test_get_company_info_rejects_invalid_jwt(monkeypatch):
    monkeypatch.setenv("PROFILAGE_JWT_SECRET", "test-secret")

    with TestClient(app) as client:
        response = client.get(
            "/company/get_company_info",
            params={"corporate_registration_number": "1301110006246"},
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authorization token"


def test_get_company_info_combines_company_sources_by_corporate_registration_number_with_valid_jwt(
    monkeypatch,
):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)
    monkeypatch.setenv("PROFILAGE_JWT_SECRET", "test-secret")

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
            headers={
                "Authorization": (
                    "Bearer "
                    + hs256_jwt({"sub": "tester", "exp": 4102444800})
                )
            },
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


def test_get_company_info_keeps_outline_when_optional_sources_fail(monkeypatch):
    monkeypatch.setenv("OPEN_API_DECODING_KEY", "decoded-service-key")
    monkeypatch.delenv("OPEN_API_ENCODING_KEY", raising=False)
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    crno = "2147140003011"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getCorpOutline_V2"):
            body = {
                "numOfRows": 10,
                "pageNo": 1,
                "totalCount": 1,
                "items": {
                    "item": {
                        "crno": crno,
                        "corpNm": "비상장테스트(주)",
                        "corpEnsnNm": "PRIVATE TEST CO.,LTD.",
                        "enpRprFnm": "테스트대표",
                    }
                },
            }
            return httpx.Response(200, json={"response": {"body": body}})
        if request.url.path.endswith("/getItemInfo"):
            return httpx.Response(502, json={"detail": "KRX unavailable"})
        if request.url.path.endswith("/getAffiliate_V2"):
            return httpx.Response(502, json={"detail": "Affiliate unavailable"})
        if request.url.path.endswith("/getConsSubsComp_V2"):
            return httpx.Response(502, json={"detail": "Subsidiary unavailable"})
        if request.url.path.endswith("/corpCode.xml"):
            return httpx.Response(200, content=dart_corp_code_zip())
        return httpx.Response(404, json={})

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_company_info",
            params={"corporate_registration_number": crno},
        )
        del app.state.http_transport

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["name"] == "비상장테스트(주)"
    assert payload["company"]["english_name"] == "PRIVATE TEST CO.,LTD."
    assert payload["listing"]["is_listed"] is False
    assert payload["relationships"]["affiliate_count"] == 0
    assert payload["relationships"]["subsidiary_count"] == 0
    assert payload["availability"]["sections"]["listed"] == "missing"
    assert payload["dart"]["corp_code"] is None
    assert "corp_outline" not in payload


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
    assert stock_price_ttl("KRX", "1D", market_open).total_seconds() == 60
    assert stock_price_ttl("KRX", "5D", market_open).total_seconds() == 300
    assert is_krx_market_open(market_closed) is False
    assert stock_price_ttl("KRX", "1D", market_closed).total_seconds() == 600
    assert stock_price_ttl("NASDAQ", "1D", market_open).total_seconds() == 600
    assert stock_price_ttl("KRX", "1M", market_open).total_seconds() == 1800
    assert stock_price_ttl("KRX", "6M", market_open).total_seconds() == 7200
    assert stock_price_ttl("KRX", "1Y", market_open).total_seconds() == 14400
    assert stock_price_ttl("KRX", "5Y", market_open).total_seconds() == 86400
    assert stock_price_ttl("KRX", "MAX", market_open).total_seconds() == 86400


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
    assert cache.set_calls[0][2] == 1800


@pytest.mark.asyncio
async def test_stock_price_data_group_response_includes_cache_metadata(monkeypatch):
    monkeypatch.setenv("SEARCHAPI_API_KEY", "searchapi-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "search_parameters": {"window": "1M"},
                "summary": {"stock": "005930", "price": 1234.0},
            },
        )

    store = FakeDataGroupStore()
    service = CompanyStockPriceService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=store,
    )

    payload = await service.fetch(
        CompanyStockPriceQuery(
            q=None,
            stock_code="005930",
            exchange="KRX",
            language="ko",
            window="1M",
        )
    )

    assert payload["_meta"]["source"] == "searchapi:google_finance"
    assert payload["_meta"]["cache_group"] == STOCK_PRICE_GROUP
    assert payload["_meta"]["fetched_at"]
    assert payload["_meta"]["expires_at"]
    assert payload["_meta"]["ttl_seconds"] == 1800


@pytest.mark.asyncio
async def test_stock_price_service_falls_back_to_latest_5d_session_for_empty_1d(monkeypatch):
    monkeypatch.setenv("SEARCHAPI_API_KEY", "searchapi-key")
    requested_windows = []

    def handler(request: httpx.Request) -> httpx.Response:
        window = request.url.params.get("window")
        requested_windows.append(window)
        if window == "1D":
            return httpx.Response(200, json={"summary": {}, "graph": []})
        return httpx.Response(
            200,
            json={
                "search_parameters": {"window": "5D"},
                "summary": {
                    "title": "Samsung Electronics Co Ltd",
                    "stock": "005930",
                    "exchange": "KRX",
                    "price": 309500,
                },
                "graph": [
                    {
                        "date": "Jul 02 2026, 03:30 PM UTC+09:00",
                        "price": 286000.0,
                    },
                    {
                        "date": "Jul 03 2026, 09:30 AM UTC+09:00",
                        "price": 304000.0,
                    },
                    {
                        "date": "Jul 03 2026, 03:30 PM UTC+09:00",
                        "price": 309500.0,
                    },
                ],
            },
        )

    service = CompanyStockPriceService(
        transport=httpx.MockTransport(handler),
        cache=FakeJsonCache(),
        data_group_store=None,
    )

    payload = await service.fetch(
        CompanyStockPriceQuery(
            q=None,
            stock_code="005930",
            exchange="KRX",
            language="ko",
            window="1D",
        )
    )

    assert requested_windows == ["1D", "5D"]
    assert payload["search_parameters"]["window"] == "1D"
    assert payload["search_parameters"]["fallback_window"] == "5D"
    assert [point["date"] for point in payload["graph"]] == [
        "Jul 03 2026, 09:30 AM UTC+09:00",
        "Jul 03 2026, 03:30 PM UTC+09:00",
    ]
    assert payload["summary"]["price"] == 309500


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
                "graph": [
                    {"date": "2026-07-01", "price": 1200, "volume": 100},
                    {"date": "2026-07-02", "price": 1234, "volume": 200},
                ],
                "compare_to": [{"name": "Other"}],
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
    payload = response.json()
    assert payload["summary"]["stock"] == "005930"
    assert payload["graph"][0] == {
        "date": "2026-07-01",
        "price": 1200,
        "volume": 100,
    }
    assert "_meta" not in payload
    assert "compare_to" not in payload
    assert "search_parameters" not in payload


def test_get_stock_price_returns_full_payload_with_valid_jwt(monkeypatch):
    monkeypatch.setenv("SEARCHAPI_API_KEY", "searchapi-key")
    monkeypatch.setenv("PROFILAGE_JWT_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "search_parameters": {"engine": "google_finance"},
                "summary": {"stock": "005930", "price": 1234.0},
                "graph": [{"date": "2026-07-01", "price": 1200}],
                "compare_to": [{"name": "Other"}],
            },
        )

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_stock_price",
            params={
                "stock_code": "005930",
                "exchange": "KRX",
                "language": "ko",
                "window": "1M",
            },
            headers={
                "Authorization": (
                    "Bearer "
                    + hs256_jwt({"sub": "tester", "exp": 4102444800})
                )
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["stock"] == "005930"
    assert payload["compare_to"] == [{"name": "Other"}]
    assert payload["search_parameters"] == {"engine": "google_finance"}


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
    assert "_meta" not in response.json()


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
                        "corp_code": "00126380",
                        "rcept_no": "20260331000001",
                        "stock_code": "005930",
                        "account_nm": "매출액",
                        "sj_nm": "손익계산서",
                        "currency": "KRW",
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
    row = response.json()["list"][0]
    assert row["account_nm"] == "매출액"
    assert row["sj_nm"] == "손익계산서"
    assert row["currency"] == "KRW"
    assert "corp_code" not in row
    assert "rcept_no" not in row
    assert "stock_code" not in row
    assert "_meta" not in response.json()


def test_get_dart_financial_trends_returns_last_five_years(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        captured_requests.append(params)
        year = int(params["bsns_year"])
        return httpx.Response(
            200,
            json={
                "status": "000",
                "message": "정상",
                "list": [
                    {
                        "bsns_year": str(year),
                        "corp_code": "00126380",
                        "rcept_no": f"{year}0331000001",
                        "stock_code": "005930",
                        "reprt_code": params["reprt_code"],
                        "fs_div": params["fs_div"],
                        "account_nm": "자산총계",
                        "thstrm_amount": str(year * 1000),
                    },
                    {
                        "bsns_year": str(year),
                        "reprt_code": params["reprt_code"],
                        "fs_div": params["fs_div"],
                        "account_nm": "부채총계",
                        "thstrm_amount": str(year * 500),
                    },
                ],
            },
        )

    with TestClient(app) as client:
        app.state.http_transport = httpx.MockTransport(handler)
        response = client.get(
            "/company/get_dart_financial_trends",
            params={
                "corp_code": "00126380",
                "end_year": "2026",
                "report_code": "11011",
                "fs_division": "CFS",
            },
        )
        del app.state.http_transport

    assert response.status_code == 200
    assert [request["bsns_year"] for request in captured_requests] == [
        "2026",
        "2025",
        "2024",
        "2023",
        "2022",
    ]
    payload = response.json()
    assert payload["selected"] == {
        "end_year": "2026",
        "report_code": "11011",
        "fs_division": "CFS",
        "years": 5,
    }
    assert [period["business_year"] for period in payload["periods"]] == [
        "2022",
        "2023",
        "2024",
        "2025",
        "2026",
    ]
    assert payload["periods"][-1]["accounts"][0]["account_nm"] == "자산총계"
    assert "corp_code" not in payload["periods"][-1]["accounts"][0]
    assert "rcept_no" not in payload["periods"][-1]["accounts"][0]
    assert "stock_code" not in payload["periods"][-1]["accounts"][0]


def test_dart_financial_accounts_ttl_expires_only_recent_periods():
    stable_query = DartFinancialAccountsQuery(
        corp_code="00126380",
        business_year="2025",
        report_code="11011",
        fs_division="CFS",
    )
    recent_query = DartFinancialAccountsQuery(
        corp_code="00126380",
        business_year="2026",
        report_code="11012",
        fs_division="CFS",
    )

    assert dart_financial_accounts_ttl(
        stable_query,
        now=datetime(2026, 7, 4, tzinfo=UTC),
    ) is None
    assert dart_financial_accounts_ttl(
        recent_query,
        now=datetime(2026, 7, 4, tzinfo=UTC),
    ) == timedelta(days=1)


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
                    "sj_div": "IS",
                    "account_nm": "매출액",
                    "thstrm_amount": "100000000",
                }
            ]
        elif (year, report_code) == ("2025", "11013"):
            items = [
                {
                    "bsns_year": "2025",
                    "reprt_code": "11013",
                    "fs_div": "CFS",
                    "sj_div": "IS",
                    "account_nm": "매출액",
                    "thstrm_amount": "80000000",
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
    assert payload["quarter"]["accounts"]["list"][0]["yoy_amount"] == "80000000"
    assert payload["quarter"]["accounts"]["list"][0]["yoy_business_year"] == "2025"
    assert payload["quarter"]["accounts"]["list"][0]["yoy_report_code"] == "11013"
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
