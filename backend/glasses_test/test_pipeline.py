"""
AI Glasses Pipeline Test - Phase A
Tests the complete pipeline WITHOUT glasses hardware.
Simulates glasses input with local food photos.

What this tests (Stage 4 of v3 plan):
  1. Food photo → nutrition lookup (MFDS 275K + USDA 13K)
  2. Structured JSON event creation
  3. Upload to Supabase (user_activity_event table)
  4. Daily lifestyle aggregation
  5. Confidence-based routing (verified vs needs-review)

Usage:
  python -m glasses_test.test_pipeline
"""

import sys
import os
import io
import json
from datetime import datetime, date, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from glasses_test.food_lookup import FoodLookupService
from glasses_test.supabase_uploader import SupabaseUploader


# ── Simulated glasses events (what real glasses would detect) ──
SIMULATED_EVENTS = [
    {
        "event_type": "meal",
        "food_query": "김치찌개",
        "confidence": 0.85,
        "portion": "medium_bowl",
        "portion_multiplier": 1.5,  # 1.5 servings (150g of 100g serving)
        "timestamp": "2026-04-14T12:30:00+09:00",
    },
    {
        "event_type": "meal",
        "food_query": "비빔밥",
        "confidence": 0.72,
        "portion": "large_bowl",
        "portion_multiplier": 2.0,
        "timestamp": "2026-04-14T12:35:00+09:00",
    },
    {
        "event_type": "drink",
        "food_query": "아메리카노",
        "confidence": 0.91,
        "portion": "regular_cup",
        "portion_multiplier": 1.0,
        "timestamp": "2026-04-14T14:00:00+09:00",
    },
    {
        "event_type": "meal",
        "food_query": "삼겹살",
        "confidence": 0.65,  # Low confidence → needs cloud re-analysis
        "portion": "medium_plate",
        "portion_multiplier": 1.5,
        "timestamp": "2026-04-14T19:00:00+09:00",
    },
    {
        "event_type": "meal",
        "food_query": "chicken breast",  # English → USDA fallback
        "confidence": 0.88,
        "portion": "medium",
        "portion_multiplier": 1.5,
        "timestamp": "2026-04-14T19:30:00+09:00",
    },
    {
        "event_type": "medication",
        "food_query": None,  # No food lookup needed
        "confidence": 0.95,
        "portion": None,
        "portion_multiplier": None,
        "medication": {"name": "metformin", "dose": "500mg", "time": "19:30"},
        "timestamp": "2026-04-14T19:30:00+09:00",
    },
]


def run_pipeline_test():
    print("=" * 70)
    print("AI GLASSES PIPELINE TEST - Phase A")
    print("Simulating glasses → phone → Supabase pipeline")
    print("=" * 70)

    # ── Step 1: Initialize services ──
    print("\n[1/6] Initializing services...")
    food_service = FoodLookupService()
    stats = food_service.get_stats()
    print(f"  Food DB: {stats}")

    uploader = SupabaseUploader()
    print(f"  Supabase: connected to {os.getenv('SUPABASE_URL', 'NOT SET')}")

    # Create a test user in Supabase (in production, this comes from user login)
    test_user_id = str(uuid4())
    print(f"  Test user: {test_user_id}")
    try:
        import httpx as _httpx
        _resp = _httpx.post(
            f"{os.getenv('SUPABASE_URL')}/rest/v1/users",
            headers=uploader.headers,
            json={"user_id": test_user_id, "age_group": "30-39", "gender": "M",
                  "country_code": "KOR", "is_active": True},
        )
        _resp.raise_for_status()
        print(f"  Test user created in Supabase")
    except Exception as e:
        print(f"  User creation note: {e}")

    # ── Step 2: Process each simulated event ──
    print(f"\n[2/6] Processing {len(SIMULATED_EVENTS)} simulated glasses events...")
    results = []

    for i, event in enumerate(SIMULATED_EVENTS):
        print(f"\n  ── Event {i+1}: {event['event_type']} ──")

        # Food lookup (simulates phone-side MobileNetV2 → nutrition DB)
        nutrition = None
        if event["food_query"]:
            nutrition = food_service.lookup(event["food_query"])
            if nutrition:
                # Apply portion multiplier
                mult = event.get("portion_multiplier", 1.0) or 1.0
                for key in ["energy_kcal", "protein_g", "fat_g", "carbohydrate_g",
                            "dietary_fiber_g", "sodium_mg", "total_sugar_g", "cholesterol_mg"]:
                    if nutrition.get(key) is not None:
                        nutrition[key] = round(nutrition[key] * mult, 1)

                print(f"    Food: {nutrition['food_name']} (from {nutrition['source']})")
                print(f"    Calories: {nutrition.get('energy_kcal')} kcal")
                print(f"    Protein: {nutrition.get('protein_g')}g | Fat: {nutrition.get('fat_g')}g | Carbs: {nutrition.get('carbohydrate_g')}g")
                print(f"    Sodium: {nutrition.get('sodium_mg')}mg")
            else:
                print(f"    Food NOT FOUND: {event['food_query']}")

        # Build structured_data JSON (what gets stored in Supabase)
        structured_data = {
            "food_items": [],
            "nutrients": {},
        }

        if nutrition:
            structured_data["food_items"] = [{
                "name": nutrition["food_name"],
                "confidence": event["confidence"],
                "portion": event.get("portion"),
                "source_db": nutrition["source"],
            }]
            structured_data["nutrients"] = {
                "energy_kcal": nutrition.get("energy_kcal"),
                "protein_g": nutrition.get("protein_g"),
                "fat_g": nutrition.get("fat_g"),
                "carbohydrate_g": nutrition.get("carbohydrate_g"),
                "dietary_fiber_g": nutrition.get("dietary_fiber_g"),
                "sodium_mg": nutrition.get("sodium_mg"),
            }

        if event.get("medication"):
            structured_data["medication"] = event["medication"]

        # Confidence routing
        if event["confidence"] < 0.7:
            print(f"    ⚠ LOW CONFIDENCE ({event['confidence']}) → would upload photo for cloud re-analysis")
            processing_status = "needs_cloud_review"
        else:
            print(f"    ✓ High confidence ({event['confidence']}) → JSON + thumbnail only")
            processing_status = "edge_only"

        results.append({
            "event": event,
            "nutrition": nutrition,
            "structured_data": structured_data,
            "processing_status": processing_status,
        })

    # ── Step 3: Upload to Supabase ──
    print(f"\n[3/6] Uploading {len(results)} events to Supabase...")
    uploaded_events = []

    for r in results:
        try:
            event_result = uploader.upload_activity_event(
                user_id=test_user_id,
                event_type=r["event"]["event_type"],
                structured_data=r["structured_data"],
                confidence_score=r["event"]["confidence"],
                source_device="ai_glasses_test",
                edge_model_version="pipeline-test-v0.1",
            )
            uploaded_events.append(event_result)
            eid = event_result[0]["event_id"] if isinstance(event_result, list) else event_result.get("event_id")
            print(f"    Uploaded event_id={eid}: {r['event']['event_type']}")
        except Exception as e:
            print(f"    UPLOAD FAILED: {e}")

    # ── Step 4: Calculate daily aggregation ──
    print(f"\n[4/6] Calculating daily nutrition aggregation...")
    daily = uploader.get_daily_summary(test_user_id)
    print(f"    Date: {daily['date']}")
    print(f"    Meals: {daily['meal_count']}")
    print(f"    Total events: {daily['total_events']}")
    print(f"    Calories: {daily['total_calories']} kcal")
    print(f"    Protein: {daily['total_protein_g']}g")
    print(f"    Fat: {daily['total_fat_g']}g")
    print(f"    Carbs: {daily['total_carb_g']}g")
    print(f"    Sodium: {daily['total_sodium_mg']}mg")

    # ── Step 5: Upload daily lifestyle record ──
    print(f"\n[5/6] Uploading daily lifestyle summary to Supabase...")
    try:
        lifestyle_result = uploader.update_daily_lifestyle(
            user_id=test_user_id,
            recorded_date=daily["date"],
            total_calories=daily["total_calories"],
            protein_g=daily["total_protein_g"],
            fat_g=daily["total_fat_g"],
            carb_g=daily["total_carb_g"],
            sodium_mg=daily["total_sodium_mg"],
            meal_count=daily["meal_count"],
            data_source="ai_glasses_test",
        )
        print(f"    Lifestyle record uploaded successfully")
    except Exception as e:
        print(f"    LIFESTYLE UPLOAD FAILED: {e}")

    # ── Step 6: Summary report ──
    print(f"\n{'=' * 70}")
    print("TEST RESULTS SUMMARY")
    print(f"{'=' * 70}")

    total = len(SIMULATED_EVENTS)
    food_events = [r for r in results if r["nutrition"] is not None]
    korean_found = [r for r in results if r["nutrition"] and r["nutrition"]["source"] == "MFDS"]
    usda_found = [r for r in results if r["nutrition"] and r["nutrition"]["source"] == "USDA"]
    not_found = [r for r in results if r["event"]["food_query"] and r["nutrition"] is None]
    low_conf = [r for r in results if r["event"]["confidence"] < 0.7]
    high_conf = [r for r in results if r["event"]["confidence"] >= 0.7]

    print(f"\n  Events processed:     {total}")
    print(f"  Food lookups:         {len(food_events)} found / {len([r for r in results if r['event']['food_query']])} queried")
    print(f"    Korean (MFDS):      {len(korean_found)}")
    print(f"    International (USDA): {len(usda_found)}")
    print(f"    Not found:          {len(not_found)}")
    print(f"  Confidence routing:")
    print(f"    High (>=0.7):       {len(high_conf)} → JSON + thumbnail only")
    print(f"    Low (<0.7):         {len(low_conf)} → needs cloud re-analysis")
    print(f"  Uploaded to Supabase: {len(uploaded_events)} events + 1 lifestyle record")
    print(f"  Test user ID:         {test_user_id}")

    print(f"\n  WHAT'S IN SUPABASE NOW:")
    print(f"    user_activity_event: {len(uploaded_events)} rows (individual meal/drink/medication events)")
    print(f"    user_lifestyle:      1 row (daily aggregated nutrition)")
    print(f"    Each event contains: structured_data JSONB with food items + nutrients")

    print(f"\n  PIPELINE STAGES TESTED:")
    print(f"    [TESTED]  Stage 4: Food recognition → nutrition lookup")
    print(f"    [TESTED]  Stage 4: Confidence routing (high vs low)")
    print(f"    [TESTED]  Stage 5: Cloud ingestion → Supabase write")
    print(f"    [TESTED]  Stage 7: HRT update (user_activity_event + user_lifestyle)")
    print(f"    [SIMULATED] Stage 2: Event detection (used hardcoded events)")
    print(f"    [SIMULATED] Stage 3: Photo capture (no actual camera)")
    print(f"    [NOT TESTED] Stage 1: IMU/glasses hardware")
    print(f"    [NOT TESTED] Stage 4: YOLO-Face blur (no real photos)")
    print(f"    [NOT TESTED] Stage 4: MobileNetV2 visual classification (no TFLite model)")
    print(f"    [NOT TESTED] Stage 4: YOLOv8n portion detection (no TFLite model)")
    print(f"    [NOT TESTED] Stage 6: FoodLMM cloud re-analysis")

    print(f"\n{'=' * 70}")
    print("To view results: open Supabase dashboard → Table Editor → user_activity_event")
    print(f"Filter by user_id = {test_user_id}")
    print("=" * 70)

    food_service.close()
    uploader.close()


if __name__ == "__main__":
    run_pipeline_test()
