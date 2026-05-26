"""
Download USDA FoodData Central bulk data into SQLite.
Uses the /v1/foods/list endpoint to paginate through all Foundation + SR Legacy foods.

API: https://api.nal.usda.gov/fdc/v1/
Key: from .env (USDA_API_KEY)
Rate limit: 1,000 requests/hour (default), 3,600/hour (with key)
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

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def flush_print(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

API_KEY = "OsnsTNR9FZamVmv0uipK0FNdJQjIgKWPLuOeb4yT"
BASE_URL = "https://api.nal.usda.gov/fdc/v1"
PAGE_SIZE = 200
DB_PATH = Path(__file__).parent.parent / "data" / "food_db" / "usda_food_nutrition.db"

# Data types to download (Foundation = lab-analyzed, SR Legacy = comprehensive)
DATA_TYPES = ["Foundation", "SR Legacy", "Survey (FNDDS)"]


def create_db():
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS foods")
    c.execute("DROP TABLE IF EXISTS nutrients")
    c.execute("DROP TABLE IF EXISTS metadata")

    c.execute("""
        CREATE TABLE foods (
            fdc_id INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            data_type TEXT,
            food_category TEXT,
            publication_date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE nutrients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fdc_id INTEGER NOT NULL,
            nutrient_id INTEGER,
            nutrient_name TEXT,
            amount REAL,
            unit TEXT,
            FOREIGN KEY (fdc_id) REFERENCES foods(fdc_id)
        )
    """)

    c.execute("CREATE INDEX idx_foods_desc ON foods(description)")
    c.execute("CREATE INDEX idx_foods_category ON foods(food_category)")
    c.execute("CREATE INDEX idx_nutrients_fdc ON nutrients(fdc_id)")
    c.execute("CREATE INDEX idx_nutrients_name ON nutrients(nutrient_name)")

    c.execute("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    return conn


def fetch_foods_list(data_type, page, retries=3):
    """Fetch a page of foods using POST /v1/foods/list."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{BASE_URL}/foods/list?api_key={API_KEY}"
    payload = json.dumps({
        "dataType": [data_type],
        "pageSize": PAGE_SIZE,
        "pageNumber": page,
        "sortBy": "fdcId",
        "sortOrder": "asc"
    }).encode('utf-8')

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, context=ctx, timeout=30)
            data = json.loads(resp.read().decode('utf-8'))
            return data
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                flush_print(f"  Retry {attempt+1} page {page}: {e}")
                time.sleep(wait)
            else:
                flush_print(f"  FAILED page {page}: {e}")
                return []


def fetch_food_details(fdc_ids, retries=3):
    """Fetch full nutrient details for a batch of foods using POST /v1/foods."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{BASE_URL}/foods?api_key={API_KEY}"
    payload = json.dumps({
        "fdcIds": fdc_ids,
        "format": "abridged"
    }).encode('utf-8')

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, context=ctx, timeout=30)
            data = json.loads(resp.read().decode('utf-8'))
            return data
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                flush_print(f"  Retry {attempt+1} details batch: {e}")
                time.sleep(wait)
            else:
                flush_print(f"  FAILED details batch: {e}")
                return []


def insert_foods_with_nutrients(conn, foods_detail):
    c = conn.cursor()
    inserted = 0

    for food in foods_detail:
        fdc_id = food.get("fdcId")
        if not fdc_id:
            continue

        c.execute(
            "INSERT OR REPLACE INTO foods VALUES (?, ?, ?, ?, ?)",
            (
                fdc_id,
                food.get("description", ""),
                food.get("dataType", ""),
                food.get("foodCategory", {}).get("description", "") if isinstance(food.get("foodCategory"), dict) else food.get("foodCategory", ""),
                food.get("publicationDate", ""),
            )
        )

        for nutrient in food.get("foodNutrients", []):
            n_id = nutrient.get("number") or nutrient.get("nutrient", {}).get("id")
            n_name = nutrient.get("nutrientName") or nutrient.get("nutrient", {}).get("name", "")
            n_amount = nutrient.get("amount") or nutrient.get("value")
            n_unit = nutrient.get("unitName") or nutrient.get("nutrient", {}).get("unitName", "")

            if n_amount is not None:
                try:
                    c.execute(
                        "INSERT INTO nutrients (fdc_id, nutrient_id, nutrient_name, amount, unit) VALUES (?, ?, ?, ?, ?)",
                        (fdc_id, n_id, n_name, float(n_amount), n_unit)
                    )
                except (ValueError, TypeError):
                    pass

        inserted += 1

    conn.commit()
    return inserted


def main():
    flush_print("=" * 60)
    flush_print("USDA FoodData Central Downloader")
    flush_print("Foundation + SR Legacy datasets")
    flush_print("=" * 60)

    conn = create_db()
    total_inserted = 0
    start_time = time.time()

    for data_type in DATA_TYPES:
        flush_print(f"\n--- Downloading: {data_type} ---")

        # First, get all food IDs via /foods/list
        page = 1
        all_fdc_ids = []

        while True:
            foods = fetch_foods_list(data_type, page)
            if not foods:
                break

            fdc_ids = [f["fdcId"] for f in foods if "fdcId" in f]
            all_fdc_ids.extend(fdc_ids)

            if page % 5 == 0:
                flush_print(f"  Listed page {page} | {len(all_fdc_ids)} foods found so far")

            if len(foods) < PAGE_SIZE:
                break
            page += 1
            time.sleep(0.5)

        flush_print(f"  Total {data_type} foods found: {len(all_fdc_ids)}")

        # Fetch details in batches of 20 (API limit)
        batch_size = 20
        for i in range(0, len(all_fdc_ids), batch_size):
            batch = all_fdc_ids[i:i + batch_size]
            details = fetch_food_details(batch)

            if details:
                inserted = insert_foods_with_nutrients(conn, details)
                total_inserted += inserted

            if (i // batch_size) % 20 == 0 and i > 0:
                elapsed = time.time() - start_time
                flush_print(
                    f"  {total_inserted:,} foods saved | "
                    f"{elapsed:.0f}s elapsed"
                )

            time.sleep(0.5)

    # Metadata
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("total_foods", str(total_inserted)))
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("download_date", time.strftime("%Y-%m-%d %H:%M:%S")))
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("source", "USDA FoodData Central (fdc.nal.usda.gov)"))
    c.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
              ("data_types", ", ".join(DATA_TYPES)))
    conn.commit()

    # Summary
    c.execute("SELECT COUNT(*) FROM foods")
    food_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM nutrients")
    nutrient_count = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT food_category) FROM foods")
    cat_count = c.fetchone()[0]

    db_size = os.path.getsize(str(DB_PATH)) / (1024 * 1024)
    elapsed = time.time() - start_time
    conn.close()

    flush_print("\n" + "=" * 60)
    flush_print("DOWNLOAD COMPLETE")
    flush_print(f"  Foods: {food_count:,}")
    flush_print(f"  Nutrient records: {nutrient_count:,}")
    flush_print(f"  Categories: {cat_count}")
    flush_print(f"  DB size: {db_size:.1f} MB")
    flush_print(f"  Time: {elapsed/60:.1f} minutes")
    flush_print(f"  File: {DB_PATH}")
    flush_print("=" * 60)


if __name__ == "__main__":
    main()
