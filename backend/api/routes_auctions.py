import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.crud import get_listings_by_job, get_job, get_platform_by_name
from backend.schemas.search import AuctionSearchRequest
from backend.schemas.auction import AuctionListingResponse, AuctionResultsResponse
from backend.schemas.job import JobCreateResponse
from backend.services.job_manager import start_scrape_job
from backend.services.aggregator import compute_auction_stats

router = APIRouter(prefix="/api/v1/auctions", tags=["auctions"])


@router.post("/search", response_model=JobCreateResponse)
async def search_auctions(request: AuctionSearchRequest, db: AsyncSession = Depends(get_db)):
    search_params = {
        "make": request.make,
        "model": request.model,
        "year_from": request.year_from,
        "year_to": request.year_to,
        "keyword": request.keyword,
        "time_filter": request.time_filter,
    }

    job_id, cached = await start_scrape_job(db, request.platforms, search_params)
    job = await get_job(db, job_id)

    return JobCreateResponse(
        job_id=job_id,
        status=job.status if job else "pending",
        cached=cached,
    )


@router.get("/results/{job_id}", response_model=AuctionResultsResponse)
async def get_auction_results(job_id: int, db: AsyncSession = Depends(get_db)):
    listings = await get_listings_by_job(db, job_id)

    # Map platform IDs to names
    platform_names = {}

    listing_responses = []
    for l in listings:
        if l.platform_id not in platform_names:
            # Resolve platform name
            from backend.db.models import Platform
            platform = await db.get(Platform, l.platform_id)
            platform_names[l.platform_id] = platform.name if platform else "Unknown"

        listing_responses.append(AuctionListingResponse(
            id=l.id,
            platform=platform_names[l.platform_id],
            year=l.year,
            make=l.make,
            model=l.model,
            starting_bid=l.starting_bid,
            sold_price=l.sold_price,
            auction_days=l.auction_days,
            bid_count=l.bid_count,
            times_listed=l.times_listed,
            description=l.description,
            url=l.url,
            image_url=l.image_url,
            auction_end_date=l.auction_end_date,
            is_sold=l.is_sold,
        ))

    stats = compute_auction_stats(listings)

    return AuctionResultsResponse(
        job_id=job_id,
        total=len(listing_responses),
        listings=listing_responses,
        stats=stats,
    )
