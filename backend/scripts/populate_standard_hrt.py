"""
Populate Standard HRT Tables with Korean Health Reference Data
Sources: KNHANES, WHO, Korean Nutrition Society, ACSM, Korean Medical Guidelines

Run: python -m scripts.populate_standard_hrt
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import get_db_admin


# ============================================================================
# 1. POPULATION CATEGORIES (based on KNHANES age/gender/income stratification)
# ============================================================================
POPULATION_CATEGORIES = [
    # Children & Adolescents
    {"age_group": "0-5",   "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "0-5",   "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "6-11",  "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "6-11",  "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "12-18", "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "12-18", "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    # Adults
    {"age_group": "19-29", "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "19-29", "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "30-39", "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "30-39", "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "40-49", "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "40-49", "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "50-59", "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "50-59", "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "60-69", "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "60-69", "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "70-79", "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "70-79", "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "80+",   "gender": "M", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    {"age_group": "80+",   "gender": "F", "disability_yn": False, "income_decile": None, "country_code": "KOR"},
    # Disability categories (representative)
    {"age_group": "19-29", "gender": "M", "disability_yn": True, "income_decile": None, "country_code": "KOR"},
    {"age_group": "19-29", "gender": "F", "disability_yn": True, "income_decile": None, "country_code": "KOR"},
    {"age_group": "40-49", "gender": "M", "disability_yn": True, "income_decile": None, "country_code": "KOR"},
    {"age_group": "40-49", "gender": "F", "disability_yn": True, "income_decile": None, "country_code": "KOR"},
    {"age_group": "60-69", "gender": "M", "disability_yn": True, "income_decile": None, "country_code": "KOR"},
    {"age_group": "60-69", "gender": "F", "disability_yn": True, "income_decile": None, "country_code": "KOR"},
]


# ============================================================================
# 2. DIAGNOSIS NORMAL RANGES
# Sources: KNHANES 2023, Korean Society of Lipidology, Korean Diabetes Assoc,
#          Korean Society of Hypertension, WHO, Korean Health Checkup Standards
# ============================================================================
def build_diagnosis_norms(category_id_map: dict) -> list[dict]:
    """Build diagnosis norms for adult categories.
    Norms vary by age/gender per Korean clinical standards."""

    # Universal adult norms (applied to all adult categories)
    universal_metrics = [
        # metric_code, metric_name_en, unit, normal_min, normal_max, warning_min, warning_max, critical_min, critical_max, source
        ("BMI", "Body Mass Index", "kg/m\u00b2", 18.5, 22.9, 23.0, 24.9, 25.0, 40.0, "Korean Society for the Study of Obesity 2023"),
        ("SBP", "Systolic Blood Pressure", "mmHg", 90, 119, 120, 139, 140, 200, "Korean Society of Hypertension 2023"),
        ("DBP", "Diastolic Blood Pressure", "mmHg", 60, 79, 80, 89, 90, 130, "Korean Society of Hypertension 2023"),
        ("FBG", "Fasting Blood Glucose", "mg/dL", 70, 99, 100, 125, 126, 400, "Korean Diabetes Association 2023"),
        ("HBA1C", "Hemoglobin A1c", "%", 4.0, 5.6, 5.7, 6.4, 6.5, 15.0, "Korean Diabetes Association 2023"),
        ("TC", "Total Cholesterol", "mg/dL", 0, 199, 200, 239, 240, 500, "Korean Society of Lipidology 2023"),
        ("HDL", "HDL Cholesterol", "mg/dL", 60, 200, 40, 59, 0, 39, "Korean Society of Lipidology 2023"),
        ("LDL", "LDL Cholesterol", "mg/dL", 0, 129, 130, 159, 160, 300, "Korean Society of Lipidology 2023"),
        ("TG", "Triglycerides", "mg/dL", 0, 149, 150, 199, 200, 1000, "Korean Society of Lipidology 2023"),
        ("HB", "Hemoglobin", "g/dL", 13.0, 17.0, 10.0, 12.9, 0, 9.9, "KNHANES Reference Range (Male)"),
        ("CR", "Serum Creatinine", "mg/dL", 0.6, 1.2, 1.3, 1.9, 2.0, 15.0, "Korean Society of Nephrology"),
        ("ALT", "Alanine Aminotransferase (GPT)", "U/L", 0, 40, 41, 80, 81, 1000, "Korean Association for the Study of the Liver"),
        ("AST", "Aspartate Aminotransferase (GOT)", "U/L", 0, 40, 41, 80, 81, 1000, "Korean Association for the Study of the Liver"),
        ("GGT", "Gamma-Glutamyl Transferase", "U/L", 0, 63, 64, 120, 121, 1000, "Korean Association for the Study of the Liver"),
        ("BF", "Body Fat Percentage", "%", 10.0, 19.9, 20.0, 24.9, 25.0, 50.0, "Korean Society for the Study of Obesity (Male)"),
        ("WC", "Waist Circumference", "cm", 0, 89, 90, 99, 100, 160, "Korean Society for the Study of Obesity (Male)"),
        ("HR_REST", "Resting Heart Rate", "bpm", 60, 80, 81, 99, 100, 200, "Korean Society of Cardiology"),
        ("SPO2", "Blood Oxygen Saturation", "%", 95.0, 100.0, 90.0, 94.9, 0, 89.9, "WHO Clinical Guidelines"),
        ("URINE_PROTEIN", "Urine Protein", "mg/dL", 0, 14, 15, 29, 30, 500, "Korean Society of Nephrology"),
        ("VITAMIN_D", "25-OH Vitamin D", "ng/mL", 30, 100, 20, 29, 0, 19, "Korean Endocrine Society"),
    ]

    # Female-specific overrides
    female_overrides = {
        "HB": ("Hemoglobin", "g/dL", 12.0, 15.5, 10.0, 11.9, 0, 9.9, "KNHANES Reference Range (Female)"),
        "BF": ("Body Fat Percentage", "%", 18.0, 27.9, 28.0, 32.9, 33.0, 55.0, "Korean Society for the Study of Obesity (Female)"),
        "WC": ("Waist Circumference", "cm", 0, 84, 85, 94, 95, 150, "Korean Society for the Study of Obesity (Female)"),
    }

    norms = []
    adult_age_groups = ["19-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]

    for age_group in adult_age_groups:
        for gender in ["M", "F"]:
            key = f"{age_group}_{gender}_False"
            cat_id = category_id_map.get(key)
            if not cat_id:
                continue

            for metric in universal_metrics:
                code, name, unit, n_min, n_max, w_min, w_max, c_min, c_max, source = metric

                # Apply female overrides
                if gender == "F" and code in female_overrides:
                    name, unit, n_min, n_max, w_min, w_max, c_min, c_max, source = female_overrides[code]

                norms.append({
                    "category_id": cat_id,
                    "metric_code": code,
                    "metric_name_en": name,
                    "unit": unit,
                    "normal_min": n_min,
                    "normal_max": n_max,
                    "warning_min": w_min,
                    "warning_max": w_max,
                    "critical_min": c_min,
                    "critical_max": c_max,
                    "source": source,
                    "effective_date": "2024-01-01",
                })

    # Pediatric norms (simplified)
    child_metrics = [
        ("BMI_CHILD", "BMI Percentile", "percentile", 5, 84, 85, 94, 95, 100, "Korean Pediatric Society Growth Chart 2023"),
        ("HR_REST", "Resting Heart Rate", "bpm", 70, 110, 111, 130, 131, 200, "Korean Pediatric Cardiology"),
        ("SPO2", "Blood Oxygen Saturation", "%", 95.0, 100.0, 90.0, 94.9, 0, 89.9, "WHO Pediatric Guidelines"),
    ]
    for age_group in ["0-5", "6-11", "12-18"]:
        for gender in ["M", "F"]:
            key = f"{age_group}_{gender}_False"
            cat_id = category_id_map.get(key)
            if not cat_id:
                continue
            for code, name, unit, n_min, n_max, w_min, w_max, c_min, c_max, source in child_metrics:
                norms.append({
                    "category_id": cat_id,
                    "metric_code": code, "metric_name_en": name, "unit": unit,
                    "normal_min": n_min, "normal_max": n_max,
                    "warning_min": w_min, "warning_max": w_max,
                    "critical_min": c_min, "critical_max": c_max,
                    "source": source, "effective_date": "2024-01-01",
                })

    return norms


# ============================================================================
# 3. LIFESTYLE PLANS (Role-Model Plans per Category)
# Sources: Korean Nutrition Society DRIs 2020, ACSM Guidelines, Korean Sleep Society
# ============================================================================
def build_lifestyle_plans(category_id_map: dict) -> list[dict]:
    plans = []
    adult_age_groups = ["19-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]

    # Calorie targets by age/gender (Korean Nutrition Society DRIs 2020)
    calorie_targets = {
        ("19-29", "M"): 2600, ("19-29", "F"): 2000,
        ("30-39", "M"): 2500, ("30-39", "F"): 1900,
        ("40-49", "M"): 2500, ("40-49", "F"): 1900,
        ("50-59", "M"): 2200, ("50-59", "F"): 1800,
        ("60-69", "M"): 2000, ("60-69", "F"): 1700,
        ("70-79", "M"): 1900, ("70-79", "F"): 1500,
        ("80+",   "M"): 1700, ("80+",   "F"): 1400,
    }

    for age_group in adult_age_groups:
        for gender in ["M", "F"]:
            key = f"{age_group}_{gender}_False"
            cat_id = category_id_map.get(key)
            if not cat_id:
                continue

            cal = calorie_targets.get((age_group, gender), 2000)
            age_start = int(age_group.split("-")[0].replace("+", ""))

            # ── DIET PLAN ──
            plans.append({
                "category_id": cat_id,
                "plan_type": "diet",
                "plan_name": f"Balanced Korean Diet Plan ({age_group}, {'Male' if gender == 'M' else 'Female'})",
                "detail_json": {
                    "daily_calories_kcal": cal,
                    "macros": {
                        "carbohydrate_pct": 55,  # 55-65% per Korean DRIs
                        "protein_pct": 20,
                        "fat_pct": 25,
                        "carbohydrate_g": round(cal * 0.55 / 4),
                        "protein_g": round(cal * 0.20 / 4),
                        "fat_g": round(cal * 0.25 / 9),
                    },
                    "micronutrients": {
                        "sodium_mg_max": 2000,
                        "fiber_g_min": 25 if gender == "M" else 20,
                        "calcium_mg": 800 if age_start < 50 else 1000,
                        "iron_mg": 10 if gender == "M" else 14,
                        "vitamin_d_mcg": 10 if age_start < 65 else 15,
                    },
                    "meal_pattern": {
                        "meals_per_day": 3,
                        "snacks_per_day": 1,
                        "breakfast_pct": 25,
                        "lunch_pct": 35,
                        "dinner_pct": 30,
                        "snack_pct": 10,
                    },
                    "guidelines": [
                        "Half the plate should be vegetables (banchan)",
                        "Include fermented foods daily (kimchi, doenjang)",
                        "Limit processed foods and instant noodles",
                        "Reduce sodium: use low-sodium soy sauce and gochujang",
                        "Eat whole grains (brown rice, barley) instead of white rice",
                        "Fish 2-3 times per week for omega-3",
                    ],
                    "avoid": ["excessive alcohol", "sugary beverages", "late-night eating", "excessive sodium (>2000mg/day)"],
                },
                "evidence_level": "A",
                "created_by": "Korean Nutrition Society DRIs 2020",
            })

            # ── EXERCISE PLAN ──
            if age_start >= 65:
                exercise_detail = {
                    "weekly_aerobic_min": 150,
                    "aerobic_type": ["walking", "swimming", "cycling", "tai chi"],
                    "aerobic_intensity": "moderate",
                    "weekly_resistance_days": 2,
                    "resistance_type": ["bodyweight exercises", "resistance bands", "light dumbbells"],
                    "balance_training": True,
                    "balance_exercises": ["single-leg stand", "heel-to-toe walk", "chair stand"],
                    "flexibility_min_per_day": 10,
                    "rest_days_per_week": 3,
                    "precautions": ["Avoid high-impact activities", "Monitor heart rate during exercise", "Stop if chest pain or dizziness"],
                }
            else:
                exercise_detail = {
                    "weekly_aerobic_min": 150 if age_start >= 40 else 200,
                    "aerobic_type": ["jogging", "swimming", "cycling", "hiking", "dance"],
                    "aerobic_intensity": "moderate-to-vigorous",
                    "weekly_resistance_days": 3,
                    "resistance_type": ["compound lifts", "bodyweight", "resistance machines"],
                    "weekly_hiit_sessions": 1 if age_start < 50 else 0,
                    "flexibility_min_per_day": 10,
                    "rest_days_per_week": 2,
                    "met_target": 8.0 if age_start < 40 else 6.0,
                }

            plans.append({
                "category_id": cat_id,
                "plan_type": "exercise",
                "plan_name": f"Exercise Prescription ({age_group}, {'Male' if gender == 'M' else 'Female'})",
                "detail_json": exercise_detail,
                "evidence_level": "A",
                "created_by": "ACSM Guidelines for Exercise Testing and Prescription, 11th Ed",
            })

            # ── SLEEP PLAN ──
            sleep_hours = 7.5 if age_start < 65 else 7.0
            plans.append({
                "category_id": cat_id,
                "plan_type": "sleep",
                "plan_name": f"Sleep Hygiene Plan ({age_group})",
                "detail_json": {
                    "target_hours": sleep_hours,
                    "target_range": [sleep_hours - 0.5, sleep_hours + 0.5],
                    "bedtime_window": "22:00-23:00",
                    "wake_window": "06:00-07:00",
                    "deep_sleep_pct_target": 20 if age_start < 50 else 15,
                    "rem_pct_target": 25 if age_start < 60 else 20,
                    "max_wake_count": 1 if age_start < 50 else 2,
                    "sleep_quality_target": 7.0,
                    "hygiene_rules": [
                        "No screens 1 hour before bed",
                        "No caffeine after 14:00",
                        "Keep bedroom temperature 18-20C",
                        "No heavy meals within 3 hours of sleep",
                        "Regular sleep/wake schedule (even weekends)",
                        "Dark and quiet bedroom environment",
                    ],
                },
                "evidence_level": "A",
                "created_by": "Korean Sleep Society Guidelines + AASM",
            })

            # ── MEDICATION/SUPPLEMENT PLAN ──
            supplements = {
                "recommended": [
                    {"name": "Vitamin D", "dose": 1000, "unit": "IU", "frequency": "daily",
                     "reason": "Most Koreans are deficient (KNHANES: 75% < 20ng/mL)"},
                ],
                "conditional": [],
            }
            if age_start >= 50:
                supplements["recommended"].append(
                    {"name": "Calcium", "dose": 500, "unit": "mg", "frequency": "daily",
                     "reason": "Bone density preservation"})
            if age_start >= 60:
                supplements["conditional"].append(
                    {"name": "Omega-3", "dose": 1000, "unit": "mg", "frequency": "daily",
                     "reason": "Cardiovascular protection (if not eating fish 2x/week)"})
            if gender == "F" and age_start < 50:
                supplements["recommended"].append(
                    {"name": "Iron", "dose": 14, "unit": "mg", "frequency": "daily",
                     "reason": "Menstrual iron loss compensation"})

            plans.append({
                "category_id": cat_id,
                "plan_type": "medication",
                "plan_name": f"Supplement Guidance ({age_group}, {'Male' if gender == 'M' else 'Female'})",
                "detail_json": supplements,
                "evidence_level": "B",
                "created_by": "Korean Endocrine Society + Korean Nutrition Society",
            })

    return plans


# ============================================================================
# 4. DISEASE RISK WEIGHTS
# Sources: Framingham Risk Score (adapted), Korean NHIS risk models,
#          Korean Diabetes Association, Korean Society of Cardiology
# ============================================================================
DISEASE_RISK_WEIGHTS = [
    # Diabetes (Type 2)
    {"disease_code": "5A11", "disease_name": "Type 2 Diabetes Mellitus", "metric_code": "FBG", "weight_value": 0.30, "formula_type": "sigmoid"},
    {"disease_code": "5A11", "disease_name": "Type 2 Diabetes Mellitus", "metric_code": "HBA1C", "weight_value": 0.25, "formula_type": "sigmoid"},
    {"disease_code": "5A11", "disease_name": "Type 2 Diabetes Mellitus", "metric_code": "BMI", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "5A11", "disease_name": "Type 2 Diabetes Mellitus", "metric_code": "WC", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "5A11", "disease_name": "Type 2 Diabetes Mellitus", "metric_code": "TG", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "5A11", "disease_name": "Type 2 Diabetes Mellitus", "metric_code": "BF", "weight_value": 0.05, "formula_type": "linear"},

    # Cardiovascular Disease (Ischemic Heart Disease)
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "SBP", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "LDL", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "HDL", "weight_value": 0.15, "formula_type": "sigmoid"},
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "TC", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "TG", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "FBG", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "BMI", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "BA80", "disease_name": "Ischemic Heart Disease", "metric_code": "HR_REST", "weight_value": 0.05, "formula_type": "linear"},

    # Hypertension
    {"disease_code": "BA00", "disease_name": "Essential Hypertension", "metric_code": "SBP", "weight_value": 0.40, "formula_type": "linear"},
    {"disease_code": "BA00", "disease_name": "Essential Hypertension", "metric_code": "DBP", "weight_value": 0.30, "formula_type": "linear"},
    {"disease_code": "BA00", "disease_name": "Essential Hypertension", "metric_code": "BMI", "weight_value": 0.15, "formula_type": "linear"},
    {"disease_code": "BA00", "disease_name": "Essential Hypertension", "metric_code": "WC", "weight_value": 0.15, "formula_type": "linear"},

    # Obesity
    {"disease_code": "5B81", "disease_name": "Obesity", "metric_code": "BMI", "weight_value": 0.35, "formula_type": "linear"},
    {"disease_code": "5B81", "disease_name": "Obesity", "metric_code": "BF", "weight_value": 0.25, "formula_type": "linear"},
    {"disease_code": "5B81", "disease_name": "Obesity", "metric_code": "WC", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "5B81", "disease_name": "Obesity", "metric_code": "TG", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "5B81", "disease_name": "Obesity", "metric_code": "FBG", "weight_value": 0.10, "formula_type": "linear"},

    # Non-Alcoholic Fatty Liver Disease (NAFLD)
    {"disease_code": "DB92", "disease_name": "Non-Alcoholic Fatty Liver Disease", "metric_code": "ALT", "weight_value": 0.25, "formula_type": "linear"},
    {"disease_code": "DB92", "disease_name": "Non-Alcoholic Fatty Liver Disease", "metric_code": "AST", "weight_value": 0.15, "formula_type": "linear"},
    {"disease_code": "DB92", "disease_name": "Non-Alcoholic Fatty Liver Disease", "metric_code": "GGT", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "DB92", "disease_name": "Non-Alcoholic Fatty Liver Disease", "metric_code": "BMI", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "DB92", "disease_name": "Non-Alcoholic Fatty Liver Disease", "metric_code": "TG", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "DB92", "disease_name": "Non-Alcoholic Fatty Liver Disease", "metric_code": "FBG", "weight_value": 0.10, "formula_type": "linear"},

    # Chronic Kidney Disease
    {"disease_code": "GB60", "disease_name": "Chronic Kidney Disease", "metric_code": "CR", "weight_value": 0.35, "formula_type": "sigmoid"},
    {"disease_code": "GB60", "disease_name": "Chronic Kidney Disease", "metric_code": "URINE_PROTEIN", "weight_value": 0.25, "formula_type": "linear"},
    {"disease_code": "GB60", "disease_name": "Chronic Kidney Disease", "metric_code": "SBP", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "GB60", "disease_name": "Chronic Kidney Disease", "metric_code": "FBG", "weight_value": 0.20, "formula_type": "linear"},

    # Stroke (Cerebrovascular Disease)
    {"disease_code": "8B20", "disease_name": "Cerebral Infarction (Stroke)", "metric_code": "SBP", "weight_value": 0.30, "formula_type": "linear"},
    {"disease_code": "8B20", "disease_name": "Cerebral Infarction (Stroke)", "metric_code": "DBP", "weight_value": 0.15, "formula_type": "linear"},
    {"disease_code": "8B20", "disease_name": "Cerebral Infarction (Stroke)", "metric_code": "LDL", "weight_value": 0.15, "formula_type": "linear"},
    {"disease_code": "8B20", "disease_name": "Cerebral Infarction (Stroke)", "metric_code": "FBG", "weight_value": 0.15, "formula_type": "sigmoid"},
    {"disease_code": "8B20", "disease_name": "Cerebral Infarction (Stroke)", "metric_code": "BMI", "weight_value": 0.10, "formula_type": "linear"},
    {"disease_code": "8B20", "disease_name": "Cerebral Infarction (Stroke)", "metric_code": "HR_REST", "weight_value": 0.15, "formula_type": "linear"},

    # Sarcopenia (age-related muscle loss)
    {"disease_code": "FB32.1", "disease_name": "Sarcopenia", "metric_code": "BF", "weight_value": 0.30, "formula_type": "linear"},
    {"disease_code": "FB32.1", "disease_name": "Sarcopenia", "metric_code": "BMI", "weight_value": 0.25, "formula_type": "sigmoid"},
    {"disease_code": "FB32.1", "disease_name": "Sarcopenia", "metric_code": "HB", "weight_value": 0.20, "formula_type": "linear"},
    {"disease_code": "FB32.1", "disease_name": "Sarcopenia", "metric_code": "VITAMIN_D", "weight_value": 0.15, "formula_type": "linear"},
    {"disease_code": "FB32.1", "disease_name": "Sarcopenia", "metric_code": "CR", "weight_value": 0.10, "formula_type": "linear"},
]


# ============================================================================
# MAIN: Insert everything into Supabase
# ============================================================================
async def main():
    db = get_db_admin()

    print("=" * 60)
    print("Populating Standard HRT Tables")
    print("=" * 60)

    # ── 1. Population Categories ──
    print("\n[1/4] Inserting population categories...")
    cats = await db.insert("std_population_category", POPULATION_CATEGORIES)
    print(f"  Inserted {len(cats)} categories")

    # Build lookup map: "age_group_gender_disability" -> category_id
    cat_map = {}
    for c in cats:
        key = f"{c['age_group']}_{c['gender']}_{c['disability_yn']}"
        cat_map[key] = c["category_id"]
    print(f"  Category ID map built ({len(cat_map)} entries)")

    # ── 2. Diagnosis Norms ──
    print("\n[2/4] Inserting diagnosis normal ranges...")
    norms = build_diagnosis_norms(cat_map)
    # Insert in batches of 50 to avoid payload limits
    total_norms = 0
    for i in range(0, len(norms), 50):
        batch = norms[i:i+50]
        result = await db.insert("std_diagnosis_norm", batch)
        total_norms += len(result)
    print(f"  Inserted {total_norms} diagnosis norms across {len(set(n['metric_code'] for n in norms))} metrics")

    # ── 3. Lifestyle Plans ──
    print("\n[3/4] Inserting lifestyle plans...")
    plans = build_lifestyle_plans(cat_map)
    total_plans = 0
    for i in range(0, len(plans), 20):
        batch = plans[i:i+20]
        result = await db.insert("std_lifestyle_plan", batch)
        total_plans += len(result)
    print(f"  Inserted {total_plans} lifestyle plans (diet + exercise + sleep + supplements)")

    # ── 4. Disease Risk Weights ──
    print("\n[4/4] Inserting disease risk weights...")
    # Assign to a default adult male 30-39 category for now (category-specific weights can be added later)
    default_cat = cat_map.get("30-39_M_False")
    for w in DISEASE_RISK_WEIGHTS:
        w["category_id"] = default_cat
    weights = await db.insert("std_disease_risk_weight", DISEASE_RISK_WEIGHTS)
    print(f"  Inserted {len(weights)} risk weights across {len(set(w['disease_code'] for w in DISEASE_RISK_WEIGHTS))} diseases")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("STANDARD HRT POPULATION COMPLETE")
    print("=" * 60)
    print(f"  Population categories: {len(cats)}")
    print(f"  Diagnosis norms:       {total_norms}")
    print(f"  Lifestyle plans:       {total_plans}")
    print(f"  Disease risk weights:  {len(weights)}")
    diseases = sorted(set(w['disease_name'] for w in DISEASE_RISK_WEIGHTS))
    print(f"\n  Diseases covered ({len(diseases)}):")
    for d in diseases:
        print(f"    - {d}")
    print(f"\n  Metrics covered ({len(set(n['metric_code'] for n in norms))}):")
    for m in sorted(set(n['metric_code'] for n in norms)):
        print(f"    - {m}")


if __name__ == "__main__":
    asyncio.run(main())
