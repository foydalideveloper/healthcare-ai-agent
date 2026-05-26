"""Pydantic models for Standard HRT tables (4 tables - reference data)."""

from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, Field


# ── std_population_category ──────────────────────────────────────────────────

class PopulationCategoryBase(BaseModel):
    age_group: str = Field(..., max_length=20, examples=["20-29", "60-69"])
    gender: str = Field(..., pattern="^[MFO]$")
    disability_yn: bool = False
    income_decile: int | None = Field(None, ge=1, le=10)
    country_code: str = "KOR"

class PopulationCategoryCreate(PopulationCategoryBase):
    pass

class PopulationCategory(PopulationCategoryBase):
    category_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── std_diagnosis_norm ───────────────────────────────────────────────────────

class DiagnosisNormBase(BaseModel):
    category_id: int
    metric_code: str = Field(..., max_length=50, examples=["BMI", "SBP", "FBG"])
    metric_name_en: str | None = None
    unit: str | None = Field(None, examples=["kg/m²", "mmHg", "mg/dL"])
    normal_min: float | None = None
    normal_max: float | None = None
    warning_min: float | None = None
    warning_max: float | None = None
    critical_min: float | None = None
    critical_max: float | None = None
    source: str | None = Field(None, examples=["KNHANES", "WHO"])
    effective_date: date | None = None

class DiagnosisNormCreate(DiagnosisNormBase):
    pass

class DiagnosisNorm(DiagnosisNormBase):
    norm_id: int

    model_config = {"from_attributes": True}


# ── std_lifestyle_plan ───────────────────────────────────────────────────────

class LifestylePlanBase(BaseModel):
    category_id: int
    plan_type: str = Field(..., pattern="^(diet|exercise|sleep|medication)$")
    plan_name: str | None = None
    detail_json: dict[str, Any] | None = None
    evidence_level: str | None = Field(None, pattern="^[ABC]$")
    created_by: str | None = None

class LifestylePlanCreate(LifestylePlanBase):
    pass

class LifestylePlan(LifestylePlanBase):
    plan_id: int
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── std_disease_risk_weight ──────────────────────────────────────────────────

class DiseaseRiskWeightBase(BaseModel):
    disease_code: str = Field(..., max_length=20)
    disease_name: str | None = None
    metric_code: str | None = None
    weight_value: float
    category_id: int | None = None
    formula_type: str = "linear"

class DiseaseRiskWeightCreate(DiseaseRiskWeightBase):
    pass

class DiseaseRiskWeight(DiseaseRiskWeightBase):
    weight_id: int

    model_config = {"from_attributes": True}
