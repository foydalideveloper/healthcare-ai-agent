"""Biometric data endpoints (wearable/CGM data ingestion and query)."""

# from uuid import UUID  # Changed to int for unified DB
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db_admin
from app.models.personal_hrt import Biometric, BiometricCreate

router = APIRouter(prefix="/biometric", tags=["biometric"])


@router.post("/", response_model=Biometric, status_code=201)
async def ingest_biometric(data: BiometricCreate):
    """Ingest a single biometric reading from wearable/CGM."""
    db = get_db_admin()
    result = await db.insert("user_biometric", data.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=400, detail="Failed to insert biometric data")
    return result[0]


@router.post("/batch", status_code=201)
async def ingest_biometric_batch(data: list[BiometricCreate]):
    """Ingest a batch of biometric readings (e.g., from wearable sync)."""
    db = get_db_admin()
    rows = [d.model_dump(exclude_none=True) for d in data]
    result = await db.insert("user_biometric", rows)
    return {"inserted": len(result)}


@router.get("/{user_id}/latest", response_model=Biometric)
async def get_latest_biometric(user_id: int):
    """Get the most recent biometric reading for a user."""
    db = get_db_admin()
    result = await db.select(
        "user_biometric",
        filters={"user_id": f"eq.{user_id}"},
        order="measured_at.desc",
        limit=1,
    )
    if not result:
        raise HTTPException(status_code=404, detail="No biometric data found")
    return result[0]


@router.get("/{user_id}/history", response_model=list[Biometric])
async def get_biometric_history(
    user_id: int,
    start: datetime = Query(..., description="Start datetime (ISO format)"),
    end: datetime = Query(..., description="End datetime (ISO format)"),
    device_type: str | None = Query(None, description="Filter by device type"),
    limit: int = Query(100, le=1000),
):
    """Get biometric history for a user within a time range."""
    db = get_db_admin()
    filters = {
        "user_id": f"eq.{user_id}",
        "measured_at": f"gte.{start.isoformat()}",
    }
    if device_type:
        filters["device_type"] = f"eq.{device_type}"
    result = await db.select(
        "user_biometric",
        filters=filters,
        order="measured_at.desc",
        limit=limit,
    )
    return result
