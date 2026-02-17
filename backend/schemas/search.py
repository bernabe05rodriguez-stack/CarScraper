from pydantic import BaseModel


class AuctionSearchRequest(BaseModel):
    make: str
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    keyword: str | None = None
    time_filter: str = "1y"  # "5m", "1y", "2y", "all"
    platforms: list[str] = ["bat", "carsandbids"]
