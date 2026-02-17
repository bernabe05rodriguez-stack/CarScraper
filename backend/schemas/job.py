from pydantic import BaseModel
from datetime import datetime


class JobStatusResponse(BaseModel):
    job_id: int
    status: str
    progress: int
    total_results: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class JobCreateResponse(BaseModel):
    job_id: int
    status: str
    cached: bool = False
