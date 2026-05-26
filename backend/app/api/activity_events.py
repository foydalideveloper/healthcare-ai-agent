"""AI Glasses activity event endpoints."""

# from uuid import UUID  # Changed to int for unified DB
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db_admin
from app.models.personal_hrt import ActivityEvent, ActivityEventCreate

router = APIRouter(prefix="/activity-events", tags=["activity-events"])


@router.post("/", response_model=ActivityEvent, status_code=201)
async def ingest_activity_event(event: ActivityEventCreate):
    """Ingest a single activity event from AI glasses or other device."""
    db = get_db_admin()
    result = await db.insert("user_activity_event", event.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=400, detail="Failed to insert activity event")
    return result[0]


@router.get("/{user_id}/recent", response_model=list[ActivityEvent])
async def get_recent_events(
    user_id: int,
    event_type: str | None = Query(None, description="Filter: meal, drink, medication, exercise"),
    limit: int = Query(20, le=100),
):
    """Get recent activity events for a user."""
    db = get_db_admin()
    filters = {"user_id": f"eq.{user_id}"}
    if event_type:
        filters["event_type"] = f"eq.{event_type}"
    result = await db.select(
        "user_activity_event",
        filters=filters,
        order="detected_at.desc",
        limit=limit,
    )
    return result


@router.get("/{user_id}/unverified", response_model=list[ActivityEvent])
async def get_unverified_events(user_id: int, limit: int = Query(10, le=50)):
    """Get low-confidence unverified events for user correction (active learning)."""
    db = get_db_admin()
    result = await db.select(
        "user_activity_event",
        filters={
            "user_id": f"eq.{user_id}",
            "verified": "eq.false",
            "confidence_score": "lt.0.7",
        },
        order="detected_at.desc",
        limit=limit,
    )
    return result


@router.patch("/{event_id}/verify")
async def verify_event(event_id: int, correction_data: dict | None = None):
    """User verifies or corrects an activity event (active learning feedback)."""
    db = get_db_admin()
    update = {"verified": True, "processing_status": "user_verified"}
    if correction_data:
        update["correction_data"] = correction_data
    result = await db.update(
        "user_activity_event",
        update,
        filters={"event_id": f"eq.{event_id}"},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return result[0]
