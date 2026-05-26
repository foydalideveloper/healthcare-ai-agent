# Complete Database Architecture
# Healthcare AI Agent - Triple-H Co., Ltd.
# NOT just HRT/LRT — the ENTIRE system

---

## Full Database: 6 Domains, 60+ Tables

### Domain 1: USER MANAGEMENT (Authentication + Profiles)
Tables needed for user accounts, login, settings:

- auth.users (Supabase Auth built-in) — email, password, OAuth
- user_profiles — extended profile (name, phone, photo, language, timezone)
- user_settings — app preferences (notifications on/off, units, privacy level)
- user_devices — registered devices (glasses ID, watch ID, phone ID)
- user_consents — GDPR/PIPA consent records (what data they agreed to share)
- user_subscriptions — plan type (free/premium/enterprise), billing

### Domain 2: HEALTH DATA (HRT — what we already have)
The 38 tables we built:

- users, user_demographic, user_biometric, user_diagnosis
- user_lifestyle, user_food_log, user_medication, user_activity_event
- user_health_level, user_multimodal, user_genomic
- std_population_category, std_diagnosis_norm, std_lifestyle_plan, std_disease_risk_weight
- simulation_result, twin_comparisons
- family_relations, family_history
- hrt_categories
- (LRT tables: agents, orders, contracts, etc.)

### Domain 3: AI AGENT SYSTEM (Orchestration + Skills)
Tables for managing 11 agents:

- agent_definitions — agent name, type, model, SOUL.md path, status
- agent_skills — skill name, agent_id, handler path, version
- agent_routing_rules — intent → agent mapping, priority, conditions
- agent_conversation_log — (already exists) chat messages
- agent_sessions — (already exists) active sessions
- agent_performance — response time, accuracy, user satisfaction per agent
- agent_models — LLM model registry (Qwen 7B v1, v2, Meditron 70B, etc.)
- agent_feedback — user thumbs up/down on agent responses

### Domain 4: ADMIN / OPERATOR (Oasis team management)
Tables for developers who manage the system:

- admin_users — operator accounts (developer, manager, support)
- admin_roles — role permissions (viewer, editor, admin, superadmin)
- admin_audit_log — who did what when (HIPAA compliance)
- admin_api_keys — third-party API keys (MFDS, USDA, Dexcom, etc.)
- system_config — global settings (model versions, feature flags, thresholds)
- system_health — server status, uptime, error rates
- model_registry — ML model versions, accuracy metrics, deploy status
- data_quality_checks — automated validation results

### Domain 5: COMMUNICATION (Notifications + Alerts)
Tables for user notifications and health alerts:

- notifications — push notifications, in-app messages
- health_alerts — HCI >= 81 emergency, anomaly detection alerts
- medication_reminders — scheduled medication alerts
- appointment_reminders — checkup/consultation reminders
- notification_templates — reusable message templates (Korean/English)
- notification_preferences — per-user channel preferences (push/email/kakao)

### Domain 6: EXPERT & EXTERNAL (Doctors + Hospitals)
Tables for expert marketplace and external data:

- experts — (already exists) doctor/nutritionist profiles
- consultations — (already exists) session records
- external_records — (already exists) FHIR hospital data
- expert_availability — weekly schedule slots
- expert_reviews — patient reviews/ratings
- insurance_providers — (future) insurance company info
- pharmacy_network — (future) pharmacy locations for prescription delivery

---

## Complete System Mermaid Diagram

```
graph TB
    subgraph Users["USER SIDE"]
        U1["Mobile App<br/>React Native"]
        U2["Web Dashboard<br/>Next.js"]
        U3["AI Glasses<br/>AIMB-G1"]
        U4["Smart Watch"]
    end

    subgraph Auth["DOMAIN 1: USER MANAGEMENT"]
        A1["auth.users<br/>Supabase Auth"]
        A2["user_profiles"]
        A3["user_settings"]
        A4["user_devices"]
        A5["user_consents"]
        A6["user_subscriptions"]
    end

    subgraph Health["DOMAIN 2: HEALTH DATA (HRT)"]
        H1["users"]
        H2["user_food_log"]
        H3["user_lifestyle"]
        H4["user_biometric"]
        H5["user_medication"]
        H6["user_diagnosis"]
        H7["user_health_level"]
        H8["user_genomic"]
        H9["user_activity_event"]
        H10["simulation_result"]
        H11["twin_comparisons"]
        H12["family_relations"]
        H13["family_history"]
        HR["hrt_drilldown()"]
        HV["SQL Views x6"]
    end

    subgraph Std["STANDARD REFERENCE"]
        S1["std_population_category"]
        S2["std_diagnosis_norm"]
        S3["std_lifestyle_plan"]
        S4["std_disease_risk_weight"]
        S5["hrt_categories"]
    end

    subgraph Agent["DOMAIN 3: AI AGENT SYSTEM"]
        AG1["agent_definitions<br/>11 agents"]
        AG2["agent_skills"]
        AG3["agent_routing_rules"]
        AG4["agent_conversation_log"]
        AG5["agent_sessions"]
        AG6["agent_performance"]
        AG7["agent_models<br/>LLM registry"]
        AG8["agent_feedback"]
    end

    subgraph Admin["DOMAIN 4: ADMIN/OPERATOR"]
        AD1["admin_users"]
        AD2["admin_roles"]
        AD3["admin_audit_log"]
        AD4["admin_api_keys"]
        AD5["system_config"]
        AD6["system_health"]
        AD7["model_registry"]
        AD8["data_quality_checks"]
    end

    subgraph Notif["DOMAIN 5: NOTIFICATIONS"]
        N1["notifications"]
        N2["health_alerts"]
        N3["medication_reminders"]
        N4["appointment_reminders"]
        N5["notification_templates"]
        N6["notification_preferences"]
    end

    subgraph Expert["DOMAIN 6: EXPERT/EXTERNAL"]
        E1["experts"]
        E2["consultations"]
        E3["external_records"]
        E4["expert_availability"]
        E5["expert_reviews"]
    end

    Users --> Auth
    Auth --> Health
    Health --> Agent
    Agent --> Notif
    Health --> Expert
    Admin --> Agent
    Admin --> Health
    Std --> Health
    Health --> HR
    HR --> HV
    HV --> U2

    style Auth fill:#E3F2FD,stroke:#1565C0
    style Health fill:#E8F5E9,stroke:#2E7D32
    style Agent fill:#FFF3E0,stroke:#E65100
    style Admin fill:#F3E5F5,stroke:#6A1B9A
    style Notif fill:#FCE4EC,stroke:#C62828
    style Expert fill:#FFFDE7,stroke:#F57F17
    style Std fill:#E0F2F1,stroke:#00695C
```
