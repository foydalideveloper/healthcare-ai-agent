"""Simulation endpoints (LSTM-Transformer health prediction)."""

# from uuid import UUID  # Changed to int for unified DB
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db_admin
from app.models.personal_hrt import SimulationResult, SimulationResultCreate

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/", response_model=SimulationResult, status_code=201)
async def create_simulation(data: SimulationResultCreate):
    """Store a simulation result (called by the LSTM-Transformer inference service)."""
    db = get_db_admin()
    result = await db.insert("simulation_result", data.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=400, detail="Failed to store simulation result")
    return result[0]


@router.get("/{user_id}/latest")
async def get_latest_simulation(
    user_id: int,
    scenario: str = Query("current", pattern="^(current|twin|optimistic)$"),
):
    """Get the latest simulation result for a user and scenario."""
    db = get_db_admin()
    result = await db.select(
        "simulation_result",
        filters={"user_id": f"eq.{user_id}", "scenario": f"eq.{scenario}"},
        order="run_at.desc",
        limit=1,
    )
    if not result:
        raise HTTPException(status_code=404, detail="No simulation results found")
    return result[0]


@router.get("/{user_id}/compare")
async def compare_scenarios(user_id: int):
    """Get latest current vs twin simulation for Digital Twin Comparison (patent feature)."""
    db = get_db_admin()

    current = await db.select(
        "simulation_result",
        filters={"user_id": f"eq.{user_id}", "scenario": "eq.current"},
        order="run_at.desc",
        limit=1,
    )
    twin = await db.select(
        "simulation_result",
        filters={"user_id": f"eq.{user_id}", "scenario": "eq.twin"},
        order="run_at.desc",
        limit=1,
    )

    if not current or not twin:
        raise HTTPException(status_code=404, detail="Both current and twin simulations required")

    return {"current": current[0], "twin": twin[0]}
