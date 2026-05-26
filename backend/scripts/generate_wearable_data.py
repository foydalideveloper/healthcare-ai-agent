"""
Generate synthetic wearable/CGM test data for pipeline testing.
Creates realistic smartwatch + CGM + AI glasses event data.

Usage: python -m scripts.generate_wearable_data
"""

import asyncio
import json
import math
import os
import random
import sys
from datetime import datetime, timedelta
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.database import get_db_admin

random.seed(42)


def generate_biometric_day(user_id: str, date: datetime, profile: dict) -> list[dict]:
    """Generate one day of realistic smartwatch biometric data (every 5 minutes)."""
    records = []
    base_hr = profile["resting_hr"]
    base_spo2 = profile["base_spo2"]
    base_temp = profile["base_temp"]
    steps_total = 0

    for hour in range(24):
        for minute in [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]:
            ts = date.replace(hour=hour, minute=minute, second=0)

            # Simulate circadian rhythm
            if 0 <= hour < 6:  # sleeping
                hr = base_hr - 10 + random.randint(-3, 3)
                stress = random.randint(5, 15)
                steps = 0
            elif 6 <= hour < 8:  # morning
                hr = base_hr + random.randint(-5, 10)
                stress = random.randint(15, 30)
                steps = random.randint(0, 200)
            elif 8 <= hour < 12:  # morning work
                hr = base_hr + random.randint(0, 15)
                stress = random.randint(20, 50)
                steps = random.randint(0, 300)
            elif 12 <= hour < 13:  # lunch
                hr = base_hr + random.randint(5, 20)
                stress = random.randint(15, 35)
                steps = random.randint(100, 500)
            elif 13 <= hour < 18:  # afternoon work
                hr = base_hr + random.randint(0, 15)
                stress = random.randint(25, 55)
                steps = random.randint(0, 200)
            elif 18 <= hour < 19:  # exercise time (some days)
                if random.random() < 0.4:  # 40% chance of exercise
                    hr = base_hr + random.randint(30, 60)
                    stress = random.randint(40, 70)
                    steps = random.randint(500, 1500)
                else:
                    hr = base_hr + random.randint(0, 10)
                    stress = random.randint(20, 40)
                    steps = random.randint(50, 300)
            elif 19 <= hour < 22:  # evening
                hr = base_hr + random.randint(-5, 10)
                stress = random.randint(15, 35)
                steps = random.randint(0, 100)
            else:  # late night
                hr = base_hr - 5 + random.randint(-5, 5)
                stress = random.randint(10, 25)
                steps = 0

            steps_total += steps
            hrv = max(20, 65 - (stress * 0.5) + random.randint(-10, 10))
            spo2 = base_spo2 + random.uniform(-0.5, 0.3)

            # Only record every 5 min (288 per day), but sample subset for DB
            if minute % 30 == 0:  # every 30 min = 48 records per day
                records.append({
                    "user_id": user_id,
                    "measured_at": ts.isoformat(),
                    "device_type": "smartwatch",
                    "heart_rate": max(45, min(200, hr)),
                    "hrv": max(10, min(100, int(hrv))),
                    "spo2": round(max(90, min(100, spo2)), 1),
                    "body_temp": round(base_temp + random.uniform(-0.3, 0.3), 1),
                    "resp_rate": random.randint(12, 20),
                    "step_count": steps_total,
                    "stress_index": round(max(0, min(100, stress + random.uniform(-5, 5))), 1),
                })

    return records


def generate_cgm_day(user_id: str, date: datetime, profile: dict) -> list[dict]:
    """Generate one day of CGM glucose data (every 15 minutes)."""
    records = []
    base_glucose = profile["base_glucose"]

    for hour in range(24):
        for minute in [0, 15, 30, 45]:
            ts = date.replace(hour=hour, minute=minute, second=0)

            # Simulate glucose response to meals
            if 7 <= hour < 8:  # post-breakfast spike
                glucose = base_glucose + random.randint(20, 50)
                trend = "rising"
            elif 8 <= hour < 10:  # coming down
                glucose = base_glucose + random.randint(5, 25)
                trend = "falling"
            elif 12 <= hour < 13:  # post-lunch spike
                glucose = base_glucose + random.randint(25, 60)
                trend = "rising"
            elif 13 <= hour < 15:  # coming down
                glucose = base_glucose + random.randint(5, 30)
                trend = "falling"
            elif 18 <= hour < 19:  # post-dinner spike
                glucose = base_glucose + random.randint(20, 55)
                trend = "rising"
            elif 19 <= hour < 21:  # coming down
                glucose = base_glucose + random.randint(0, 20)
                trend = "falling"
            else:  # baseline
                glucose = base_glucose + random.randint(-10, 10)
                trend = "stable"

            records.append({
                "user_id": user_id,
                "measured_at": ts.isoformat(),
                "device_type": "cgm",
                "glucose_mgdl": round(max(60, min(300, glucose + random.uniform(-5, 5))), 1),
                "glucose_trend": trend,
            })

    return records


def generate_activity_events(user_id: str, date: datetime, profile: dict) -> list[dict]:
    """Generate AI glasses activity events for one day."""
    events = []
    foods = [
        {"name": "toast_egg", "kr": "토스트와 계란", "cal": 350, "carb": 40, "protein": 15, "fat": 14},
        {"name": "bibimbap", "kr": "비빔밥", "cal": 550, "carb": 85, "protein": 20, "fat": 15},
        {"name": "kimchi_jjigae_rice", "kr": "김치찌개+밥", "cal": 480, "carb": 75, "protein": 18, "fat": 10},
        {"name": "samgyeopsal", "kr": "삼겹살", "cal": 650, "carb": 30, "protein": 28, "fat": 45},
        {"name": "gimbap", "kr": "김밥", "cal": 380, "carb": 55, "protein": 12, "fat": 12},
        {"name": "ramyeon", "kr": "라면", "cal": 500, "carb": 65, "protein": 10, "fat": 20},
        {"name": "chicken_breast_salad", "kr": "닭가슴살 샐러드", "cal": 280, "carb": 15, "protein": 35, "fat": 8},
    ]

    # Breakfast (~7:30)
    if random.random() < 0.8:
        food = random.choice(foods[:3])
        events.append({
            "user_id": user_id,
            "detected_at": date.replace(hour=7, minute=random.randint(15, 45)).isoformat(),
            "event_type": "meal",
            "source_device": "ai_glasses",
            "confidence_score": round(random.uniform(0.65, 0.95), 2),
            "structured_data": {
                "food_items": [food["kr"]],
                "calories": food["cal"],
                "nutrients": {"carb_g": food["carb"], "protein_g": food["protein"], "fat_g": food["fat"]},
                "meal_type": "breakfast",
            },
            "thumbnail_ref": f"s3://health-media/thumbnails/{date.strftime('%Y%m%d')}_breakfast.webp",
            "edge_model_version": "mobilenetv2-food-v1.0",
            "processing_status": "edge_only",
        })

    # Morning coffee (~9:00)
    events.append({
        "user_id": user_id,
        "detected_at": date.replace(hour=9, minute=random.randint(0, 30)).isoformat(),
        "event_type": "drink",
        "source_device": "ai_glasses",
        "confidence_score": round(random.uniform(0.85, 0.98), 2),
        "structured_data": {"beverage": "americano", "calories": 5},
        "edge_model_version": "mobilenetv2-food-v1.0",
        "processing_status": "edge_only",
    })

    # Lunch (~12:30)
    food = random.choice(foods)
    events.append({
        "user_id": user_id,
        "detected_at": date.replace(hour=12, minute=random.randint(15, 45)).isoformat(),
        "event_type": "meal",
        "source_device": "ai_glasses",
        "confidence_score": round(random.uniform(0.60, 0.92), 2),
        "structured_data": {
            "food_items": [food["kr"]],
            "calories": food["cal"],
            "nutrients": {"carb_g": food["carb"], "protein_g": food["protein"], "fat_g": food["fat"]},
            "meal_type": "lunch",
        },
        "thumbnail_ref": f"s3://health-media/thumbnails/{date.strftime('%Y%m%d')}_lunch.webp",
        "edge_model_version": "mobilenetv2-food-v1.0",
        "processing_status": "edge_only",
    })

    # Afternoon water (~15:00)
    if random.random() < 0.5:
        events.append({
            "user_id": user_id,
            "detected_at": date.replace(hour=15, minute=random.randint(0, 30)).isoformat(),
            "event_type": "drink",
            "source_device": "ai_glasses",
            "confidence_score": round(random.uniform(0.70, 0.90), 2),
            "structured_data": {"beverage": "water", "volume_ml": 250, "calories": 0},
            "processing_status": "edge_only",
        })

    # Medication (~8:00 and ~20:00)
    if profile.get("takes_medication"):
        events.append({
            "user_id": user_id,
            "detected_at": date.replace(hour=8, minute=0).isoformat(),
            "event_type": "medication",
            "source_device": "ai_glasses",
            "confidence_score": round(random.uniform(0.70, 0.88), 2),
            "structured_data": {"medication": "vitamin_d", "dose_iu": 1000},
            "processing_status": "edge_only",
        })

    # Dinner (~19:00)
    food = random.choice(foods)
    events.append({
        "user_id": user_id,
        "detected_at": date.replace(hour=19, minute=random.randint(0, 30)).isoformat(),
        "event_type": "meal",
        "source_device": "ai_glasses",
        "confidence_score": round(random.uniform(0.55, 0.90), 2),
        "structured_data": {
            "food_items": [food["kr"]],
            "calories": food["cal"],
            "nutrients": {"carb_g": food["carb"], "protein_g": food["protein"], "fat_g": food["fat"]},
            "meal_type": "dinner",
        },
        "thumbnail_ref": f"s3://health-media/thumbnails/{date.strftime('%Y%m%d')}_dinner.webp",
        "edge_model_version": "mobilenetv2-food-v1.0",
        "processing_status": "edge_only",
    })

    # Exercise (~18:00, 40% chance)
    if random.random() < 0.4:
        ex_type = random.choice(["walking", "jogging", "cycling", "gym"])
        events.append({
            "user_id": user_id,
            "detected_at": date.replace(hour=18, minute=random.randint(0, 30)).isoformat(),
            "event_type": "exercise",
            "source_device": "ai_glasses",
            "confidence_score": round(random.uniform(0.80, 0.95), 2),
            "structured_data": {
                "exercise_type": ex_type,
                "duration_min": random.randint(20, 60),
                "estimated_kcal": random.randint(150, 400),
            },
            "processing_status": "edge_only",
        })

    return events


# ── User profiles for synthetic data ──
USER_PROFILES = [
    {
        "name": "Healthy 30s Male",
        "age_group": "30-39", "gender": "M",
        "resting_hr": 68, "base_spo2": 98.0, "base_temp": 36.5,
        "base_glucose": 90, "takes_medication": False,
    },
    {
        "name": "Pre-diabetic 50s Male",
        "age_group": "50-59", "gender": "M",
        "resting_hr": 75, "base_spo2": 97.5, "base_temp": 36.6,
        "base_glucose": 115, "takes_medication": True,
    },
    {
        "name": "Active 40s Female",
        "age_group": "40-49", "gender": "F",
        "resting_hr": 62, "base_spo2": 98.5, "base_temp": 36.4,
        "base_glucose": 85, "takes_medication": True,
    },
    {
        "name": "Elderly 70s Male",
        "age_group": "70-79", "gender": "M",
        "resting_hr": 72, "base_spo2": 96.5, "base_temp": 36.3,
        "base_glucose": 105, "takes_medication": True,
    },
    {
        "name": "Young 20s Female",
        "age_group": "19-29", "gender": "F",
        "resting_hr": 65, "base_spo2": 98.8, "base_temp": 36.5,
        "base_glucose": 82, "takes_medication": False,
    },
]


async def main():
    print("=" * 60)
    print("Synthetic Wearable/CGM/Glasses Data Generator")
    print("=" * 60)

    db = get_db_admin()
    days_to_generate = 7  # 1 week of data per user
    base_date = datetime(2026, 4, 7)  # start 1 week ago

    total_biometric = 0
    total_cgm = 0
    total_events = 0

    for profile in USER_PROFILES:
        print(f"\n{'─' * 50}")
        print(f"Generating data for: {profile['name']}")

        # Create user
        user = await db.insert("users", {
            "age_group": profile["age_group"],
            "gender": profile["gender"],
            "country_code": "KOR",
        })
        user_id = user[0]["user_id"]
        print(f"  User ID: {user_id}")

        for day_offset in range(days_to_generate):
            current_date = base_date + timedelta(days=day_offset)

            # Generate smartwatch data (48 records/day)
            bio_records = generate_biometric_day(user_id, current_date, profile)
            for i in range(0, len(bio_records), 20):
                batch = bio_records[i:i+20]
                await db.insert("user_biometric", batch)
            total_biometric += len(bio_records)

            # Generate CGM data (96 records/day)
            cgm_records = generate_cgm_day(user_id, current_date, profile)
            for i in range(0, len(cgm_records), 20):
                batch = cgm_records[i:i+20]
                await db.insert("user_biometric", batch)
            total_cgm += len(cgm_records)

            # Generate AI glasses events (5-8 per day)
            events = generate_activity_events(user_id, current_date, profile)
            for event in events:
                await db.insert("user_activity_event", [event])
            total_events += len(events)

        print(f"  Generated {days_to_generate} days: {len(bio_records)*days_to_generate} biometric, "
              f"{len(cgm_records)*days_to_generate} CGM, {total_events} events")

    print(f"\n{'=' * 60}")
    print("SYNTHETIC DATA GENERATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Users created:     {len(USER_PROFILES)}")
    print(f"  Biometric records: {total_biometric}")
    print(f"  CGM records:       {total_cgm}")
    print(f"  Activity events:   {total_events}")
    print(f"  Days per user:     {days_to_generate}")
    print(f"\n  Data is in Supabase — ready for API testing and pipeline development.")


if __name__ == "__main__":
    asyncio.run(main())
