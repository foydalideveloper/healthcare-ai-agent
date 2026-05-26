"""
Step 2: Smart Event Processor
Reads raw events from user_activity_event → extracts health facts →
distributes to proper tables (user_lifestyle, user_food_log, user_medication).

This is what the Lifestyle & Gene Agent will do in production.
For now, uses rule-based extraction (no LLM needed).

Usage:
  C:\\...\\python.exe backend/glasses_watcher/event_processor.py
"""

import io
import json
import os
import re
import sys
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

if sys.platform == "win32":
    # Idempotent: only wrap if the host (e.g. watcher.py) didn't already
    # set stdout to utf-8. Double-wrapping causes the OLD wrapper to be
    # garbage-collected immediately, which CPython implements by closing
    # the shared underlying raw stdout buffer — making the NEW wrapper
    # unwritable. Symptom: ValueError "I/O operation on closed file" the
    # first time event_processor.print() runs after import.
    _enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    if not _enc.startswith("utf"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx

PROJECT_ROOT = Path(__file__).parent.parent.parent
KST = timezone(timedelta(hours=9))

# Supabase config
SUPABASE_URL = ""
SUPABASE_KEY = ""
env_path = PROJECT_ROOT / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SUPABASE_URL="):
            SUPABASE_URL = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            SUPABASE_KEY = line.split("=", 1)[1].strip()

TEST_USER_ID = 1
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ── Food Knowledge Base (common foods with estimated calories) ──
FOOD_DB = {
    # Korean foods
    "samgyeopsal": {"kr": "삼겹살", "kcal_per_serving": 500, "protein_g": 30, "fat_g": 40, "carb_g": 0, "serving_g": 200},
    "삼겹살": {"kr": "삼겹살", "kcal_per_serving": 500, "protein_g": 30, "fat_g": 40, "carb_g": 0, "serving_g": 200},
    "bibimbap": {"kr": "비빔밥", "kcal_per_serving": 550, "protein_g": 18, "fat_g": 12, "carb_g": 85, "serving_g": 400},
    "비빔밥": {"kr": "비빔밥", "kcal_per_serving": 550, "protein_g": 18, "fat_g": 12, "carb_g": 85, "serving_g": 400},
    "kimchi jjigae": {"kr": "김치찌개", "kcal_per_serving": 200, "protein_g": 12, "fat_g": 8, "carb_g": 15, "serving_g": 300},
    "김치찌개": {"kr": "김치찌개", "kcal_per_serving": 200, "protein_g": 12, "fat_g": 8, "carb_g": 15, "serving_g": 300},
    "rice": {"kr": "밥", "kcal_per_serving": 300, "protein_g": 6, "fat_g": 1, "carb_g": 65, "serving_g": 200},
    "밥": {"kr": "밥", "kcal_per_serving": 300, "protein_g": 6, "fat_g": 1, "carb_g": 65, "serving_g": 200},
    "ramen": {"kr": "라면", "kcal_per_serving": 500, "protein_g": 10, "fat_g": 16, "carb_g": 75, "serving_g": 550},
    "라면": {"kr": "라면", "kcal_per_serving": 500, "protein_g": 10, "fat_g": 16, "carb_g": 75, "serving_g": 550},
    "chicken": {"kr": "치킨", "kcal_per_serving": 400, "protein_g": 35, "fat_g": 20, "carb_g": 15, "serving_g": 200},
    "pizza": {"kr": "피자", "kcal_per_serving": 300, "protein_g": 12, "fat_g": 12, "carb_g": 35, "serving_g": 150},
    "sandwich": {"kr": "샌드위치", "kcal_per_serving": 350, "protein_g": 15, "fat_g": 14, "carb_g": 40, "serving_g": 200},
    "coffee": {"kr": "커피", "kcal_per_serving": 5, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250},
    "water": {"kr": "물", "kcal_per_serving": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250},
    # Teas
    "black tea": {"kr": "홍차", "kcal_per_serving": 2, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250},
    "green tea": {"kr": "녹차", "kcal_per_serving": 2, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250},
    "tea": {"kr": "차", "kcal_per_serving": 2, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250},
    "홍차": {"kr": "홍차", "kcal_per_serving": 2, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250},
    "녹차": {"kr": "녹차", "kcal_per_serving": 2, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250},
    # More drinks
    "juice": {"kr": "주스", "kcal_per_serving": 110, "protein_g": 1, "fat_g": 0, "carb_g": 26, "serving_g": 250},
    "milk": {"kr": "우유", "kcal_per_serving": 150, "protein_g": 8, "fat_g": 8, "carb_g": 12, "serving_g": 250},
    "soda": {"kr": "탄산음료", "kcal_per_serving": 140, "protein_g": 0, "fat_g": 0, "carb_g": 39, "serving_g": 355},
    "beer": {"kr": "맥주", "kcal_per_serving": 150, "protein_g": 1, "fat_g": 0, "carb_g": 13, "serving_g": 355},
    "soju": {"kr": "소주", "kcal_per_serving": 540, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 360},
    # More Korean foods
    "kimchi": {"kr": "김치", "kcal_per_serving": 15, "protein_g": 1, "fat_g": 0, "carb_g": 2, "serving_g": 50},
    "tteokbokki": {"kr": "떡볶이", "kcal_per_serving": 330, "protein_g": 8, "fat_g": 5, "carb_g": 65, "serving_g": 250},
    "떡볶이": {"kr": "떡볶이", "kcal_per_serving": 330, "protein_g": 8, "fat_g": 5, "carb_g": 65, "serving_g": 250},
    "gimbap": {"kr": "김밥", "kcal_per_serving": 400, "protein_g": 12, "fat_g": 8, "carb_g": 70, "serving_g": 250},
    "김밥": {"kr": "김밥", "kcal_per_serving": 400, "protein_g": 12, "fat_g": 8, "carb_g": 70, "serving_g": 250},
    "jjajangmyeon": {"kr": "짜장면", "kcal_per_serving": 650, "protein_g": 15, "fat_g": 18, "carb_g": 100, "serving_g": 500},
    "짜장면": {"kr": "짜장면", "kcal_per_serving": 650, "protein_g": 15, "fat_g": 18, "carb_g": 100, "serving_g": 500},
    "doenjang jjigae": {"kr": "된장찌개", "kcal_per_serving": 150, "protein_g": 10, "fat_g": 5, "carb_g": 12, "serving_g": 300},
    "된장찌개": {"kr": "된장찌개", "kcal_per_serving": 150, "protein_g": 10, "fat_g": 5, "carb_g": 12, "serving_g": 300},
    # Common international foods
    "egg": {"kr": "계란", "kcal_per_serving": 70, "protein_g": 6, "fat_g": 5, "carb_g": 0, "serving_g": 50},
    "eggs": {"kr": "계란", "kcal_per_serving": 140, "protein_g": 12, "fat_g": 10, "carb_g": 0, "serving_g": 100},
    "bread": {"kr": "빵", "kcal_per_serving": 80, "protein_g": 3, "fat_g": 1, "carb_g": 15, "serving_g": 30},
    "salad": {"kr": "샐러드", "kcal_per_serving": 100, "protein_g": 3, "fat_g": 5, "carb_g": 10, "serving_g": 150},
    "steak": {"kr": "스테이크", "kcal_per_serving": 500, "protein_g": 45, "fat_g": 35, "carb_g": 0, "serving_g": 200},
    "pasta": {"kr": "파스타", "kcal_per_serving": 400, "protein_g": 12, "fat_g": 8, "carb_g": 70, "serving_g": 250},
    "burger": {"kr": "버거", "kcal_per_serving": 550, "protein_g": 25, "fat_g": 30, "carb_g": 45, "serving_g": 200},
    "hamburger": {"kr": "햄버거", "kcal_per_serving": 550, "protein_g": 25, "fat_g": 30, "carb_g": 45, "serving_g": 200},
    "french fries": {"kr": "감자튀김", "kcal_per_serving": 365, "protein_g": 4, "fat_g": 17, "carb_g": 48, "serving_g": 117},
    "fries": {"kr": "감자튀김", "kcal_per_serving": 365, "protein_g": 4, "fat_g": 17, "carb_g": 48, "serving_g": 117},
    "감자튀김": {"kr": "감자튀김", "kcal_per_serving": 365, "protein_g": 4, "fat_g": 17, "carb_g": 48, "serving_g": 117},
    "potato": {"kr": "감자", "kcal_per_serving": 160, "protein_g": 4, "fat_g": 0, "carb_g": 37, "serving_g": 200},
    "nuggets": {"kr": "치킨너겟", "kcal_per_serving": 300, "protein_g": 15, "fat_g": 18, "carb_g": 16, "serving_g": 100},
    "chicken nuggets": {"kr": "치킨너겟", "kcal_per_serving": 300, "protein_g": 15, "fat_g": 18, "carb_g": 16, "serving_g": 100},
    "wings": {"kr": "치킨윙", "kcal_per_serving": 400, "protein_g": 28, "fat_g": 28, "carb_g": 5, "serving_g": 150},
    "soup": {"kr": "수프", "kcal_per_serving": 150, "protein_g": 5, "fat_g": 5, "carb_g": 20, "serving_g": 300},
    "yogurt": {"kr": "요거트", "kcal_per_serving": 120, "protein_g": 6, "fat_g": 3, "carb_g": 18, "serving_g": 150},
    "요거트": {"kr": "요거트", "kcal_per_serving": 120, "protein_g": 6, "fat_g": 3, "carb_g": 18, "serving_g": 150},
    "cereal": {"kr": "시리얼", "kcal_per_serving": 200, "protein_g": 5, "fat_g": 3, "carb_g": 40, "serving_g": 50},
    "toast": {"kr": "토스트", "kcal_per_serving": 180, "protein_g": 6, "fat_g": 6, "carb_g": 26, "serving_g": 60},
    "bacon": {"kr": "베이컨", "kcal_per_serving": 200, "protein_g": 14, "fat_g": 15, "carb_g": 1, "serving_g": 50},
    "sausage": {"kr": "소시지", "kcal_per_serving": 250, "protein_g": 12, "fat_g": 22, "carb_g": 2, "serving_g": 80},
    "donut": {"kr": "도넛", "kcal_per_serving": 250, "protein_g": 3, "fat_g": 14, "carb_g": 28, "serving_g": 60},
    "muffin": {"kr": "머핀", "kcal_per_serving": 300, "protein_g": 5, "fat_g": 12, "carb_g": 45, "serving_g": 100},
    "bagel": {"kr": "베이글", "kcal_per_serving": 280, "protein_g": 10, "fat_g": 2, "carb_g": 56, "serving_g": 100},
    "noodle": {"kr": "국수", "kcal_per_serving": 350, "protein_g": 10, "fat_g": 3, "carb_g": 70, "serving_g": 300},
    "noodles": {"kr": "국수", "kcal_per_serving": 350, "protein_g": 10, "fat_g": 3, "carb_g": 70, "serving_g": 300},
    # Snacks
    "chocolate": {"kr": "초콜릿", "kcal_per_serving": 230, "protein_g": 3, "fat_g": 13, "carb_g": 25, "serving_g": 45},
    "candy": {"kr": "사탕", "kcal_per_serving": 60, "protein_g": 0, "fat_g": 0, "carb_g": 15, "serving_g": 15},
    "chips": {"kr": "과자", "kcal_per_serving": 150, "protein_g": 2, "fat_g": 10, "carb_g": 15, "serving_g": 28},
    "cookie": {"kr": "쿠키", "kcal_per_serving": 140, "protein_g": 2, "fat_g": 7, "carb_g": 19, "serving_g": 30},
    "cookies": {"kr": "쿠키", "kcal_per_serving": 140, "protein_g": 2, "fat_g": 7, "carb_g": 19, "serving_g": 30},
    "ice cream": {"kr": "아이스크림", "kcal_per_serving": 200, "protein_g": 3, "fat_g": 11, "carb_g": 22, "serving_g": 100},
    "fruit": {"kr": "과일", "kcal_per_serving": 60, "protein_g": 1, "fat_g": 0, "carb_g": 15, "serving_g": 100},
    # Generic meal labels (previously fell to 200g-for-everything default)
    "breakfast": {"kr": "아침식사", "kcal_per_serving": 400, "protein_g": 15, "fat_g": 15, "carb_g": 50, "serving_g": 300, "portion_confidence": 0.4},
    "lunch":     {"kr": "점심식사", "kcal_per_serving": 600, "protein_g": 25, "fat_g": 20, "carb_g": 75, "serving_g": 400, "portion_confidence": 0.4},
    "dinner":    {"kr": "저녁식사", "kcal_per_serving": 600, "protein_g": 25, "fat_g": 20, "carb_g": 75, "serving_g": 400, "portion_confidence": 0.4},
    "snack":     {"kr": "간식",     "kcal_per_serving": 150, "protein_g": 3,  "fat_g": 7,  "carb_g": 20, "serving_g": 60,  "portion_confidence": 0.4},
    "meal":      {"kr": "식사",     "kcal_per_serving": 500, "protein_g": 20, "fat_g": 18, "carb_g": 60, "serving_g": 350, "portion_confidence": 0.4},
    # Generic drinks detected by YOLO container label
    "drink (cup)":    {"kr": "음료수", "kcal_per_serving": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 250, "portion_confidence": 0.6},
    "drink (bottle)": {"kr": "음료수", "kcal_per_serving": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 500, "portion_confidence": 0.6},
    "drink (glass)":  {"kr": "음료수", "kcal_per_serving": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0, "serving_g": 150, "portion_confidence": 0.6},
}

# ── Medication Knowledge Base ──
MED_DB = {
    "vitamin d": {"drug_name": "Vitamin D", "drug_code": "A11CC05", "default_dose": 1000, "unit": "IU"},
    "vitamin c": {"drug_name": "Vitamin C", "drug_code": "A11GA01", "default_dose": 500, "unit": "mg"},
    "omega 3": {"drug_name": "Omega-3", "drug_code": "C10AX06", "default_dose": 1000, "unit": "mg"},
    "metformin": {"drug_name": "Metformin", "drug_code": "A10BA02", "default_dose": 500, "unit": "mg"},
    "aspirin": {"drug_name": "Aspirin", "drug_code": "N02BA01", "default_dose": 100, "unit": "mg"},
    "multivitamin": {"drug_name": "Multivitamin", "drug_code": "A11BA", "default_dose": 1, "unit": "tablet"},
    "iron": {"drug_name": "Iron supplement", "drug_code": "B03AA07", "default_dose": 65, "unit": "mg"},
    "calcium": {"drug_name": "Calcium", "drug_code": "A12AA04", "default_dose": 500, "unit": "mg"},
    "magnesium": {"drug_name": "Magnesium", "drug_code": "A12CC", "default_dose": 400, "unit": "mg"},
    "probiotics": {"drug_name": "Probiotics", "drug_code": "A07FA", "default_dose": 1, "unit": "capsule"},
    "protein powder": {"drug_name": "Protein Powder", "drug_code": "SUPP01", "default_dose": 30, "unit": "g"},
    "pre-workout": {"drug_name": "Pre-workout", "drug_code": "SUPP02", "default_dose": 1, "unit": "scoop"},
    "creatine": {"drug_name": "Creatine", "drug_code": "SUPP03", "default_dose": 5, "unit": "g"},
    "zinc": {"drug_name": "Zinc", "drug_code": "A12CB", "default_dose": 15, "unit": "mg"},
    "melatonin": {"drug_name": "Melatonin", "drug_code": "N05CH01", "default_dose": 3, "unit": "mg"},
    "collagen": {"drug_name": "Collagen", "drug_code": "SUPP04", "default_dose": 10, "unit": "g"},
}

# Tobacco/Nicotine tracking (health RISK items)
TOBACCO_DB = {
    "cigarette": {"name": "Cigarette", "risk_level": "HIGH", "health_impact": "lung cancer, heart disease, stroke"},
    "cigarettes": {"name": "Cigarette", "risk_level": "HIGH", "health_impact": "lung cancer, heart disease, stroke"},
    "smoked": {"name": "Cigarette", "risk_level": "HIGH", "health_impact": "lung cancer, heart disease, stroke"},
    "smoking": {"name": "Cigarette", "risk_level": "HIGH", "health_impact": "lung cancer, heart disease, stroke"},
    "vape": {"name": "Vape/E-cigarette", "risk_level": "HIGH", "health_impact": "lung damage, nicotine addiction"},
    "vaping": {"name": "Vape/E-cigarette", "risk_level": "HIGH", "health_impact": "lung damage, nicotine addiction"},
    "e-cigarette": {"name": "E-cigarette", "risk_level": "HIGH", "health_impact": "lung damage, nicotine addiction"},
    "hookah": {"name": "Hookah", "risk_level": "HIGH", "health_impact": "lung cancer, heart disease"},
    "cigar": {"name": "Cigar", "risk_level": "HIGH", "health_impact": "oral cancer, lung cancer"},
    "snus": {"name": "Snus", "risk_level": "MODERATE", "health_impact": "oral cancer risk"},
    "nicotine gum": {"name": "Nicotine Gum", "risk_level": "LOW", "health_impact": "nicotine replacement therapy"},
    "nicotine patch": {"name": "Nicotine Patch", "risk_level": "LOW", "health_impact": "nicotine replacement therapy"},
    "담배": {"name": "Cigarette", "risk_level": "HIGH", "health_impact": "lung cancer, heart disease, stroke"},
    "전자담배": {"name": "E-cigarette", "risk_level": "HIGH", "health_impact": "lung damage, nicotine addiction"},
}


class EventProcessor:
    """Processes raw events from user_activity_event and distributes to proper tables."""

    def __init__(self):
        self.daily_totals = {
            "total_calories": 0,
            "protein_g": 0,
            "fat_g": 0,
            "carb_g": 0,
            "meal_count": 0,
            "exercise_min": 0,
            "hydration_ml": 0,
            "medications": [],
            "foods": [],
        }
        # Load MFDS + USDA databases for real nutrition lookup
        self.mfds_conn = None
        self.usda_conn = None
        mfds_path = PROJECT_ROOT / "backend" / "data" / "food_db" / "food_nutrition.db"
        usda_path = PROJECT_ROOT / "backend" / "data" / "food_db" / "usda_food_nutrition.db"
        if mfds_path.exists():
            import sqlite3
            self.mfds_conn = sqlite3.connect(str(mfds_path))
            self.mfds_conn.row_factory = sqlite3.Row
        if usda_path.exists():
            import sqlite3
            self.usda_conn = sqlite3.connect(str(usda_path))
            self.usda_conn.row_factory = sqlite3.Row

    # Common English words that are NOT food names but appear in MFDS product names,
    # causing false-positive matches (e.g. "delicious" → "DELICIOUS PROJECT 베이글칩").
    _NON_FOOD_WORDS = {
        "delicious", "tasty", "yummy", "good", "great", "bad", "nice", "amazing",
        "wonderful", "fantastic", "spicy", "sweet", "salty", "savory", "fresh",
        "healthy", "unhealthy", "real", "original", "special", "premium", "classic",
        "natural", "organic", "light", "rich", "smooth", "crispy", "crunchy",
    }

    @staticmethod
    def _parse_serving_size_g(s: str | None) -> float:
        """Parse MFDS `serving_size` (e.g. '100g', '100mL', '354mL', '30g',
        '4㎍ RAE') into a gram-equivalent. Treats g and mL as 1:1 (true for
        water-density foods, close enough for soups/drinks). Falls back to
        100 g for unparseable / vitamin-microgram entries — matches the
        per-100 normalization that 99.8% of MFDS rows use anyway."""
        if not s:
            return 100.0
        # Find the first numeric run; handle unicode digits as well.
        m = re.match(r'\s*([0-9]+(?:\.[0-9]+)?)', s.strip())
        if not m:
            return 100.0
        try:
            n = float(m.group(1))
        except ValueError:
            return 100.0
        # Accept g and mL; reject µg/mg/RAE (those are vitamin units, not portions).
        unit = s[m.end():].strip().lower()
        if unit in ("", "g", "ml", "mℓ", "그램"):
            return n
        # Unrecognized unit (㎍, ㎎ etc. = trace-nutrient row, not a real serving)
        return 100.0

    def lookup_food_nutrition(self, food_name: str, portion_g: float | None = None) -> dict | None:
        """Search 289,447 foods in MFDS + USDA databases.

        MFDS values are normalized per `serving_size` (almost always 100 g/mL),
        so callers that want absolute nutrition for a real portion must supply
        `portion_g`. The legacy `portion_g=None` form returns raw per-source
        values — kept for backward compat but typically a bug at the call site.

        Return shape:
            name, source, kcal, protein_g, fat_g, carb_g,
            serving_size_g (source serving as parsed grams),
            portion_g      (echo of requested portion, or serving_size_g if None)
        """
        # Block common English adjectives — they substring-match branded product names
        # and produce false positives (e.g. "delicious" → "DELICIOUS PROJECT 갈릭디핑...").
        if food_name.lower().strip() in self._NON_FOOD_WORDS:
            return None

        def _scale(raw: dict, source_serving_g: float) -> dict:
            """Scale per-source values to the caller's requested portion.
            If `portion_g` is None, leave values raw and report the source
            serving as the effective portion."""
            target = portion_g if portion_g is not None else source_serving_g
            factor = (target / source_serving_g) if source_serving_g > 0 else 1.0
            return {
                **raw,
                "kcal":      round((raw.get("kcal")      or 0) * factor, 2),
                "protein_g": round((raw.get("protein_g") or 0) * factor, 2),
                "fat_g":     round((raw.get("fat_g")     or 0) * factor, 2),
                "carb_g":    round((raw.get("carb_g")    or 0) * factor, 2),
                "serving_size_g": source_serving_g,
                "portion_g": target,
            }

        # Try MFDS first (Korean foods)
        if self.mfds_conn:
            cursor = self.mfds_conn.cursor()
            cursor.execute(
                """SELECT food_name_kr, energy_kcal, protein_g, fat_g, carbohydrate_g,
                          dietary_fiber_g, sodium_mg, serving_size
                   FROM foods WHERE food_name_kr LIKE ?
                   ORDER BY LENGTH(food_name_kr) ASC LIMIT 1""",
                (f"%{food_name}%",)
            )
            row = cursor.fetchone()
            if row:
                source_serving_g = self._parse_serving_size_g(row["serving_size"])
                return _scale({
                    "name": row["food_name_kr"],
                    "source": "MFDS",
                    "kcal": row["energy_kcal"] or 0,
                    "protein_g": row["protein_g"] or 0,
                    "fat_g": row["fat_g"] or 0,
                    "carb_g": row["carbohydrate_g"] or 0,
                }, source_serving_g)

        # Try USDA (international). USDA `nutrients` are per 100 g by convention
        # (the FDC "Foundation Foods" / "SR Legacy" tables both use 100 g basis).
        if self.usda_conn:
            cursor = self.usda_conn.cursor()
            cursor.execute(
                """SELECT f.description, f.fdc_id FROM foods f
                   WHERE f.description LIKE ?
                   ORDER BY LENGTH(f.description) ASC LIMIT 1""",
                (f"%{food_name}%",)
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    """SELECT nutrient_name, amount FROM nutrients
                       WHERE fdc_id = ? AND nutrient_name IN
                       ('Energy','Protein','Total lipid (fat)','Carbohydrate, by difference')""",
                    (row["fdc_id"],)
                )
                nutrients = {r["nutrient_name"]: r["amount"] for r in cursor.fetchall()}
                return _scale({
                    "name": row["description"],
                    "source": "USDA",
                    "kcal": nutrients.get("Energy", 0),
                    "protein_g": nutrients.get("Protein", 0),
                    "fat_g": nutrients.get("Total lipid (fat)", 0),
                    "carb_g": nutrients.get("Carbohydrate, by difference", 0),
                }, 100.0)

        return None

    # ── Extract from Audio Transcript ──

    def extract_from_transcript(self, transcript: str) -> dict:
        """Extract health facts from voice transcript using rule-based parsing."""
        text = transcript.lower()
        extracted = {
            "exercise": None,
            "foods": [],
            "medications": [],
            "tobacco": [],
            "sleep": None,
            "hydration": None,
            "biometrics": {},   # heart_rate, sbp, dbp, glucose_mgdl, weight_kg
            "mental": {},        # stress_level, mood, energy
        }

        # Exercise extraction
        exercise_patterns = [
            r'exercis\w*\s+(?:for\s+)?(\d+)\s*(?:to\s*(\d+))?\s*min',
            r'(\d+)\s*(?:to\s*(\d+))?\s*min\w*\s+(?:of\s+)?exercis',
            r'(?:ran|run|jog\w*|walk\w*|swim\w*|cycl\w*)\s+(?:for\s+)?(\d+)\s*min',
            r'운동\s*(\d+)\s*분',
            r'(\d+)\s*분\s*운동',
        ]
        for pattern in exercise_patterns:
            m = re.search(pattern, text)
            if m:
                mins = int(m.group(1))
                if m.lastindex >= 2 and m.group(2):
                    mins = (int(m.group(1)) + int(m.group(2))) // 2
                extracted["exercise"] = {"minutes": mins, "type": "general"}
                for etype in ["running", "jogging", "walking", "swimming", "cycling", "yoga", "weight"]:
                    if etype in text:
                        extracted["exercise"]["type"] = etype
                        break
                # Extract stated time-of-day so caller can backfill detected_at.
                # Matches "at 9am", "at 9:30 am", "at 14:00", etc.
                tm = re.search(
                    r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b'
                    r'|\bat\s+(1[0-9]|2[0-3]|[0-9]):([0-5][0-9])\b',
                    text,
                )
                if tm:
                    if tm.group(3):  # 12-hour form
                        h = int(tm.group(1)); minute = int(tm.group(2) or 0)
                        if tm.group(3) == 'pm' and h != 12:
                            h += 12
                        elif tm.group(3) == 'am' and h == 12:
                            h = 0
                    else:            # 24-hour form
                        h = int(tm.group(4)); minute = int(tm.group(5))
                    extracted["exercise"]["event_time"] = f"{h:02d}:{minute:02d}"
                break

        # Food extraction - Step 1: Check hardcoded list (longest-match wins,
        # deduped by canonical Korean name). Prevents "black tea" from also
        # matching "tea" as a substring, and prevents "tea"+"차" double-logging.
        found_foods = set()
        found_canonical = set()
        matched_ranges: list[tuple[int, int]] = []
        text_lower = text.lower()
        for food_key in sorted(FOOD_DB.keys(), key=len, reverse=True):
            food_info = FOOD_DB[food_key]
            key_lower = food_key.lower()
            idx = text_lower.find(key_lower)
            if idx == -1:
                continue
            end = idx + len(key_lower)
            if any(not (end <= ms or idx >= me) for ms, me in matched_ranges):
                continue
            canonical = food_info["kr"]
            if canonical in found_canonical:
                continue
            extracted["foods"].append({
                "name": food_info["kr"],
                "english": food_key,
                "kcal": food_info["kcal_per_serving"],
                "protein_g": food_info["protein_g"],
                "fat_g": food_info["fat_g"],
                "carb_g": food_info["carb_g"],
                "serving_g": food_info.get("serving_g", 200),
            })
            found_foods.add(food_key)
            found_canonical.add(canonical)
            matched_ranges.append((idx, end))

        # Food extraction - Step 2: Search MFDS/USDA for foods NOT in hardcoded list
        # Patterns catch: "had X", "with X", "and X", "plus X" — continuation
        # phrases after an initial food verb (so "a burger with fries" extracts both).
        food_patterns = [
            r'(?:ate|eat|eating|had|have)\s+(?:a\s+|some\s+)?(.+?)(?:\s+for|\s+in|\s+at|\.|\,|$)',
            r'(?:drinking|drank|drink)\s+(?:a\s+|some\s+)?(.+?)(?:\s+and|\s+now|\.|\,|$)',
            r'(?:with|and|plus)\s+(?:a\s+|some\s+)?([a-z가-힣]+(?:\s+[a-z가-힣]+){0,2})(?:\s+and|\s+in|\.|\,|$)',
        ]
        for pattern in food_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                food_term = match.strip().rstrip('.')
                if not food_term or len(food_term) <= 2:
                    continue
                if food_term in found_foods:
                    continue
                # Skip MFDS lookup if any word of the phrase already matched
                # via hardcoded FOOD_DB. Prevents "iced tea" matching a random
                # product named "... Iced Tea" in the 275K MFDS database.
                term_words = set(food_term.lower().split())
                if term_words & found_foods:
                    continue
                # Search in 289K food database
                if True:
                    db_result = self.lookup_food_nutrition(food_term)
                    if db_result:
                        extracted["foods"].append({
                            "name": db_result["name"],
                            "english": food_term,
                            "kcal": db_result["kcal"],
                            "protein_g": db_result["protein_g"],
                            "fat_g": db_result["fat_g"],
                            "carb_g": db_result["carb_g"],
                            "source_db": db_result["source"],
                        })
                        found_foods.add(food_term)

        # Medication extraction
        for med_key, med_info in MED_DB.items():
            if med_key in text:
                extracted["medications"].append({
                    "drug_name": med_info["drug_name"],
                    "drug_code": med_info["drug_code"],
                    "dose": med_info["default_dose"],
                    "unit": med_info["unit"],
                })

        # Tobacco/nicotine detection
        for tob_key, tob_info in TOBACCO_DB.items():
            if tob_key in text:
                extracted["tobacco"].append({
                    "name": tob_info["name"],
                    "risk_level": tob_info["risk_level"],
                    "health_impact": tob_info["health_impact"],
                })
                break  # Don't double-count same smoking event

        # Sleep extraction
        sleep_patterns = [
            r'(?:woke up|woke|got up|wake up)\s+(?:at\s+)?(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?',
            r'(?:slept|sleep|went to bed)\s+(?:at\s+)?(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?',
            r'(\d{1,2})\s*시\s*(?:에\s+)?(?:일어|기상)',
        ]
        for pattern in sleep_patterns:
            m = re.search(pattern, text)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.lastindex >= 2 and m.group(2) else 0
                period = m.group(3) if m.lastindex >= 3 and m.group(3) else None
                if period and "p" in period.lower() and hour < 12:
                    hour += 12
                extracted["sleep"] = {"wake_time": f"{hour:02d}:{minute:02d}"}
                break

        # Water/hydration
        water_patterns = [
            r'(?:drank|drink|drinking)\s+(?:a\s+)?(?:glass|cup|bottle)\s+(?:of\s+)?water',
            r'(?:drank|drink)\s+water',
            r'물\s*(?:을\s+)?마',
        ]
        for pattern in water_patterns:
            if re.search(pattern, text):
                extracted["hydration"] = {"ml": 250, "type": "water"}
                break

        # Sleep hours (in addition to wake-time patterns above)
        m = re.search(r'slept\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)', text)
        if not m:
            m = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\s+(?:of\s+)?sleep', text)
        if not m:
            m = re.search(r'(\d+(?:\.\d+)?)\s*시간\s*(?:잠|잤|수면)', text)
        if m:
            hours = float(m.group(1))
            if extracted["sleep"] is None:
                extracted["sleep"] = {}
            extracted["sleep"]["hours"] = hours

        # Biometrics: heart rate
        m = re.search(r'(?:heart\s*rate|pulse|hr|심박수)\s*(?:is|was|=|:)?\s*(\d{2,3})', text)
        if m: extracted["biometrics"]["heart_rate"] = int(m.group(1))
        # Blood pressure e.g. "BP 120/80" or "blood pressure 120 over 80"
        m = re.search(r'(?:bp|blood\s*pressure|혈압)\s*(?:is|was|=|:)?\s*(\d{2,3})\s*[/over]+\s*(\d{2,3})', text)
        if m:
            extracted["biometrics"]["sbp"] = int(m.group(1))
            extracted["biometrics"]["dbp"] = int(m.group(2))
        # Glucose
        m = re.search(r'(?:glucose|blood\s*sugar|혈당)\s*(?:is|was|=|:)?\s*(\d{2,3})', text)
        if m: extracted["biometrics"]["glucose_mgdl"] = int(m.group(1))
        # Weight
        m = re.search(r'(?:weight|체중)\s*(?:is|was|=|:)?\s*(\d{2,3}(?:\.\d+)?)\s*(?:kg|킬로)', text)
        if m: extracted["biometrics"]["weight_kg"] = float(m.group(1))

        # Mental: stress level 1-10
        m = re.search(r'(?:stress|stressed|스트레스)\s*(?:level|is|=|:)?\s*(\d{1,2})', text)
        if m:
            lvl = int(m.group(1))
            if 1 <= lvl <= 10:
                extracted["mental"]["stress_level"] = lvl
        # Mood keywords
        for mood_kw in ["happy", "sad", "anxious", "tired", "energetic", "calm", "angry", "frustrated",
                         "기분좋", "우울", "피곤", "불안", "화나", "평온"]:
            if mood_kw in text:
                extracted["mental"]["mood"] = mood_kw
                break

        return extracted

    # ── Extract from Photo/Video Events ──

    def extract_from_detection(self, event_data: dict) -> dict:
        """Extract health facts from YOLO detection events."""
        extracted = {
            "exercise": None,
            "foods": [],
            "medications": [],
            "hydration": None,
        }

        health_data = event_data.get("health_data", {})
        event_type = event_data.get("event_type", "")

        if event_type == "drink":
            ml = health_data.get("hydration_ml", 250)
            extracted["hydration"] = {"ml": ml, "type": health_data.get("container", "cup")}

        elif event_type == "meal":
            extracted["foods"].append({
                "name": health_data.get("meal_type", "meal"),
                "kcal": 400,  # Default estimate when we can't identify specific food
                "protein_g": 15,
                "fat_g": 15,
                "carb_g": 50,
            })

        elif event_type == "exercise":
            extracted["exercise"] = {
                "minutes": 30,  # Default estimate
                "type": health_data.get("equipment", "general"),
            }

        return extracted

    # ── Write to Supabase Tables ──

    def _supabase_insert(self, table: str, data: dict) -> dict | None:
        try:
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                json=data,
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            print(f"    DB insert to {table} failed: {e}")
            if hasattr(e, "response"):
                print(f"    Response: {e.response.text[:300]}")
            return None

    def _supabase_upsert(self, table: str, data: dict, conflict_cols: str) -> dict | None:
        try:
            headers = {**HEADERS, "Prefer": "return=representation,resolution=merge-duplicates"}
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                json=data,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            print(f"    DB upsert to {table} failed: {e}")
            if hasattr(e, "response"):
                print(f"    Response: {e.response.text[:300]}")
            return None

    def write_food_log(self, user_id: int, food: dict):
        """Write to user_food_log table.

        Portion tracking: when FOOD_DB returns a known serving_g for the
        matched food, portion is "measured" (high confidence). When the food
        is unrecognized we fall back to 200g with low confidence. The JSONB
        metadata lets the dashboard show "~200g" for guessed portions instead
        of presenting them as accurate measurements.
        """
        now = datetime.now(KST)
        serving_g = food.get("serving_g")
        if serving_g is None:
            portion_g = 200
            portion_source = "default"
            portion_confidence = 0.3
        else:
            portion_g = serving_g
            portion_source = "food_db_lookup"
            portion_confidence = food.get("portion_confidence", 0.85)

        row = {
            "user_id": user_id,
            "consumed_at": now.isoformat(),
            "food_name": food.get("name", "unknown"),
            "portion_g": portion_g,
            # Pass as dict, NOT json.dumps() — httpx JSON-encodes the outer body.
            # json.dumps() here would double-encode and store a JSON string in the
            # JSONB column, making `nutrients_json ->> 'energy_kcal'` return NULL.
            "nutrients_json": {
                "energy_kcal": food.get("kcal", 0),
                "protein_g": food.get("protein_g", 0),
                "fat_g": food.get("fat_g", 0),
                "carbohydrate_g": food.get("carb_g", 0),
                "portion_source": portion_source,
                "portion_confidence": portion_confidence,
            },
            "recognition_confidence": 0.7,
        }
        result = self._supabase_insert("user_food_log", row)
        if result:
            fid = result.get("food_id", "?")
            kcal_disp = food.get("kcal") or 0  # LLMs sometimes return null for kcal
            print(f"    -> user_food_log: food_id={fid} | {food['name']} ({kcal_disp} kcal)")
            self.daily_totals["foods"].append(food["name"])
            # `or 0` guards against LLMs returning null (vs missing key).
            self.daily_totals["total_calories"] += food.get("kcal")     or 0
            self.daily_totals["protein_g"]     += food.get("protein_g") or 0
            self.daily_totals["fat_g"]         += food.get("fat_g")     or 0
            self.daily_totals["carb_g"]        += food.get("carb_g")    or 0
            self.daily_totals["meal_count"] += 1

    def write_medication(self, user_id: int, med: dict):
        """Write a confirmed intake event to user_medication_intake.

        user_medication is a prescription registry (what the user is *supposed*
        to take) and must not be inflated with one row per voice mention — that
        caused the "Vitamin D shows on every day in range" bug because the
        drill-down was expanding each prescription's [start_date, today] window.

        Intakes go to user_medication_intake.taken_at and the drill-down
        aggregates from there. An empty day stays empty until a dose is
        actually confirmed.
        """
        now = datetime.now(timezone.utc)
        row = {
            "user_id": user_id,
            "drug_name": med.get("drug_name", "unknown"),
            "drug_code": med.get("drug_code", ""),
            "dose": med.get("dose", 0),
            "unit": med.get("unit", "mg"),
            "taken_at": now.isoformat(),
            "source": "voice_report",
            "confidence": med.get("confidence", 0.80),
        }
        result = self._supabase_insert("user_medication_intake", row)
        if result:
            iid = result.get("intake_id", "?")
            print(f"    -> user_medication_intake: intake_id={iid} | {med['drug_name']} {med['dose']}{med['unit']}")
            self.daily_totals["medications"].append(med["drug_name"])

    def update_daily_lifestyle(self, user_id: int, exercise_min: int = 0,
                                sleep_end: str = None, hydration_ml: int = 0):
        """Update user_lifestyle daily record."""
        today = date.today().isoformat()
        row = {
            "user_id": user_id,
            "recorded_date": today,
            "total_calories": self.daily_totals["total_calories"],
            "protein_g": self.daily_totals["protein_g"],
            "fat_g": self.daily_totals["fat_g"],
            "carb_g": self.daily_totals["carb_g"],
            "meal_count": self.daily_totals["meal_count"],
            "exercise_min": exercise_min or self.daily_totals["exercise_min"],
            "data_source": "ai_glasses_pipeline",
        }
        result = self._supabase_insert("user_lifestyle", row)
        if result:
            lid = result.get("ls_id", "?")
            print(f"    -> user_lifestyle: ls_id={lid} | {self.daily_totals['total_calories']} kcal, "
                  f"{exercise_min}min exercise, {self.daily_totals['meal_count']} meals")

    # ── Main Process ──

    def process_events(self, user_id: int = TEST_USER_ID):
        """Fetch unprocessed events from Supabase and distribute to proper tables."""
        print("=" * 60)
        print("STEP 2: EVENT PROCESSOR")
        print("user_activity_event -> extract -> distribute to tables")
        print("=" * 60)

        # Fetch recent unprocessed events
        print("\nFetching raw events from user_activity_event...")
        try:
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/user_activity_event",
                params={
                    "user_id": f"eq.{user_id}",
                    "processing_status": "eq.edge_only",
                    "order": "detected_at.desc",
                    "limit": "20",
                },
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            events = resp.json()
        except Exception as e:
            print(f"Failed to fetch events: {e}")
            return

        print(f"Found {len(events)} unprocessed events\n")

        exercise_total = 0
        hydration_total = 0

        for event in events:
            eid = event.get("event_id", "?")
            etype = event.get("event_type", "?")
            raw_data = event.get("structured_data", "{}")

            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    data = {}
            else:
                data = raw_data

            print(f"Event #{eid} ({etype}):")
            desc = data.get("description", "no description")
            print(f"  Raw: {desc[:80]}")

            # Extract health facts based on event type
            if etype == "voice_report":
                transcript = data.get("health_data", {}).get("transcript", "")
                if transcript:
                    extracted = self.extract_from_transcript(transcript)
                    print(f"  Extracted: {json.dumps({k: v for k, v in extracted.items() if v}, default=str)[:200]}")

                    # Distribute to tables
                    for food in extracted["foods"]:
                        self.write_food_log(user_id, food)

                    for med in extracted["medications"]:
                        self.write_medication(user_id, med)

                    if extracted["exercise"]:
                        exercise_total += extracted["exercise"]["minutes"]
                        self.daily_totals["exercise_min"] += extracted["exercise"]["minutes"]
                        print(f"    -> Exercise: {extracted['exercise']['minutes']}min ({extracted['exercise']['type']})")

                    if extracted["sleep"]:
                        print(f"    -> Wake time: {extracted['sleep']['wake_time']}")

                    if extracted["hydration"]:
                        hydration_total += extracted["hydration"]["ml"]
                        self.daily_totals["hydration_ml"] += extracted["hydration"]["ml"]
                        print(f"    -> Hydration: {extracted['hydration']['ml']}ml")

            elif etype in ("meal", "drink", "exercise", "video_analysis"):
                extracted = self.extract_from_detection(data)

                if extracted["hydration"]:
                    hydration_total += extracted["hydration"]["ml"]
                    self.daily_totals["hydration_ml"] += extracted["hydration"]["ml"]
                    print(f"    -> Hydration: {extracted['hydration']['ml']}ml ({extracted['hydration']['type']})")

                for food in extracted["foods"]:
                    self.write_food_log(user_id, food)

                if extracted["exercise"]:
                    exercise_total += extracted["exercise"]["minutes"]
                    self.daily_totals["exercise_min"] += extracted["exercise"]["minutes"]

            # Mark as processed
            try:
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/user_activity_event",
                    params={"event_id": f"eq.{eid}"},
                    json={"processing_status": "processed"},
                    headers=HEADERS,
                    timeout=15,
                )
            except Exception:
                pass

            print()

        # Write daily lifestyle summary
        if self.daily_totals["total_calories"] > 0 or exercise_total > 0:
            print("-" * 60)
            print("DAILY SUMMARY:")
            self.update_daily_lifestyle(user_id, exercise_min=exercise_total)

        # Final report
        print("\n" + "=" * 60)
        print("PROCESSING COMPLETE")
        print("=" * 60)
        print(f"  Events processed: {len(events)}")
        print(f"  Foods logged:     {self.daily_totals['foods']}")
        print(f"  Medications:      {self.daily_totals['medications']}")
        print(f"  Exercise:         {self.daily_totals['exercise_min']}min")
        print(f"  Hydration:        {self.daily_totals['hydration_ml']}ml")
        print(f"  Total calories:   {self.daily_totals['total_calories']} kcal")
        print(f"  Meals counted:    {self.daily_totals['meal_count']}")

        print(f"\n  Data distributed to:")
        if self.daily_totals["foods"]:
            print(f"    user_food_log:    {len(self.daily_totals['foods'])} entries")
        if self.daily_totals["medications"]:
            print(f"    user_medication:  {len(self.daily_totals['medications'])} entries")
        if self.daily_totals["total_calories"] > 0 or exercise_total > 0:
            print(f"    user_lifestyle:   1 daily summary")

        print(f"\n  Raw events in user_activity_event marked as 'processed'")
        print(f"  (In production: auto-delete after 7 days)")


if __name__ == "__main__":
    processor = EventProcessor()
    processor.process_events()
