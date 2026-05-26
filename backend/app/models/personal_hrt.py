"""Pydantic models for Unified HRT+LRT tables."""

from datetime import date, datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, Field


# ── users (UNIFIED — BIGINT PK + UUID token) ──────────────────────────────

class UserBase(BaseModel):
    age_group: str | None = None
    birth_year: int | None = None
    gender: str | None = Field(None, pattern="^[MFX]$")
    nationality: str = "KOR"
    disability_yn: bool = False
    disability_type: str | None = None
    income_decile: int | None = Field(None, ge=1, le=10)
    occupation_category: str | None = None
    household_type: str | None = None
    income_bracket: str | None = None
    region: str | None = None
    mbti: str | None = Field(None, max_length=4)
    past_history: list[str] | None = None
    family_history: list[str] | None = None

class UserCreate(UserBase):
    user_hash: str | None = Field(None, max_length=64)

class User(UserBase):
    user_id: int
    user_token: UUID
    user_hash: str | None = None
    auth_user_id: UUID | None = None
    cluster_id: int | None = None
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# ── user_demographic ─────────────────────────────────────────────────────────

class DemographicBase(BaseModel):
    age: int | None = None
    gender: str | None = Field(None, pattern="^[MFO]$")
    disability_type: str | None = None
    income_decile: int | None = None
    past_history: list[str] | None = None
    family_history: list[str] | None = None

class DemographicCreate(DemographicBase):
    user_id: int

class Demographic(DemographicBase):
    demo_id: int
    user_id: int
    recorded_at: datetime

    model_config = {"from_attributes": True}


# ── user_biometric ───────────────────────────────────────────────────────────

class BiometricBase(BaseModel):
    device_type: str | None = Field(None, examples=["smartwatch", "bp_monitor", "cgm", "ai_glasses"])
    heart_rate: int | None = None
    hrv: int | None = None
    spo2: float | None = None
    body_temp: float | None = None
    resp_rate: int | None = None
    step_count: int | None = None
    stress_index: float | None = None
    glucose_mgdl: float | None = None
    glucose_trend: str | None = None
    raw_ecg_ref: str | None = None

class BiometricCreate(BiometricBase):
    user_id: int

class Biometric(BiometricBase):
    bio_id: int
    user_id: int
    measured_at: datetime

    model_config = {"from_attributes": True}


# ── user_diagnosis ───────────────────────────────────────────────────────────

class DiagnosisBase(BaseModel):
    period_type: str = Field(..., pattern="^(daily|weekly|monthly)$")
    period_start: date
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    sbp: int | None = None
    dbp: int | None = None
    fasting_glucose: int | None = None
    total_chol: int | None = None
    hdl_chol: int | None = None
    ldl_chol: int | None = None
    triglyceride: int | None = None
    hemoglobin: float | None = None
    creatinine: float | None = None
    alt: int | None = None
    ast: int | None = None
    ggt: int | None = None
    body_fat_pct: float | None = None
    muscle_mass_kg: float | None = None
    data_source: str | None = None

class DiagnosisCreate(DiagnosisBase):
    user_id: int

class Diagnosis(DiagnosisBase):
    diag_id: int
    user_id: int

    model_config = {"from_attributes": True}


# ── user_lifestyle ───────────────────────────────────────────────────────────

class LifestyleBase(BaseModel):
    recorded_date: date
    total_calories: int | None = None
    carb_g: int | None = None
    protein_g: int | None = None
    fat_g: int | None = None
    fiber_g: float | None = None
    sodium_mg: int | None = None
    alcohol_ml: int | None = None
    meal_count: int | None = None
    exercise_min: int | None = None
    exercise_type: str | None = None
    exercise_kcal: int | None = None
    exercise_intensity: str | None = Field(None, pattern="^(low|moderate|high)$")
    sleep_start: datetime | None = None
    sleep_end: datetime | None = None
    sleep_hours: float | None = None
    sleep_quality: float | None = None
    wake_count: int | None = None
    medication_json: dict[str, Any] | list[dict[str, Any]] | None = None
    data_source: str | None = None

class LifestyleCreate(LifestyleBase):
    user_id: int

class Lifestyle(LifestyleBase):
    ls_id: int
    user_id: int

    model_config = {"from_attributes": True}


# ── user_activity_event (NEW - AI Glasses) ───────────────────────────────────

class ActivityEventBase(BaseModel):
    event_type: str = Field(..., examples=["meal", "drink", "medication", "exercise", "walk"])
    source_device: str = Field(..., examples=["ai_glasses", "smartwatch", "cgm", "phone"])
    confidence_score: float | None = Field(None, ge=0, le=1)
    structured_data: dict[str, Any] | None = None
    thumbnail_ref: str | None = None
    clip_ref: str | None = None
    media_size_bytes: int | None = None
    edge_model_version: str | None = None
    verified: bool = False
    correction_data: dict[str, Any] | None = None
    processing_status: str = "edge_only"

class ActivityEventCreate(ActivityEventBase):
    user_id: int

class ActivityEvent(ActivityEventBase):
    event_id: int
    user_id: int
    detected_at: datetime

    model_config = {"from_attributes": True}


# ── user_health_level ────────────────────────────────────────────────────────

class HealthLevelBase(BaseModel):
    period_type: str | None = Field(None, pattern="^(daily|weekly|monthly)$")
    healthcare_index: float | None = Field(None, ge=0, le=100, description="HCI score T (0-100)")
    dri: float | None = None
    fatigue_level: int | None = Field(None, ge=1, le=10)
    stress_level: int | None = Field(None, ge=1, le=10)
    appetite_level: int | None = Field(None, ge=1, le=10)
    disease_risk_json: dict[str, Any] | None = None
    predicted: bool = False
    sim_scenario: str | None = None
    confidence_interval: dict[str, Any] | None = None

class HealthLevelCreate(HealthLevelBase):
    user_id: int

class HealthLevel(HealthLevelBase):
    hl_id: int
    user_id: int
    measured_at: datetime

    model_config = {"from_attributes": True}


# ── user_multimodal ──────────────────────────────────────────────────────────

class MultimodalBase(BaseModel):
    modal_type: str = Field(..., pattern="^(voice|image|video|sensor)$")
    context_place: str | None = None
    context_weather: str | None = None
    emotion_state: str | None = None
    intent_summary: str | None = None
    behavior_motive: str | None = None
    storage_ref: str | None = None

class MultimodalCreate(MultimodalBase):
    user_id: int

class Multimodal(MultimodalBase):
    mm_id: int
    user_id: int
    captured_at: datetime

    model_config = {"from_attributes": True}


# ── agent_conversation_log ───────────────────────────────────────────────────

class ConversationLogBase(BaseModel):
    agent_name: str = Field(..., examples=["HealthCore", "Nutrition", "Exercise", "Glasses"])
    channel: str | None = Field(None, examples=["webapp", "whatsapp", "kakao", "glasses_hud"])
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str
    tokens_used: int | None = None
    model_used: str | None = Field(None, examples=["qwen-7b", "meditron-70b", "claude-api"])

class ConversationLogCreate(ConversationLogBase):
    user_id: int

class ConversationLog(ConversationLogBase):
    log_id: int
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── simulation_result ────────────────────────────────────────────────────────

class SimulationResultBase(BaseModel):
    base_date: date
    scenario: str = Field(..., pattern="^(current|twin|optimistic)$")
    horizon_days: int = Field(..., examples=[30, 365, 3650])
    predicted_diag_json: dict[str, Any] | list[dict[str, Any]] | None = None
    predicted_risk_json: dict[str, Any] | list[dict[str, Any]] | None = None
    hci_series_json: dict[str, Any] | list[dict[str, Any]] | None = None
    confidence_bounds_json: dict[str, Any] | None = None
    model_version: str | None = None
    rmse: float | None = None
    mae_per_metric: dict[str, float] | None = None

class SimulationResultCreate(SimulationResultBase):
    user_id: int

class SimulationResult(SimulationResultBase):
    sim_id: int
    user_id: int
    run_at: datetime

    model_config = {"from_attributes": True}
