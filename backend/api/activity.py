from fastapi import APIRouter, Query

from services.activity_service import get_activity, get_stats

router = APIRouter(tags=["Activity"])


@router.get("/activity")
async def activity_endpoint(
    filter: str = Query("All"),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    return await get_activity(filter_status=filter, limit=limit)


@router.get("/activity/stats")
async def activity_stats_endpoint() -> dict:
    return await get_stats()
