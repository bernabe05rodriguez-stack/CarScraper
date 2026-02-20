from pydantic import BaseModel


class ComparisonRequest(BaseModel):
    make: str
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None


class ComparisonResponse(BaseModel):
    make: str
    model: str | None
    year_range: str
    stats: dict
