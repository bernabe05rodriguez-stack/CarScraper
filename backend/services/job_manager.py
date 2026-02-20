import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.crud import (
    create_job, update_job_status, get_platform_by_name,
    add_auction_listings, add_used_car_listings,
    build_cache_key, get_cached_job, set_cache,
)
from backend.db.database import async_session
from backend.scrapers.bat import BaTScraper
from backend.scrapers.carsandbids import CarsAndBidsScraper

logger = logging.getLogger(__name__)

# (platform_display_name, scraper_class, listing_type)
SCRAPER_MAP = {
    # Auction platforms
    "bat": ("Bring a Trailer", BaTScraper, "auction"),
    "carsandbids": ("Cars & Bids", CarsAndBidsScraper, "auction"),
    # USA used car platforms
    "autotrader": ("Autotrader", None, "used_car"),
    "carscom": ("Cars.com", None, "used_car"),
    # Germany used car platforms
    "mobilede": ("Mobile.de", None, "used_car"),
    "autoscout24": ("AutoScout24", None, "used_car"),
    "kleinanzeigen": ("eBay Kleinanzeigen", None, "used_car"),
}


def _get_scraper_map():
    """Lazy-load scraper classes to avoid circular imports."""
    from backend.scrapers.autotrader import AutotraderScraper
    from backend.scrapers.carscom import CarsComScraper
    from backend.scrapers.mobilede import MobileDeScraper
    from backend.scrapers.autoscout24 import AutoScout24Scraper
    from backend.scrapers.kleinanzeigen import KleinanzeigenScraper

    SCRAPER_MAP["autotrader"] = ("Autotrader", AutotraderScraper, "used_car")
    SCRAPER_MAP["carscom"] = ("Cars.com", CarsComScraper, "used_car")
    SCRAPER_MAP["mobilede"] = ("Mobile.de", MobileDeScraper, "used_car")
    SCRAPER_MAP["autoscout24"] = ("AutoScout24", AutoScout24Scraper, "used_car")
    SCRAPER_MAP["kleinanzeigen"] = ("eBay Kleinanzeigen", KleinanzeigenScraper, "used_car")
    return SCRAPER_MAP


# In-memory store for active background tasks
_active_tasks: dict[int, asyncio.Task] = {}


async def start_scrape_job(
    db: AsyncSession,
    platforms: list[str],
    search_params: dict,
    job_type: str = "auction",
) -> tuple[int, bool]:
    """Create and start a scraping job. Returns (job_id, cached)."""

    # Check cache first
    cache_key = build_cache_key(search_params, platforms)
    cached_job_id = await get_cached_job(db, cache_key)
    if cached_job_id is not None:
        logger.info(f"Cache hit for search, returning job {cached_job_id}")
        return cached_job_id, True

    # Create new job
    job = await create_job(db, platforms, search_params, job_type=job_type)
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
    scraper_map = _get_scraper_map()

    async with async_session() as db:
        try:
            await update_job_status(db, job_id, "running", progress=0)

            total_listings = 0
            platform_count = len(platforms)

            for idx, platform_key in enumerate(platforms):
                if platform_key not in scraper_map:
                    logger.warning(f"Unknown platform: {platform_key}")
                    continue

                platform_name, scraper_class, listing_type = scraper_map[platform_key]

                if scraper_class is None:
                    logger.warning(f"Scraper not implemented yet: {platform_name}")
                    continue

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
                        if listing_type == "used_car":
                            await add_used_car_listings(db, listings, job_id, platform.id)
                        else:
                            await add_auction_listings(db, listings, job_id, platform.id)
                        total_listings += len(listings)
                        logger.info(f"[Job {job_id}] {platform_name}: {len(listings)} listings saved")

                except Exception as e:
                    logger.error(f"[Job {job_id}] {platform_name} failed: {e}")

            await update_job_status(
                db, job_id, "completed", progress=100, total_results=total_listings
            )

            # Save to cache
            if cache_key:
                await set_cache(db, cache_key, job_id)
            logger.info(f"[Job {job_id}] Completed with {total_listings} total listings")

        except Exception as e:
            logger.error(f"[Job {job_id}] Fatal error: {e}")
            await update_job_status(db, job_id, "failed", error_message=str(e))
