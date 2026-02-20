import logging
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.crud import get_used_car_listings_by_region
from backend.schemas.comparison import ComparisonRequest, ComparisonResponse
from backend.services.aggregator import compute_comparison_stats
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/comparison", tags=["comparison"])


async def _get_eur_usd_rate() -> float:
    """Fetch current EUR/USD rate from API, fallback to config."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.EUR_USD_API, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            rate = data.get("rates", {}).get("USD", settings.EUR_USD_RATE)
            logger.info(f"EUR/USD rate from API: {rate}")
            return rate
    except Exception as e:
        logger.warning(f"Failed to fetch EUR/USD rate: {e}, using fallback {settings.EUR_USD_RATE}")
        return settings.EUR_USD_RATE


@router.post("/analyze", response_model=ComparisonResponse)
async def compare_prices(request: ComparisonRequest, db: AsyncSession = Depends(get_db)):
    # Get historical USA listings
    usa_listings = await get_used_car_listings_by_region(
        db,
        make=request.make,
        model=request.model,
        year_from=request.year_from,
        year_to=request.year_to,
        region="USA",
    )

    # Get historical Germany listings
    germany_listings = await get_used_car_listings_by_region(
        db,
        make=request.make,
        model=request.model,
        year_from=request.year_from,
        year_to=request.year_to,
        region="Germany",
    )

    # Get current exchange rate
    eur_usd_rate = await _get_eur_usd_rate()

    # Compute comparison stats
    stats = compute_comparison_stats(usa_listings, germany_listings, eur_usd_rate)

    year_range = ""
    if request.year_from and request.year_to:
        year_range = f"{request.year_from}-{request.year_to}"
    elif request.year_from:
        year_range = f"{request.year_from}+"
    elif request.year_to:
        year_range = f"up to {request.year_to}"
    else:
        year_range = "All Years"

    return ComparisonResponse(
        make=request.make,
        model=request.model,
        year_range=year_range,
        stats=stats,
    )
