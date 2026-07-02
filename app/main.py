from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.company import router as company_router

app = FastAPI(title="Profilage API")
app.include_router(company_router)
app.include_router(company_router, prefix="/api")


@app.api_route("/profile", methods=["GET", "HEAD"], include_in_schema=False)
async def company_profile_page():
    return FileResponse("app/static/profile.html")


app.mount("/", StaticFiles(directory="app/static", html=True), name="frontend")
