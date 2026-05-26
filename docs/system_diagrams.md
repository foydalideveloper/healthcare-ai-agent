# Healthcare AI Agent - System Block Diagrams
# Copy each diagram code into: https://mermaid.live or ChatGPT or Claude

---

## Diagram 1: Patent System Block Diagram (도 3 style - matching boss's picture)

```mermaid
graph TB
    subgraph System30["Healthcare System (30)"]
        AI38["AI Agent<br/>(AI 에이전트)<br/>38"]
        
        AI38 --> DC31
        AI38 --> GAI41
        
        DC31["Health Data Collector<br/>(건강데이터 수집부)<br/>31"]
        GAI41["Generative AI Module<br/>(생성형AI 모듈)<br/>41"]
        FB39["Feedback Learning<br/>(피드백 학습부)<br/>39"]
        DL42["Deep Learning Module<br/>(딥러닝 모듈)<br/>42"]
        
        DC31 --> HRT32
        HRT32["HRT Generator<br/>(기록표 생성부)<br/>32"]
        
        HRT32 --> HS33
        HRT32 --> HP34
        HS33["Health Simulation<br/>(건강상태 모의부)<br/>33"]
        HP34["Health Prediction<br/>(건강상태 예측부)<br/>34"]
        
        HP34 --> HCI35
        HP34 --> MP36
        HCI35["Healthcare Index Calculator<br/>(헬스지수 산출부)<br/>35"]
        MP36["Management Plan Extractor<br/>(관리방안 추출부)<br/>36"]
        
        HCI35 --> TW37
        MP36 --> TW37
        TW37["Twin Model Comparator<br/>(트윈모델 비교부)<br/>37"]
        
        SM43["Standard Plan Module<br/>(표준방안 모듈)<br/>43"]
        SM43 --> MP36
        SM43 --> HS33
        
        DL42 --> HP34
        FB39 --> DL42
        DC31 -.-> FB39
        GAI41 -.-> HRT32
    end

    style AI38 fill:#4CAF50,color:#fff,stroke:#2E7D32
    style DC31 fill:#E3F2FD,stroke:#1565C0
    style HRT32 fill:#E3F2FD,stroke:#1565C0
    style HP34 fill:#E3F2FD,stroke:#1565C0
    style HS33 fill:#E3F2FD,stroke:#1565C0
    style HCI35 fill:#E3F2FD,stroke:#1565C0
    style MP36 fill:#E3F2FD,stroke:#1565C0
    style TW37 fill:#E3F2FD,stroke:#1565C0
    style GAI41 fill:#FFF3E0,stroke:#E65100
    style DL42 fill:#FFF3E0,stroke:#E65100
    style FB39 fill:#FFF3E0,stroke:#E65100
    style SM43 fill:#E8F5E9,stroke:#2E7D32
```

---

## Diagram 2: Complete 7-Layer System Architecture

```mermaid
graph TB
    subgraph L1["Layer 1: Data Collection"]
        G["AI Glasses<br/>AIMB-G1<br/>8MP Camera"]
        W["Smart Watch<br/>HR, SpO2<br/>Steps"]
        C["CGM<br/>Glucose<br/>Dexcom/Libre"]
        P["Phone Camera<br/>Food Photos"]
        V["Voice Input<br/>Whisper STT"]
    end

    subgraph L2["Layer 2: AI Processing"]
        Y["YOLOv8n<br/>80 Objects<br/>cup/bowl/food"]
        WH["Whisper Base<br/>Korean+English<br/>Speech-to-Text"]
        EF["EfficientNetV2-S<br/>150 Korean Foods<br/>TRAINING"]
        MF["MFDS Lookup<br/>275,856 Foods"]
        LLM["LLM Extraction<br/>Gemini Flash<br/>PENDING"]
    end

    subgraph L3["Layer 3: Supabase Database"]
        T["38 Tables<br/>user_food_log<br/>user_lifestyle<br/>user_biometric<br/>user_medication"]
        VW["6 SQL Views<br/>hrt_yearly_summary<br/>hrt_monthly_food<br/>hrt_daily_food"]
        FN["hrt_drilldown()<br/>Database Function<br/>4-Level Query"]
        IX["42 Indexes<br/>45 RLS Policies"]
    end

    subgraph L4["Layer 4: HRT Drill-Down"]
        D1["Level 1<br/>Years<br/>Birth→120"]
        D2["Level 2<br/>Months<br/>1월→12월"]
        D3["Level 3<br/>Days<br/>1→31"]
        D4["Level 4<br/>Hours<br/>00:00→23:00"]
    end

    subgraph L5["Layer 5: Forecasting"]
        LSTM["LSTM-Transformer<br/>65-dim Input"]
        MIRA["MIRA<br/>Microsoft 455M"]
        TFM["TimesFM<br/>Google 200M"]
        CB["Chronos-Bolt<br/>Amazon 200M"]
        TFT["TFT<br/>Interpretable"]
    end

    subgraph L6["Layer 6: AI Agents (11)"]
        OA["Orchestration<br/>Agent"]
        JA["Judgement<br/>Agent"]
        A1["Data<br/>Collection"]
        A2["Lifestyle<br/>& Gene"]
        A3["Analytics<br/>HCI/DRI"]
        A4["Expert<br/>Doctor"]
        A5["External<br/>DB/FHIR"]
        A6["Order"]
        A7["Simulation"]
        A8["Glasses"]
        A9["Community"]
        OA --> JA
        JA --> A1
        JA --> A2
        JA --> A3
        JA --> A4
    end

    subgraph L7["Layer 7: Frontend"]
        HD["HRT Dashboard<br/>Next.js"]
        MA["Mobile App<br/>React Native"]
        GH["Glasses HUD"]
        WC["Web Chat"]
    end

    L1 --> L2
    L2 --> L3
    L3 --> L4
    L3 --> L5
    L5 --> L6
    L4 --> L7
    L6 --> L7

    style L1 fill:#E8F5E9,stroke:#2E7D32
    style L2 fill:#E3F2FD,stroke:#1565C0
    style L3 fill:#FFF3E0,stroke:#E65100
    style L4 fill:#FCE4EC,stroke:#C62828
    style L5 fill:#F3E5F5,stroke:#6A1B9A
    style L6 fill:#E0F2F1,stroke:#00695C
    style L7 fill:#FFFDE7,stroke:#F57F17
```

---

## Diagram 3: Database Table Relationships (ERD)

```mermaid
erDiagram
    users ||--o{ user_food_log : "has"
    users ||--o{ user_lifestyle : "has"
    users ||--o{ user_biometric : "has"
    users ||--o{ user_diagnosis : "has"
    users ||--o{ user_medication : "has"
    users ||--o{ user_health_level : "has"
    users ||--o{ user_activity_event : "has"
    users ||--o{ user_genomic : "has"
    users ||--o{ user_multimodal : "has"
    users ||--o{ agent_conversation_log : "has"
    users ||--o{ simulation_result : "has"
    users ||--o{ consultations : "has"
    users ||--o{ external_records : "has"
    users ||--o{ family_relations : "has"
    users ||--o{ family_history : "has"
    users ||--o{ twin_comparisons : "has"

    experts ||--o{ consultations : "provides"
    simulation_result ||--o{ twin_comparisons : "compared_in"
    std_population_category ||--o{ std_diagnosis_norm : "defines"
    std_population_category ||--o{ std_lifestyle_plan : "defines"
    std_population_category ||--o{ std_disease_risk_weight : "defines"
    hrt_categories ||--o{ hrt_categories : "parent"

    users {
        bigint user_id PK
        uuid user_token
        varchar age_group
        char gender
        int birth_year
        boolean is_active
    }
    user_food_log {
        bigint food_id PK
        bigint user_id FK
        timestamptz consumed_at
        varchar food_name
        jsonb nutrients_json
        float confidence
    }
    user_lifestyle {
        bigint ls_id PK
        bigint user_id FK
        date recorded_date
        int total_calories
        int exercise_min
        float sleep_hours
    }
    user_biometric {
        bigint bio_id PK
        bigint user_id FK
        timestamptz measured_at
        int heart_rate
        float spo2
        float glucose_mgdl
    }
    user_medication {
        bigint med_id PK
        bigint user_id FK
        varchar drug_code
        varchar drug_name
        numeric dose
        boolean interaction_flag
    }
    user_health_level {
        bigint hl_id PK
        bigint user_id FK
        float healthcare_index
        float dri
        jsonb disease_risk_json
    }
```

---

## Diagram 4: Data Flow (Glasses to Dashboard)

```mermaid
flowchart LR
    A["🕶️ AI Glasses<br/>AIMB-G1"] -->|photo/video| B["📱 iPhone<br/>Cyan App"]
    B -->|auto-sync| C["☁️ OneDrive"]
    C -->|auto-download| D["💻 PC"]
    D --> E["🔍 YOLOv8<br/>Object Detection"]
    D --> F["🎤 Whisper<br/>Speech-to-Text"]
    E -->|"cup detected"| G["📊 Event Processor"]
    F -->|"I ate 삼겹살"| G
    G -->|food| H["🗄️ user_food_log"]
    G -->|exercise| I["🗄️ user_lifestyle"]
    G -->|medicine| J["🗄️ user_medication"]
    H --> K["📈 SQL Views<br/>Aggregation"]
    I --> K
    J --> K
    K --> L["⚙️ hrt_drilldown()<br/>Function"]
    L --> M["🔌 FastAPI<br/>Endpoints"]
    M --> N["📊 Next.js<br/>HRT Dashboard"]

    style A fill:#4CAF50,color:#fff
    style H fill:#FF9800,color:#fff
    style I fill:#FF9800,color:#fff
    style J fill:#FF9800,color:#fff
    style K fill:#2196F3,color:#fff
    style L fill:#2196F3,color:#fff
    style N fill:#9C27B0,color:#fff
```

---

## Diagram 5: HRT Drill-Down Levels

```mermaid
flowchart TB
    L1["Level 1: LIFETIME<br/>━━━━━━━━━━━━━━━━━━<br/>X: Years (1990-2026)<br/>Y: Food|Exercise|Sleep|Med|Bio<br/>Cell: '1,095 meals' or '5,475 min'"]
    L1 -->|"click [2026] + [Food]"| L2
    
    L2["Level 2: YEARLY<br/>━━━━━━━━━━━━━━━━━━<br/>X: Months (Jan-Dec)<br/>Y: Food subcategories<br/>Cell: '1,800 kcal/day avg (90 meals)'"]
    L2 -->|"click [April]"| L3
    
    L3["Level 3: MONTHLY<br/>━━━━━━━━━━━━━━━━━━<br/>X: Days (1-30)<br/>Y: Specific foods<br/>Cell: '1,935 kcal (3 meals)'"]
    L3 -->|"click [Day 17]"| L4
    
    L4["Level 4: DAILY<br/>━━━━━━━━━━━━━━━━━━<br/>X: Hours (00:00-23:00)<br/>Y: Nutrients per meal<br/>Cell: 'Bibimbap 550kcal, 18g protein'"]

    style L1 fill:#FFCDD2,stroke:#C62828,color:#000
    style L2 fill:#EF9A9A,stroke:#C62828,color:#000
    style L3 fill:#E57373,stroke:#C62828,color:#fff
    style L4 fill:#F44336,stroke:#C62828,color:#fff
```

---

## Diagram 6: Multi-Agent Architecture

```mermaid
flowchart TB
    User["👤 User Request"]
    User --> GW["OpenClaw Gateway<br/>ws://127.0.0.1:18789"]
    
    GW --> OA["🎯 Orchestration Agent<br/>━━━━━━━━━━━━━━━<br/>Intent Classification<br/>8 Categories<br/>Emergency Bypass"]
    
    OA --> JA["🛡️ Judgement Agent<br/>━━━━━━━━━━━━━━━<br/>Level 0: Auto (general info)<br/>Level 1: Review (diet/exercise)<br/>Level 2: Confirm (medication)<br/>Level 3: Block (diagnosis)"]
    
    JA --> A1["📡 Agent 1<br/>Data Collection<br/>Wearable sync<br/>YOLOv11, Whisper"]
    JA --> A2["🥗 Agent 2<br/>Lifestyle & Gene<br/>Food, Exercise<br/>Sleep, DNA"]
    JA --> A3["📊 Agent 3<br/>Analytics<br/>HCI/DRI Calc<br/>Disease Predict"]
    JA --> A4["👨‍⚕️ Agent 4<br/>Expert<br/>Doctor Match<br/>Consultation"]
    JA --> A5["🏥 Agent 5<br/>External DB<br/>FHIR, NHIS<br/>Family Network"]
    JA --> A6["📦 Agent 6<br/>Order<br/>Medication<br/>Supplements"]
    JA --> A7["🔮 Agent 7<br/>Simulation<br/>LSTM Predict<br/>Digital Twin"]
    JA --> A8["🕶️ Agent 8<br/>Glasses<br/>Event Process<br/>Food Correction"]
    JA --> A9["👥 Agent 9<br/>Community<br/>Health Trends<br/>Statistics"]
    
    A3 --> Response["💬 Natural Language Response"]
    
    style OA fill:#FF9800,color:#fff
    style JA fill:#F44336,color:#fff
    style A1 fill:#4CAF50,color:#fff
    style A2 fill:#4CAF50,color:#fff
    style A3 fill:#4CAF50,color:#fff
    style A4 fill:#4CAF50,color:#fff
    style A5 fill:#4CAF50,color:#fff
    style A6 fill:#4CAF50,color:#fff
    style A7 fill:#4CAF50,color:#fff
    style A8 fill:#4CAF50,color:#fff
    style A9 fill:#4CAF50,color:#fff
```

---

## Diagram 7: Forecasting Pipeline

```mermaid
flowchart LR
    subgraph Input["HRT Input Data (65 dimensions)"]
        D1["Sociodemographic<br/>age, gender<br/>4 dims"]
        D2["Lifestyle<br/>calories, exercise<br/>sleep, alcohol<br/>7 dims"]
        D3["Diagnostic<br/>BMI, BP, glucose<br/>cholesterol, etc<br/>44 dims"]
        D4["Glasses-Derived<br/>meal count, hydration<br/>portion confidence<br/>10 dims"]
    end

    Input --> Ensemble

    subgraph Ensemble["5-Model Ensemble"]
        M1["LSTM-Transformer<br/>Custom"]
        M2["MIRA<br/>Microsoft 455M"]
        M3["TimesFM<br/>Google 200M"]
        M4["Chronos-Bolt<br/>Amazon 200M"]
        M5["TFT<br/>Interpretable"]
    end

    Ensemble --> Output

    subgraph Output["Predictions"]
        P1["30 Days<br/>BMI: 24.1→24.3"]
        P2["1 Year<br/>Glucose: 95→102"]
        P3["10 Years<br/>Diabetes: 5%→15%"]
    end

    Output --> Twin["Digital Twin<br/>Compare vs<br/>Role Model"]
    Twin --> HCI["HCI Score<br/>T = a(X-X0) + b(Y-Y0)<br/>+ c(Z-Z0) - d(E-E0)<br/>+ e(N-N0) + f(M)"]

    style Input fill:#E3F2FD,stroke:#1565C0
    style Ensemble fill:#FFF3E0,stroke:#E65100
    style Output fill:#FCE4EC,stroke:#C62828
    style Twin fill:#E8F5E9,stroke:#2E7D32
    style HCI fill:#4CAF50,color:#fff
```

---

## Diagram 8: LLM Training Pipeline

```mermaid
flowchart TB
    subgraph Stage1["Stage 1: SFT (Supervised Fine-Tuning)"]
        D1["AI Hub 17K QA<br/>Medical Corpus 52K<br/>Doctor Dialogues 50K"]
        D1 --> Q1["Qwen 2.5 7B<br/>4-bit QLoRA<br/>RTX 4070 SUPER<br/>~8 hours"]
        D1 --> L1["Llama 3.1 8B<br/>4-bit QLoRA<br/>RTX 4070 SUPER<br/>~8 hours"]
    end

    subgraph Stage2["Stage 2: DPO (Preference Alignment)"]
        D2["10,000 Preference Pairs<br/>Doctor A vs Doctor B<br/>Which answer is better?"]
        D2 --> Q2["DPO Training<br/>TRL DPOTrainer<br/>~4 hours each"]
    end

    subgraph Stage3["Stage 3: RAG (Retrieval)"]
        D3["User asks health question"]
        D3 --> R1["Retrieve user's HRT data<br/>from Supabase<br/>via pgvector search"]
        R1 --> R2["Feed HRT context<br/>to fine-tuned LLM"]
        R2 --> R3["Personalized answer<br/>based on user's<br/>actual health data"]
    end

    Stage1 --> Stage2
    Stage2 --> Stage3

    style Stage1 fill:#E8F5E9,stroke:#2E7D32
    style Stage2 fill:#FFF3E0,stroke:#E65100
    style Stage3 fill:#E3F2FD,stroke:#1565C0
```

---

# How to render these diagrams:

## Option 1: Mermaid Live Editor (FREE, instant)
1. Go to https://mermaid.live
2. Paste any diagram code above
3. See the visual diagram instantly
4. Click "Download PNG" to save as image

## Option 2: ChatGPT / Claude
1. Paste the Mermaid code
2. Ask: "Render this Mermaid diagram as an image"

## Option 3: VS Code Extension
1. Install "Mermaid Preview" extension
2. Open this .md file
3. Preview shows all diagrams

## Option 4: GitHub
1. Push this file to GitHub
2. GitHub automatically renders Mermaid diagrams
