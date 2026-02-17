import json
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Platform, AuctionListing, ScrapeJob, SearchCache
from backend.config import settings


# --- Platforms ---

async def seed_platforms(db: AsyncSession):
    existing = await db.execute(select(func.count(Platform.id)))
    if existing.scalar() > 0:
        return

    platforms = [
        Platform(name="Bring a Trailer", platform_type="auction", region="USA", base_url="https://bringatrailer.com"),
        Platform(name="Cars & Bids", platform_type="auction", region="USA", base_url="https://carsandbids.com"),
    ]
    db.add_all(platforms)
    await db.commit()


async def get_platform_by_name(db: AsyncSession, name: str) -> Platform | None:
    result = await db.execute(select(Platform).where(Platform.name == name))
    return result.scalar_one_or_none()


# --- Jobs ---

async def create_job(db: AsyncSession, platforms: list[str], search_params: dict) -> ScrapeJob:
    job = ScrapeJob(
        platforms_requested=",".join(platforms),
        search_params=json.dumps(search_params),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: int) -> ScrapeJob | None:
    return await db.get(ScrapeJob, job_id)


async def update_job_status(
    db: AsyncSession,
    job_id: int,
    status: str,
    progress: int | None = None,
    total_results: int | None = None,
    error_message: str | None = None,
):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        return
    job.status = status
    if progress is not None:
        job.progress = progress
    if total_results is not None:
        job.total_results = total_results
    if error_message is not None:
        job.error_message = error_message
    if status in ("completed", "failed"):
        job.completed_at = datetime.now(timezone.utc)
    await db.commit()


# --- Auction Listings ---

async def add_auction_listings(db: AsyncSession, listings: list[dict], job_id: int, platform_id: int):
    for data in listings:
        listing = AuctionListing(
            platform_id=platform_id,
            job_id=job_id,
            year=data.get("year"),
            make=data.get("make"),
            model=data.get("model"),
            starting_bid=data.get("starting_bid"),
            sold_price=data.get("sold_price"),
            auction_days=data.get("auction_days"),
            bid_count=data.get("bid_count"),
            times_listed=data.get("times_listed", 1),
            description=data.get("description"),
            url=data.get("url"),
            image_url=data.get("image_url"),
            auction_end_date=data.get("auction_end_date"),
            is_sold=data.get("is_sold", True),
        )
        db.add(listing)
    await db.commit()


async def get_listings_by_job(db: AsyncSession, job_id: int) -> list[AuctionListing]:
    result = await db.execute(
        select(AuctionListing)
        .where(AuctionListing.job_id == job_id)
        .order_by(AuctionListing.auction_end_date.desc().nullslast())
    )
    return list(result.scalars().all())


# --- Cache ---

def build_cache_key(search_params: dict, platforms: list[str]) -> str:
    raw = json.dumps({"params": search_params, "platforms": sorted(platforms)}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_cached_job(db: AsyncSession, cache_key: str) -> int | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(SearchCache)
        .where(SearchCache.cache_key == cache_key, SearchCache.expires_at > now)
    )
    cache = result.scalar_one_or_none()
    if cache:
        return cache.job_id
    return None


async def set_cache(db: AsyncSession, cache_key: str, job_id: int):
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.CACHE_TTL_HOURS)
    cache = SearchCache(cache_key=cache_key, job_id=job_id, expires_at=expires)
    db.add(cache)
    await db.commit()
