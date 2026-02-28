import json
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Platform, AuctionListing, UsedCarListing, ScrapeJob, SearchCache
from backend.config import settings


# --- Platforms ---

async def seed_platforms(db: AsyncSession):
    platforms_to_seed = [
        # Auction platforms
        Platform(name="Bring a Trailer", platform_type="auction", region="USA", base_url="https://bringatrailer.com"),
        Platform(name="Cars & Bids", platform_type="auction", region="USA", base_url="https://carsandbids.com"),
        # USA used car platforms
        Platform(name="Autotrader", platform_type="used_car", region="USA", base_url="https://www.autotrader.com"),
        Platform(name="Cars.com", platform_type="used_car", region="USA", base_url="https://www.cars.com"),
        Platform(name="CarGurus", platform_type="used_car", region="USA", base_url="https://www.cargurus.com"),
        # Germany used car platforms
        Platform(name="Mobile.de", platform_type="used_car", region="Germany", base_url="https://www.mobile.de"),
        Platform(name="AutoScout24", platform_type="used_car", region="Germany", base_url="https://www.autoscout24.de"),
        Platform(name="eBay Kleinanzeigen", platform_type="used_car", region="Germany", base_url="https://www.kleinanzeigen.de"),
    ]
    for p in platforms_to_seed:
        existing = await db.execute(select(Platform).where(Platform.name == p.name))
        if not existing.scalar_one_or_none():
            db.add(p)
    await db.commit()


async def get_platform_by_name(db: AsyncSession, name: str) -> Platform | None:
    result = await db.execute(select(Platform).where(Platform.name == name))
    return result.scalar_one_or_none()


# --- Jobs ---

async def create_job(db: AsyncSession, platforms: list[str], search_params: dict, job_type: str = "auction") -> ScrapeJob:
    job = ScrapeJob(
        platforms_requested=",".join(platforms),
        search_params=json.dumps(search_params),
        job_type=job_type,
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


# --- Used Car Listings ---

async def add_used_car_listings(db: AsyncSession, listings: list[dict], job_id: int, platform_id: int):
    for data in listings:
        listing = UsedCarListing(
            platform_id=platform_id,
            job_id=job_id,
            year=data.get("year"),
            make=data.get("make"),
            model=data.get("model"),
            trim=data.get("trim"),
            list_price=data.get("list_price"),
            mileage=data.get("mileage"),
            days_on_market=data.get("days_on_market"),
            dealer_name=data.get("dealer_name"),
            location=data.get("location"),
            description=data.get("description"),
            url=data.get("url"),
            image_url=data.get("image_url"),
            listing_date=data.get("listing_date"),
            is_active=data.get("is_active", True),
            currency=data.get("currency", "USD"),
        )
        db.add(listing)
    await db.commit()


async def get_used_car_listings_by_job(db: AsyncSession, job_id: int) -> list[UsedCarListing]:
    result = await db.execute(
        select(UsedCarListing)
        .where(UsedCarListing.job_id == job_id)
        .order_by(UsedCarListing.list_price.desc().nullslast())
    )
    return list(result.scalars().all())


async def get_used_car_listings_by_region(
    db: AsyncSession,
    make: str,
    model: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    region: str | None = None,
) -> list[UsedCarListing]:
    """Query historical used car listings filtered by region/make/model/year."""
    query = select(UsedCarListing).join(Platform, UsedCarListing.platform_id == Platform.id)

    if region:
        query = query.where(Platform.region == region)
    if make:
        query = query.where(UsedCarListing.make == make)
    if model:
        query = query.where(UsedCarListing.model == model)
    if year_from:
        query = query.where(UsedCarListing.year >= year_from)
    if year_to:
        query = query.where(UsedCarListing.year <= year_to)

    result = await db.execute(query.order_by(UsedCarListing.created_at.desc()))
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
