"""
Food Nutrition Lookup Service
Searches MFDS (275K Korean foods) then falls back to USDA (13K international).
"""

import sqlite3
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data" / "food_db"
MFDS_DB = DATA_DIR / "food_nutrition.db"
USDA_DB = DATA_DIR / "usda_food_nutrition.db"


class FoodLookupService:
    """Query local SQLite food databases for nutrition info."""

    def __init__(self):
        self.mfds_conn = None
        self.usda_conn = None
        self._connect()

    def _connect(self):
        if MFDS_DB.exists():
            self.mfds_conn = sqlite3.connect(str(MFDS_DB))
            self.mfds_conn.row_factory = sqlite3.Row
        if USDA_DB.exists():
            self.usda_conn = sqlite3.connect(str(USDA_DB))
            self.usda_conn.row_factory = sqlite3.Row

    def lookup_korean(self, food_name: str, limit: int = 5) -> list[dict]:
        """Search MFDS Korean food DB by name (fuzzy match)."""
        if not self.mfds_conn:
            return []
        cursor = self.mfds_conn.cursor()
        cursor.execute(
            """SELECT food_name_kr, category1, category2, serving_size,
                      energy_kcal, protein_g, fat_g, carbohydrate_g,
                      dietary_fiber_g, sodium_mg, calcium_mg, iron_mg,
                      vitamin_c_mg, cholesterol_mg, total_sugar_g
               FROM foods
               WHERE food_name_kr LIKE ?
               ORDER BY LENGTH(food_name_kr) ASC
               LIMIT ?""",
            (f"%{food_name}%", limit)
        )
        return [dict(row) for row in cursor.fetchall()]

    def lookup_international(self, food_name: str, limit: int = 5) -> list[dict]:
        """Search USDA international food DB by description."""
        if not self.usda_conn:
            return []
        cursor = self.usda_conn.cursor()
        cursor.execute(
            """SELECT f.fdc_id, f.description, f.food_category, f.data_type
               FROM foods f
               WHERE f.description LIKE ?
               ORDER BY LENGTH(f.description) ASC
               LIMIT ?""",
            (f"%{food_name}%", limit)
        )
        foods = [dict(row) for row in cursor.fetchall()]

        for food in foods:
            cursor.execute(
                """SELECT nutrient_name, amount, unit
                   FROM nutrients
                   WHERE fdc_id = ?
                   AND nutrient_name IN (
                       'Energy', 'Protein', 'Total lipid (fat)',
                       'Carbohydrate, by difference', 'Fiber, total dietary',
                       'Sodium, Na', 'Sugars, Total',
                       'Cholesterol', 'Calcium, Ca', 'Iron, Fe'
                   )""",
                (food["fdc_id"],)
            )
            food["nutrients"] = {row["nutrient_name"]: row["amount"] for row in cursor.fetchall()}

        return foods

    def lookup(self, food_name: str) -> Optional[dict]:
        """
        Primary lookup: try Korean DB first, then USDA fallback.
        Returns standardized nutrition dict or None.
        """
        # Try Korean DB first
        korean_results = self.lookup_korean(food_name)
        if korean_results:
            best = korean_results[0]
            return {
                "food_name": best["food_name_kr"],
                "source": "MFDS",
                "category": best.get("category1", ""),
                "serving_size": best.get("serving_size", "100g"),
                "energy_kcal": best.get("energy_kcal"),
                "protein_g": best.get("protein_g"),
                "fat_g": best.get("fat_g"),
                "carbohydrate_g": best.get("carbohydrate_g"),
                "dietary_fiber_g": best.get("dietary_fiber_g"),
                "sodium_mg": best.get("sodium_mg"),
                "total_sugar_g": best.get("total_sugar_g"),
                "cholesterol_mg": best.get("cholesterol_mg"),
            }

        # Fallback to USDA
        usda_results = self.lookup_international(food_name)
        if usda_results:
            best = usda_results[0]
            nutrients = best.get("nutrients", {})
            return {
                "food_name": best["description"],
                "source": "USDA",
                "category": best.get("food_category", ""),
                "serving_size": "100g",
                "energy_kcal": nutrients.get("Energy"),
                "protein_g": nutrients.get("Protein"),
                "fat_g": nutrients.get("Total lipid (fat)"),
                "carbohydrate_g": nutrients.get("Carbohydrate, by difference"),
                "dietary_fiber_g": nutrients.get("Fiber, total dietary"),
                "sodium_mg": nutrients.get("Sodium, Na"),
                "total_sugar_g": nutrients.get("Sugars, Total"),
                "cholesterol_mg": nutrients.get("Cholesterol"),
            }

        return None

    def get_stats(self) -> dict:
        """Get database statistics."""
        stats = {}
        if self.mfds_conn:
            c = self.mfds_conn.cursor()
            c.execute("SELECT COUNT(*) FROM foods")
            stats["mfds_foods"] = c.fetchone()[0]
        if self.usda_conn:
            c = self.usda_conn.cursor()
            c.execute("SELECT COUNT(*) FROM foods")
            stats["usda_foods"] = c.fetchone()[0]
        stats["total_foods"] = stats.get("mfds_foods", 0) + stats.get("usda_foods", 0)
        return stats

    def close(self):
        if self.mfds_conn:
            self.mfds_conn.close()
        if self.usda_conn:
            self.usda_conn.close()
