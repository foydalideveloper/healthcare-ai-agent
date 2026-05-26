# Multi-Dimensional HRT System Overview
## Triple-H Co., Ltd. | Healthcare AI Agent

---

## What is Multi-Dimensional Health Data?

Think of a normal health app — it shows your weight on a line graph. That's ONE dimension (weight over time).

Our system is like a **Rubik's cube of health data** — you can look at it from any angle:

```
Example: User Kim, age 30

Dimension 1 — TIME (when):
  Lifetime: "In 30 years, Kim ate 32,850 meals"
  This year: "Kim ate 1,095 meals in 2026"
  This month: "Kim ate 90 meals in April"
  Today: "Kim ate 3 meals today"
  Right now: "Kim is eating bibimbap (550 kcal)"

Dimension 2 — CATEGORY (what):
  Food: "Kim ate 1,800 kcal today"
  Exercise: "Kim jogged 30 minutes"
  Sleep: "Kim slept 7.5 hours"
  Medicine: "Kim took Vitamin D"
  Biometrics: "Kim's BP is 120/80"
  
Dimension 3 — USER (who):
  Kim: BMI 24, healthy
  Park: BMI 29, overweight
  100,000 users: average BMI 23.5
```

---

## How It Works (Simple Example)

### Step 1: Data comes in
```
Kim wears AI glasses → takes video of lunch
→ YOLOv8 sees: bowl + spoon → "eating"
→ Whisper hears: "I'm eating bibimbap"
→ System saves: food_name="비빔밥", kcal=550, time=12:30
```

### Step 2: Data is stored in Supabase
```
Table: user_food_log
  | food_id | user_id | consumed_at          | food_name | kcal |
  |---------|---------|----------------------|-----------|------|
  | 42      | 1       | 2026-04-17 12:30:00  | 비빔밥     | 550  |
  | 43      | 1       | 2026-04-17 18:30:00  | 삼겹살     | 500  |
```

### Step 3: Database automatically calculates summaries
```
SQL View: hrt_monthly_food
  "In April 2026, Kim ate 90 meals, total 54,000 kcal"
  
SQL View: hrt_yearly_summary  
  "In 2026, Kim ate 1,095 meals, exercised 5,475 minutes"
```

### Step 4: User clicks on dashboard
```
Click [2026] → sees all months
Click [April] → sees all 30 days
Click [Day 17] → sees hourly: breakfast, lunch, dinner
Click [Lunch 12:30] → sees: 비빔밥, 550 kcal, 18g protein
```

### Step 5: AI predicts the future
```
LSTM model reads Kim's HRT data:
  "Kim eats 2,200 kcal/day but burns only 1,800"
  "Kim exercises only 15 min/day (recommended: 30)"
  
Prediction:
  30 days: BMI 24.1 → 24.3
  1 year: BMI 24.1 → 25.8 (overweight!)
  10 years: Diabetes risk 5% → 15%
  
Digital Twin says:
  "If Kim exercises 30 min/day instead of 15,
   diabetes risk drops from 15% to 6%"
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              USER DEVICES                    │
│  AI Glasses  │  Smart Watch  │  Phone        │
└──────────────┬──────────────────────────────┘
               ↓
┌──────────────┴──────────────────────────────┐
│           AI PROCESSING                      │
│  YOLOv8 (see food) + Whisper (hear speech)   │
│  EfficientNetV2 (identify Korean food)       │
│  MFDS DB (lookup nutrition: 275K foods)      │
└──────────────┬──────────────────────────────┘
               ↓
┌──────────────┴──────────────────────────────┐
│        SUPABASE DATABASE (38 tables)         │
│                                              │
│  Raw data:     user_food_log                 │
│                user_lifestyle                │
│                user_biometric                │
│                user_medication               │
│                                              │
│  Aggregation:  hrt_yearly_summary (VIEW)     │
│                hrt_monthly_food (VIEW)       │
│                hrt_daily_food (VIEW)         │
│                                              │
│  Drill-down:   hrt_drilldown() (FUNCTION)    │
│                                              │
│  This is NOT just storage.                   │
│  The database CALCULATES and AGGREGATES.     │
└──────────────┬──────────────────────────────┘
               ↓
┌──────────────┴──────────────────────────────┐
│        MULTI-DIMENSIONAL VIEW                │
│                                              │
│  Level 1: LIFETIME  (Year 1 → Year 120)     │
│  Level 2: YEARLY    (Jan → Dec)              │
│  Level 3: MONTHLY   (Day 1 → Day 31)        │
│  Level 4: DAILY     (Hour 0 → Hour 23)       │
│                                              │
│  × Food | Exercise | Sleep | Medicine | Bio  │
│                                              │
│  = 4 time levels × 7 categories              │
│  = 28 possible views of the same data        │
└──────────────┬──────────────────────────────┘
               ↓
┌──────────────┴──────────────────────────────┐
│        FORECASTING + AI AGENTS               │
│                                              │
│  LSTM predicts future health (30d/1y/10y)    │
│  Digital Twin compares vs ideal lifestyle    │
│  Agents give personalized advice             │
│  Judgement Agent checks medical safety       │
└─────────────────────────────────────────────┘
```

---

## Why This is Special

| Feature | Normal Health Apps | Our HRT System |
|---------|-------------------|----------------|
| Data storage | Flat tables | Multi-dimensional cube |
| Time view | One chart at a time | Drill-down: year→month→day→hour |
| Categories | Separate apps for food/exercise | All health dimensions unified |
| Intelligence | Just shows data | AI predicts future health |
| Calculation | In the app (slow) | In the database (fast) |
| Scale | Single user | 100,000 users |
| Patent | None | No. 10-2025-0145274 |
