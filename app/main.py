from fastapi import FastAPI

from app.api.company import router as company_router

app = FastAPI(title="Profilage API")
app.include_router(company_router)
