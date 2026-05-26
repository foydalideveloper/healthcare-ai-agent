"""Healthcare Index and health level endpoints."""

# from uuid import UUID  # Changed to int for unified DB
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db_admin
from app.models.personal_hrt import HealthLevel, HealthLevelCreate

router = APIRouter(prefix="/health-level", tags=["health-level"])


@router.post("/", response_model=HealthLevel, status_code=201)
async def create_health_level(data: HealthLevelCreate):
    """Record a health level calculation (HCI + DRI)."""
    db = get_db_admin()
    result = await db.insert("user_health_level", data.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=400, detail="Failed to insert health level")
    return result[0]


@router.get("/{user_id}/latest", response_model=HealthLevel)
async def get_latest_health_level(user_id: int):
    """Get the latest actual (non-predicted) health level for a user."""
    db = get_db_admin()
    result = await db.select(
        "user_health_level",
        filters={"user_id": f"eq.{user_id}", "predicted": "eq.false"},
        order="measured_at.desc",
        limit=1,
    )
    if not result:
        raise HTTPException(status_code=404, detail="No health level data found")
    return result[0]


@router.get("/{user_id}/history", response_model=list[HealthLevel])
async def get_health_level_history(
    user_id: int,
    include_predicted: bool = Query(False),
    limit: int = Query(30, le=365),
):
    """Get health level history (HCI trend over time)."""
    db = get_db_admin()
    filters = {"user_id": f"eq.{user_id}"}
    if not include_predicted:
        filters["predicted"] = "eq.false"
    result = await db.select(
        "user_health_level",
        filters=filters,
        order="measured_at.desc",
        limit=limit,
    )
    return result
