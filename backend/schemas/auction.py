from pydantic import BaseModel
from datetime import datetime


class AuctionListingResponse(BaseModel):
    id: int
    platform: str
    year: int | None
    make: str | None
    model: str | None
    starting_bid: float | None
    sold_price: float | None
    auction_days: int | None
    bid_count: int | None
    times_listed: int | None
    description: str | None
    url: str | None
    image_url: str | None
    auction_end_date: datetime | None
    is_sold: bool


class AuctionResultsResponse(BaseModel):
    job_id: int
    total: int
    listings: list[AuctionListingResponse]
    stats: dict | None = None
