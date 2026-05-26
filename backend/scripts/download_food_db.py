"""
Korean Food Nutrition Database Loader
Downloads food nutrition data from MFDS (식품의약품안전처) and USDA APIs,
then stores in a local SQLite cache for fast food recognition lookups.

Usage: python -m scripts.download_food_db

Sources:
  - MFDS 식품영양성분DB: https://various.foodsafetykorea.go.kr/nutrient/
  - 공공데이터포털 API: https://www.data.go.kr/data/15127578/openapi.do
  - USDA FoodData Central: https://api.nal.usda.gov/fdc/v1/
"""

import asyncio
import json
import os
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import httpx

DATA_DIR = Path(__file__).parent.parent / "data" / "food_db"
SQLITE_PATH = DATA_DIR / "food_nutrition.db"

# MFDS API (공공데이터포털)
MFDS_API_BASE = "https://apis.data.go.kr/1471000/FoodNtrIrdntInfoService1"
# USDA API
USDA_API_BASE = "https://api.nal.usda.gov/fdc/v1"


def init_sqlite_db():
    """Initialize the local food nutrition SQLite database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS korean_foods (
            food_id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_code TEXT UNIQUE,
            food_name_kr TEXT NOT NULL,
            food_name_en TEXT,
            food_category TEXT,
            serving_size_g REAL,
            calories_kcal REAL,
            carbohydrate_g REAL,
            protein_g REAL,
            fat_g REAL,
            fiber_g REAL,
            sodium_mg REAL,
            sugar_g REAL,
            saturated_fat_g REAL,
            cholesterol_mg REAL,
            calcium_mg REAL,
            iron_mg REAL,
            potassium_mg REAL,
            vitamin_a_ug REAL,
            vitamin_c_mg REAL,
            vitamin_d_ug REAL,
            source TEXT DEFAULT 'MFDS',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS international_foods (
            fdc_id INTEGER PRIMARY KEY,
            food_name TEXT NOT NULL,
            food_category TEXT,
            serving_size_g REAL,
            calories_kcal REAL,
            carbohydrate_g REAL,
            protein_g REAL,
            fat_g REAL,
            fiber_g REAL,
            sodium_mg REAL,
            sugar_g REAL,
            source TEXT DEFAULT 'USDA',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Full-text search index for food name matching
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS food_search
        USING fts5(food_name, food_category, source, content='')
    """)

    conn.commit()
    return conn


async def download_mfds_data(api_key: str | None = None):
    """Download Korean food nutrition data from MFDS API."""
    if not api_key:
        print("\n  MFDS API key not set.")
        print("  To get a free API key:")
        print("  1. Go to https://www.data.go.kr/data/15127578/openapi.do")
        print("  2. Register and request API key (instant approval)")
        print("  3. Add MFDS_API_KEY=your-key to backend/.env")
        print("\n  Alternatively, download manually:")
        print("  1. Go to https://various.foodsafetykorea.go.kr/nutrient/general/down/list.do")
        print("  2. Download the full Excel/CSV file")
        print("  3. Place it in: backend/data/food_db/mfds_food_data.csv")
        return []

    foods = []
    page = 1
    page_size = 100

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params = {
                "serviceKey": api_key,
                "pageNo": str(page),
                "numOfRows": str(page_size),
                "type": "json",
            }

            try:
                resp = await client.get(
                    f"{MFDS_API_BASE}/getFoodNtrItdntList1",
                    params=params,
                )
                data = resp.json()

                items = data.get("body", {}).get("items", [])
                if not items:
                    break

                for item in items:
                    food = {
                        "food_code": item.get("FOOD_CD", ""),
                        "food_name_kr": item.get("DESC_KOR", ""),
                        "food_category": item.get("GROUP_NAME", ""),
                        "serving_size_g": safe_float(item.get("SERVING_SIZE")),
                        "calories_kcal": safe_float(item.get("NUTR_CONT1")),
                        "carbohydrate_g": safe_float(item.get("NUTR_CONT2")),
                        "protein_g": safe_float(item.get("NUTR_CONT3")),
                        "fat_g": safe_float(item.get("NUTR_CONT4")),
                        "sugar_g": safe_float(item.get("NUTR_CONT5")),
                        "sodium_mg": safe_float(item.get("NUTR_CONT6")),
                        "cholesterol_mg": safe_float(item.get("NUTR_CONT7")),
                        "saturated_fat_g": safe_float(item.get("NUTR_CONT8")),
                        "fiber_g": safe_float(item.get("NUTR_CONT9")),
                        "calcium_mg": safe_float(item.get("NUTR_CONT10")),
                        "iron_mg": safe_float(item.get("NUTR_CONT11")),
                        "source": "MFDS",
                    }
                    foods.append(food)

                print(f"  Page {page}: fetched {len(items)} items (total: {len(foods)})")

                if len(items) < page_size:
                    break
                page += 1

            except Exception as e:
                print(f"  Error on page {page}: {e}")
                break

    return foods


async def download_usda_common_foods(api_key: str | None = None):
    """Download common international foods from USDA FoodData Central."""
    if not api_key:
        print("\n  USDA API key not set.")
        print("  To get a free API key:")
        print("  1. Go to https://fdc.nal.usda.gov/api-guide")
        print("  2. Sign up for a free API key")
        print("  3. Add USDA_API_KEY=your-key to backend/.env")
        return []

    # Common food categories to download
    search_terms = [
        "rice", "chicken", "beef", "pork", "fish", "egg",
        "milk", "bread", "pasta", "apple", "banana",
        "broccoli", "spinach", "tomato", "potato",
        "cheese", "yogurt", "salmon", "tofu", "bean",
    ]

    foods = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for term in search_terms:
            try:
                resp = await client.get(
                    f"{USDA_API_BASE}/foods/search",
                    params={
                        "api_key": api_key,
                        "query": term,
                        "pageSize": 10,
                        "dataType": "Foundation,SR Legacy",
                    },
                )
                data = resp.json()

                for item in data.get("foods", []):
                    nutrients = {n["nutrientName"]: n.get("value", 0) for n in item.get("foodNutrients", [])}
                    food = {
                        "fdc_id": item.get("fdcId"),
                        "food_name": item.get("description", ""),
                        "food_category": item.get("foodCategory", ""),
                        "serving_size_g": 100,  # USDA reports per 100g
                        "calories_kcal": nutrients.get("Energy", 0),
                        "carbohydrate_g": nutrients.get("Carbohydrate, by difference", 0),
                        "protein_g": nutrients.get("Protein", 0),
                        "fat_g": nutrients.get("Total lipid (fat)", 0),
                        "fiber_g": nutrients.get("Fiber, total dietary", 0),
                        "sodium_mg": nutrients.get("Sodium, Na", 0),
                        "sugar_g": nutrients.get("Sugars, total including NLEA", 0),
                        "source": "USDA",
                    }
                    foods.append(food)

                print(f"  '{term}': fetched {len(data.get('foods', []))} items")

            except Exception as e:
                print(f"  Error searching '{term}': {e}")

    return foods


def safe_float(val) -> float | None:
    if val is None or str(val).strip() in ("", "-", "N/A", "nan"):
        return None
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return None


def insert_korean_foods(conn: sqlite3.Connection, foods: list[dict]):
    cursor = conn.cursor()
    inserted = 0
    for food in foods:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO korean_foods
                (food_code, food_name_kr, food_category, serving_size_g,
                 calories_kcal, carbohydrate_g, protein_g, fat_g, fiber_g,
                 sodium_mg, sugar_g, saturated_fat_g, cholesterol_mg,
                 calcium_mg, iron_mg, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                food["food_code"], food["food_name_kr"], food.get("food_category"),
                food.get("serving_size_g"), food.get("calories_kcal"),
                food.get("carbohydrate_g"), food.get("protein_g"),
                food.get("fat_g"), food.get("fiber_g"),
                food.get("sodium_mg"), food.get("sugar_g"),
                food.get("saturated_fat_g"), food.get("cholesterol_mg"),
                food.get("calcium_mg"), food.get("iron_mg"), food.get("source", "MFDS"),
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    return inserted


def insert_international_foods(conn: sqlite3.Connection, foods: list[dict]):
    cursor = conn.cursor()
    inserted = 0
    for food in foods:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO international_foods
                (fdc_id, food_name, food_category, serving_size_g,
                 calories_kcal, carbohydrate_g, protein_g, fat_g,
                 fiber_g, sodium_mg, sugar_g, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                food["fdc_id"], food["food_name"], food.get("food_category"),
                food.get("serving_size_g"), food.get("calories_kcal"),
                food.get("carbohydrate_g"), food.get("protein_g"),
                food.get("fat_g"), food.get("fiber_g"),
                food.get("sodium_mg"), food.get("sugar_g"), food.get("source", "USDA"),
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    return inserted


# ── Built-in Korean common foods (no API needed) ──
KOREAN_COMMON_FOODS = [
    {"food_code": "KR0001", "food_name_kr": "흰쌀밥", "food_category": "밥류", "serving_size_g": 210, "calories_kcal": 313, "carbohydrate_g": 69, "protein_g": 5, "fat_g": 0.5, "fiber_g": 0.6, "sodium_mg": 5},
    {"food_code": "KR0002", "food_name_kr": "잡곡밥", "food_category": "밥류", "serving_size_g": 210, "calories_kcal": 310, "carbohydrate_g": 65, "protein_g": 7, "fat_g": 1.5, "fiber_g": 3.5, "sodium_mg": 5},
    {"food_code": "KR0003", "food_name_kr": "김치찌개", "food_category": "찌개류", "serving_size_g": 300, "calories_kcal": 120, "carbohydrate_g": 8, "protein_g": 10, "fat_g": 5, "fiber_g": 2, "sodium_mg": 1800},
    {"food_code": "KR0004", "food_name_kr": "된장찌개", "food_category": "찌개류", "serving_size_g": 300, "calories_kcal": 100, "carbohydrate_g": 10, "protein_g": 8, "fat_g": 3, "fiber_g": 2.5, "sodium_mg": 1600},
    {"food_code": "KR0005", "food_name_kr": "비빔밥", "food_category": "밥류", "serving_size_g": 450, "calories_kcal": 550, "carbohydrate_g": 85, "protein_g": 20, "fat_g": 15, "fiber_g": 5, "sodium_mg": 1200},
    {"food_code": "KR0006", "food_name_kr": "불고기", "food_category": "육류", "serving_size_g": 200, "calories_kcal": 340, "carbohydrate_g": 15, "protein_g": 28, "fat_g": 18, "fiber_g": 1, "sodium_mg": 900},
    {"food_code": "KR0007", "food_name_kr": "삼겹살 (구이)", "food_category": "육류", "serving_size_g": 200, "calories_kcal": 510, "carbohydrate_g": 0, "protein_g": 22, "fat_g": 46, "fiber_g": 0, "sodium_mg": 70},
    {"food_code": "KR0008", "food_name_kr": "배추김치", "food_category": "김치류", "serving_size_g": 50, "calories_kcal": 10, "carbohydrate_g": 2, "protein_g": 1, "fat_g": 0.3, "fiber_g": 1.5, "sodium_mg": 350},
    {"food_code": "KR0009", "food_name_kr": "깍두기", "food_category": "김치류", "serving_size_g": 50, "calories_kcal": 15, "carbohydrate_g": 3, "protein_g": 0.5, "fat_g": 0.2, "fiber_g": 1, "sodium_mg": 300},
    {"food_code": "KR0010", "food_name_kr": "된장국", "food_category": "국류", "serving_size_g": 250, "calories_kcal": 45, "carbohydrate_g": 5, "protein_g": 3, "fat_g": 1.5, "fiber_g": 1, "sodium_mg": 1200},
    {"food_code": "KR0011", "food_name_kr": "미역국", "food_category": "국류", "serving_size_g": 250, "calories_kcal": 55, "carbohydrate_g": 3, "protein_g": 5, "fat_g": 2.5, "fiber_g": 1.5, "sodium_mg": 1100},
    {"food_code": "KR0012", "food_name_kr": "삼계탕", "food_category": "탕류", "serving_size_g": 600, "calories_kcal": 550, "carbohydrate_g": 35, "protein_g": 40, "fat_g": 25, "fiber_g": 2, "sodium_mg": 1500},
    {"food_code": "KR0013", "food_name_kr": "떡볶이", "food_category": "분식류", "serving_size_g": 300, "calories_kcal": 430, "carbohydrate_g": 75, "protein_g": 8, "fat_g": 10, "fiber_g": 2, "sodium_mg": 1400},
    {"food_code": "KR0014", "food_name_kr": "라면 (봉지)", "food_category": "면류", "serving_size_g": 550, "calories_kcal": 500, "carbohydrate_g": 65, "protein_g": 10, "fat_g": 20, "fiber_g": 2, "sodium_mg": 1800},
    {"food_code": "KR0015", "food_name_kr": "김밥", "food_category": "밥류", "serving_size_g": 250, "calories_kcal": 380, "carbohydrate_g": 55, "protein_g": 12, "fat_g": 12, "fiber_g": 2.5, "sodium_mg": 900},
    {"food_code": "KR0016", "food_name_kr": "제육볶음", "food_category": "육류", "serving_size_g": 200, "calories_kcal": 320, "carbohydrate_g": 12, "protein_g": 25, "fat_g": 20, "fiber_g": 1.5, "sodium_mg": 1000},
    {"food_code": "KR0017", "food_name_kr": "갈비탕", "food_category": "탕류", "serving_size_g": 500, "calories_kcal": 450, "carbohydrate_g": 5, "protein_g": 30, "fat_g": 35, "fiber_g": 0.5, "sodium_mg": 1300},
    {"food_code": "KR0018", "food_name_kr": "순두부찌개", "food_category": "찌개류", "serving_size_g": 350, "calories_kcal": 150, "carbohydrate_g": 8, "protein_g": 12, "fat_g": 8, "fiber_g": 1.5, "sodium_mg": 1500},
    {"food_code": "KR0019", "food_name_kr": "잡채", "food_category": "반찬류", "serving_size_g": 150, "calories_kcal": 210, "carbohydrate_g": 30, "protein_g": 5, "fat_g": 8, "fiber_g": 2, "sodium_mg": 600},
    {"food_code": "KR0020", "food_name_kr": "계란후라이", "food_category": "반찬류", "serving_size_g": 60, "calories_kcal": 95, "carbohydrate_g": 1, "protein_g": 7, "fat_g": 7, "fiber_g": 0, "sodium_mg": 200},
    {"food_code": "KR0021", "food_name_kr": "두부 (반모)", "food_category": "콩류", "serving_size_g": 150, "calories_kcal": 120, "carbohydrate_g": 3, "protein_g": 12, "fat_g": 7, "fiber_g": 1, "sodium_mg": 10},
    {"food_code": "KR0022", "food_name_kr": "고등어구이", "food_category": "생선류", "serving_size_g": 150, "calories_kcal": 280, "carbohydrate_g": 0, "protein_g": 25, "fat_g": 20, "fiber_g": 0, "sodium_mg": 300},
    {"food_code": "KR0023", "food_name_kr": "삼각김밥", "food_category": "밥류", "serving_size_g": 110, "calories_kcal": 180, "carbohydrate_g": 32, "protein_g": 4, "fat_g": 3.5, "fiber_g": 1, "sodium_mg": 450},
    {"food_code": "KR0024", "food_name_kr": "짜장면", "food_category": "면류", "serving_size_g": 550, "calories_kcal": 620, "carbohydrate_g": 85, "protein_g": 15, "fat_g": 22, "fiber_g": 3, "sodium_mg": 1600},
    {"food_code": "KR0025", "food_name_kr": "짬뽕", "food_category": "면류", "serving_size_g": 600, "calories_kcal": 480, "carbohydrate_g": 60, "protein_g": 20, "fat_g": 15, "fiber_g": 4, "sodium_mg": 2200},
    {"food_code": "KR0026", "food_name_kr": "치킨 (후라이드)", "food_category": "육류", "serving_size_g": 200, "calories_kcal": 480, "carbohydrate_g": 15, "protein_g": 30, "fat_g": 35, "fiber_g": 0.5, "sodium_mg": 800},
    {"food_code": "KR0027", "food_name_kr": "피자 (1조각)", "food_category": "빵류", "serving_size_g": 120, "calories_kcal": 300, "carbohydrate_g": 30, "protein_g": 14, "fat_g": 14, "fiber_g": 1.5, "sodium_mg": 700},
    {"food_code": "KR0028", "food_name_kr": "아메리카노", "food_category": "음료류", "serving_size_g": 350, "calories_kcal": 5, "carbohydrate_g": 0, "protein_g": 0, "fat_g": 0, "fiber_g": 0, "sodium_mg": 5},
    {"food_code": "KR0029", "food_name_kr": "소주 (1잔)", "food_category": "주류", "serving_size_g": 50, "calories_kcal": 65, "carbohydrate_g": 0, "protein_g": 0, "fat_g": 0, "fiber_g": 0, "sodium_mg": 0},
    {"food_code": "KR0030", "food_name_kr": "맥주 (1캔)", "food_category": "주류", "serving_size_g": 355, "calories_kcal": 150, "carbohydrate_g": 13, "protein_g": 1, "fat_g": 0, "fiber_g": 0, "sodium_mg": 10},
    {"food_code": "KR0031", "food_name_kr": "시금치나물", "food_category": "반찬류", "serving_size_g": 70, "calories_kcal": 25, "carbohydrate_g": 2, "protein_g": 2, "fat_g": 1, "fiber_g": 2, "sodium_mg": 250},
    {"food_code": "KR0032", "food_name_kr": "콩나물국", "food_category": "국류", "serving_size_g": 250, "calories_kcal": 35, "carbohydrate_g": 3, "protein_g": 3, "fat_g": 1, "fiber_g": 1.5, "sodium_mg": 900},
    {"food_code": "KR0033", "food_name_kr": "닭가슴살 (삶은)", "food_category": "육류", "serving_size_g": 100, "calories_kcal": 165, "carbohydrate_g": 0, "protein_g": 31, "fat_g": 3.6, "fiber_g": 0, "sodium_mg": 74},
    {"food_code": "KR0034", "food_name_kr": "고구마 (찐)", "food_category": "서류", "serving_size_g": 150, "calories_kcal": 130, "carbohydrate_g": 30, "protein_g": 2, "fat_g": 0.1, "fiber_g": 3, "sodium_mg": 35},
    {"food_code": "KR0035", "food_name_kr": "바나나", "food_category": "과일류", "serving_size_g": 120, "calories_kcal": 105, "carbohydrate_g": 27, "protein_g": 1.3, "fat_g": 0.4, "fiber_g": 3, "sodium_mg": 1},
    {"food_code": "KR0036", "food_name_kr": "사과", "food_category": "과일류", "serving_size_g": 200, "calories_kcal": 100, "carbohydrate_g": 25, "protein_g": 0.5, "fat_g": 0.3, "fiber_g": 4.5, "sodium_mg": 2},
    {"food_code": "KR0037", "food_name_kr": "우유 (흰우유)", "food_category": "유제품", "serving_size_g": 200, "calories_kcal": 130, "carbohydrate_g": 10, "protein_g": 7, "fat_g": 7, "fiber_g": 0, "sodium_mg": 100},
    {"food_code": "KR0038", "food_name_kr": "요거트 (플레인)", "food_category": "유제품", "serving_size_g": 150, "calories_kcal": 90, "carbohydrate_g": 12, "protein_g": 6, "fat_g": 2, "fiber_g": 0, "sodium_mg": 70},
    {"food_code": "KR0039", "food_name_kr": "식빵 (1장)", "food_category": "빵류", "serving_size_g": 35, "calories_kcal": 95, "carbohydrate_g": 17, "protein_g": 3, "fat_g": 1.5, "fiber_g": 0.8, "sodium_mg": 150},
    {"food_code": "KR0040", "food_name_kr": "칼국수", "food_category": "면류", "serving_size_g": 500, "calories_kcal": 420, "carbohydrate_g": 65, "protein_g": 15, "fat_g": 8, "fiber_g": 3, "sodium_mg": 1800},
    {"food_code": "KR0041", "food_name_kr": "냉면", "food_category": "면류", "serving_size_g": 500, "calories_kcal": 460, "carbohydrate_g": 80, "protein_g": 12, "fat_g": 8, "fiber_g": 2, "sodium_mg": 2000},
    {"food_code": "KR0042", "food_name_kr": "김치볶음밥", "food_category": "밥류", "serving_size_g": 350, "calories_kcal": 480, "carbohydrate_g": 70, "protein_g": 12, "fat_g": 15, "fiber_g": 3, "sodium_mg": 1300},
    {"food_code": "KR0043", "food_name_kr": "부대찌개", "food_category": "찌개류", "serving_size_g": 400, "calories_kcal": 350, "carbohydrate_g": 25, "protein_g": 18, "fat_g": 20, "fiber_g": 3, "sodium_mg": 2500},
    {"food_code": "KR0044", "food_name_kr": "돈까스", "food_category": "육류", "serving_size_g": 250, "calories_kcal": 550, "carbohydrate_g": 35, "protein_g": 25, "fat_g": 32, "fiber_g": 1.5, "sodium_mg": 800},
    {"food_code": "KR0045", "food_name_kr": "떡국", "food_category": "국류", "serving_size_g": 450, "calories_kcal": 380, "carbohydrate_g": 55, "protein_g": 15, "fat_g": 10, "fiber_g": 1, "sodium_mg": 1400},
    {"food_code": "KR0046", "food_name_kr": "감자탕", "food_category": "탕류", "serving_size_g": 500, "calories_kcal": 400, "carbohydrate_g": 20, "protein_g": 30, "fat_g": 22, "fiber_g": 3, "sodium_mg": 1800},
    {"food_code": "KR0047", "food_name_kr": "오이소박이", "food_category": "김치류", "serving_size_g": 50, "calories_kcal": 8, "carbohydrate_g": 1.5, "protein_g": 0.5, "fat_g": 0.1, "fiber_g": 0.8, "sodium_mg": 280},
    {"food_code": "KR0048", "food_name_kr": "멸치볶음", "food_category": "반찬류", "serving_size_g": 30, "calories_kcal": 80, "carbohydrate_g": 8, "protein_g": 5, "fat_g": 3, "fiber_g": 0.5, "sodium_mg": 400},
    {"food_code": "KR0049", "food_name_kr": "김치전", "food_category": "전류", "serving_size_g": 150, "calories_kcal": 220, "carbohydrate_g": 25, "protein_g": 5, "fat_g": 10, "fiber_g": 2, "sodium_mg": 600},
    {"food_code": "KR0050", "food_name_kr": "해물파전", "food_category": "전류", "serving_size_g": 200, "calories_kcal": 280, "carbohydrate_g": 30, "protein_g": 12, "fat_g": 12, "fiber_g": 2, "sodium_mg": 700},
]


async def main():
    print("=" * 60)
    print("Food Nutrition Database Loader")
    print("=" * 60)

    conn = init_sqlite_db()

    # 1. Insert built-in Korean common foods (always available)
    print("\n[1/3] Inserting built-in Korean common foods (50 items)...")
    inserted = insert_korean_foods(conn, KOREAN_COMMON_FOODS)
    print(f"  Inserted {inserted} Korean food items")

    # 2. Try MFDS API
    print("\n[2/3] Checking MFDS API...")
    mfds_key = os.getenv("MFDS_API_KEY")
    if mfds_key:
        mfds_foods = await download_mfds_data(mfds_key)
        if mfds_foods:
            inserted = insert_korean_foods(conn, mfds_foods)
            print(f"  Inserted {inserted} foods from MFDS API")
    else:
        await download_mfds_data(None)  # Prints instructions

    # 3. Try USDA API
    print("\n[3/3] Checking USDA API...")
    usda_key = os.getenv("USDA_API_KEY")
    if usda_key:
        usda_foods = await download_usda_common_foods(usda_key)
        if usda_foods:
            inserted = insert_international_foods(conn, usda_foods)
            print(f"  Inserted {inserted} foods from USDA API")
    else:
        await download_usda_common_foods(None)  # Prints instructions

    # Summary
    cursor = conn.cursor()
    kr_count = cursor.execute("SELECT COUNT(*) FROM korean_foods").fetchone()[0]
    intl_count = cursor.execute("SELECT COUNT(*) FROM international_foods").fetchone()[0]

    print("\n" + "=" * 60)
    print("FOOD DATABASE SUMMARY")
    print("=" * 60)
    print(f"  Korean foods:        {kr_count}")
    print(f"  International foods: {intl_count}")
    print(f"  Database location:   {SQLITE_PATH}")
    print(f"\n  To expand, add API keys to .env:")
    print(f"    MFDS_API_KEY=your-key   (from data.go.kr)")
    print(f"    USDA_API_KEY=your-key   (from fdc.nal.usda.gov)")

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
