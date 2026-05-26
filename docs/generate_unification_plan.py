"""
Generate HRT + LRT Unified Database Plan as .docx
Triple-H Co., Ltd. | April 15, 2026 | FINAL v2.0
Updated: BIGINT PK + UUID token architecture
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

# Styles
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.15

for level in range(1, 4):
    hs = doc.styles[f'Heading {level}']
    hs.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)
    hs.font.name = 'Calibri'

doc.styles['Heading 1'].font.size = Pt(20)
doc.styles['Heading 2'].font.size = Pt(16)
doc.styles['Heading 3'].font.size = Pt(13)


def add_table(headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = str(val)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
    return table


def bullet(text, level=0):
    p = doc.add_paragraph(text, style='List Bullet')
    p.paragraph_format.left_indent = Cm(1.27 + level * 1.27)
    return p


def code_block(code):
    p = doc.add_paragraph()
    run = p.add_run(code)
    run.font.name = 'Consolas'
    run.font.size = Pt(9)
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), 'F5F5F5')
    shading.set(qn('w:val'), 'clear')
    p.paragraph_format.element.get_or_add_pPr().append(shading)


# ═══════════════════════════════════════════════════════════
# COVER PAGE
# ═══════════════════════════════════════════════════════════
for _ in range(5):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('HRT + LRT\nUnified Database Plan')
run.font.size = Pt(32)
run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)
run.bold = True

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Health Record Table + Lifetime Record Table\nComplete Technical Specification')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x42, 0x42, 0x42)

doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | April 15, 2026')
run.font.size = Pt(14)
run.bold = True
run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Version 2.0 \u2014 Final')
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0xC6, 0x28, 0x28)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 1. WHY WE MUST UNIFY
# ═══════════════════════════════════════════════════════════
doc.add_heading('1. Why We Must Unify', level=1)

doc.add_paragraph(
    'Triple-H currently operates two separate database systems tracking the same user: '
    'HRT (Health Record Table) for healthcare data, and LRT (Lifetime Record Table) for '
    'life events and commerce. These systems are on separate Supabase projects with no '
    'connection between them.'
)

doc.add_heading('The Problem', level=3)
bullet('Health affects purchases. A user with high blood pressure should receive low-sodium food recommendations from the LRT Pre-Order system \u2014 not random products.')
bullet('Life events affect health. Marriage, job changes, or retirement (LRT events) cause stress that directly impacts health metrics (HRT simulation should factor this in).')
bullet('Same AI glasses pipeline. Both systems plan to use AI glasses for data collection. Building two separate pipelines is wasteful and doubles development cost.')
bullet('Same user, one experience. Users should not have two apps, two logins, two AI agents. They need ONE unified system that understands their complete life.')
bullet('Patent alignment. The healthcare patent (10-2025-0145274) describes "1st/2nd/3rd degree collaborative agents" and "multimodal data collection" \u2014 both already implemented better in the LRT agent system.')

doc.add_heading('The Goal', level=3)
doc.add_paragraph(
    'One unified database where HRT handles health prediction (BMI, glucose, cholesterol \u2192 '
    '10-year trajectory), LRT handles life prediction (purchases, events, behavioral patterns), '
    'and both share the same user, same glasses data, same AI agents. The health simulation '
    'informs purchase recommendations, and life events inform health predictions.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 2. CURRENT STATE
# ═══════════════════════════════════════════════════════════
doc.add_heading('2. Current State', level=1)

doc.add_heading('2.1 HRT Database (14 tables \u2014 healthcare-ai-agent project)', level=2)
add_table(
    ['Table', 'Rows', 'Purpose'],
    [
        ['users', '8', 'User profiles (UUID PK)'],
        ['user_demographic', '0', 'Sociodemographic time-series'],
        ['user_biometric', '5,042', 'Heart rate, glucose, SpO2 from wearables'],
        ['user_diagnosis', '0', 'Medical lab data (BMI, BP, cholesterol)'],
        ['user_lifestyle', '1', 'Daily diet, exercise, sleep'],
        ['user_activity_event', '193', 'AI glasses events (meals, drinks, medication)'],
        ['user_health_level', '1', 'Healthcare Index, Disease Risk Index'],
        ['user_multimodal', '0', 'Voice/image/video with pgvector embeddings'],
        ['agent_conversation_log', '0', 'AI agent chat history'],
        ['simulation_result', '0', 'LSTM health predictions'],
        ['std_population_category', '26', 'Population segments for health benchmarking'],
        ['std_diagnosis_norm', '298', 'Normal/warning/critical health ranges'],
        ['std_lifestyle_plan', '56', 'Role-model lifestyle plans'],
        ['std_disease_risk_weight', '44', 'Disease risk contribution weights'],
    ])

doc.add_paragraph()

doc.add_heading('2.2 LRT Database (17 tables \u2014 LRT project)', level=2)
add_table(
    ['Table', 'Rows', 'Purpose'],
    [
        ['users', '0', 'User profiles (BIGINT PK, MBTI, occupation)'],
        ['demographic_clusters', '0', 'Population segments for life prediction'],
        ['standard_lrt_header', '0', 'Standard LRT templates per cluster'],
        ['standard_lrt_events', '0', 'Expected life events (marriage, birth, retirement)'],
        ['standard_lrt_activities', '0', 'Expected behaviors per event (spending, needs)'],
        ['standard_lrt_products', '0', 'Product recommendations per activity'],
        ['personal_lrt_header', '0', 'Per-user personalized LRT'],
        ['personal_lrt_events', '0', 'Individual predicted life events'],
        ['personal_lrt_activities', '0', 'Individual behaviors with predicted/actual spend'],
        ['agents', '0', 'AI agents (User, Supplier, Holder, Producer)'],
        ['agent_sessions', '0', 'Agent conversation sessions'],
        ['agent_relationship_permissions', '0', '1st/2nd/3rd degree sharing permissions'],
        ['contracts', '0', 'Auto-negotiated purchase contracts'],
        ['orders', '0', 'Order execution with delivery'],
        ['history_record_table', '0', 'Blockchain-style audit trail'],
        ['multimodal_inputs', '0', 'Multimodal data with TTL'],
        ['lrt_simulations', '0', 'Monte Carlo/Particle Filter simulations'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 3. CONFLICTS AND SOLUTIONS
# ═══════════════════════════════════════════════════════════
doc.add_heading('3. Conflicts and Solutions', level=1)

# Conflict 1
doc.add_heading('3.1 User ID Type (CRITICAL)', level=2)
add_table(
    ['', 'HRT (Current)', 'LRT (Current)', 'Unified (Decision)'],
    [
        ['Primary Key', 'UUID', 'BIGINT', 'BIGINT \u2014 best performance for JOINs'],
        ['External Token', 'user_hash (SHA-256)', 'user_token (UUID)', 'user_token (UUID) \u2014 secure, API-safe'],
        ['Auth Link', 'None', 'auth_user_id (UUID)', 'auth_user_id (UUID) \u2014 Supabase Auth'],
    ])

doc.add_paragraph()
doc.add_paragraph(
    'Decision: Use BIGINT as primary key for maximum database performance (faster JOINs, '
    'smaller indexes, 8 bytes vs 16 bytes per FK). Use UUID user_token as the external-facing '
    'identifier for APIs, mobile apps, and glasses communication. This is the "best of both worlds" '
    'approach \u2014 fast internally, secure externally.'
)

bullet('BIGINT user_id: Used in all database JOINs, foreign keys, indexes \u2014 never exposed to users or APIs')
bullet('UUID user_token: Used in all API responses, mobile app, glasses events, URLs \u2014 cannot be guessed or enumerated')
bullet('UUID auth_user_id: Links to Supabase Auth for login, RLS, and session management')

doc.add_paragraph()
doc.add_paragraph(
    'Action: Both HRT and LRT adopt BIGINT PK. HRT\'s existing UUID-based data (8 users, 5,042 biometric, '
    '193 events) will be migrated to BIGINT with UUID user_token preserved for API compatibility.'
)

# Conflict 2
doc.add_heading('3.2 Gender Code', level=2)
add_table(
    ['', 'HRT', 'LRT', 'Unified'],
    [
        ['Type', "CHAR(1) CHECK (M, F, O)", "ENUM (M, F, X)", "CHAR(1) CHECK (M, F, X)"],
        ['Non-binary code', "'O' (Other)", "'X' (Other)", "'X' \u2014 ICAO international standard"],
    ])

doc.add_paragraph(
    'Decision: Use CHAR(1) with values M, F, X. "X" is the ICAO passport standard for non-binary. '
    'CHAR(1) is more flexible than PostgreSQL ENUM (easier to add new values without migration). '
    'All existing HRT data with gender=\'O\' will be updated to \'X\'.'
)

# Conflict 3
doc.add_heading('3.3 Multimodal Data (Two Tables \u2192 One)', level=2)
add_table(
    ['Feature', 'HRT user_multimodal', 'LRT multimodal_inputs', 'Unified multimodal_inputs'],
    [
        ['Input types', 'voice, image, video, sensor', 'IMAGE, AUDIO, TEXT, SENSOR, BIO_SIGNAL', 'IMAGE, AUDIO, TEXT, SENSOR, BIO_SIGNAL, VIDEO'],
        ['Embeddings', 'vector(1536) via pgvector', 'feature_vector JSONB', 'vector(1536) + feature_vector JSONB (both)'],
        ['Emotion', 'emotion_state VARCHAR', 'emotion_tags JSONB', 'emotion_tags JSONB (more flexible)'],
        ['Storage ref', 'storage_ref VARCHAR', 'raw_data_ref TEXT', 'raw_data_ref TEXT'],
        ['Health link', 'None', 'health_metrics JSONB', 'health_metrics JSONB (connects health + multimodal)'],
        ['Auto-delete', 'None', 'ttl_delete_at TIMESTAMPTZ', 'ttl_delete_at (HIPAA compliance)'],
        ['Context', 'context_place, context_weather', 'None', 'context_place, context_weather (added)'],
    ])

doc.add_paragraph(
    'Decision: Merge into one multimodal_inputs table, keeping the best features from both. '
    'LRT\'s structure is the base (broader input types, JSONB flexibility, TTL auto-delete), '
    'with HRT\'s pgvector embeddings and context fields added.'
)

# Conflict 4
doc.add_heading('3.4 Simulation Engines (Keep Both)', level=2)
add_table(
    ['', 'HRT health_simulations', 'LRT lrt_simulations'],
    [
        ['Algorithm', 'LSTM-Transformer hybrid', 'Monte Carlo / Particle Filter / Scenario Tree'],
        ['Predicts', 'Health trajectory (BMI, glucose, BP)', 'Life events (marriage, purchases, career)'],
        ['Scenarios', 'current / twin / optimistic', 'ANOMALY / PEER_UPDATE / GROUP_SHIFT'],
        ['Output', 'Time-series diagnostic predictions', 'Probability distributions of events'],
    ])

doc.add_paragraph(
    'Decision: Keep BOTH simulation tables \u2014 they serve fundamentally different purposes. '
    'Health simulations predict medical outcomes; LRT simulations predict life events and purchase timing. '
    'They connect bidirectionally: health results inform LRT (e.g., "user needs blood pressure monitor"), '
    'and LRT events inform health (e.g., "marriage stress increases BP risk").'
)

# Conflict 5
doc.add_heading('3.5 Agent System', level=2)
add_table(
    ['', 'HRT', 'LRT', 'Unified'],
    [
        ['Agent definition', 'None (only chat log)', 'agents table with roles, soul_config, model_id', 'LRT agents table'],
        ['Session mgmt', 'None', 'agent_sessions with state tracking', 'LRT agent_sessions'],
        ['Permissions', 'RLS only', 'agent_relationship_permissions (1st/2nd/3rd degree, share levels)', 'LRT permissions system'],
        ['Chat history', 'agent_conversation_log', 'Implicit in sessions', 'HRT conversation_log linked to LRT sessions'],
        ['Audit trail', 'None', 'history_record_table (bi-temporal, blockchain hash)', 'LRT audit trail'],
    ])

doc.add_paragraph(
    'Decision: Use LRT\'s agent system as the base \u2014 it is architecturally more mature. '
    'HRT\'s agent_conversation_log is kept and linked to agent_sessions as a child table. '
    'The agent system now manages both health agents (HealthCore, Nutrition, Exercise, Medical) '
    'and commerce agents (Supplier, Holder, Producer) under one framework.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 4. UNIFIED DATABASE SCHEMA
# ═══════════════════════════════════════════════════════════
doc.add_heading('4. Unified Database Schema', level=1)

doc.add_heading('4.1 Architecture: One Project, Three Domains', level=2)
doc.add_paragraph(
    'The unified database organizes 26 tables into three domains within a single Supabase project, '
    'plus a cross-domain layer that connects health and life data.'
)

add_table(
    ['Domain', 'Tables', 'Count', 'Purpose'],
    [
        ['Shared Core', 'users, demographic_clusters, multimodal_inputs, agents, agent_sessions', '5', 'Common foundation shared by both HRT and LRT'],
        ['Health Domain (HRT)', 'user_biometric, user_diagnosis, user_lifestyle, user_health_level, health_simulations, std_population_category, std_diagnosis_norm, std_lifestyle_plan, std_disease_risk_weight', '9', 'Health-specific data, norms, and simulation'],
        ['Life Domain (LRT)', 'standard_lrt_header/events/activities/products, personal_lrt_header/events/activities, contracts, orders', '9', 'Life events, commerce, pre-order system'],
        ['Cross-Domain', 'user_activity_event, agent_relationship_permissions, agent_conversation_log, history_record_table', '4', 'Shared events, permissions, chat, audit trail'],
        ['', '', '27 total', '(reduced from 31 separate)'],
    ])

doc.add_heading('4.2 Unified users Table', level=2)
code_block(
    'CREATE TABLE users (\n'
    '    user_id              BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,\n'
    '    user_token           UUID UNIQUE DEFAULT gen_random_uuid(),  -- external API token\n'
    '    user_hash            VARCHAR(64) UNIQUE,                     -- de-identification (HRT)\n'
    '    auth_user_id         UUID REFERENCES auth.users(id),         -- Supabase Auth link\n'
    '    cluster_id           BIGINT REFERENCES demographic_clusters, -- demographic cluster (LRT)\n'
    '\n'
    '    -- Demographics (merged)\n'
    '    birth_year           SMALLINT CHECK (birth_year >= 1900 AND birth_year <= 2200),\n'
    '    age_group            VARCHAR(20),             -- backward compat (HRT)\n'
    '    gender               CHAR(1) CHECK (gender IN (\'M\',\'F\',\'X\')),\n'
    '    nationality          CHAR(3) DEFAULT \'KOR\',\n'
    '\n'
    '    -- Health-specific (from HRT)\n'
    '    disability_yn        BOOLEAN DEFAULT false,\n'
    '    income_decile        SMALLINT CHECK (income_decile >= 1 AND income_decile <= 10),\n'
    '\n'
    '    -- Life-specific (from LRT)\n'
    '    occupation_category  TEXT,\n'
    '    household_type       TEXT,\n'
    '    income_bracket       TEXT,\n'
    '    region               TEXT,\n'
    '    mbti                 CHAR(4),\n'
    '\n'
    '    -- System\n'
    '    is_active            BOOLEAN DEFAULT true,\n'
    '    created_at           TIMESTAMPTZ DEFAULT now(),\n'
    '    deleted_at           TIMESTAMPTZ              -- soft delete (LRT)\n'
    ');'
)

doc.add_heading('4.3 Table-by-Table Decisions', level=2)
add_table(
    ['#', 'Table', 'Source', 'Action'],
    [
        ['1', 'users', 'Both', 'MERGE \u2014 BIGINT PK + UUID token, combined fields'],
        ['2', 'demographic_clusters', 'LRT', 'KEEP \u2014 population clustering'],
        ['3', 'std_population_category', 'HRT', 'KEEP \u2014 health-specific benchmarking'],
        ['4', 'std_diagnosis_norm', 'HRT', 'KEEP \u2014 health normal/warning/critical ranges'],
        ['5', 'std_lifestyle_plan', 'HRT', 'KEEP \u2014 role-model lifestyle plans'],
        ['6', 'std_disease_risk_weight', 'HRT', 'KEEP \u2014 disease risk contribution weights'],
        ['7', 'user_demographic', 'HRT', 'REMOVE \u2014 merged into unified users table'],
        ['8', 'user_biometric', 'HRT', 'KEEP \u2014 wearable biometric data'],
        ['9', 'user_diagnosis', 'HRT', 'KEEP \u2014 medical lab data'],
        ['10', 'user_lifestyle', 'HRT', 'KEEP \u2014 daily diet/exercise/sleep'],
        ['11', 'user_activity_event', 'HRT', 'EXTEND \u2014 add LRT event types (purchase, social)'],
        ['12', 'user_health_level', 'HRT', 'KEEP \u2014 HCI and DRI scores'],
        ['13', 'multimodal_inputs', 'Both', 'MERGE \u2014 best features from both'],
        ['14', 'agents', 'LRT', 'KEEP \u2014 multi-role agent system'],
        ['15', 'agent_sessions', 'LRT', 'KEEP \u2014 session management'],
        ['16', 'agent_relationship_permissions', 'LRT', 'KEEP \u2014 1st/2nd/3rd degree permissions'],
        ['17', 'agent_conversation_log', 'HRT', 'KEEP \u2014 linked to agent_sessions'],
        ['18', 'health_simulations', 'HRT', 'RENAME \u2014 was simulation_result'],
        ['19', 'lrt_simulations', 'LRT', 'KEEP \u2014 life event simulations'],
        ['20', 'standard_lrt_header', 'LRT', 'KEEP \u2014 life event templates'],
        ['21', 'standard_lrt_events', 'LRT', 'KEEP \u2014 expected life events'],
        ['22', 'standard_lrt_activities', 'LRT', 'KEEP \u2014 expected behaviors'],
        ['23', 'standard_lrt_products', 'LRT', 'KEEP \u2014 product recommendations'],
        ['24', 'personal_lrt_header', 'LRT', 'KEEP \u2014 per-user LRT'],
        ['25', 'personal_lrt_events', 'LRT', 'KEEP \u2014 individual predicted events'],
        ['26', 'personal_lrt_activities', 'LRT', 'KEEP \u2014 individual behaviors'],
        ['27', 'contracts', 'LRT', 'KEEP \u2014 purchase contracts'],
        ['28', 'orders', 'LRT', 'KEEP \u2014 order execution'],
        ['29', 'history_record_table', 'LRT', 'KEEP \u2014 blockchain audit trail'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 5. HOW IT WORKS AFTER UNIFICATION
# ═══════════════════════════════════════════════════════════
doc.add_heading('5. How It Works After Unification', level=1)

doc.add_heading('5.1 User Registration Flow', level=2)
bullet('User signs up \u2192 Supabase Auth creates auth.users record (UUID)')
bullet('Unified users table row created: BIGINT user_id (internal) + UUID user_token (external) + auth_user_id link')
bullet('demographic_clusters matched based on birth_year, gender, nationality, occupation')
bullet('HRT side: std_population_category matched \u2192 health benchmarks loaded, user_health_level initialized')
bullet('LRT side: personal_lrt_header created \u2192 linked to standard_lrt for their cluster, predicted life events generated')

doc.add_heading('5.2 AI Glasses Data Flow (Unified)', level=2)
doc.add_paragraph('All glasses events go through ONE pipeline and are routed to both domains:')
bullet('FOOD DETECTED \u2192 user_activity_event (meal) + user_lifestyle update (HRT) + LRT checks if food purchase was predicted')
bullet('MEDICATION DETECTED \u2192 user_activity_event (medication) + adherence tracking (HRT) + LRT auto-reorders when supply is low')
bullet('STORE VISIT DETECTED \u2192 user_activity_event (purchase) + personal_lrt_activities (LRT) + HRT checks if purchased food is healthy')
bullet('EXERCISE DETECTED \u2192 user_activity_event (exercise) + user_lifestyle (HRT) + LRT learns patterns for product predictions')

doc.add_heading('5.3 Cross-Domain Intelligence', level=2)
doc.add_paragraph('Health Simulation \u2192 Life Simulation:')
bullet('LSTM predicts glucose rising \u2192 LRT pre-orders blood glucose monitor')
bullet('LSTM predicts BMI increasing \u2192 LRT recommends gym membership, healthy meal kits')

doc.add_paragraph('Life Simulation \u2192 Health Simulation:')
bullet('LRT predicts marriage in 6 months \u2192 HRT adjusts stress factor in health simulation')
bullet('LRT detects job change \u2192 HRT monitors for stress-related health changes')

doc.add_heading('5.4 Unified Agent System', level=2)
add_table(
    ['Agent', 'Role', 'Degree', 'Domain'],
    [
        ['User AI Agent', 'Manages everything for the user', 'Direct', 'Shared'],
        ['HealthCore Agent', 'Health queries, HCI monitoring', '2nd', 'HRT'],
        ['Nutrition Agent', 'Food analysis, diet recommendations', '2nd', 'HRT'],
        ['Exercise Agent', 'Exercise prescription', '2nd', 'HRT'],
        ['Medical Agent', 'FHIR integration, emergency', '2nd', 'HRT'],
        ['Glasses Agent', 'Processes glasses events', 'Direct (device)', 'Shared'],
        ['Family Agent', 'Family health + life sharing', '1st', 'Shared'],
        ['Community Agent', 'Anonymized trends', '3rd', 'Shared'],
        ['Supplier Agent', 'Negotiates with suppliers', 'N/A', 'LRT'],
        ['Holder Agent', 'Manages owned assets/subscriptions', 'N/A', 'LRT'],
        ['Producer Agent', 'Interfaces with manufacturers', 'N/A', 'LRT'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 6. MIGRATION PLAN
# ═══════════════════════════════════════════════════════════
doc.add_heading('6. Migration Plan', level=1)

doc.add_heading('6.1 Phase 1: Prepare (Week 1)', level=2)
add_table(
    ['Task', 'Who', 'Details'],
    [
        ['Agree on unified users schema', 'Both teams + boss', 'BIGINT PK + UUID token, gender=X, merged fields'],
        ['Choose target Supabase project', 'Boss', 'Create NEW unified project (clean start, no legacy issues)'],
        ['Backup both databases', 'Both', 'pg_dump both projects before any changes'],
        ['Design unified migration SQL', 'Both', 'Complete DDL for all 27 tables'],
    ])

doc.add_heading('6.2 Phase 2: Create Unified Schema (Week 2)', level=2)
add_table(
    ['Task', 'Details'],
    [
        ['Create new Supabase project', 'Name: "triple-h-unified" or similar, Seoul region, Pro plan'],
        ['Run unified migration SQL', 'Create all 27 tables with correct types, constraints, indexes'],
        ['Set up RLS policies', 'Per-user data isolation using auth_user_id'],
        ['Migrate HRT standard data', 'Insert 26 categories, 298 norms, 56 plans, 44 risk weights'],
        ['Migrate HRT user data', 'Convert 8 users (UUID \u2192 BIGINT), 5042 biometric, 193 events'],
    ])

doc.add_heading('6.3 Phase 3: Connect Domains (Week 3)', level=2)
add_table(
    ['Task', 'Details'],
    [
        ['Extend user_activity_event', 'Add LRT event types: purchase, social, mobility, employment'],
        ['Create cross-domain views', 'Views joining health + life data for agent queries'],
        ['Update HRT FastAPI backend', 'Point to new project, update user_id handling (BIGINT + token)'],
        ['Update LRT backend', 'Point to new project, update user_id from BIGINT to match unified schema'],
        ['Update Pydantic models', 'Add LRT models, update user model with merged fields'],
    ])

doc.add_heading('6.4 Phase 4: Verify (Week 4)', level=2)
add_table(
    ['Task', 'Details'],
    [
        ['Test all HRT API endpoints', 'Must work exactly as before (backward compatible)'],
        ['Test all LRT API endpoints', 'Must work with unified user_id + token'],
        ['Test cross-domain queries', 'Health data informs LRT, LRT data informs health'],
        ['Test agent system', 'All 11 agents can read/write their respective tables'],
        ['Test RLS policies', 'Each user can only see their own data'],
        ['Load test', 'Verify performance with unified schema under simulated load'],
        ['Security audit', 'Verify HIPAA/PIPA compliance with unified data'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 7. RISK MANAGEMENT
# ═══════════════════════════════════════════════════════════
doc.add_heading('7. Risk Management', level=1)
add_table(
    ['Risk', 'Impact', 'Probability', 'Mitigation'],
    [
        ['Data loss during migration', 'HIGH', 'LOW', 'Full backup of both projects before any changes. Migrate to NEW project (originals preserved).'],
        ['HRT API breaks after migration', 'HIGH', 'MEDIUM', 'Run full test suite. Keep original HRT project running in parallel until verified.'],
        ['LRT API breaks after migration', 'MEDIUM', 'LOW', 'LRT has 0 user data. Only schema changes needed in code.'],
        ['Performance degradation', 'MEDIUM', 'LOW', '27 tables is well within Supabase limits. BIGINT PKs ensure fast JOINs. Index strategy pre-defined.'],
        ['Team disagreement on decisions', 'MEDIUM', 'MEDIUM', 'This document serves as the agreed plan. Boss makes final call on any disputes.'],
        ['Cross-domain data inconsistency', 'MEDIUM', 'LOW', 'Foreign key constraints enforce referential integrity. history_record_table provides audit trail.'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 8. SUMMARY
# ═══════════════════════════════════════════════════════════
doc.add_heading('8. Summary', level=1)

add_table(
    ['Question', 'Answer'],
    [
        ['Why unify?', 'Same user, same glasses, same agents \u2014 two systems waste resources and miss cross-domain insights (health \u2194 purchases)'],
        ['Where?', 'New unified Supabase project (both originals preserved as backup)'],
        ['How many tables?', '27 unified (reduced from 14 HRT + 17 LRT = 31)'],
        ['User ID decision?', 'BIGINT primary key (fast JOINs) + UUID user_token (secure APIs) + UUID auth_user_id (Supabase Auth)'],
        ['Gender code?', 'CHAR(1) with M, F, X (ICAO international standard)'],
        ['Multimodal?', 'Merged into one table with pgvector + JSONB + TTL auto-delete'],
        ['Simulations?', 'Keep both: health_simulations (LSTM) + lrt_simulations (Monte Carlo), connected bidirectionally'],
        ['Agent system?', "LRT's agent system (more mature) + HRT's conversation log, 11 unified agents"],
        ['Will HRT still work?', 'Yes \u2014 all health tables, API endpoints, and data preserved'],
        ['Will LRT still work?', 'Yes \u2014 all LRT tables migrated, relationships preserved'],
        ['Timeline?', '4 weeks (1 prepare + 1 create + 1 connect + 1 verify)'],
        ['Who does what?', 'HRT team: health tables + backend. LRT team: LRT tables + code. Together: unified users + testing'],
    ])

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | HRT + LRT Unified Database Plan v2.0 | April 15, 2026')
run.font.size = Pt(9)
run.font.color.rgb = RGBColor(0x75, 0x75, 0x75)

# Save
output_path = r'C:\Users\tripleh\projects\healthcare-ai-agent\docs\HRT_LRT_Unification_Plan_v2_FINAL.docx'
doc.save(output_path)
print(f'Saved: {output_path}')
