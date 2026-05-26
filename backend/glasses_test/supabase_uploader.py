"""
Supabase Uploader for Glasses Pipeline
Uploads activity events, thumbnails, and daily lifestyle aggregations.
"""

import httpx
import json
import os
from datetime import datetime, date, timezone
from pathlib import Path
from uuid import UUID
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


class SupabaseUploader:
    """Upload glasses pipeline results to Supabase."""

    def __init__(self):
        self.base_url = f"{SUPABASE_URL}/rest/v1"
        self.storage_url = f"{SUPABASE_URL}/storage/v1"
        self.headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self.client = httpx.Client(timeout=30.0)

    def upload_activity_event(
        self,
        user_id: str,
        event_type: str,
        structured_data: dict,
        confidence_score: float,
        source_device: str = "ai_glasses",
        edge_model_version: str = "test-v0.1",
        thumbnail_ref: str = None,
    ) -> dict:
        """Upload a single activity event to user_activity_event table."""
        payload = {
            "user_id": user_id,
            "event_type": event_type,
            "source_device": source_device,
            "confidence_score": confidence_score,
            "structured_data": structured_data,
            "edge_model_version": edge_model_version,
            "verified": False,
            "processing_status": "edge_only",
        }
        if thumbnail_ref:
            payload["thumbnail_ref"] = thumbnail_ref

        resp = self.client.post(
            f"{self.base_url}/user_activity_event",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def upload_thumbnail(self, bucket: str, file_path: str, data: bytes) -> str:
        """Upload thumbnail image to Supabase Storage. Returns public URL."""
        upload_headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "image/webp",
        }
        resp = self.client.post(
            f"{self.storage_url}/object/{bucket}/{file_path}",
            headers=upload_headers,
            content=data,
        )
        if resp.status_code == 400 and "already exists" in resp.text:
            # File exists, use upsert
            resp = self.client.put(
                f"{self.storage_url}/object/{bucket}/{file_path}",
                headers=upload_headers,
                content=data,
            )
        resp.raise_for_status()
        return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{file_path}"

    def update_daily_lifestyle(
        self,
        user_id: str,
        recorded_date: str,
        total_calories: int,
        protein_g: int,
        fat_g: int,
        carb_g: int,
        sodium_mg: int,
        meal_count: int,
        data_source: str = "ai_glasses",
    ) -> dict:
        """Upsert daily lifestyle aggregation."""
        payload = {
            "user_id": user_id,
            "recorded_date": recorded_date,
            "total_calories": total_calories,
            "protein_g": protein_g,
            "fat_g": fat_g,
            "carb_g": carb_g,
            "sodium_mg": sodium_mg,
            "meal_count": meal_count,
            "data_source": data_source,
        }
        resp = self.client.post(
            f"{self.base_url}/user_lifestyle",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def get_user_events_today(self, user_id: str) -> list[dict]:
        """Get all activity events for a user today."""
        today = date.today().isoformat()
        resp = self.client.get(
            f"{self.base_url}/user_activity_event",
            headers=self.headers,
            params={
                "user_id": f"eq.{user_id}",
                "detected_at": f"gte.{today}T00:00:00",
                "order": "detected_at.desc",
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_daily_summary(self, user_id: str) -> dict:
        """Calculate daily nutrition summary from today's events."""
        events = self.get_user_events_today(user_id)
        meals = [e for e in events if e.get("event_type") == "meal"]

        total_cal = 0
        total_protein = 0
        total_fat = 0
        total_carb = 0
        total_sodium = 0

        for meal in meals:
            data = meal.get("structured_data", {})
            nutrients = data.get("nutrients", {})
            total_cal += nutrients.get("energy_kcal", 0) or 0
            total_protein += nutrients.get("protein_g", 0) or 0
            total_fat += nutrients.get("fat_g", 0) or 0
            total_carb += nutrients.get("carbohydrate_g", 0) or 0
            total_sodium += nutrients.get("sodium_mg", 0) or 0

        return {
            "date": date.today().isoformat(),
            "meal_count": len(meals),
            "total_events": len(events),
            "total_calories": round(total_cal),
            "total_protein_g": round(total_protein),
            "total_fat_g": round(total_fat),
            "total_carb_g": round(total_carb),
            "total_sodium_mg": round(total_sodium),
        }

    def close(self):
        self.client.close()
