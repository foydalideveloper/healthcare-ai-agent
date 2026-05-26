"""Food nutrition lookup API endpoint.
Queries MFDS (275K Korean foods) with USDA (13K international) fallback."""

from fastapi import APIRouter, Query
from pathlib import Path
import sqlite3

router = APIRouter(prefix="/food-lookup", tags=["food-lookup"])

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "food_db"
MFDS_DB = DATA_DIR / "food_nutrition.db"
USDA_DB = DATA_DIR / "usda_food_nutrition.db"


def _get_mfds_conn():
    if MFDS_DB.exists():
        conn = sqlite3.connect(str(MFDS_DB))
        conn.row_factory = sqlite3.Row
        return conn
    return None


def _get_usda_conn():
    if USDA_DB.exists():
        conn = sqlite3.connect(str(USDA_DB))
        conn.row_factory = sqlite3.Row
        return conn
    return None


@router.get("/")
async def lookup_food(
    query: str = Query(..., min_length=1, description="Food name to search"),
    limit: int = Query(5, le=20),
):
    """Search for food nutrition data. Tries MFDS (Korean) first, then USDA fallback."""
    results = []

    # Search MFDS
    conn = _get_mfds_conn()
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT food_name_kr, category1, serving_size,
                      energy_kcal, protein_g, fat_g, carbohydrate_g,
                      dietary_fiber_g, sodium_mg, total_sugar_g, cholesterol_mg
               FROM foods WHERE food_name_kr LIKE ?
               ORDER BY LENGTH(food_name_kr) ASC LIMIT ?""",
            (f"%{query}%", limit),
        )
        for row in cursor.fetchall():
            results.append({**dict(row), "source": "MFDS"})
        conn.close()

    # If not enough results, search USDA
    if len(results) < limit:
        conn = _get_usda_conn()
        if conn:
            remaining = limit - len(results)
            cursor = conn.cursor()
            cursor.execute(
                """SELECT f.fdc_id, f.description, f.food_category
                   FROM foods f WHERE f.description LIKE ?
                   ORDER BY LENGTH(f.description) ASC LIMIT ?""",
                (f"%{query}%", remaining),
            )
            for row in cursor.fetchall():
                food = dict(row)
                # Get nutrients
                cursor.execute(
                    """SELECT nutrient_name, amount FROM nutrients
                       WHERE fdc_id = ? AND nutrient_name IN
                       ('Energy','Protein','Total lipid (fat)',
                        'Carbohydrate, by difference','Fiber, total dietary',
                        'Sodium, Na','Sugars, Total','Cholesterol')""",
                    (food["fdc_id"],),
                )
                nutrients = {r["nutrient_name"]: r["amount"] for r in cursor.fetchall()}
                results.append({
                    "food_name_kr": food["description"],
                    "category1": food.get("food_category", ""),
                    "serving_size": "100g",
                    "energy_kcal": nutrients.get("Energy"),
                    "protein_g": nutrients.get("Protein"),
                    "fat_g": nutrients.get("Total lipid (fat)"),
                    "carbohydrate_g": nutrients.get("Carbohydrate, by difference"),
                    "dietary_fiber_g": nutrients.get("Fiber, total dietary"),
                    "sodium_mg": nutrients.get("Sodium, Na"),
                    "total_sugar_g": nutrients.get("Sugars, Total"),
                    "cholesterol_mg": nutrients.get("Cholesterol"),
                    "source": "USDA",
                })
            conn.close()

    return {"query": query, "count": len(results), "results": results}


@router.get("/stats")
async def food_db_stats():
    """Get food database statistics."""
    stats = {}
    conn = _get_mfds_conn()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM foods")
        stats["mfds_foods"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT category1) FROM foods")
        stats["mfds_categories"] = cursor.fetchone()[0]
        conn.close()

    conn = _get_usda_conn()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM foods")
        stats["usda_foods"] = cursor.fetchone()[0]
        conn.close()

    stats["total_foods"] = stats.get("mfds_foods", 0) + stats.get("usda_foods", 0)
    return stats
