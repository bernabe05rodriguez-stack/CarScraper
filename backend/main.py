import asyncio
import json
import logging
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.config import settings
from backend.db.database import init_db
from backend.db.crud import seed_platforms
from backend.db.database import async_session
from backend.api.routes_auctions import router as auctions_router
from backend.api.routes_jobs import router as jobs_router
from backend.api.routes_export import router as export_router
from backend.api.routes_used_cars import router as used_cars_router
from backend.api.routes_comparison import router as comparison_router
from backend.services.scheduler import run_scheduled_scrapes

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        await seed_platforms(db)

    # Start background scheduler for historical data collection
    scheduler_task = asyncio.create_task(run_scheduled_scrapes())
    yield
    scheduler_task.cancel()


app = FastAPI(title="CarScraper", version="0.2.0", lifespan=lifespan)

logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


@app.get("/api/v1/health")
async def health_check():
    """Check DB connectivity and table existence."""
    from sqlalchemy import text
    try:
        async with async_session() as db:
            result = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
            tables = [row[0] for row in result.fetchall()]
        return {"status": "ok", "database": "connected", "tables": tables}
    except Exception as e:
        return {"status": "error", "database": str(e)}


# API routes
app.include_router(auctions_router)
app.include_router(jobs_router)
app.include_router(export_router)
app.include_router(used_cars_router)
app.include_router(comparison_router)


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


@app.get("/usa-used")
async def serve_usa_used():
    return FileResponse(str(frontend_dir / "usa-used.html"))


@app.get("/germany-used")
async def serve_germany_used():
    return FileResponse(str(frontend_dir / "germany-used.html"))


@app.get("/comparison")
async def serve_comparison():
    return FileResponse(str(frontend_dir / "comparison.html"))
