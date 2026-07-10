from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.company import router as company_router
from app.core.config import get_app_settings
from app.services.company_store import get_default_data_group_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_default_data_group_store()
    if store is not None:
        await store.initialize()
    yield


settings = get_app_settings()
app = FastAPI(
    title="Profilage API",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)
app.include_router(company_router)
app.include_router(company_router, prefix="/api")


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' https://profile.fin-ally.net; "
        "font-src 'self' data:; "
        "media-src 'self' blob: data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains; preload"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    return response


@app.api_route("/profile", methods=["GET", "HEAD"], include_in_schema=False)
async def company_profile_page():
    return FileResponse("app/static/profile.html")


@app.api_route("/compare", methods=["GET", "HEAD"], include_in_schema=False)
async def company_compare_page():
    return FileResponse("app/static/compare.html")


app.mount("/", StaticFiles(directory="app/static", html=True), name="frontend")
