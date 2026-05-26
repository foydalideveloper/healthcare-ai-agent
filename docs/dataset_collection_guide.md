# Healthcare AI Agent - Dataset Collection Guide
## Triple-H Co., Ltd. | April 2026

---

## Overview

We need 3 categories of data:
1. **LSTM-Transformer Training Data** — Health checkup time-series (NHIS, KNHANES)
2. **LLM Fine-Tuning Data** — Korean medical dialogues, QA pairs (AI Hub)
3. **Nutrition Database** — Korean food nutrition info (MFDS, KFCT)

---

## 1. NHIS Sample Cohort (국민건강보험 표본코호트DB)

### What It Contains
- **1 million+ Koreans** tracked over 10+ years
- Health checkups: BMI, BP, glucose, cholesterol, liver enzymes
- Diagnosis history (ICD codes)
- Prescription/medication records
- Demographics: age, gender, income, disability

### Why We Need It
- **Primary training data for LSTM-Transformer model**
- Time-series health trajectories (exactly what our simulation predicts)
- Maps directly to `user_diagnosis` + `user_demographic` tables

### How to Apply
1. Go to: https://nhiss.nhis.or.kr/
2. Register an account (requires 공인인증서 or 간편인증)
3. Navigate: 데이터신청 > 신청하기
4. Select: **표본연구DB (Sample Cohort DB)**
5. Submit research plan describing your use case
6. **Approval time: 2-4 weeks**
7. Data access: via 가상화분석센터 (virtual analysis center) or data download

### Available Cohorts
| Cohort | Period | Size | Key Variables |
|--------|--------|------|---------------|
| 표본코호트DB 2.0 | 2002-2019 | 1M people | Checkups, diagnoses, prescriptions |
| 건강검진코호트DB | 2002-2019 | 514K people | Focus on health checkup results |
| 노인코호트DB | 2002-2019 | 558K elderly | 60+ age group focus |

### Data Format
- SAS (.sas7bdat) or CSV
- ~800 variables per record
- Key columns: 개인식별번호, 성별, 연령, BMI, 수축기혈압, 공복혈당, 총콜레스테롤, etc.

---

## 2. KNHANES Raw Data (국민건강영양조사 원시자료)

### What It Contains
- **~10,000 participants/year** surveyed since 1998
- Health examination: blood tests, body composition, BP
- Nutrition survey: 24-hour dietary recall, food frequency
- Health behavior: exercise, smoking, alcohol, sleep
- ~800 variables per survey year

### Why We Need It
- **Lifestyle + nutrition data** for training
- Maps to `user_lifestyle` table (diet, exercise, sleep)
- Validates our Standard HRT normal ranges
- Free and immediately downloadable

### How to Download (FREE - No approval needed)
1. Go to: https://knhanes.kdca.go.kr/knhanes
2. Click: 원시자료 다운로드
3. Select year(s): recommend 2019-2024
4. Download: SAS/SPSS/CSV format
5. Also download: 이용지침서 (user guide PDF)

### Key Files Per Year
| File | Content | Our Use |
|------|---------|---------|
| HN_ALL.csv | Health examination data | BMI, BP, glucose, cholesterol → `user_diagnosis` |
| HN_NUT.csv | Nutrition survey (24hr recall) | Calories, macros, food items → `user_lifestyle` |
| HN_PHY.csv | Physical activity data | Exercise min, type, intensity → `user_lifestyle` |
| HN_SM.csv | Smoking/alcohol data | Lifestyle risk factors |
| HN_SL.csv | Sleep data | Sleep hours, quality → `user_lifestyle` |

### Data Format
- CSV (UTF-8 or EUC-KR encoding)
- SPSS (.sav) or SAS (.sas7bdat)
- Codebook provided in PDF

---

## 3. AI Hub Medical Datasets (AI 허브 의료 데이터)

### Available Datasets

#### 3a. 필수의료 의학지식 질의응답 데이터 (2024)
- **15,000 QA pairs** from Big 5 hospitals (서울대, 삼성서울, 서울성모, 세브란스, 보라매)
- **100M tokens** of Korean/English medical corpus
- **Our use**: LLM SFT training data (direct QA pairs)
- URL: https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71875
- **Access**: 안심존 (Secure Zone) — apply online

#### 3b. 의료분야 음성 데이터 (2022)
- Patient consultation voice recordings
- Labeled by department, consultation type
- **Our use**: MedASR training, health conversation understanding
- URL: https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=566
- **Access**: 안심존

#### 3c. 응급실 임상 대화 데이터
- ER doctor-patient dialogues
- 4 stages: triage, initial exam, testing, results/discharge
- **Our use**: Emergency agent training, medical dialogue patterns
- URL: https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71433
- **Access**: 안심존

#### 3d. 고객 상담 음성 데이터 — 의료/보건 클래스 (2022)
- 3,300 hours customer consultation voice
- Includes 의료/보건 (medical/health) category
- Emotion/intent tagging + summaries
- **Our use**: Health consultation intent classification
- URL: https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=543

### How to Apply for AI Hub 안심존
1. Go to: https://aihub.or.kr
2. Register account
3. Navigate to dataset page
4. Click: 안심존 이용신청
5. Submit: IRB approval (if required), research plan, employment verification
6. **Approval time: 1-3 weeks**

---

## 4. Korean Food Nutrition Database (식품영양성분DB)

### 4a. MFDS Food Safety Korea (식품의약품안전처)
- **100,000+ food items** with nutritional data
- Includes Korean traditional foods
- REST API available

#### Download
- Web: https://various.foodsafetykorea.go.kr/nutrient/
- DB Download: https://various.foodsafetykorea.go.kr/nutrient/general/down/list.do
- API: https://www.data.go.kr/data/15127578/openapi.do
- Format: Excel/CSV download or REST API (JSON)
- **Free, no approval needed**

### 4b. 공공데이터포털 — 전국통합식품영양성분정보
- Standardized nationwide food nutrition data
- API with JSON responses
- URL: https://www.data.go.kr/data/15100070/standard.do
- **Free, requires API key (instant)**

### 4c. Korean Food Composition Table (KFCT) — 한국영양학회
- ~3,000 foods with up to 140 nutrients each
- Most authoritative Korean nutrition reference
- URL: https://www.kns.or.kr/can6.0/FoodDB.asp
- Format: Web-based lookup (may need scraping)

### 4d. USDA FoodData Central
- 300,000+ international foods
- Free REST API
- URL: https://fdc.nal.usda.gov/
- API: https://api.nal.usda.gov/fdc/v1/ (free API key)
- **Our use**: Fallback for non-Korean foods

---

## 5. Priority and Timeline

| Priority | Dataset | Action | Timeline | Blocker? |
|----------|---------|--------|----------|----------|
| **P0** | KNHANES raw data | Download NOW (free) | Today | No |
| **P0** | MFDS Food Nutrition DB | Download NOW (free) | Today | No |
| **P0** | USDA FoodData Central | Get API key NOW (free) | Today | No |
| **P1** | NHIS Sample Cohort | Apply today, wait for approval | 2-4 weeks | YES — approval required |
| **P1** | AI Hub 의학지식 QA | Apply for 안심존 access | 1-3 weeks | YES — 안심존 approval |
| **P2** | AI Hub 응급실 대화 | Apply alongside P1 | 1-3 weeks | YES — 안심존 approval |
| **P2** | AI Hub 의료 음성 | Apply alongside P1 | 1-3 weeks | YES — 안심존 approval |
| **P3** | KFCT (한국영양학회) | Web scraping or manual | 1-2 weeks | Limited API |

### Immediate Actions (Do Today)
1. ✅ Download KNHANES 2019-2024 from knhanes.kdca.go.kr
2. ✅ Download MFDS food nutrition DB from foodsafetykorea.go.kr
3. ✅ Get USDA API key from fdc.nal.usda.gov
4. ⏳ Apply for NHIS cohort at nhiss.nhis.or.kr
5. ⏳ Apply for AI Hub 안심존 at aihub.or.kr

---

## 6. How Each Dataset Maps to Our System

| Dataset | Training Target | DB Table(s) | Model |
|---------|----------------|-------------|-------|
| NHIS Cohort | Health trajectory prediction | user_diagnosis, user_demographic | LSTM-Transformer |
| KNHANES Health | Diagnostic data patterns | user_diagnosis, std_diagnosis_norm | LSTM-Transformer |
| KNHANES Nutrition | Lifestyle patterns | user_lifestyle | LSTM-Transformer |
| AI Hub 의학 QA | Medical question answering | (training data, not DB) | Qwen/Llama SFT |
| AI Hub 응급실 대화 | Emergency dialogue patterns | (training data, not DB) | Qwen/Llama SFT |
| MFDS Food DB | Food recognition → nutrition | std_lifestyle_plan, user_activity_event | Food AI pipeline |
| USDA FoodData | International food lookup | (API integration) | Food AI pipeline |
