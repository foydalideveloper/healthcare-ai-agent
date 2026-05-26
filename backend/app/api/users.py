"""User management endpoints."""

# from uuid import UUID  # Changed to int for unified DB
from fastapi import APIRouter, HTTPException
from app.database import get_db_admin
from app.models.personal_hrt import User, UserCreate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=User, status_code=201)
async def create_user(user: UserCreate):
    """Create a new user profile."""
    db = get_db_admin()
    result = await db.insert("users", user.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create user")
    return result[0]


@router.get("/{user_id}", response_model=User)
async def get_user(user_id: int):
    """Get user profile by ID."""
    db = get_db_admin()
    result = await db.select("users", filters={"user_id": f"eq.{user_id}"})
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return result[0]


@router.patch("/{user_id}", response_model=User)
async def update_user(user_id: int, updates: UserCreate):
    """Update user profile."""
    db = get_db_admin()
    result = await db.update(
        "users",
        updates.model_dump(exclude_none=True),
        filters={"user_id": f"eq.{user_id}"},
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return result[0]
