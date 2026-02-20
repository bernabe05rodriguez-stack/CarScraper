from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.crud import get_used_car_listings_by_job, get_job
from backend.db.models import Platform
from backend.schemas.used_car import UsedCarSearchRequest, UsedCarListingResponse, UsedCarResultsResponse
from backend.schemas.job import JobCreateResponse
from backend.services.job_manager import start_scrape_job
from backend.services.aggregator import compute_used_car_stats

router = APIRouter(prefix="/api/v1/used-cars", tags=["used-cars"])

# Default platforms per region
REGION_PLATFORMS = {
    "usa": ["autotrader", "carscom"],
    "germany": ["mobilede", "autoscout24", "kleinanzeigen"],
}


@router.post("/search", response_model=JobCreateResponse)
async def search_used_cars(request: UsedCarSearchRequest, db: AsyncSession = Depends(get_db)):
    platforms = request.platforms
    if not platforms:
        platforms = REGION_PLATFORMS.get(request.region, [])

    search_params = {
        "make": request.make,
        "model": request.model,
        "year_from": request.year_from,
        "year_to": request.year_to,
        "keyword": request.keyword,
        "region": request.region,
    }

    job_id, cached = await start_scrape_job(db, platforms, search_params, job_type="used_car")
    job = await get_job(db, job_id)

    return JobCreateResponse(
        job_id=job_id,
        status=job.status if job else "pending",
        cached=cached,
    )


@router.get("/results/{job_id}", response_model=UsedCarResultsResponse)
async def get_used_car_results(job_id: int, db: AsyncSession = Depends(get_db)):
    listings = await get_used_car_listings_by_job(db, job_id)

    # Map platform IDs to names
    platform_names = {}

    listing_responses = []
    for l in listings:
        if l.platform_id not in platform_names:
            platform = await db.get(Platform, l.platform_id)
            platform_names[l.platform_id] = platform.name if platform else "Unknown"

        listing_responses.append(UsedCarListingResponse(
            id=l.id,
            platform=platform_names[l.platform_id],
            year=l.year,
            make=l.make,
            model=l.model,
            trim=l.trim,
            list_price=l.list_price,
            mileage=l.mileage,
            days_on_market=l.days_on_market,
            dealer_name=l.dealer_name,
            location=l.location,
            description=l.description,
            url=l.url,
            image_url=l.image_url,
            currency=l.currency or "USD",
            is_active=l.is_active,
        ))

    stats = compute_used_car_stats(listings)

    return UsedCarResultsResponse(
        job_id=job_id,
        total=len(listing_responses),
        listings=listing_responses,
        stats=stats,
    )
