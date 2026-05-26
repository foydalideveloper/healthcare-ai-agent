"""
KNHANES Data Downloader & Parser
Downloads and parses 국민건강영양조사 raw data into HRT-compatible format.

NOTE: KNHANES data must be manually downloaded from https://knhanes.kdca.go.kr
This script parses the downloaded CSV/SAS files and loads them into Supabase.

Usage:
  1. Download KNHANES data from https://knhanes.kdca.go.kr/knhanes (원시자료 다운로드)
  2. Place CSV files in: backend/data/knhanes/
  3. Run: python -m scripts.download_knhanes

Expected files in data/knhanes/:
  - HN_ALL_{year}.csv  (health examination)
  - HN_NUT_{year}.csv  (nutrition survey)
"""

import asyncio
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.database import get_db_admin

DATA_DIR = Path(__file__).parent.parent / "data" / "knhanes"

# KNHANES variable name → our schema column mapping
HEALTH_EXAM_MAP = {
    # KNHANES code → (our_column, conversion_func)
    "HE_BMI": ("bmi", float),
    "HE_sbp": ("sbp", int),
    "HE_dbp": ("dbp", int),
    "HE_glu": ("fasting_glucose", int),
    "HE_chol": ("total_chol", int),
    "HE_HDL_st2": ("hdl_chol", int),
    "HE_LDL_drct": ("ldl_chol", int),
    "HE_TG": ("triglyceride", int),
    "HE_HB": ("hemoglobin", float),
    "HE_crea": ("creatinine", float),
    "HE_alt": ("alt", int),
    "HE_ast": ("ast", int),
    "HE_GGT": ("ggt", int),
    "HE_BFP": ("body_fat_pct", float),
    "HE_ht": ("height_cm", float),
    "HE_wt": ("weight_kg", float),
}

LIFESTYLE_MAP = {
    # Nutrition
    "N_KCAL": ("total_calories", int),
    "N_CHO": ("carb_g", int),
    "N_PROT": ("protein_g", int),
    "N_FAT": ("fat_g", int),
    "N_FIBER": ("fiber_g", float),
    "N_NA": ("sodium_mg", int),
    # Exercise (converted from KNHANES exercise frequency/duration)
    "PA_VIG_DUR": ("exercise_min", int),  # vigorous activity duration
}

DEMOGRAPHIC_MAP = {
    "age": ("age", int),
    "sex": ("gender", lambda x: "M" if str(x) == "1" else "F"),
    "incm": ("income_decile", lambda x: min(10, max(1, int(float(x) * 2.5))) if x else None),
}


def parse_csv_file(filepath: Path, encoding: str = "cp949") -> list[dict]:
    """Parse a KNHANES CSV file, handling Korean encodings."""
    rows = []
    try:
        with open(filepath, "r", encoding=encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except UnicodeDecodeError:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


def safe_convert(value, converter):
    """Safely convert a value, returning None for missing/invalid data."""
    if value is None or str(value).strip() in ("", ".", "NA", "nan", "NaN", "-"):
        return None
    try:
        return converter(value)
    except (ValueError, TypeError):
        return None


def parse_health_exam(rows: list[dict], year: int) -> list[dict]:
    """Parse health examination data into user_diagnosis format."""
    records = []
    for row in rows:
        record = {
            "period_type": "monthly",
            "period_start": f"{year}-06-15",  # KNHANES runs annually, use mid-year
            "data_source": f"KNHANES_{year}",
        }

        has_data = False
        for knhanes_col, (our_col, converter) in HEALTH_EXAM_MAP.items():
            val = safe_convert(row.get(knhanes_col), converter)
            if val is not None:
                record[our_col] = val
                has_data = True

        if has_data:
            records.append(record)

    return records


def parse_nutrition(rows: list[dict], year: int) -> list[dict]:
    """Parse nutrition survey data into user_lifestyle format."""
    records = []
    for row in rows:
        record = {
            "recorded_date": f"{year}-06-15",
            "data_source": f"KNHANES_{year}",
        }

        has_data = False
        for knhanes_col, (our_col, converter) in LIFESTYLE_MAP.items():
            val = safe_convert(row.get(knhanes_col), converter)
            if val is not None:
                record[our_col] = val
                has_data = True

        if has_data:
            records.append(record)

    return records


async def main():
    print("=" * 60)
    print("KNHANES Data Loader")
    print("=" * 60)

    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"\nData directory created: {DATA_DIR}")
        print("\nPlease download KNHANES data and place CSV files here:")
        print(f"  {DATA_DIR}")
        print("\nDownload from: https://knhanes.kdca.go.kr/knhanes")
        print("  → 원시자료 다운로드 → Select years 2019-2024 → Download CSV")
        print("\nExpected files:")
        print("  - HN_ALL_2019.csv, HN_ALL_2020.csv, ... (health exam)")
        print("  - HN_NUT_2019.csv, HN_NUT_2020.csv, ... (nutrition)")
        print("\nAfter placing files, run this script again.")
        return

    csv_files = list(DATA_DIR.glob("*.csv"))
    if not csv_files:
        print(f"\nNo CSV files found in {DATA_DIR}")
        print("Please download KNHANES data from: https://knhanes.kdca.go.kr/knhanes")
        return

    print(f"\nFound {len(csv_files)} CSV files in {DATA_DIR}")
    for f in sorted(csv_files):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name} ({size_mb:.1f} MB)")

    db = get_db_admin()

    for csv_file in sorted(csv_files):
        filename = csv_file.stem.upper()
        print(f"\nProcessing: {csv_file.name}...")

        # Detect year from filename
        year = None
        for y in range(2018, 2027):
            if str(y) in filename:
                year = y
                break
        if not year:
            print(f"  Skipping (cannot detect year from filename)")
            continue

        rows = parse_csv_file(csv_file)
        print(f"  Parsed {len(rows)} rows")

        if "ALL" in filename or "HE" in filename:
            # Health examination data
            records = parse_health_exam(rows, year)
            if records:
                print(f"  Converted {len(records)} health exam records")
                # Store as training data (not as real user records)
                # Save to a training data file for LSTM training
                output_path = DATA_DIR / f"parsed_diagnosis_{year}.csv"
                save_parsed_csv(records, output_path)
                print(f"  Saved to {output_path}")

        elif "NUT" in filename:
            # Nutrition data
            records = parse_nutrition(rows, year)
            if records:
                print(f"  Converted {len(records)} nutrition records")
                output_path = DATA_DIR / f"parsed_lifestyle_{year}.csv"
                save_parsed_csv(records, output_path)
                print(f"  Saved to {output_path}")

    print("\n" + "=" * 60)
    print("KNHANES DATA PARSING COMPLETE")
    print("=" * 60)
    print("\nParsed files are saved in:", DATA_DIR)
    print("These will be used for LSTM-Transformer training in Phase 4.")


def save_parsed_csv(records: list[dict], output_path: Path):
    """Save parsed records to CSV for training."""
    if not records:
        return
    fieldnames = sorted(set().union(*[r.keys() for r in records]))
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":
    asyncio.run(main())
