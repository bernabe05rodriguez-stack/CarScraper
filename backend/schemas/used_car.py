from pydantic import BaseModel
from datetime import datetime


class UsedCarSearchRequest(BaseModel):
    make: str
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    keyword: str | None = None
    platforms: list[str] = []
    region: str = "usa"  # "usa" or "germany"


class UsedCarListingResponse(BaseModel):
    id: int
    platform: str
    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    list_price: float | None
    mileage: int | None
    days_on_market: int | None
    dealer_name: str | None
    location: str | None
    description: str | None
    url: str | None
    image_url: str | None
    currency: str
    is_active: bool


class UsedCarResultsResponse(BaseModel):
    job_id: int
    total: int
    listings: list[UsedCarListingResponse]
    stats: dict | None = None
