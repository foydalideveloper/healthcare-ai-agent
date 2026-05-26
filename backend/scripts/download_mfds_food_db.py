"""
Download MFDS Food Nutrition DB (식품의약품안전처 식품영양성분DB)
Total: ~275,000 food items with 80+ nutrient fields

API: https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02
Key issued: 2026-04-14, valid until 2028-04-14
Daily limit: 10,000 calls (1,000 rows per call = 10M rows/day capacity)
"""

import urllib.request
import ssl
import json
import sqlite3
import os
import sys
import io
import time
from pathlib import Path

# Force UTF-8 stdout on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = "565db252454b1d2a38a93cdbfc6c563f73be7df4acca6f7b5b058f1b03b99221"
BASE_URL = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
ROWS_PER_PAGE = 500
DB_PATH = Path(__file__).parent.parent / "data" / "food_db" / "food_nutrition.db"

# Nutrient field mapping: AMT_NUM -> human-readable name + unit
NUTRIENT_MAP = {
    "AMT_NUM1": ("energy_kcal", "kcal"),
    "AMT_NUM2": ("water_g", "g"),
    "AMT_NUM3": ("protein_g", "g"),
    "AMT_NUM4": ("fat_g", "g"),
    "AMT_NUM5": ("ash_g", "g"),
    "AMT_NUM6": ("carbohydrate_g", "g"),
    "AMT_NUM7": ("dietary_fiber_g", "g"),
    "AMT_NUM8": ("total_sugar_g", "g"),
    "AMT_NUM9": ("calcium_mg", "mg"),
    "AMT_NUM10": ("iron_mg", "mg"),
    "AMT_NUM11": ("phosphorus_mg", "mg"),
    "AMT_NUM12": ("potassium_mg", "mg"),
    "AMT_NUM13": ("sodium_mg", "mg"),
    "AMT_NUM14": ("vitamin_a_ug_rae", "ug"),
    "AMT_NUM15": ("retinol_ug", "ug"),
    "AMT_NUM16": ("beta_carotene_ug", "ug"),
    "AMT_NUM17": ("thiamine_mg", "mg"),       # B1
    "AMT_NUM18": ("riboflavin_mg", "mg"),     # B2
    "AMT_NUM19": ("niacin_mg", "mg"),
    "AMT_NUM20": ("vitamin_c_mg", "mg"),
    "AMT_NUM21": ("vitamin_d_ug", "ug"),
    "AMT_NUM22": ("cholesterol_mg", "mg"),
    "AMT_NUM23": ("total_saturated_fat_g", "g"),
    "AMT_NUM24": ("trans_fat_g", "g"),
    "AMT_NUM25": ("linoleic_acid_g", "g"),      # omega-6
    "AMT_NUM26": ("alpha_linolenic_acid_g", "g"),  # omega-3
    "AMT_NUM27": ("other_fatty_acids_g", "g"),
    "AMT_NUM28": ("epa_g", "g"),
    "AMT_NUM29": ("dha_g", "g"),
    "AMT_NUM30": ("magnesium_mg", "mg"),
    "AMT_NUM31": ("zinc_mg", "mg"),
    "AMT_NUM32": ("copper_mg", "mg"),
    "AMT_NUM33": ("manganese_mg", "mg"),
    "AMT_NUM34": ("selenium_ug", "ug"),
    "AMT_NUM35": ("iodine_ug", "ug"),
    "AMT_NUM36": ("folate_ug_dfe", "ug"),
    "AMT_NUM37": ("vitamin_b6_mg", "mg"),
    "AMT_NUM38": ("vitamin_b12_ug", "ug"),
    "AMT_NUM39": ("vitamin_e_mg", "mg"),
    "AMT_NUM40": ("vitamin_k_ug", "ug"),
    "AMT_NUM41": ("pantothenic_acid_mg", "mg"),
    "AMT_NUM42": ("biotin_ug", "ug"),
}


def create_db():
    """Create SQLite database with proper schema."""
    os.makedirs(DB_PATH.parent, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS foods")
    c.execute("DROP TABLE IF EXISTS food_nutrients")
    c.execute("DROP TABLE IF EXISTS metadata")

    # Main foods table
    c.execute("""
        CREATE TABLE foods (
            food_cd TEXT PRIMARY KEY,
            food_name_kr TEXT NOT NULL,
            db_group TEXT,
            db_class TEXT,
            food_origin TEXT,
            category1 TEXT,
            category2 TEXT,
            category3 TEXT,
            category4 TEXT,
            serving_size TEXT,
            energy_kcal REAL,
            water_g REAL,
            protein_g REAL,
            fat_g REAL,
            ash_g REAL,
            carbohydrate_g REAL,
            dietary_fiber_g REAL,
            total_sugar_g REAL,
            calcium_mg REAL,
            iron_mg REAL,
            phosphorus_mg REAL,
            potassium_mg REAL,
            sodium_mg REAL,
            vitamin_a_ug_rae REAL,
            retinol_ug REAL,
            beta_carotene_ug REAL,
            thiamine_mg REAL,
            riboflavin_mg REAL,
            niacin_mg REAL,
            vitamin_c_mg REAL,
            vitamin_d_ug REAL,
            cholesterol_mg REAL,
            total_saturated_fat_g REAL,
            trans_fat_g REAL,
            linoleic_acid_g REAL,
            alpha_linolenic_acid_g REAL,
            magnesium_mg REAL,
            zinc_mg REAL,
            copper_mg REAL,
            manganese_mg REAL,
            selenium_ug REAL,
            folate_ug_dfe REAL,
            vitamin_b6_mg REAL,
            vitamin_b12_ug REAL,
            vitamin_e_mg REAL,
            vitamin_k_ug REAL,
            pantothenic_acid_mg REAL,
            epa_g REAL,
            dha_g REAL
        )
    """)

    # Indexes for common lookups
    c.execute("CREATE INDEX idx_food_name ON foods(food_name_kr)")
    c.execute("CREATE INDEX idx_category1 ON foods(category1)")
    c.execute("CREATE INDEX idx_category2 ON foods(category2)")

    # Metadata table
    c.execute("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    return conn


def parse_float(val):
    """Safely parse a numeric string to float."""
    if val is None or val == "" or val == "-" or val == "N/A":
        return None
    try:
        return float(str(val).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def fetch_page(page_no, retries=3):
    """Fetch a single page from the API."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = (
        f"{BASE_URL}?serviceKey={API_KEY}"
        f"&pageNo={page_no}&numOfRows={ROWS_PER_PAGE}&type=json"
    )

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, context=ctx, timeout=30)
            raw = resp.read()
            data = json.loads(raw.decode('utf-8'))

            header = data.get("header", {})
            if header.get("resultCode") not in ("00", None):
                msg = header.get("resultMsg", "Unknown error")
                print(f"  API error on page {page_no}: {msg}")
                return None, 0

            body = data.get("body", {})
            items = body.get("items", [])
            total = body.get("totalCount", 0)
            return items, total

        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt+1} for page {page_no} after {wait}s: {e}")
                time.sleep(wait)
            else:
                print(f"  FAILED page {page_no} after {retries} attempts: {e}")
                return None, 0


def insert_items(conn, items):
    """Insert food items into SQLite."""
    c = conn.cursor()
    inserted = 0

    for item in items:
        food_cd = item.get("FOOD_CD", "")
        if not food_cd:
            continue

        values = {
            "food_cd": food_cd,
            "food_name_kr": item.get("FOOD_NM_KR", ""),
            "db_group": item.get("DB_GRP_NM", ""),
            "db_class": item.get("DB_CLASS_NM", ""),
            "food_origin": item.get("FOOD_OR_NM", ""),
            "category1": item.get("FOOD_CAT1_NM", ""),
            "category2": item.get("FOOD_CAT2_NM", ""),
            "category3": item.get("FOOD_CAT3_NM", ""),
            "category4": item.get("FOOD_CAT4_NM", ""),
            "serving_size": item.get("SERVING_SIZE", "100g"),
        }

        # Map nutrient fields
        for amt_key, (col_name, _) in NUTRIENT_MAP.items():
            if col_name in [
                "energy_kcal", "water_g", "protein_g", "fat_g", "ash_g",
                "carbohydrate_g", "dietary_fiber_g", "total_sugar_g",
                "calcium_mg", "iron_mg", "phosphorus_mg", "potassium_mg",
                "sodium_mg", "vitamin_a_ug_rae", "retinol_ug", "beta_carotene_ug",
                "thiamine_mg", "riboflavin_mg", "niacin_mg", "vitamin_c_mg",
                "vitamin_d_ug", "cholesterol_mg", "total_saturated_fat_g",
                "trans_fat_g", "linoleic_acid_g", "alpha_linolenic_acid_g",
                "magnesium_mg", "zinc_mg", "copper_mg", "manganese_mg",
                "selenium_ug", "folate_ug_dfe", "vitamin_b6_mg", "vitamin_b12_ug",
                "vitamin_e_mg", "vitamin_k_ug", "pantothenic_acid_mg",
                "epa_g", "dha_g",
            ]:
                values[col_name] = parse_float(item.get(amt_key))

        cols = list(values.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_str = ", ".join(cols)

        try:
            c.execute(
                f"INSERT OR REPLACE INTO foods ({col_str}) VALUES ({placeholders})",
                [values[col] for col in cols],
            )
            inserted += 1
        except Exception as e:
            print(f"  Insert error for {food_cd}: {e}")

    conn.commit()
    return inserted


def main():
    print("=" * 60)
    print("MFDS Food Nutrition DB Downloader")
    print("식품의약품안전처 식품영양성분DB 다운로드")
    print("=" * 60)

    # Step 1: Get total count
    print("\nFetching total count...")
    items, total_count = fetch_page(1)
    if items is None:
        print("ERROR: Could not connect to API. Check your key.")
        return

    total_pages = (total_count + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE
    print(f"Total foods: {total_count:,}")
    print(f"Total pages: {total_pages} (at {ROWS_PER_PAGE}/page)")
    print(f"Estimated time: ~{total_pages * 1.5 / 60:.0f} minutes")
    print(f"Output: {DB_PATH}")

    # Step 2: Create database
    print("\nCreating database...")
    conn = create_db()

    # Step 3: Download all pages
    total_inserted = 0
    start_time = time.time()

    for page in range(1, total_pages + 1):
        items, _ = fetch_page(page)
        if items is None:
            print(f"  Skipping page {page} due to error")
            continue

        inserted = insert_items(conn, items)
        total_inserted += inserted

        elapsed = time.time() - start_time
        rate = total_inserted / elapsed if elapsed > 0 else 0
        eta = (total_count - total_inserted) / rate if rate > 0 else 0

        if page % 10 == 0 or page == total_pages:
            print(
                f"  Page {page}/{total_pages} | "
                f"{total_inserted:,}/{total_count:,} foods | "
                f"{rate:.0f}/sec | "
                f"ETA: {eta/60:.1f}min"
            )

        # Small delay to respect rate limits
        time.sleep(0.3)

    # Step 4: Save metadata
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("total_foods", str(total_inserted)))
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("download_date", time.strftime("%Y-%m-%d %H:%M:%S")))
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("source", "MFDS 식품의약품안전처 식품영양성분DB (data.go.kr/15127578)"))
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("api_endpoint", BASE_URL))
    conn.commit()

    # Step 5: Summary
    c.execute("SELECT COUNT(*) FROM foods")
    final_count = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT category1) FROM foods")
    cat_count = c.fetchone()[0]

    elapsed_total = time.time() - start_time
    db_size = os.path.getsize(str(DB_PATH)) / (1024 * 1024)

    conn.close()

    print("\n" + "=" * 60)
    print("DOWNLOAD COMPLETE")
    print(f"  Foods in DB: {final_count:,}")
    print(f"  Categories: {cat_count}")
    print(f"  DB size: {db_size:.1f} MB")
    print(f"  Time: {elapsed_total/60:.1f} minutes")
    print(f"  File: {DB_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
