from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

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
)
from app.services.company_dart import (
    DartCompanyQuery,
    DartCompanyService,
    DartCorpCodeQuery,
    DartDisclosureQuery,
    DartFinancialAccountsQuery,
    DartFinancialTrendsQuery,
)

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/get_affiliate")
async def get_affiliate(
    request: Request,
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

    service = CompanyAffiliateService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    return await service.fetch(
        CompanyAffiliateQuery(
            company_name=company_name,
            corporate_registration_number=corporate_registration_number,
            base_date=base_date,
            page=page,
            per_page=per_page,
        )
    )


@router.get("/get_cons_subs_comp")
async def get_cons_subs_comp(
    request: Request,
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

    service = CompanyConsSubsCompService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    return await service.fetch(
        CompanyConsSubsCompQuery(
            subsidiary_name=subsidiary_name,
            corporate_registration_number=corporate_registration_number,
            base_date=base_date,
            page=page,
            per_page=per_page,
        )
    )


@router.get("/get_corp_outline")
async def get_corp_outline(
    request: Request,
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

    service = CompanyCorpOutlineService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    return await service.fetch(
        CompanyCorpOutlineQuery(
            company_name=company_name,
            corporate_registration_number=corporate_registration_number,
            page=page,
            per_page=per_page,
        )
    )


@router.get("/get_krx_listed_item")
async def get_krx_listed_item(
    request: Request,
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

    service = CompanyKrxListedItemService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    return await service.fetch(
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


@router.get("/get_company_info")
async def get_company_info(
    request: Request,
    corporate_registration_number: Annotated[
        str, Query(description="법인등록번호")
    ],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=1000)] = 10,
):
    service = CompanyInfoService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    return await service.fetch(
        CompanyInfoQuery(
            corporate_registration_number=corporate_registration_number,
            page=page,
            per_page=per_page,
        )
    )


@router.get("/get_stock_price")
async def get_stock_price(
    request: Request,
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

    service = CompanyStockPriceService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    return await service.fetch(
        CompanyStockPriceQuery(
            q=q,
            stock_code=stock_code,
            exchange=exchange,
            language=language,
            window=window,
            corporate_registration_number=corporate_registration_number,
        )
    )


@router.get("/get_dart_corp_code")
async def get_dart_corp_code(
    request: Request,
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
    return await service.find_corp_code(
        DartCorpCodeQuery(
            corporate_registration_number=corporate_registration_number,
            stock_code=stock_code,
            company_name=company_name,
        )
    )


@router.get("/get_dart_company")
async def get_dart_company(
    request: Request,
    corp_code: Annotated[str, Query(description="DART 고유번호")],
):
    service = DartCompanyService(
        transport=getattr(request.app.state, "http_transport", None)
    )
    return await service.get_company(DartCompanyQuery(corp_code=corp_code))


@router.get("/get_dart_disclosures")
async def get_dart_disclosures(
    request: Request,
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
    return await service.get_disclosures(
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


@router.get("/get_dart_financial_accounts")
async def get_dart_financial_accounts(
    request: Request,
    corp_code: Annotated[str, Query(description="DART 고유번호")],
    business_year: Annotated[str, Query(description="사업연도(YYYY)")],
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
    return await service.get_financial_accounts(
        DartFinancialAccountsQuery(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
            fs_division=fs_division,
        )
    )


@router.get("/get_dart_financial_trends")
async def get_dart_financial_trends(
    request: Request,
    corp_code: Annotated[str, Query(description="DART 고유번호")],
    end_year: Annotated[str, Query(description="마지막 사업연도(YYYY)")],
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
    return await service.get_financial_trends(
        DartFinancialTrendsQuery(
            corp_code=corp_code,
            end_year=end_year,
            report_code=report_code,
            fs_division=fs_division,
            years=years,
        )
    )
