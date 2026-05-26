"""
KNHANES SPSS (.sav) Parser
Parses downloaded KNHANES data into training-ready CSV files for LSTM-Transformer.

Usage: python -m scripts.parse_knhanes
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyreadstat
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data" / "knhanes"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "training"


# ── Column mappings: KNHANES variable name → our schema ──

DIAGNOSIS_COLUMNS = {
    "HE_ht": "height_cm",
    "HE_wt": "weight_kg",
    "HE_BMI": "bmi",
    "HE_sbp": "sbp",
    "HE_dbp": "dbp",
    "HE_glu": "fasting_glucose",
    "HE_HbA1c": "hba1c",
    "HE_chol": "total_chol",
    "HE_HDL_st2": "hdl_chol",
    "HE_LDL_drct": "ldl_chol",
    "HE_TG": "triglyceride",
    "HE_HB": "hemoglobin",
    "HE_crea": "creatinine",
    "HE_alt": "alt",
    "HE_ast": "ast",
    "HE_GGT": "ggt",
    "HE_BFP": "body_fat_pct",
    "HE_WC": "waist_circumference",
    "HE_Uph": "urine_ph",
    "HE_Upro": "urine_protein",
}

NUTRITION_COLUMNS = {
    "N_EN": "total_calories",
    "N_PROT": "protein_g",
    "N_FAT": "fat_g",
    "N_CHO": "carb_g",
    "N_FIBER": "fiber_g",
    "N_CA": "calcium_mg",
    "N_FE": "iron_mg",
    "N_NA": "sodium_mg",
    "N_KA": "potassium_mg",
    "N_VITA_RE": "vitamin_a_ug",
    "N_VITC": "vitamin_c_mg",
    "N_WATER": "water_ml",
    "N_CHOL": "dietary_cholesterol_mg",
    "N_SFA": "saturated_fat_g",
}

DEMOGRAPHIC_COLUMNS = {
    "sex": "gender",
    "age": "age",
    "incm": "income_quartile",
    "edu": "education_level",
}

# Disease diagnosis columns (1=yes, 0=no diagnosed by doctor)
DISEASE_COLUMNS = {
    "DI1_dg": "diabetes_diagnosed",
    "DI2_dg": "hyperlipidemia_diagnosed",
    "DI3_dg": "stroke_diagnosed",
    "DI4_dg": "heart_disease_diagnosed",
    "DI5_dg": "hypertension_diagnosed",
}

# Lifestyle columns
LIFESTYLE_COLUMNS = {
    "pa_aerobic": "aerobic_activity",
    "sm_presnt": "current_smoker",
    "dr_month": "alcohol_monthly",
    "BD1_11": "sleep_hours_weekday",
    "BD2_1": "sleep_hours_weekend",
}


def parse_sav_file(filepath: Path) -> tuple[pd.DataFrame, dict]:
    """Read SPSS .sav file and return DataFrame + metadata."""
    print(f"  Reading: {filepath.name} ...", end=" ", flush=True)
    df, meta = pyreadstat.read_sav(str(filepath))
    print(f"{len(df)} rows x {len(df.columns)} cols")
    return df, meta


def extract_diagnosis_data(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Extract diagnosis/health exam data for LSTM training."""
    available = {k: v for k, v in DIAGNOSIS_COLUMNS.items() if k in df.columns}
    demo_available = {k: v for k, v in DEMOGRAPHIC_COLUMNS.items() if k in df.columns}
    disease_available = {k: v for k, v in DISEASE_COLUMNS.items() if k in df.columns}

    cols_to_select = list(available.keys()) + list(demo_available.keys()) + list(disease_available.keys())
    subset = df[cols_to_select].copy()

    # Rename columns
    rename_map = {**available, **demo_available, **disease_available}
    subset = subset.rename(columns=rename_map)

    # Convert gender: 1=M, 2=F
    if "gender" in subset.columns:
        subset["gender"] = subset["gender"].map({1: "M", 2: "F"})

    # Add metadata
    subset["year"] = year
    subset["data_source"] = f"KNHANES_{year}"

    # Drop rows where ALL diagnosis columns are NaN
    diag_cols = list(available.values())
    subset = subset.dropna(subset=diag_cols, how="all")

    return subset


def extract_nutrition_data(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Extract nutrition intake data for lifestyle modeling."""
    available = {k: v for k, v in NUTRITION_COLUMNS.items() if k in df.columns}
    demo_available = {k: v for k, v in DEMOGRAPHIC_COLUMNS.items() if k in df.columns}

    cols_to_select = list(available.keys()) + list(demo_available.keys())
    subset = df[cols_to_select].copy()

    rename_map = {**available, **demo_available}
    subset = subset.rename(columns=rename_map)

    if "gender" in subset.columns:
        subset["gender"] = subset["gender"].map({1: "M", 2: "F"})

    subset["year"] = year
    subset["data_source"] = f"KNHANES_{year}"

    nut_cols = list(available.values())
    subset = subset.dropna(subset=nut_cols, how="all")

    return subset


def extract_lifestyle_data(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Extract lifestyle data (exercise, smoking, alcohol, sleep)."""
    available = {k: v for k, v in LIFESTYLE_COLUMNS.items() if k in df.columns}
    demo_available = {k: v for k, v in DEMOGRAPHIC_COLUMNS.items() if k in df.columns}

    if not available:
        return pd.DataFrame()

    cols_to_select = list(available.keys()) + list(demo_available.keys())
    subset = df[cols_to_select].copy()

    rename_map = {**available, **demo_available}
    subset = subset.rename(columns=rename_map)

    if "gender" in subset.columns:
        subset["gender"] = subset["gender"].map({1: "M", 2: "F"})

    subset["year"] = year
    return subset


def main():
    print("=" * 60)
    print("KNHANES SPSS Data Parser")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Find all .sav files
    sav_files = list(DATA_DIR.rglob("*.sav"))
    if not sav_files:
        print(f"\nNo .sav files found in {DATA_DIR}")
        return

    print(f"\nFound {len(sav_files)} SPSS files:")
    for f in sorted(sav_files):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.parent.name}/{f.name} ({size_mb:.1f} MB)")

    all_diagnosis = []
    all_nutrition = []
    all_lifestyle = []

    for sav_file in sorted(sav_files):
        filename = sav_file.stem.upper()

        # Detect year
        year = None
        for y in range(2018, 2027):
            if str(y)[2:] in filename[:4]:  # HN23 -> 23 -> 2023
                year = y
                break
        if not year:
            print(f"\n  Skipping {sav_file.name} (cannot detect year)")
            continue

        print(f"\n{'─' * 50}")
        print(f"Processing: {sav_file.parent.name}/{sav_file.name} (Year: {year})")

        # Skip large 24RC files for now (food recall detail)
        if "24RC" in filename:
            print(f"  Skipping 24-hour food recall (will process separately)")
            continue

        df, meta = parse_sav_file(sav_file)

        # Extract diagnosis data
        diag_df = extract_diagnosis_data(df, year)
        if len(diag_df) > 0:
            all_diagnosis.append(diag_df)
            print(f"  Diagnosis records: {len(diag_df)} (cols: {len([c for c in diag_df.columns if c in DIAGNOSIS_COLUMNS.values()])})")

        # Extract nutrition data
        nut_df = extract_nutrition_data(df, year)
        if len(nut_df) > 0:
            all_nutrition.append(nut_df)
            print(f"  Nutrition records: {len(nut_df)} (cols: {len([c for c in nut_df.columns if c in NUTRITION_COLUMNS.values()])})")

        # Extract lifestyle data
        life_df = extract_lifestyle_data(df, year)
        if len(life_df) > 0:
            all_lifestyle.append(life_df)
            print(f"  Lifestyle records: {len(life_df)}")

    # ── Combine and save ──
    print(f"\n{'=' * 60}")
    print("Saving combined training data...")

    if all_diagnosis:
        combined_diag = pd.concat(all_diagnosis, ignore_index=True)
        out_path = OUTPUT_DIR / "knhanes_diagnosis_all.csv"
        combined_diag.to_csv(out_path, index=False, encoding="utf-8")
        print(f"\n  Diagnosis: {len(combined_diag)} records → {out_path.name}")
        print(f"    Columns: {list(combined_diag.columns)}")
        print(f"    Years: {sorted(combined_diag['year'].unique())}")
        print(f"    Sample stats:")
        for col in ["bmi", "sbp", "fasting_glucose", "total_chol"]:
            if col in combined_diag.columns:
                valid = combined_diag[col].dropna()
                print(f"      {col}: mean={valid.mean():.1f}, std={valid.std():.1f}, n={len(valid)}")

    if all_nutrition:
        combined_nut = pd.concat(all_nutrition, ignore_index=True)
        out_path = OUTPUT_DIR / "knhanes_nutrition_all.csv"
        combined_nut.to_csv(out_path, index=False, encoding="utf-8")
        print(f"\n  Nutrition: {len(combined_nut)} records → {out_path.name}")
        for col in ["total_calories", "protein_g", "sodium_mg"]:
            if col in combined_nut.columns:
                valid = combined_nut[col].dropna()
                print(f"      {col}: mean={valid.mean():.1f}, std={valid.std():.1f}, n={len(valid)}")

    if all_lifestyle:
        combined_life = pd.concat(all_lifestyle, ignore_index=True)
        out_path = OUTPUT_DIR / "knhanes_lifestyle_all.csv"
        combined_life.to_csv(out_path, index=False, encoding="utf-8")
        print(f"\n  Lifestyle: {len(combined_life)} records → {out_path.name}")

    print(f"\n{'=' * 60}")
    print("KNHANES PARSING COMPLETE")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"These files are ready for LSTM-Transformer training (Phase 4)")
    print("=" * 60)


if __name__ == "__main__":
    main()
