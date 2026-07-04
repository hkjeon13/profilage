from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.company import router as company_router
from app.services.company_store import get_default_data_group_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_default_data_group_store()
    if store is not None:
        await store.initialize()
    yield


app = FastAPI(title="Profilage API", lifespan=lifespan)
app.include_router(company_router)
app.include_router(company_router, prefix="/api")


@app.api_route("/profile", methods=["GET", "HEAD"], include_in_schema=False)
async def company_profile_page():
    return FileResponse("app/static/profile.html")


@app.api_route("/compare", methods=["GET", "HEAD"], include_in_schema=False)
async def company_compare_page():
    return FileResponse("app/static/compare.html")


app.mount("/", StaticFiles(directory="app/static", html=True), name="frontend")
