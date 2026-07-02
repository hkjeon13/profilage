from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.company import router as company_router

app = FastAPI(title="Profilage API")
app.include_router(company_router)
app.include_router(company_router, prefix="/api")
app.mount("/", StaticFiles(directory="app/static", html=True), name="frontend")
