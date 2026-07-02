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
        )
    )
