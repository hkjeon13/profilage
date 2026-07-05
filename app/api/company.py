from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.api.auth import has_valid_full_response_jwt
from app.services.company_affiliate import (
    CompanyAffiliateQuery,
    CompanyAffiliateService,
    CompanyConsSubsCompQuery,
    CompanyConsSubsCompService,
    CompanyCorpOutlineQuery,
    CompanyCorpOutlineService,
    CompanyInfoQuery,
    CompanyInfoService,
    CompanyKrxListedItemQuery,
    CompanyKrxListedItemService,
    CompanyStockPriceQuery,
    CompanyStockPriceService,
    compact_company_info_payload,
    compact_dart_disclosures_payload,
    compact_dart_financial_accounts_payload,
    compact_dart_financial_trends_payload,
    compact_openapi_payload,
    compact_stock_price_payload,
)
from app.services.company_dart import (
    DartCompanyQuery,
    DartCompanyService,
    DartCorpCodeQuery,
    DartDisclosureQuery,
    DartFinancialAccountsQuery,
    DartFinancialTrendsQuery,
)
from app.services.company_disclosure_summary import (
    DisclosureSummaryQuery,
    DisclosureSummaryService,
)
from app.services.company_insights import (
    normalize_capital_detail,
    normalize_people_detail,
)
from app.services.company_profile_summary import (
    CompanyProfileSummaryQuery,
    CompanyProfileSummaryService,
)
from app.services.company_store import get_default_data_group_store

router = APIRouter(prefix="/company", tags=["company"])


SUMMARY_INTERNAL_KEYS = {"cached", "fingerprint", "model", "prompt_version"}


def _public_summary_payload(payload: dict) -> dict:
    return {
        key: value
        for key, value in payload.items()
        if key not in SUMMARY_INTERNAL_KEYS
    }


def _public_dart_corp_code_payload(payload: dict) -> dict:
    def compact_match(row: dict | None) -> dict | None:
        if not isinstance(row, dict):
            return None
        keys = ["corp_code", "corp_name", "corp_eng_name", "stock_code"]
        return {
            key: row.get(key)
            for key in keys
            if row.get(key) not in (None, "")
        }

    matches = payload.get("matches", [])
    if not isinstance(matches, list):
        matches = []
    return {
        "status": payload.get("status"),
        "message": payload.get("message"),
        "match": compact_match(payload.get("match")),
        "matches": [
            item
            for item in (compact_match(row) for row in matches)
            if item
        ],
    }


def _public_dart_company_payload(payload: dict) -> dict:
    keys = [
        "status",
        "message",
        "corp_code",
        "corp_name",
        "corp_name_eng",
        "stock_code",
        "ceo_nm",
        "corp_cls",
        "jurir_no",
        "bizr_no",
        "adres",
        "hm_url",
        "phn_no",
        "est_dt",
        "acc_mt",
    ]
    return {
        key: payload.get(key)
        for key in keys
        if payload.get(key) not in (None, "")
    }


def _public_insight_detail_payload(payload: dict) -> dict:
    if payload.get("kind") == "people":
        executive_keys = [
            "nm",
            "sexdstn",
            "birth_ym",
            "ofcps",
            "rgist_exctv_at",
            "fte_at",
            "chrg_job",
            "main_career",
            "mxmm_shrholdr_relate",
            "hffc_pd",
            "tenure_end_on",
            "stlm_dt",
        ]
        employee_keys = [
            "fo_bbm",
            "sexdstn",
            "reform_bfe_emp_co_rgllbr",
            "reform_bfe_emp_co_cnttk",
            "reform_bfe_emp_co_etc",
            "rgllbr_co",
            "rgllbr_abacpt_labrr_co",
            "cnttk_co",
            "cnttk_abacpt_labrr_co",
            "sm",
            "avrg_cnwk_sdytrn",
            "fyer_salary_totamt",
            "jan_salary_am",
            "rm",
            "stlm_dt",
        ]
        return {
            "kind": "people",
            "executives": [
                {
                    key: row.get(key)
                    for key in executive_keys
                    if row.get(key) not in (None, "")
                }
                for row in payload.get("executives", [])
                if isinstance(row, dict)
            ],
            "employees": [
                {
                    key: row.get(key)
                    for key in employee_keys
                    if row.get(key) not in (None, "")
                }
                for row in payload.get("employees", [])
                if isinstance(row, dict)
            ],
        }

    stock_keys = [
        "se",
        "stock_knd",
        "istc_totqy",
        "trmend_qy",
        "acqs_stock_qy",
        "dsps_stock_qy",
        "qota_rt",
        "stock_qota_rt",
        "bsis_qy",
        "bsis_posesn_stock_co",
        "incrs_qy",
        "dcrs_qy",
        "trmend_posesn_stock_co",
        "stlm_dt",
    ]
    return {
        "kind": "capital",
        "total_stock": [
            {
                key: row.get(key)
                for key in stock_keys
                if row.get(key) not in (None, "")
            }
            for row in payload.get("total_stock", [])
            if isinstance(row, dict)
        ],
        "treasury_stock": [
            {
                key: row.get(key)
                for key in stock_keys
                if row.get(key) not in (None, "")
            }
            for row in payload.get("treasury_stock", [])
            if isinstance(row, dict)
        ],
    }


@router.get("/get_affiliate")
async def get_affiliate(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    company_name: Annotated[
        str | None, Query(description="계열 회사명")
    ] = None,
    corporate_registration_number: Annotated[
        str | None, Query(description="법인등록번호")
    ] = None,
    base_date: Annotated[
        str | None, Query(description="기준일자(YYYYMMDD)")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=1000)] = 10,
):
    if not company_name and not corporate_registration_number:
        raise HTTPException(
            status_code=400,
            detail="company_name or corporate_registration_number is required",
        )

    wants_full_response = has_valid_full_response_jwt(authorization)
    service = CompanyAffiliateService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.fetch(
        CompanyAffiliateQuery(
            company_name=company_name,
            corporate_registration_number=corporate_registration_number,
            base_date=base_date,
            page=page,
            per_page=per_page,
        )
    )
    if wants_full_response:
        return payload
    return compact_openapi_payload(payload, kind="affiliate")


@router.get("/get_cons_subs_comp")
async def get_cons_subs_comp(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    subsidiary_name: Annotated[
        str | None, Query(description="종속기업명")
    ] = None,
    corporate_registration_number: Annotated[
        str | None, Query(description="법인등록번호")
    ] = None,
    base_date: Annotated[
        str | None, Query(description="기준일자(YYYYMMDD)")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=1000)] = 10,
):
    if not subsidiary_name and not corporate_registration_number:
        raise HTTPException(
            status_code=400,
            detail="subsidiary_name or corporate_registration_number is required",
        )

    wants_full_response = has_valid_full_response_jwt(authorization)
    service = CompanyConsSubsCompService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.fetch(
        CompanyConsSubsCompQuery(
            subsidiary_name=subsidiary_name,
            corporate_registration_number=corporate_registration_number,
            base_date=base_date,
            page=page,
            per_page=per_page,
        )
    )
    if wants_full_response:
        return payload
    return compact_openapi_payload(payload, kind="subsidiary")


@router.get("/get_corp_outline")
async def get_corp_outline(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    company_name: Annotated[
        str | None, Query(description="법인명")
    ] = None,
    corporate_registration_number: Annotated[
        str | None, Query(description="법인등록번호")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=1000)] = 10,
):
    if not company_name and not corporate_registration_number:
        raise HTTPException(
            status_code=400,
            detail="company_name or corporate_registration_number is required",
        )

    wants_full_response = has_valid_full_response_jwt(authorization)
    service = CompanyCorpOutlineService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.fetch(
        CompanyCorpOutlineQuery(
            company_name=company_name,
            corporate_registration_number=corporate_registration_number,
            page=page,
            per_page=per_page,
        )
    )
    if wants_full_response:
        return payload
    return compact_openapi_payload(payload, kind="corp_outline")


@router.get("/get_krx_listed_item")
async def get_krx_listed_item(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    corporate_registration_number: Annotated[
        str | None, Query(description="법인등록번호")
    ] = None,
    company_name: Annotated[
        str | None, Query(description="법인명")
    ] = None,
    item_name: Annotated[
        str | None, Query(description="종목명")
    ] = None,
    isin_code: Annotated[
        str | None, Query(description="ISIN 코드")
    ] = None,
    base_date: Annotated[
        str | None, Query(description="기준일자(YYYYMMDD)")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=1000)] = 10,
):
    if not any(
        [corporate_registration_number, company_name, item_name, isin_code]
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "one of corporate_registration_number, company_name, "
                "item_name, or isin_code is required"
            ),
        )

    wants_full_response = has_valid_full_response_jwt(authorization)
    service = CompanyKrxListedItemService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.fetch(
        CompanyKrxListedItemQuery(
            corporate_registration_number=corporate_registration_number,
            company_name=company_name,
            item_name=item_name,
            isin_code=isin_code,
            base_date=base_date,
            page=page,
            per_page=per_page,
        )
    )
    if wants_full_response:
        return payload
    return compact_openapi_payload(payload, kind="krx_listed_item")


@router.get("/get_company_info")
async def get_company_info(
    request: Request,
    corporate_registration_number: Annotated[
        str, Query(description="법인등록번호")
    ],
    authorization: Annotated[str | None, Header()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=1000)] = 10,
):
    wants_full_response = has_valid_full_response_jwt(authorization)
    service = CompanyInfoService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.fetch(
        CompanyInfoQuery(
            corporate_registration_number=corporate_registration_number,
            page=page,
            per_page=per_page,
        )
    )
    if wants_full_response:
        return payload
    return compact_company_info_payload(payload)


@router.get("/get_stock_price")
async def get_stock_price(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    q: Annotated[
        str | None, Query(description="Google Finance query, e.g. 005930:KRX")
    ] = None,
    stock_code: Annotated[
        str | None, Query(description="종목 코드")
    ] = None,
    exchange: Annotated[
        str | None, Query(description="거래소 코드, e.g. KRX, NASDAQ")
    ] = None,
    language: Annotated[
        str | None, Query(description="Google Finance language, e.g. ko, en")
    ] = None,
    window: Annotated[
        str | None, Query(description="Chart window, e.g. 1D, 5D, 1M, 6M, YTD, 1Y, 5Y, MAX")
    ] = None,
    corporate_registration_number: Annotated[
        str | None, Query(description="법인등록번호")
    ] = None,
):
    if not q and not stock_code:
        raise HTTPException(
            status_code=400,
            detail="q or stock_code is required",
        )

    wants_full_response = has_valid_full_response_jwt(authorization)
    service = CompanyStockPriceService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.fetch(
        CompanyStockPriceQuery(
            q=q,
            stock_code=stock_code,
            exchange=exchange,
            language=language,
            window=window,
            corporate_registration_number=corporate_registration_number,
        )
    )
    if wants_full_response:
        return payload
    return compact_stock_price_payload(payload)


@router.get("/get_dart_corp_code")
async def get_dart_corp_code(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    corporate_registration_number: Annotated[
        str | None, Query(description="법인등록번호")
    ] = None,
    stock_code: Annotated[
        str | None, Query(description="종목 코드")
    ] = None,
    company_name: Annotated[
        str | None, Query(description="회사명")
    ] = None,
):
    if not any([corporate_registration_number, stock_code, company_name]):
        raise HTTPException(
            status_code=400,
            detail="one of corporate_registration_number, stock_code, or company_name is required",
        )

    service = DartCompanyService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.find_corp_code(
        DartCorpCodeQuery(
            corporate_registration_number=corporate_registration_number,
            stock_code=stock_code,
            company_name=company_name,
        )
    )
    if has_valid_full_response_jwt(authorization):
        return payload
    return _public_dart_corp_code_payload(payload)


@router.get("/get_dart_company")
async def get_dart_company(
    request: Request,
    corp_code: Annotated[str, Query(description="DART 고유번호")],
    authorization: Annotated[str | None, Header()] = None,
):
    service = DartCompanyService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.get_company(DartCompanyQuery(corp_code=corp_code))
    if has_valid_full_response_jwt(authorization):
        return payload
    return _public_dart_company_payload(payload)


@router.get("/get_dart_disclosures")
async def get_dart_disclosures(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    corp_code: Annotated[
        str | None, Query(description="DART 고유번호")
    ] = None,
    begin_date: Annotated[
        str | None, Query(description="시작일자(YYYYMMDD)")
    ] = None,
    end_date: Annotated[
        str | None, Query(description="종료일자(YYYYMMDD)")
    ] = None,
    disclosure_type: Annotated[
        str | None, Query(description="공시유형")
    ] = None,
    disclosure_detail_type: Annotated[
        str | None, Query(description="공시상세유형")
    ] = None,
    corporation_class: Annotated[
        str | None, Query(description="법인구분")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 10,
):
    service = DartCompanyService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.get_disclosures(
        DartDisclosureQuery(
            corp_code=corp_code,
            begin_date=begin_date,
            end_date=end_date,
            disclosure_type=disclosure_type,
            disclosure_detail_type=disclosure_detail_type,
            corporation_class=corporation_class,
            page=page,
            per_page=per_page,
        )
    )
    if has_valid_full_response_jwt(authorization):
        return payload
    return compact_dart_disclosures_payload(payload)


@router.get("/get_dart_disclosure_summary")
async def get_dart_disclosure_summary(
    request: Request,
    receipt_no: Annotated[str, Query(description="DART 접수번호")],
    viewer_url: Annotated[str, Query(description="DART viewer URL")],
    authorization: Annotated[str | None, Header()] = None,
    title: Annotated[str | None, Query(description="공시 제목")] = None,
):
    service = DisclosureSummaryService(
        transport=getattr(request.app.state, "http_transport", None),
        data_group_store=get_default_data_group_store(),
    )
    payload = await service.fetch(
        DisclosureSummaryQuery(
            receipt_no=receipt_no,
            viewer_url=viewer_url,
            title=title,
        )
    )
    if has_valid_full_response_jwt(authorization):
        return payload
    return _public_summary_payload(payload)


@router.get("/get_company_profile_summary")
async def get_company_profile_summary(
    request: Request,
    corporate_registration_number: Annotated[
        str, Query(description="법인등록번호")
    ],
    authorization: Annotated[str | None, Header()] = None,
):
    transport = getattr(request.app.state, "http_transport", None)
    store = get_default_data_group_store()
    profile_service = CompanyInfoService(
        transport=transport,
        data_group_store=store,
    )
    profile_payload = await profile_service.fetch(
        CompanyInfoQuery(
            corporate_registration_number=corporate_registration_number,
            page=1,
            per_page=10,
        )
    )
    summary_service = CompanyProfileSummaryService(
        transport=transport,
        data_group_store=store,
    )
    payload = await summary_service.fetch(
        CompanyProfileSummaryQuery(
            corporate_registration_number=corporate_registration_number,
            profile_payload=profile_payload,
        )
    )
    if has_valid_full_response_jwt(authorization):
        return payload
    return _public_summary_payload(payload)


@router.get("/get_dart_financial_accounts")
async def get_dart_financial_accounts(
    request: Request,
    corp_code: Annotated[str, Query(description="DART 고유번호")],
    business_year: Annotated[str, Query(description="사업연도(YYYY)")],
    authorization: Annotated[str | None, Header()] = None,
    report_code: Annotated[
        str, Query(description="보고서 코드: 11011 사업보고서, 11012 반기, 11013 1분기, 11014 3분기")
    ] = "11011",
    fs_division: Annotated[
        str | None, Query(description="CFS 연결재무제표, OFS 재무제표")
    ] = "CFS",
):
    service = DartCompanyService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.get_financial_accounts(
        DartFinancialAccountsQuery(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
            fs_division=fs_division,
        )
    )
    if has_valid_full_response_jwt(authorization):
        return payload
    return compact_dart_financial_accounts_payload(payload)


@router.get("/get_dart_financial_trends")
async def get_dart_financial_trends(
    request: Request,
    corp_code: Annotated[str, Query(description="DART 고유번호")],
    end_year: Annotated[str, Query(description="마지막 사업연도(YYYY)")],
    authorization: Annotated[str | None, Header()] = None,
    report_code: Annotated[
        str, Query(description="보고서 코드: 11011 사업보고서, 11012 반기, 11013 1분기, 11014 3분기")
    ] = "11011",
    fs_division: Annotated[
        str | None, Query(description="CFS 연결재무제표, OFS 재무제표")
    ] = "CFS",
    years: Annotated[int, Query(ge=1, le=10)] = 5,
):
    service = DartCompanyService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    payload = await service.get_financial_trends(
        DartFinancialTrendsQuery(
            corp_code=corp_code,
            end_year=end_year,
            report_code=report_code,
            fs_division=fs_division,
            years=years,
        )
    )
    if has_valid_full_response_jwt(authorization):
        return payload
    return compact_dart_financial_trends_payload(payload)


@router.get("/get_dart_company_insight_detail")
async def get_dart_company_insight_detail(
    request: Request,
    corp_code: Annotated[str, Query(description="DART 고유번호")],
    business_year: Annotated[str, Query(description="사업연도(YYYY)")],
    authorization: Annotated[str | None, Header()] = None,
    report_code: Annotated[
        str,
        Query(description="보고서 코드: 11011 사업보고서, 11012 반기, 11013 1분기, 11014 3분기"),
    ] = "11011",
    kind: Annotated[Literal["capital", "people"], Query(description="상세 정보 종류")] = "capital",
):
    service = DartCompanyService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    if kind == "capital":
        raw = await service.get_company_capital_sources(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
        )
        payload = normalize_capital_detail(raw)
        if has_valid_full_response_jwt(authorization):
            return payload
        return _public_insight_detail_payload(payload)
    raw = await service.get_company_people_sources(
        corp_code=corp_code,
        business_year=business_year,
        report_code=report_code,
    )
    payload = normalize_people_detail(raw)
    if has_valid_full_response_jwt(authorization):
        return payload
    return _public_insight_detail_payload(payload)
