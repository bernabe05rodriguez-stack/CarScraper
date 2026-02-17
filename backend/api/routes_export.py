from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.crud import get_job, get_listings_by_job
from backend.services.exporter import export_listings_to_excel
from backend.services.aggregator import compute_auction_stats

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/{job_id}")
async def export_job_results(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")

    listings = await get_listings_by_job(db, job_id)
    if not listings:
        raise HTTPException(status_code=404, detail="No results to export")

    stats = compute_auction_stats(listings)
    excel_file = export_listings_to_excel(listings, stats)

    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=auction_results_{job_id}.xlsx"},
    )
