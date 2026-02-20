import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from backend.db.database import async_session
from backend.db.models import WatchList
from backend.db.crud import create_job, update_job_status, get_platform_by_name, add_auction_listings, add_used_car_listings
from backend.config import settings

logger = logging.getLogger(__name__)


async def run_scheduled_scrapes():
    """Background task that runs periodic scrapes based on WatchList entries."""
    # Wait 60 seconds after startup before first run
    await asyncio.sleep(60)

    while True:
        try:
            async with async_session() as db:
                # Get active watch list entries
                result = await db.execute(
                    select(WatchList).where(WatchList.is_active == True)
                )
                entries = list(result.scalars().all())

                if not entries:
                    logger.info("[Scheduler] No active watch list entries, sleeping...")
                else:
                    logger.info(f"[Scheduler] Running {len(entries)} scheduled scrapes...")

                for entry in entries:
                    try:
                        platforms = [p.strip() for p in entry.platforms.split(",") if p.strip()] if entry.platforms else []
                        if not platforms:
                            continue

                        search_params = {
                            "make": entry.make,
                            "model": entry.model,
                            "year_from": entry.year_from,
                            "year_to": entry.year_to,
                        }

                        # Determine job type from platforms
                        from backend.services.job_manager import _get_scraper_map
                        scraper_map = _get_scraper_map()

                        job_type = "auction"
                        for p_key in platforms:
                            if p_key in scraper_map and scraper_map[p_key][2] == "used_car":
                                job_type = "used_car"
                                break

                        job = await create_job(db, platforms, search_params, job_type=job_type)
                        await update_job_status(db, job.id, "running", progress=0)

                        total = 0
                        for p_key in platforms:
                            if p_key not in scraper_map:
                                continue
                            p_name, scraper_class, listing_type = scraper_map[p_key]
                            if scraper_class is None:
                                continue

                            platform = await get_platform_by_name(db, p_name)
                            if not platform:
                                continue

                            scraper = scraper_class()
                            try:
                                listings = await scraper.search(
                                    make=search_params["make"],
                                    model=search_params.get("model"),
                                    year_from=search_params.get("year_from"),
                                    year_to=search_params.get("year_to"),
                                )

                                if listings:
                                    if listing_type == "used_car":
                                        await add_used_car_listings(db, listings, job.id, platform.id)
                                    else:
                                        await add_auction_listings(db, listings, job.id, platform.id)
                                    total += len(listings)
                                    logger.info(f"[Scheduler] {p_name}: {len(listings)} listings")

                            except Exception as e:
                                logger.error(f"[Scheduler] {p_name} failed: {e}")

                        await update_job_status(db, job.id, "completed", progress=100, total_results=total)

                        # Update last_run_at
                        entry.last_run_at = datetime.now(timezone.utc)
                        await db.commit()

                        logger.info(f"[Scheduler] {entry.make} {entry.model or ''}: {total} listings collected")

                        # Delay between entries to avoid rate limiting
                        await asyncio.sleep(60)

                    except Exception as e:
                        logger.error(f"[Scheduler] Entry {entry.id} failed: {e}")

        except Exception as e:
            logger.error(f"[Scheduler] Fatal error: {e}")

        # Sleep until next run
        interval = settings.SCHEDULER_INTERVAL_HOURS * 3600
        logger.info(f"[Scheduler] Sleeping for {settings.SCHEDULER_INTERVAL_HOURS} hours...")
        await asyncio.sleep(interval)
