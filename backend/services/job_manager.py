import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.crud import (
    create_job, update_job_status, get_platform_by_name,
    add_auction_listings, build_cache_key, get_cached_job, set_cache,
)
from backend.db.database import async_session
from backend.scrapers.bat import BaTScraper
from backend.scrapers.carsandbids import CarsAndBidsScraper

logger = logging.getLogger(__name__)

SCRAPER_MAP = {
    "bat": ("Bring a Trailer", BaTScraper),
    "carsandbids": ("Cars & Bids", CarsAndBidsScraper),
}

# In-memory store for active background tasks
_active_tasks: dict[int, asyncio.Task] = {}


async def start_scrape_job(
    db: AsyncSession,
    platforms: list[str],
    search_params: dict,
) -> tuple[int, bool]:
    """Create and start a scraping job. Returns (job_id, cached)."""

    # Check cache first
    cache_key = build_cache_key(search_params, platforms)
    cached_job_id = await get_cached_job(db, cache_key)
    if cached_job_id is not None:
        logger.info(f"Cache hit for search, returning job {cached_job_id}")
        return cached_job_id, True

    # Create new job
    job = await create_job(db, platforms, search_params)
    job_id = job.id

    # Launch background task
    task = asyncio.create_task(_run_scrape_job(job_id, platforms, search_params, cache_key))
    _active_tasks[job_id] = task
    task.add_done_callback(lambda t: _active_tasks.pop(job_id, None))

    return job_id, False


async def _run_scrape_job(
    job_id: int,
    platforms: list[str],
    search_params: dict,
    cache_key: str,
):
    """Execute scraping across all requested platforms."""
    async with async_session() as db:
        try:
            await update_job_status(db, job_id, "running", progress=0)

            total_listings = 0
            platform_count = len(platforms)

            for idx, platform_key in enumerate(platforms):
                if platform_key not in SCRAPER_MAP:
                    logger.warning(f"Unknown platform: {platform_key}")
                    continue

                platform_name, scraper_class = SCRAPER_MAP[platform_key]
                scraper = scraper_class()

                platform = await get_platform_by_name(db, platform_name)
                if not platform:
                    logger.warning(f"Platform not in DB: {platform_name}")
                    continue

                # Progress callback
                base_progress = int((idx / platform_count) * 100)
                range_progress = int(100 / platform_count)

                async def on_progress(page, max_pages, count):
                    pct = base_progress + int((page / max_pages) * range_progress)
                    await update_job_status(db, job_id, "running", progress=min(pct, 95))

                logger.info(f"[Job {job_id}] Scraping {platform_name}...")

                try:
                    listings = await scraper.search(
                        make=search_params.get("make", ""),
                        model=search_params.get("model"),
                        year_from=search_params.get("year_from"),
                        year_to=search_params.get("year_to"),
                        keyword=search_params.get("keyword"),
                        on_progress=on_progress,
                    )

                    if listings:
                        await add_auction_listings(db, listings, job_id, platform.id)
                        total_listings += len(listings)
                        logger.info(f"[Job {job_id}] {platform_name}: {len(listings)} listings saved")

                except Exception as e:
                    logger.error(f"[Job {job_id}] {platform_name} failed: {e}")

            await update_job_status(
                db, job_id, "completed", progress=100, total_results=total_listings
            )

            # Save to cache
            await set_cache(db, cache_key, job_id)
            logger.info(f"[Job {job_id}] Completed with {total_listings} total listings")

        except Exception as e:
            logger.error(f"[Job {job_id}] Fatal error: {e}")
            await update_job_status(db, job_id, "failed", error_message=str(e))
