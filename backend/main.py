import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.db.database import init_db
from backend.db.crud import seed_platforms
from backend.db.database import async_session
from backend.api.routes_auctions import router as auctions_router
from backend.api.routes_jobs import router as jobs_router
from backend.api.routes_export import router as export_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        await seed_platforms(db)
    yield


app = FastAPI(title="CarScraper", version="0.1.0", lifespan=lifespan)

# API routes
app.include_router(auctions_router)
app.include_router(jobs_router)
app.include_router(export_router)


# Makes/models endpoints
@app.get("/api/v1/makes")
async def get_makes():
    data_file = settings.DATA_DIR / "vehicles.json"
    if not data_file.exists():
        return []
    with open(data_file) as f:
        data = json.load(f)
    return sorted(data.keys())


@app.get("/api/v1/models/{make}")
async def get_models(make: str):
    data_file = settings.DATA_DIR / "vehicles.json"
    if not data_file.exists():
        return []
    with open(data_file) as f:
        data = json.load(f)
    return sorted(data.get(make, []))


# Serve frontend static files
frontend_dir = settings.FRONTEND_DIR
app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")


@app.get("/")
async def serve_index():
    return FileResponse(str(frontend_dir / "index.html"))


@app.get("/auctions")
async def serve_auctions():
    return FileResponse(str(frontend_dir / "auctions.html"))
