"use client";

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * LSTM Prediction Dashboard — Patent Diagrams 도4 & 도5
 * ═══════════════════════════════════════════════════════════════════════════
 * Healthcare AI Agent · Triple-H Co., Ltd. · Patent No. 10-2025-0145274
 *
 * Visualizes the output of the LSTM-Transformer ensemble (LSTM + MIRA +
 * TimesFM + Chronos-Bolt + TFT) for each user at four forecast horizons:
 *   6 months · 1 year · 2 years · 10 years
 *
 * Layout:
 *   Section 1 — Health Metric Trajectories (도4)
 *     Line + confidence-interval bands for 8 clinical metrics
 *   Section 2 — Disease Risk Scoring Table (도5)
 *     Per-disease predicted probability at each horizon + trend arrow
 *
 * ⚠ Data is currently MOCK — replace `mockTrajectoryData` and `mockRiskData`
 *   with calls to the FastAPI /api/v1/predictions/{user_id} endpoint once the
 *   LSTM model is deployed. The data shape is documented in each mock block
 *   so the swap is a drop-in.
 * ═══════════════════════════════════════════════════════════════════════════
 */

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Line,
  ComposedChart,
} from "recharts";

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

type Horizon = "6mo" | "1yr" | "2yr" | "10yr";

interface MetricDefinition {
  id: string;
  label: string;
  labelKo: string;
  labelKoShort: string;      // compact version for narrow cards (e.g. 혈압 vs 수축기 혈압)
  unit: string;
  normalMin: number;
  normalMax: number;
  warningThreshold?: number; // intermediate layer (pre-disease: pre-diabetes, elevated BP)
  warningDirection?: "above" | "below";
  criticalThreshold?: number;
  criticalDirection: "above" | "below";
  icon: string;
  // Plain-language content shown in the detail modal
  info: {
    whatIsIt: string;
    howMeasured: string;
    koreanContext?: string;  // Korean-specific reference ranges or risk factors
    practicalTips: string[];
  };
}

interface TrajectoryPoint {
  t: string;          // e.g. "Now", "6mo", "1yr", "2yr", "10yr"
  predicted: number;  // point estimate from LSTM ensemble
  lowerCI: number;    // 95% CI lower bound
  upperCI: number;    // 95% CI upper bound
  normalMin: number;  // from std_diagnosis_norm
  normalMax: number;
}

interface DiseaseRisk {
  diseaseCode: string;
  diseaseName: string;
  diseaseNameKo: string;
  category: "cardiovascular" | "metabolic" | "cognitive" | "oncological" | "mental" | "other";
  baseline: number;   // current risk %
  predictions: Record<Horizon, { probability: number; confidence: number }>;
  primaryDrivers: string[];
}

// ═══════════════════════════════════════════════════════════════════════════
// METRIC DEFINITIONS (reference — production reads from std_diagnosis_norm)
// ═══════════════════════════════════════════════════════════════════════════

// ─────────────────────────────────────────────────────────────────────────────
// CLINICAL THRESHOLDS — Korean-localized where applicable
// ─────────────────────────────────────────────────────────────────────────────
// BMI uses Korean Society for the Study of Obesity (KSSO) criteria which are
//   SIGNIFICANTLY lower than WHO global: 23 = overweight, 25 = obese (vs WHO
//   25 = overweight, 30 = obese). This is because Asian populations develop
//   metabolic complications at lower BMI.
// Fasting glucose + HbA1c use ADA thresholds (global); add warning layer at
//   pre-diabetes cutoff so users can see the risk before crossing diagnostic.
// BP uses AHA 2017 guidelines (Normal <120, Elevated 120-129, HTN Stage 1 130).
// LDL uses ATP III (Optimal <100, Borderline 130, High 160).
// ─────────────────────────────────────────────────────────────────────────────

const METRIC_DEFS: MetricDefinition[] = [
  {
    id: "bmi", label: "BMI", labelKo: "체질량지수", labelKoShort: "BMI",
    unit: "kg/m²",
    normalMin: 18.5, normalMax: 22.9,
    warningThreshold: 23, warningDirection: "above",
    criticalThreshold: 25, criticalDirection: "above",
    icon: "/icons/BMI.png",
    info: {
      whatIsIt: "BMI (Body Mass Index) is weight divided by height squared. It estimates body fat and is a screening tool for weight-related health risks.",
      howMeasured: "BMI = weight (kg) / height² (m²). Measured from your onboarding weight + height, updated any time you log new values.",
      koreanContext: "Korean Society for the Study of Obesity (KSSO) uses lower thresholds than WHO global: ≥23 = overweight, ≥25 = obese — because Asians develop diabetes and heart disease at lower BMI than Europeans. Our cutoffs follow KSSO, not WHO.",
      practicalTips: [
        "Reduce average daily calories by 200-400 kcal",
        "Aim for 150+ min/week moderate exercise (brisk walking, cycling)",
        "Prioritize protein and fiber at every meal — they keep you full",
        "Track your food in the Food & Nutrition category",
      ],
    },
  },
  {
    id: "sbp", label: "Systolic BP", labelKo: "수축기 혈압", labelKoShort: "혈압",
    unit: "mmHg",
    normalMin: 90, normalMax: 120,
    warningThreshold: 130, warningDirection: "above",
    criticalThreshold: 140, criticalDirection: "above",
    icon: "/icons/systolic bp.png",
    info: {
      whatIsIt: "Systolic blood pressure is the top number — the force your heart exerts when it beats. It's one of the strongest predictors of stroke and heart attack.",
      howMeasured: "Measured in mmHg by the AI glasses via PPG sensor, or manually entered from a cuff reading. Takes the rolling 7-day median to smooth out daily noise.",
      koreanContext: "BP in Koreans is typically 5-10 mmHg HIGHER in winter than summer due to cold-induced vasoconstriction (Korean Society of Hypertension 2024). Our seasonal curve accounts for this.",
      practicalTips: [
        "Reduce sodium to <2,000 mg/day (one Korean instant noodle = ~1,800 mg alone)",
        "Try DASH-style eating: more vegetables, fruits, low-fat dairy",
        "Aerobic exercise 30+ min most days drops SBP by 5-8 mmHg",
        "Limit alcohol — each drink raises SBP by 1 mmHg for 24h",
      ],
    },
  },
  {
    id: "glucose", label: "Fasting Glucose", labelKo: "공복 혈당", labelKoShort: "혈당",
    unit: "mg/dL",
    normalMin: 70, normalMax: 99,
    warningThreshold: 100, warningDirection: "above",  // pre-diabetes
    criticalThreshold: 126, criticalDirection: "above", // diabetes
    icon: "/icons/Fasting Glucose.png",
    info: {
      whatIsIt: "Fasting glucose is the amount of sugar in your blood after 8+ hours without eating. It shows how well your body handles sugar baseline.",
      howMeasured: "From a finger-prick meter or lab draw, entered manually or via connected glucometer. Must be fasting (no food/drink except water for 8 hours).",
      koreanContext: "Koreans have a higher genetic predisposition to insulin resistance at lower body weight than Europeans. A 'normal' BMI Korean with rising glucose is at real risk — don't wait for BMI to go up.",
      practicalTips: [
        "Drop sugary drinks first — biggest single win",
        "Eat fiber before carbs (vegetables first, then rice) — lowers glucose spike 30%",
        "Resistance training 2x/week improves insulin sensitivity",
        "Weight loss of 5-7% often reverses pre-diabetes",
      ],
    },
  },
  {
    id: "ldl", label: "LDL Cholesterol", labelKo: "LDL 콜레스테롤", labelKoShort: "LDL",
    unit: "mg/dL",
    normalMin: 0, normalMax: 100,
    warningThreshold: 130, warningDirection: "above",   // borderline
    criticalThreshold: 160, criticalDirection: "above",  // high
    icon: "/icons/LDL.png",
    info: {
      whatIsIt: "LDL (Low-Density Lipoprotein) is the 'bad' cholesterol. It builds up in artery walls and drives atherosclerosis — the cause of most heart attacks and strokes.",
      howMeasured: "From a lipid panel blood test, typically as part of an annual health check. Enter results manually after your physical exam.",
      koreanContext: "Korean diets traditionally have low LDL due to low saturated fat, but Westernization (fried chicken, processed meats, pastries) has driven LDL up sharply in the past 20 years.",
      practicalTips: [
        "Replace saturated fat (pork belly, butter) with monounsaturated (olive oil, avocado)",
        "Eat more soluble fiber: oats, beans, apples (lowers LDL by 5-10 mg/dL)",
        "Limit fried foods — trans fats are the worst offender",
        "Statin medication is very effective if lifestyle alone isn't enough — discuss with doctor",
      ],
    },
  },
  {
    id: "hba1c", label: "HbA1c", labelKo: "당화혈색소", labelKoShort: "HbA1c",
    unit: "%",
    normalMin: 4.0, normalMax: 5.6,
    warningThreshold: 5.7, warningDirection: "above",   // pre-diabetes
    criticalThreshold: 6.5, criticalDirection: "above",  // diabetes
    icon: "/icons/HbA1c.jpg",
    info: {
      whatIsIt: "HbA1c is the percentage of your hemoglobin coated in sugar — it reflects your average blood glucose over the past 2-3 months. A more stable picture than a single fasting glucose.",
      howMeasured: "Blood test, typically every 3-6 months for at-risk individuals. Enter results manually after lab draws.",
      koreanContext: "Korean Diabetes Association uses the same cutoffs as ADA: <5.7 normal, 5.7-6.4 pre-diabetes, ≥6.5 diabetes. At pre-diabetes stage, lifestyle intervention can still reverse trajectory.",
      practicalTips: [
        "Same advice as fasting glucose — fiber first, cut sugar, exercise",
        "Check every 3 months if you're in pre-diabetes range",
        "Weight loss is the single most effective intervention",
        "Quality sleep matters: poor sleep raises HbA1c independently",
      ],
    },
  },
  {
    id: "rhr", label: "Resting Heart Rate", labelKo: "안정시 심박수", labelKoShort: "심박수",
    unit: "bpm",
    normalMin: 60, normalMax: 100,
    criticalThreshold: 110, criticalDirection: "above",
    icon: "/icons/Resting Heart Rate.png",
    info: {
      whatIsIt: "Resting heart rate is how many times your heart beats per minute when you're relaxed and still. Lower (within healthy range) = more efficient heart + better fitness.",
      howMeasured: "From a wearable (watch/band) or manual pulse check, typically first thing in the morning before getting out of bed.",
      koreanContext: "Trained athletes can have resting HR of 40-60 bpm — this is healthy, not bradycardia. The 60 lower bound is for non-athletes.",
      practicalTips: [
        "Regular aerobic exercise (running, cycling) lowers RHR by 5-10 bpm over months",
        "Chronic stress + poor sleep raise RHR — manage both",
        "Caffeine, alcohol, and dehydration temporarily raise RHR",
        "Consistent >100 bpm at rest deserves a cardiology consult",
      ],
    },
  },
  {
    id: "sleep_quality", label: "Sleep Quality Score", labelKo: "수면 품질", labelKoShort: "수면",
    unit: "/100",
    normalMin: 70, normalMax: 100,
    warningThreshold: 60, warningDirection: "below",
    criticalThreshold: 50, criticalDirection: "below",
    icon: "/icons/Sleep.svg.png",
    info: {
      whatIsIt: "A composite score (0-100) of your sleep duration, deep-sleep %, REM %, wake-ups, and sleep consistency. Higher = more restorative sleep.",
      howMeasured: "Calculated nightly from your wearable or AI glasses EEG sensor (if equipped), combining time in each sleep stage with awakening count.",
      koreanContext: "Korea has one of the shortest average sleep durations among OECD countries (7h 24min) — chronic sleep debt is a national health issue.",
      practicalTips: [
        "Target 7-9 hours in bed, 85%+ efficiency (time asleep ÷ time in bed)",
        "Consistent wake time (even weekends) is the biggest driver of quality",
        "No screens for 30 min before bed — blue light suppresses melatonin",
        "Cool, dark room (18-20°C). Caffeine cutoff by 2 PM.",
      ],
    },
  },
  {
    id: "stress", label: "Mental Stress", labelKo: "정신 스트레스", labelKoShort: "스트레스",
    unit: "/10",
    normalMin: 0, normalMax: 4,
    warningThreshold: 5, warningDirection: "above",
    criticalThreshold: 7, criticalDirection: "above",
    icon: "/icons/mental health.png",
    info: {
      whatIsIt: "A self-reported stress level (0-10) combined with HRV (heart rate variability) from your wearable. Sustained high stress damages cardiovascular and immune health.",
      howMeasured: "Daily self-check-in through the app (0-10 slider), combined with HRV data from wearable when available. Rolling 7-day average shown.",
      koreanContext: "Stress patterns in Korea correlate strongly with work-hour culture and exam seasons. Winter SAD (Seasonal Affective Disorder) adds ~15% to baseline stress Nov-Feb.",
      practicalTips: [
        "10 min daily mindfulness (apps: Calm, Headspace) — measurable HRV improvement in 2 weeks",
        "Exercise is the most effective stress buffer — even a 20-min walk works",
        "Talk to someone — social support lowers cortisol",
        "If stress stays >6 for >2 weeks, consider professional counseling",
      ],
    },
  },
];

// ═══════════════════════════════════════════════════════════════════════════
// MOCK TRAJECTORY DATA — replace with API call
// Expected API shape:
//   GET /api/v1/predictions/trajectories/{user_id}
//   → { [metric_id]: TrajectoryPoint[] }
// ═══════════════════════════════════════════════════════════════════════════

const mockTrajectoryData: Record<string, TrajectoryPoint[]> = {
  bmi: [
    { t: "Now",  predicted: 24.1, lowerCI: 23.8, upperCI: 24.4, normalMin: 18.5, normalMax: 24.9 },
    { t: "6mo", predicted: 24.6, lowerCI: 24.0, upperCI: 25.2, normalMin: 18.5, normalMax: 24.9 },
    { t: "1yr", predicted: 25.2, lowerCI: 24.3, upperCI: 26.1, normalMin: 18.5, normalMax: 24.9 },
    { t: "2yr", predicted: 26.1, lowerCI: 24.8, upperCI: 27.4, normalMin: 18.5, normalMax: 24.9 },
    { t: "10yr", predicted: 28.4, lowerCI: 25.7, upperCI: 31.1, normalMin: 18.5, normalMax: 24.9 },
  ],
  sbp: [
    { t: "Now",  predicted: 122, lowerCI: 120, upperCI: 124, normalMin: 90, normalMax: 120 },
    { t: "6mo", predicted: 124, lowerCI: 121, upperCI: 127, normalMin: 90, normalMax: 120 },
    { t: "1yr", predicted: 126, lowerCI: 122, upperCI: 130, normalMin: 90, normalMax: 120 },
    { t: "2yr", predicted: 130, lowerCI: 125, upperCI: 135, normalMin: 90, normalMax: 120 },
    { t: "10yr", predicted: 142, lowerCI: 132, upperCI: 152, normalMin: 90, normalMax: 120 },
  ],
  glucose: [
    { t: "Now",  predicted: 94,  lowerCI: 92,  upperCI: 96,  normalMin: 70, normalMax: 99 },
    { t: "6mo", predicted: 97,  lowerCI: 94,  upperCI: 100, normalMin: 70, normalMax: 99 },
    { t: "1yr", predicted: 101, lowerCI: 97,  upperCI: 105, normalMin: 70, normalMax: 99 },
    { t: "2yr", predicted: 108, lowerCI: 102, upperCI: 114, normalMin: 70, normalMax: 99 },
    { t: "10yr", predicted: 128, lowerCI: 118, upperCI: 138, normalMin: 70, normalMax: 99 },
  ],
  ldl: [
    { t: "Now",  predicted: 112, lowerCI: 108, upperCI: 116, normalMin: 0, normalMax: 100 },
    { t: "6mo", predicted: 118, lowerCI: 112, upperCI: 124, normalMin: 0, normalMax: 100 },
    { t: "1yr", predicted: 125, lowerCI: 117, upperCI: 133, normalMin: 0, normalMax: 100 },
    { t: "2yr", predicted: 134, lowerCI: 124, upperCI: 144, normalMin: 0, normalMax: 100 },
    { t: "10yr", predicted: 152, lowerCI: 138, upperCI: 166, normalMin: 0, normalMax: 100 },
  ],
  hba1c: [
    { t: "Now",  predicted: 5.4, lowerCI: 5.3, upperCI: 5.5, normalMin: 4.0, normalMax: 5.6 },
    { t: "6mo", predicted: 5.6, lowerCI: 5.4, upperCI: 5.8, normalMin: 4.0, normalMax: 5.6 },
    { t: "1yr", predicted: 5.8, lowerCI: 5.6, upperCI: 6.0, normalMin: 4.0, normalMax: 5.6 },
    { t: "2yr", predicted: 6.1, lowerCI: 5.8, upperCI: 6.4, normalMin: 4.0, normalMax: 5.6 },
    { t: "10yr", predicted: 6.9, lowerCI: 6.4, upperCI: 7.4, normalMin: 4.0, normalMax: 5.6 },
  ],
  rhr: [
    { t: "Now",  predicted: 72, lowerCI: 70, upperCI: 74, normalMin: 60, normalMax: 100 },
    { t: "6mo", predicted: 71, lowerCI: 69, upperCI: 73, normalMin: 60, normalMax: 100 },
    { t: "1yr", predicted: 70, lowerCI: 67, upperCI: 73, normalMin: 60, normalMax: 100 },
    { t: "2yr", predicted: 68, lowerCI: 65, upperCI: 71, normalMin: 60, normalMax: 100 },
    { t: "10yr", predicted: 74, lowerCI: 68, upperCI: 80, normalMin: 60, normalMax: 100 },
  ],
  sleep_quality: [
    { t: "Now",  predicted: 76, lowerCI: 74, upperCI: 78, normalMin: 70, normalMax: 100 },
    { t: "6mo", predicted: 78, lowerCI: 75, upperCI: 81, normalMin: 70, normalMax: 100 },
    { t: "1yr", predicted: 79, lowerCI: 75, upperCI: 83, normalMin: 70, normalMax: 100 },
    { t: "2yr", predicted: 77, lowerCI: 72, upperCI: 82, normalMin: 70, normalMax: 100 },
    { t: "10yr", predicted: 70, lowerCI: 62, upperCI: 78, normalMin: 70, normalMax: 100 },
  ],
  stress: [
    { t: "Now",  predicted: 4.2, lowerCI: 4.0, upperCI: 4.4, normalMin: 0, normalMax: 4 },
    { t: "6mo", predicted: 4.4, lowerCI: 4.1, upperCI: 4.7, normalMin: 0, normalMax: 4 },
    { t: "1yr", predicted: 4.5, lowerCI: 4.1, upperCI: 4.9, normalMin: 0, normalMax: 4 },
    { t: "2yr", predicted: 4.7, lowerCI: 4.2, upperCI: 5.2, normalMin: 0, normalMax: 4 },
    { t: "10yr", predicted: 5.3, lowerCI: 4.5, upperCI: 6.1, normalMin: 0, normalMax: 4 },
  ],
};

// ═══════════════════════════════════════════════════════════════════════════
// MOCK DISEASE RISK DATA — replace with API call
// Expected API shape:
//   GET /api/v1/predictions/disease-risk/{user_id}
//   → DiseaseRisk[]
// ═══════════════════════════════════════════════════════════════════════════

const mockRiskData: DiseaseRisk[] = [
  { diseaseCode: "HTN",   diseaseName: "Hypertension",        diseaseNameKo: "고혈압",
    category: "cardiovascular", baseline: 8.2,
    predictions: { "6mo": { probability: 10.5, confidence: 0.82 }, "1yr": { probability: 13.8, confidence: 0.78 }, "2yr": { probability: 19.4, confidence: 0.71 }, "10yr": { probability: 42.6, confidence: 0.58 } },
    primaryDrivers: ["Rising SBP trajectory", "Winter seasonal elevation", "Family history"] },

  { diseaseCode: "T2D",   diseaseName: "Type 2 Diabetes",     diseaseNameKo: "제2형 당뇨병",
    category: "metabolic", baseline: 3.1,
    predictions: { "6mo": { probability: 4.2, confidence: 0.80 }, "1yr": { probability: 6.8, confidence: 0.75 }, "2yr": { probability: 11.3, confidence: 0.69 }, "10yr": { probability: 28.7, confidence: 0.54 } },
    primaryDrivers: ["Fasting glucose trending up", "HbA1c approaching pre-diabetes", "BMI increasing"] },

  { diseaseCode: "CVD",   diseaseName: "Cardiovascular Disease", diseaseNameKo: "심혈관 질환",
    category: "cardiovascular", baseline: 5.6,
    predictions: { "6mo": { probability: 6.8, confidence: 0.79 }, "1yr": { probability: 8.5, confidence: 0.74 }, "2yr": { probability: 12.1, confidence: 0.67 }, "10yr": { probability: 31.4, confidence: 0.52 } },
    primaryDrivers: ["LDL cholesterol elevated", "BP + stress combination", "Low exercise adherence"] },

  { diseaseCode: "STROKE", diseaseName: "Ischemic Stroke",    diseaseNameKo: "허혈성 뇌졸중",
    category: "cardiovascular", baseline: 1.8,
    predictions: { "6mo": { probability: 2.1, confidence: 0.76 }, "1yr": { probability: 2.6, confidence: 0.70 }, "2yr": { probability: 3.9, confidence: 0.63 }, "10yr": { probability: 12.5, confidence: 0.48 } },
    primaryDrivers: ["Sustained BP elevation", "LDL + inflammation markers"] },

  { diseaseCode: "METS",  diseaseName: "Metabolic Syndrome",  diseaseNameKo: "대사증후군",
    category: "metabolic", baseline: 12.4,
    predictions: { "6mo": { probability: 15.2, confidence: 0.83 }, "1yr": { probability: 19.8, confidence: 0.79 }, "2yr": { probability: 27.6, confidence: 0.72 }, "10yr": { probability: 52.1, confidence: 0.60 } },
    primaryDrivers: ["BMI + BP + glucose converging", "Central adiposity risk"] },

  { diseaseCode: "DEPR",  diseaseName: "Depressive Episode",  diseaseNameKo: "우울증",
    category: "mental", baseline: 6.8,
    predictions: { "6mo": { probability: 7.5, confidence: 0.71 }, "1yr": { probability: 8.9, confidence: 0.65 }, "2yr": { probability: 11.2, confidence: 0.58 }, "10yr": { probability: 18.7, confidence: 0.46 } },
    primaryDrivers: ["Chronic stress >4/10", "Sleep quality declining", "Winter SAD pattern"] },

  { diseaseCode: "COG",   diseaseName: "Cognitive Decline",   diseaseNameKo: "인지 기능 저하",
    category: "cognitive", baseline: 0.9,
    predictions: { "6mo": { probability: 1.0, confidence: 0.62 }, "1yr": { probability: 1.3, confidence: 0.58 }, "2yr": { probability: 2.1, confidence: 0.52 }, "10yr": { probability: 8.4, confidence: 0.41 } },
    primaryDrivers: ["Sleep quality projected to decline at 10yr", "Vascular risk contribution"] },

  { diseaseCode: "CANC",  diseaseName: "Cancer (any site)",   diseaseNameKo: "암 (종합)",
    category: "oncological", baseline: 2.3,
    predictions: { "6mo": { probability: 2.4, confidence: 0.55 }, "1yr": { probability: 2.6, confidence: 0.51 }, "2yr": { probability: 3.1, confidence: 0.46 }, "10yr": { probability: 7.2, confidence: 0.38 } },
    primaryDrivers: ["Age progression", "Lifestyle screening score"] },
];

// ═══════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function riskColor(p: number): string {
  if (p < 5)  return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (p < 15) return "text-amber-700 bg-amber-50 border-amber-200";
  if (p < 30) return "text-orange-700 bg-orange-50 border-orange-200";
  return "text-red-700 bg-red-100 border-red-300";
}

/**
 * Risk trend arrow — uses RELATIVE change (not absolute) so the arrow severity
 * is meaningful across diseases with very different baselines. E.g., Cognitive
 * Decline going 0.9% → 8.4% is a 9× increase and should scream ↑↑ even though
 * the absolute delta is only 7.5 percentage points. Hypertension going 8.2% →
 * 10.5% is only a 28% increase (mild) so it gets a single ↑.
 *
 * Rules:
 *   |Δ| < 0.5pp                       → stable
 *   relative ≥ +100% (doubled or more) → ↑↑ (severe)
 *   relative > 0%                      → ↑  (mild)
 *   relative ≤ -30%                    → ↓↓ (strong improvement)
 *   otherwise                          → ↓  (mild improvement)
 */
function riskTrendArrow(baseline: number, future: number): { arrow: string; color: string } {
  const delta = future - baseline;
  if (Math.abs(delta) < 0.5) return { arrow: "→", color: "text-gray-500" };
  const relative = delta / Math.max(baseline, 0.5);  // guard against tiny baselines
  if (relative >= 1)    return { arrow: "↑↑", color: "text-red-600" };
  if (relative > 0)     return { arrow: "↑",  color: "text-amber-600" };
  if (relative <= -0.3) return { arrow: "↓↓", color: "text-emerald-600" };
  return { arrow: "↓", color: "text-green-600" };
}

function confidenceLabel(c: number): string {
  if (c >= 0.75) return "High";
  if (c >= 0.60) return "Medium";
  return "Low";
}

function categoryBadge(cat: DiseaseRisk["category"]): string {
  const map: Record<DiseaseRisk["category"], string> = {
    cardiovascular: "bg-red-100 text-red-700",
    metabolic:      "bg-amber-100 text-amber-700",
    cognitive:      "bg-purple-100 text-purple-700",
    oncological:    "bg-pink-100 text-pink-700",
    mental:         "bg-blue-100 text-blue-700",
    other:          "bg-gray-100 text-gray-700",
  };
  return map[cat];
}

// ═══════════════════════════════════════════════════════════════════════════
// COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Compute a focused Y-axis domain that shows the data + relevant thresholds
 * without wasting vertical space on arbitrary normal-range bounds.
 *
 * For "above is bad" metrics (BP, glucose, LDL, ...), the normalMin is often
 * arbitrary (LDL = 0, BP = 90) and pushing it into the domain creates a huge
 * empty chart bottom. So we only include the bounds that are CLINICALLY
 * meaningful on the "danger side":
 *   - above direction: include normalMax, warning, critical (upper side)
 *   - below direction: include normalMin, warning, critical (lower side)
 * The opposite-side normal bound is omitted.
 */
function computeYDomain(metric: MetricDefinition, data: TrajectoryPoint[]): [number, number] {
  const dataValues = data.flatMap((d) => [d.predicted, d.lowerCI, d.upperCI]);
  const relevant: number[] = [...dataValues];
  if (metric.criticalDirection === "above") {
    relevant.push(metric.normalMax);
    if (metric.warningThreshold !== undefined) relevant.push(metric.warningThreshold);
    if (metric.criticalThreshold !== undefined) relevant.push(metric.criticalThreshold);
  } else {
    relevant.push(metric.normalMin);
    if (metric.warningThreshold !== undefined) relevant.push(metric.warningThreshold);
    if (metric.criticalThreshold !== undefined) relevant.push(metric.criticalThreshold);
  }
  const yMin = Math.min(...relevant);
  const yMax = Math.max(...relevant);
  const pad = (yMax - yMin) * 0.15 || 1;
  return [Math.floor(yMin - pad), Math.ceil(yMax + pad)];
}

/**
 * Compute the status for a single predicted value against the metric thresholds.
 * Returns the tier + display color. Handles both "above is bad" and "below is bad".
 */
function computeStatus(metric: MetricDefinition, value: number): {
  tier: "critical" | "warning" | "elevated" | "normal";
  label: string;
  textClass: string;
  bgClass: string;
} {
  const crit = metric.criticalThreshold;
  const warn = metric.warningThreshold;
  const warnDir = metric.warningDirection ?? metric.criticalDirection;
  const inCritical = crit !== undefined &&
    ((metric.criticalDirection === "above" && value >= crit) ||
     (metric.criticalDirection === "below" && value <= crit));
  const inWarning = warn !== undefined &&
    ((warnDir === "above" && value >= warn) ||
     (warnDir === "below" && value <= warn));
  const inElevated = value > metric.normalMax || value < metric.normalMin;

  if (inCritical) return { tier: "critical", label: "Critical",    textClass: "text-red-700",      bgClass: "bg-red-100" };
  if (inWarning)  return { tier: "warning",  label: "Warning",     textClass: "text-orange-700",   bgClass: "bg-orange-100" };
  if (inElevated) return { tier: "elevated", label: "Out of range", textClass: "text-amber-700",   bgClass: "bg-amber-100" };
  return          { tier: "normal",   label: "Within normal",       textClass: "text-emerald-700", bgClass: "bg-emerald-100" };
}

function TrajectoryChart({
  metric,
  data,
  onExpand,
}: {
  metric: MetricDefinition;
  data: TrajectoryPoint[];
  onExpand: () => void;
}) {
  const gradientId = `grad-${metric.id}`;
  const ciGradientId = `ci-${metric.id}`;
  const [yDomainMin, yDomainMax] = computeYDomain(metric, data);

  const now = data.find((d) => d.t === "Now") ?? data[0];
  const last = data[data.length - 1];
  const status = computeStatus(metric, now.predicted);                      // card badge = CURRENT
  const futureStatus = computeStatus(metric, last.predicted);               // 10yr projection
  const worsens = status.tier !== futureStatus.tier &&
    (["normal", "elevated", "warning", "critical"].indexOf(futureStatus.tier) >
     ["normal", "elevated", "warning", "critical"].indexOf(status.tier));

  // Direction-aware "Normal threshold" label. For metrics where higher is bad
  // (BMI, BP, glucose, LDL, HbA1c, RHR, stress), the line sits at normalMax
  // and is labeled "Upper normal". For metrics where LOWER is bad (sleep quality),
  // the line sits at normalMin and is labeled "Lower normal" — because the
  // ceiling (100) isn't a meaningful boundary, the floor (70) is.
  const normalLineY = metric.criticalDirection === "above" ? metric.normalMax : metric.normalMin;
  const normalLineLabel = metric.criticalDirection === "above" ? "Upper normal" : "Lower normal";

  return (
    <button
      type="button"
      onClick={onExpand}
      className="text-left w-full border border-red-100 rounded-xl p-4 bg-white shadow-sm hover:shadow-md hover:border-red-300 transition-all cursor-pointer group"
    >
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-bold text-gray-800 flex items-center gap-2">
            <img
              src={metric.icon}
              alt=""
              className="w-6 h-6 object-contain flex-shrink-0"
            />
            <span className="truncate">{metric.label}</span>
            <span className="text-xs font-normal text-gray-500 flex-shrink-0">({metric.labelKoShort})</span>
          </h3>
          <div className="text-[11px] text-gray-500 mt-0.5">
            Normal: {metric.normalMin}–{metric.normalMax} {metric.unit}
          </div>
        </div>
        <div className="flex flex-col items-end gap-0.5 flex-shrink-0">
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${status.textClass} ${status.bgClass}`}>
            {status.label}
          </span>
          {worsens && (
            <span
              title={`Projected to worsen to "${futureStatus.label}" by 10 years`}
              className="text-[9px] text-red-600 font-medium flex items-center gap-0.5"
            >
              ↑ 10yr: {futureStatus.label}
            </span>
          )}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#EF4444" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#EF4444" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id={ciGradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#FCA5A5" stopOpacity={0.20} />
              <stop offset="100%" stopColor="#FCA5A5" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
          <XAxis dataKey="t" tick={{ fontSize: 11 }} stroke="#999" />
          <YAxis
            tick={{ fontSize: 10 }}
            stroke="#999"
            domain={[yDomainMin, yDomainMax]}
            width={40}
          />
          <Tooltip
            contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: 8, fontSize: 12 }}
            formatter={(v: number) => [`${v} ${metric.unit}`]}
          />
          {/* Threshold lines. Labels positioned at true opposite corners so
              when lines are nearly coincident (BMI 22.9 vs 23, glucose 99 vs
              100, HbA1c 5.6 vs 5.7) the labels still land on opposite sides
              of the chart and never visually collide. */}
          <ReferenceLine y={normalLineY} stroke="#10B981" strokeDasharray="4 2" strokeWidth={1}
            label={{ value: normalLineLabel, position: "insideBottomLeft", fontSize: 9, fill: "#059669" }} />
          {metric.warningThreshold !== undefined && (
            <ReferenceLine y={metric.warningThreshold} stroke="#F59E0B" strokeDasharray="4 2" strokeWidth={1}
              label={{ value: "Warning", position: "insideTopRight", fontSize: 9, fill: "#D97706" }} />
          )}
          {metric.criticalThreshold !== undefined && (
            <ReferenceLine y={metric.criticalThreshold} stroke="#DC2626" strokeDasharray="4 2" strokeWidth={1}
              label={{ value: "Critical", position: "insideTopLeft", fontSize: 9, fill: "#B91C1C" }} />
          )}
          {/* 95% confidence interval band */}
          <Area type="monotone" dataKey="upperCI" stroke="none" fill={`url(#${ciGradientId})`} />
          <Area type="monotone" dataKey="lowerCI" stroke="none" fill="#fff" fillOpacity={1} />
          {/* Predicted trajectory */}
          <Area
            type="monotone"
            dataKey="predicted"
            stroke="#EF4444"
            strokeWidth={2.5}
            fill={`url(#${gradientId})`}
            dot={{ fill: "#EF4444", r: 4, strokeWidth: 2, stroke: "#fff" }}
            activeDot={{ r: 6 }}
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-2 grid grid-cols-4 gap-1 text-[10px]">
        {(["6mo", "1yr", "2yr", "10yr"] as const).map((h) => {
          const pt = data.find((d) => d.t === h);
          if (!pt) return <div key={h}></div>;
          return (
            <div key={h} className="text-center p-1 rounded bg-gray-50">
              <div className="text-gray-500">{h}</div>
              <div className="font-semibold text-red-700">{pt.predicted}</div>
              <div className="text-gray-400">±{((pt.upperCI - pt.lowerCI) / 2).toFixed(1)}</div>
            </div>
          );
        })}
      </div>

      <div className="mt-2 text-center text-[10px] text-gray-400 group-hover:text-red-500 transition-colors">
        Click for details →
      </div>
    </button>
  );
}

function RiskTableRow({ risk }: { risk: DiseaseRisk }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <tr
        className="border-t border-gray-200 hover:bg-red-50/40 cursor-pointer transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-3 py-3">
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-xs">{expanded ? "▼" : "▶"}</span>
            <div>
              <div className="font-semibold text-gray-800 text-sm">{risk.diseaseName}</div>
              <div className="text-[11px] text-gray-500">{risk.diseaseNameKo}</div>
            </div>
          </div>
        </td>
        <td className="px-3 py-3">
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${categoryBadge(risk.category)}`}>
            {risk.category}
          </span>
        </td>
        <td className="px-3 py-3 text-center">
          <div className="text-sm font-medium text-gray-700">{risk.baseline.toFixed(1)}%</div>
          <div className="text-[10px] text-gray-400">now</div>
        </td>
        {(["6mo", "1yr", "2yr", "10yr"] as const).map((h) => {
          const p = risk.predictions[h].probability;
          const c = risk.predictions[h].confidence;
          const trend = riskTrendArrow(risk.baseline, p);
          return (
            <td key={h} className="px-3 py-3 text-center">
              <div className={`inline-flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg border ${riskColor(p)}`}>
                <div className="flex items-center gap-1 font-bold">
                  {p.toFixed(1)}%
                  <span className={`text-xs ${trend.color}`}>{trend.arrow}</span>
                </div>
                <div className="text-[9px] opacity-70">conf: {confidenceLabel(c)}</div>
              </div>
            </td>
          );
        })}
      </tr>
      {expanded && (
        <tr className="bg-gray-50/50">
          <td colSpan={7} className="px-6 py-3">
            <div className="text-xs text-gray-600">
              <div className="font-semibold text-gray-700 mb-1">Primary risk drivers (LSTM attribution):</div>
              <ul className="list-disc list-inside space-y-0.5">
                {risk.primaryDrivers.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MODERN INLINE ICONS (Lucide-style) — used in detail modal section headers
// ═══════════════════════════════════════════════════════════════════════════

const ICON_SVG_PROPS = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

// "What is X?" — Info circle
function InfoIcon({ className = "" }: { className?: string }) {
  return (
    <svg {...ICON_SVG_PROPS} stroke="currentColor" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  );
}

// "Your trajectory — in plain language" — TrendingUp
function TrendingUpIcon({ className = "" }: { className?: string }) {
  return (
    <svg {...ICON_SVG_PROPS} stroke="currentColor" className={className} aria-hidden="true">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  );
}

// "What you can do" — Checklist / clipboard with checkmark
function ChecklistIcon({ className = "" }: { className?: string }) {
  return (
    <svg {...ICON_SVG_PROPS} stroke="currentColor" className={className} aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <path d="M8 2v4" />
      <path d="M16 2v4" />
      <path d="M3 10h18" />
      <path d="m9 16 2 2 4-4" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// METRIC DETAIL MODAL — large chart + plain-language explanation
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Build a data-driven narrative from the trajectory. Keeps wording simple
 * enough that a non-clinical reader can understand what's happening.
 */
function buildNarrative(metric: MetricDefinition, data: TrajectoryPoint[]): {
  now: string;
  tenYear: string;
  interpretation: string;
} {
  const now = data.find((d) => d.t === "Now")!;
  const tenYr = data.find((d) => d.t === "10yr")!;
  const nowStatus = computeStatus(metric, now.predicted);
  const tenStatus = computeStatus(metric, tenYr.predicted);

  const nowPart =
    nowStatus.tier === "normal"
      ? `You're currently in the healthy range at ${now.predicted} ${metric.unit}.`
      : nowStatus.tier === "elevated"
      ? `You're currently at ${now.predicted} ${metric.unit} — slightly outside the healthy range of ${metric.normalMin}–${metric.normalMax} ${metric.unit}.`
      : nowStatus.tier === "warning"
      ? `You're currently at ${now.predicted} ${metric.unit} — in the early warning zone.`
      : `You're currently at ${now.predicted} ${metric.unit} — already in the critical zone.`;

  const delta = tenYr.predicted - now.predicted;
  const direction = Math.abs(delta) < 0.5 ? "stay about the same"
    : delta > 0 ? `rise by about ${Math.abs(delta).toFixed(1)} ${metric.unit}`
    : `drop by about ${Math.abs(delta).toFixed(1)} ${metric.unit}`;

  const tenYrPart =
    `In 10 years, without lifestyle change, the model projects ${metric.label.toLowerCase()} will ${direction} to about ${tenYr.predicted} ${metric.unit}.`;

  const interpretation =
    tenStatus.tier === "critical" && nowStatus.tier !== "critical"
      ? `⚠️ This trajectory crosses into the CRITICAL zone. Small lifestyle changes now are far more effective than medication later.`
      : tenStatus.tier === "warning" && nowStatus.tier === "normal"
      ? `⚠️ This trajectory exits the healthy range within a decade. Early action has big returns — each month delayed compounds risk.`
      : tenStatus.tier === "normal"
      ? `✅ Your projected trajectory stays in the healthy range. Keep doing what you're doing.`
      : `Trajectory continues in the current zone. Review what you can do (below) to improve it.`;

  return { now: nowPart, tenYear: tenYrPart, interpretation };
}

function MetricDetailModal({
  metric,
  data,
  onClose,
}: {
  metric: MetricDefinition;
  data: TrajectoryPoint[];
  onClose: () => void;
}) {
  // ESC to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    // lock body scroll while modal open
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  const last = data[data.length - 1];
  const status = computeStatus(metric, last.predicted);
  const narrative = buildNarrative(metric, data);

  const gradientId = `grad-modal-${metric.id}`;
  const ciGradientId = `ci-modal-${metric.id}`;
  const [yDomainMin, yDomainMax] = computeYDomain(metric, data);

  const normalLineY = metric.criticalDirection === "above" ? metric.normalMax : metric.normalMin;
  const normalLineLabel = metric.criticalDirection === "above" ? "Upper normal boundary" : "Lower normal boundary";

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="metric-detail-title"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full my-8 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-gradient-to-r from-red-50 via-orange-50 to-red-50 border-b border-red-100 px-6 py-5 flex items-start justify-between gap-4">
          <div className="flex items-center gap-4 min-w-0 flex-1">
            <img src={metric.icon} alt="" className="w-12 h-12 object-contain flex-shrink-0" />
            <div className="min-w-0">
              <h2 id="metric-detail-title" className="text-2xl font-bold text-gray-900 truncate">
                {metric.label}
                <span className="text-base font-normal text-gray-500 ml-2">({metric.labelKo})</span>
              </h2>
              <div className="text-sm text-gray-600 mt-1">
                Healthy range:&nbsp;
                <span className="font-medium">{metric.normalMin}–{metric.normalMax} {metric.unit}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <span className={`text-xs font-semibold px-3 py-1 rounded-full ${status.textClass} ${status.bgClass}`}>
              {status.label}
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="w-9 h-9 rounded-full bg-white hover:bg-gray-100 border border-gray-200 text-gray-500 hover:text-gray-800 transition-colors flex items-center justify-center"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Large chart — expanded vertical room + alternating label positions so
            the three threshold lines don't pile labels in the same corner. */}
        <div className="px-6 pt-8 pb-4">
          <ResponsiveContainer width="100%" height={420}>
            <ComposedChart data={data} margin={{ top: 30, right: 50, left: 20, bottom: 20 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#EF4444" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#EF4444" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id={ciGradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#FCA5A5" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#FCA5A5" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
              <XAxis dataKey="t" tick={{ fontSize: 13, fontWeight: 500 }} stroke="#666" />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="#666"
                domain={[yDomainMin, yDomainMax]}
                width={55}
                label={{ value: metric.unit, angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#666" } }}
              />
              <Tooltip
                contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: 8, fontSize: 13, padding: 12 }}
                formatter={(v: number, name: string) => {
                  if (name === "predicted") return [`${v} ${metric.unit}`, "Predicted"];
                  if (name === "upperCI")   return [`${v} ${metric.unit}`, "Upper 95% CI"];
                  if (name === "lowerCI")   return [`${v} ${metric.unit}`, "Lower 95% CI"];
                  return [v, name];
                }}
              />
              {/* All three threshold lines always visible. Labels at opposite
                  corners so nearly-coincident lines (BMI 22.9 vs 23, glucose
                  99 vs 100, HbA1c 5.6 vs 5.7) don't overlap:
                    • Upper normal → bottom-LEFT (below line, left side)
                    • Warning      → top-RIGHT  (above line, right side)
                    • Critical     → top-LEFT   (above line, left side) */}
              <ReferenceLine y={normalLineY} stroke="#10B981" strokeDasharray="5 3" strokeWidth={1.5}
                label={{ value: normalLineLabel, position: "insideBottomLeft", fontSize: 11, fill: "#059669", offset: 6 }} />
              {metric.warningThreshold !== undefined && (
                <ReferenceLine y={metric.warningThreshold} stroke="#F59E0B" strokeDasharray="5 3" strokeWidth={1.5}
                  label={{ value: "Warning zone", position: "insideTopRight", fontSize: 11, fill: "#D97706", offset: 6 }} />
              )}
              {metric.criticalThreshold !== undefined && (
                <ReferenceLine y={metric.criticalThreshold} stroke="#DC2626" strokeDasharray="5 3" strokeWidth={1.5}
                  label={{ value: "Critical threshold", position: "insideTopLeft", fontSize: 11, fill: "#B91C1C", offset: 6 }} />
              )}
              <Area type="monotone" dataKey="upperCI" stroke="none" fill={`url(#${ciGradientId})`} />
              <Area type="monotone" dataKey="lowerCI" stroke="none" fill="#fff" fillOpacity={1} />
              <Area
                type="monotone"
                dataKey="predicted"
                stroke="#EF4444"
                strokeWidth={3}
                fill={`url(#${gradientId})`}
                dot={{ fill: "#EF4444", r: 5, strokeWidth: 2, stroke: "#fff" }}
                activeDot={{ r: 8 }}
              />
            </ComposedChart>
          </ResponsiveContainer>

          {/* Chart legend */}
          <div className="flex items-center gap-4 text-[11px] text-gray-600 flex-wrap pt-1">
            <span className="flex items-center gap-1.5">
              <span className="w-4 h-0.5 bg-red-500"></span>
              Your predicted trajectory
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-4 h-2 bg-red-300/30 rounded-sm"></span>
              95% confidence interval
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-4 border-t border-dashed border-emerald-500"></span>
              Healthy boundary
            </span>
            {metric.warningThreshold !== undefined && (
              <span className="flex items-center gap-1.5">
                <span className="w-4 border-t border-dashed border-amber-500"></span>
                Warning
              </span>
            )}
            {metric.criticalThreshold !== undefined && (
              <span className="flex items-center gap-1.5">
                <span className="w-4 border-t border-dashed border-red-600"></span>
                Critical
              </span>
            )}
          </div>
        </div>

        {/* Horizon summary grid */}
        <div className="px-6 pt-4">
          <div className="grid grid-cols-5 gap-2">
            {data.map((pt) => {
              const ptStatus = computeStatus(metric, pt.predicted);
              return (
                <div
                  key={pt.t}
                  className={`text-center rounded-lg py-2 px-1 border ${
                    pt.t === "Now" ? "bg-gray-50 border-gray-200" : "bg-white border-gray-100"
                  }`}
                >
                  <div className="text-[11px] text-gray-500 font-medium">{pt.t}</div>
                  <div className={`text-lg font-bold ${ptStatus.textClass}`}>{pt.predicted}</div>
                  <div className="text-[10px] text-gray-400">
                    {pt.lowerCI}–{pt.upperCI}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Plain-language sections — generous vertical spacing so the modal
            doesn't feel compressed the way the previous 5-unit gap did. */}
        <div className="px-6 py-8 space-y-7">
          {/* What is it */}
          <section>
            <h3 className="text-sm font-bold text-gray-800 mb-2 flex items-center gap-2">
              <InfoIcon className="text-sky-600" />
              What is {metric.label}?
            </h3>
            <p className="text-sm text-gray-700 leading-relaxed">{metric.info.whatIsIt}</p>
            <p className="text-xs text-gray-500 mt-2 italic">{metric.info.howMeasured}</p>
          </section>

          {/* Your trajectory */}
          <section className="bg-gradient-to-br from-red-50/60 to-orange-50/40 rounded-xl p-5 border border-red-100">
            <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
              <TrendingUpIcon className="text-red-600" />
              Your trajectory — in plain language
            </h3>
            <div className="space-y-2 text-sm text-gray-700 leading-relaxed">
              <p><span className="font-semibold">Right now:</span> {narrative.now}</p>
              <p><span className="font-semibold">In 10 years:</span> {narrative.tenYear}</p>
              <p className="pt-2 border-t border-red-100 text-gray-800">{narrative.interpretation}</p>
            </div>
          </section>

          {/* Korean context (optional) */}
          {metric.info.koreanContext && (
            <section>
              <h3 className="text-sm font-bold text-gray-800 mb-2 flex items-center gap-2">
                <span>🇰🇷</span> Korean context
              </h3>
              <p className="text-sm text-gray-700 leading-relaxed">{metric.info.koreanContext}</p>
            </section>
          )}

          {/* Practical tips */}
          <section>
            <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
              <ChecklistIcon className="text-emerald-600" />
              What you can do
            </h3>
            <ul className="space-y-2 text-sm text-gray-700">
              {metric.info.practicalTips.map((tip, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-red-500 mt-0.5 flex-shrink-0">•</span>
                  <span>{tip}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Disclaimer */}
          <section className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-[11px] text-gray-600 leading-relaxed">
            <strong className="text-gray-700">Important:</strong>{" "}
            These are predictions from a statistical model, not a medical diagnosis. Actual outcomes depend on many factors not captured in the model (genetics, medication changes, major life events). Always discuss with your physician before making major health decisions.
          </section>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// PAGE
// ═══════════════════════════════════════════════════════════════════════════

export default function PredictionsPage() {
  const [sortBy, setSortBy] = useState<"baseline" | "10yr">("10yr");
  const [selectedMetricId, setSelectedMetricId] = useState<string | null>(null);

  const selectedMetric = selectedMetricId
    ? METRIC_DEFS.find((m) => m.id === selectedMetricId) ?? null
    : null;

  const sortedRisks = [...mockRiskData].sort((a, b) => {
    if (sortBy === "baseline") return b.baseline - a.baseline;
    return b.predictions["10yr"].probability - a.predictions["10yr"].probability;
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-white to-red-50/30 pb-12">
      {/* Header */}
      <header className="bg-white border-b border-red-100 px-6 py-4 shadow-sm">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-sm text-gray-500 hover:text-red-600 transition-colors">
              ← Dashboard
            </Link>
            <span className="text-gray-300">/</span>
            <h1 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <img src="/icons/prediction.png" alt="" className="w-6 h-6 object-contain" />
              Health Predictions
              <span className="text-xs font-normal text-gray-500">(도4 · 도5)</span>
            </h1>
          </div>
          <div className="text-[11px] text-gray-400">
            LSTM-Transformer ensemble · 65-dim input · updated daily
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 pt-6 space-y-8">
        {/* Model transparency box */}
        <section className="bg-white border border-gray-200 rounded-xl p-4 text-xs text-gray-600">
          <div className="flex items-start gap-3">
            <span className="text-xl">ℹ️</span>
            <div>
              <div className="font-semibold text-gray-800 mb-1">How these predictions are made</div>
              <p className="leading-relaxed">
                Forecasts come from the <span className="font-medium">LSTM-Transformer ensemble</span> (LSTM backbone + MIRA + TimesFM + Chronos-Bolt + TFT), trained on KNHANES 2018–2024 (49K+ records) + your personal HRT. Inputs: 65-dimensional time-series (food, exercise, sleep, biometrics, mental, hydration, medication, seasonal, circadian). 95% confidence intervals shown as shaded bands. Forecasts are probabilistic — <span className="font-medium">not clinical diagnoses</span>. Consult a physician for interpretation.
              </p>
            </div>
          </div>
        </section>

        {/* SECTION 1 — TRAJECTORIES (도4) */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
              <img
                src="/icons/Health Metric Trajectories.png"
                alt=""
                className="w-7 h-7 object-contain"
              />
              Health Metric Trajectories
              <span className="text-xs font-normal text-gray-400">(Patent 도4)</span>
            </h2>
            <div className="flex items-center gap-3 text-[10px] text-gray-500">
              <span className="flex items-center gap-1">
                <span className="w-4 h-2 bg-red-400/30 rounded"></span>
                95% CI
              </span>
              <span className="flex items-center gap-1">
                <span className="w-4 border-t border-dashed border-emerald-500"></span>
                Upper normal
              </span>
              <span className="flex items-center gap-1">
                <span className="w-4 border-t border-dashed border-red-600"></span>
                Critical threshold
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {METRIC_DEFS.map((m) => (
              <TrajectoryChart
                key={m.id}
                metric={m}
                data={mockTrajectoryData[m.id]}
                onExpand={() => setSelectedMetricId(m.id)}
              />
            ))}
          </div>
        </section>

        {/* Detail modal — rendered here so it overlays everything */}
        {selectedMetric && (
          <MetricDetailModal
            metric={selectedMetric}
            data={mockTrajectoryData[selectedMetric.id]}
            onClose={() => setSelectedMetricId(null)}
          />
        )}

        {/* SECTION 2 — DISEASE RISK TABLE (도5) */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
              <span className="text-red-500">⚠️</span> Disease Risk Scoring
              <span className="text-xs font-normal text-gray-400">(Patent 도5)</span>
            </h2>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-500">Sort by:</span>
              <button
                onClick={() => setSortBy("baseline")}
                className={`px-2 py-1 rounded border text-[11px] transition-colors ${
                  sortBy === "baseline"
                    ? "bg-red-100 border-red-300 text-red-700"
                    : "bg-white border-gray-200 text-gray-600 hover:border-red-200"
                }`}
              >
                Current
              </button>
              <button
                onClick={() => setSortBy("10yr")}
                className={`px-2 py-1 rounded border text-[11px] transition-colors ${
                  sortBy === "10yr"
                    ? "bg-red-100 border-red-300 text-red-700"
                    : "bg-white border-gray-200 text-gray-600 hover:border-red-200"
                }`}
              >
                10-year risk
              </button>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <table className="w-full">
              <thead className="bg-gradient-to-r from-red-50 to-orange-50 border-b border-red-100">
                <tr>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-gray-700">Disease</th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-gray-700">Category</th>
                  <th className="px-3 py-3 text-center text-xs font-semibold text-gray-700">Baseline</th>
                  <th className="px-3 py-3 text-center text-xs font-semibold text-gray-700">6 months</th>
                  <th className="px-3 py-3 text-center text-xs font-semibold text-gray-700">1 year</th>
                  <th className="px-3 py-3 text-center text-xs font-semibold text-gray-700">2 years</th>
                  <th className="px-3 py-3 text-center text-xs font-semibold text-gray-700">10 years</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                {sortedRisks.map((r) => <RiskTableRow key={r.diseaseCode} risk={r} />)}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center gap-4 text-[10px] text-gray-500 flex-wrap">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded border border-emerald-200 bg-emerald-50"></span>
              Low (&lt;5%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded border border-amber-200 bg-amber-50"></span>
              Elevated (5-15%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded border border-orange-200 bg-orange-50"></span>
              High (15-30%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded border border-red-300 bg-red-100"></span>
              Critical (&gt;30%)
            </span>
            <span className="ml-auto italic">Click any row for primary risk drivers</span>
          </div>
        </section>

        {/* Footer */}
        <footer className="text-center text-[11px] text-gray-400 pt-4">
          Healthcare AI Agent · Triple-H Co., Ltd. · Patent No. 10-2025-0145274 ·
          Predictions regenerated nightly from your latest HRT data
        </footer>
      </main>
    </div>
  );
}
