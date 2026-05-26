"""
Generate Healthcare AI Agent Development Plan — Updated After Meeting
For VP and President review
Triple-H Co., Ltd. | April 15, 2026
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

doc = Document()

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


def bullet(text):
    p = doc.add_paragraph(text, style='List Bullet')
    p.paragraph_format.left_indent = Cm(1.27)


# ═══════════════════════════════════════════════════════════
# COVER
# ═══════════════════════════════════════════════════════════
for _ in range(5):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Healthcare AI Agent\nDevelopment Plan')
run.font.size = Pt(32)
run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)
run.bold = True

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Updated After April 15, 2026 Meeting\nIncorporating Multi-Agent, Data Collector, Monte Carlo,\nand DNA/Family History Requirements')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x42, 0x42, 0x42)

doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | AI Business Division\nKorean Patent Application No. 10-2025-0145274')
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 1. CURRENT STATUS
# ═══════════════════════════════════════════════════════════
doc.add_heading('1. Current Status', level=1)

doc.add_heading('1.1 What Has Been Completed', level=2)

add_table(
    ['Item', 'Status', 'Details'],
    [
        ['Healthcare v3 Plan', 'COMPLETE', '58-page development plan covering all technical specifications'],
        ['Database (HRT)', 'COMPLETE', '14 tables, 5,669 rows, Supabase PostgreSQL, Seoul region'],
        ['HRT + LRT Unification', 'COMPLETE (Today)', '28 unified tables, all data migrated, zero data lost'],
        ['FastAPI Backend', 'COMPLETE', '10 API endpoints, food lookup, activity events, simulation'],
        ['Data Collection', 'COMPLETE', 'KNHANES 2018-2024 (49K records), MFDS 275K foods, USDA 13K foods, AI Hub 17K QA'],
        ['AI Glasses Research', 'COMPLETE', 'Mentra Live selected ($349, 12MP camera, open SDK)'],
        ['Forecasting Models', 'RESEARCHED', '5 models identified: LSTM-Transformer, MIRA, TimesFM, Chronos, TFT'],
        ['Companion App', 'IN PROGRESS', 'React Native app structure built, ML pipeline services coded'],
        ['LSTM Training', 'NOT STARTED', 'Data ready, waiting to begin training'],
        ['Agent Skills (OpenClaw)', 'NOT STARTED', '12 skill directories created, code empty'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 2. MULTI-AGENT SYSTEM
# ═══════════════════════════════════════════════════════════
doc.add_heading('2. Multi-Agent System', level=1)

doc.add_paragraph(
    'The Healthcare AI Agent uses a multi-agent architecture based on OpenClaw v2026.4 '
    'with SOUL.md persona definitions. Each agent specializes in one domain and they '
    'collaborate through structured message passing.'
)

doc.add_heading('2.1 Agent Roster (12 Agents)', level=2)

add_table(
    ['#', 'Agent', 'Role', 'Degree', 'Domain', 'Status'],
    [
        ['1', 'User AI Agent', 'Master agent \u2014 manages all interactions for the user', 'Direct', 'Shared', 'Planned'],
        ['2', 'HealthCore Agent', 'Health queries, HCI monitoring, simulation execution', '2nd', 'Health', 'Planned'],
        ['3', 'Nutrition Agent', 'Food analysis, diet recommendations, MFDS/USDA lookup', '2nd', 'Health', 'Planned'],
        ['4', 'Exercise Agent', 'Exercise prescription, MET-based calorie calculation', '2nd', 'Health', 'Planned'],
        ['5', 'Medical Agent', 'Hospital FHIR integration, emergency detection (HCI\u226581)', '2nd', 'Health', 'Planned'],
        ['6', 'Glasses Agent', 'AI glasses event processing, food/activity detection', 'Direct (Device)', 'Shared', 'Planned'],
        ['7', 'Family Agent', 'Family health + life sharing, family history analysis', '1st', 'Shared', 'Planned'],
        ['8', 'Community Agent', 'Anonymized health trends, de-identified statistics', '3rd', 'Shared', 'Planned'],
        ['9', 'Supplier Agent', 'Negotiates with product/service suppliers (LRT)', 'N/A', 'Life', 'Planned'],
        ['10', 'Holder Agent', 'Manages owned assets and subscriptions (LRT)', 'N/A', 'Life', 'Planned'],
        ['11', 'Producer Agent', 'Interfaces with manufacturers (LRT)', 'N/A', 'Life', 'Planned'],
        ['12', 'Data Collector Agent', 'Automatic data collection from ALL devices (NEW)', 'Direct', 'Shared', 'NEW \u2014 Added today'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 3. DATA COLLECTOR AGENT (NEW)
# ═══════════════════════════════════════════════════════════
doc.add_heading('3. Data Collector Agent (New \u2014 From Today\'s Meeting)', level=1)

doc.add_paragraph(
    'A dedicated agent responsible for automatically collecting, validating, normalizing, '
    'and uploading health and life data from ALL connected devices. This agent acts as the '
    'single entry point for all device data entering the system.'
)

doc.add_heading('3.1 Supported Data Sources', level=2)

add_table(
    ['Device', 'Data Collected', 'Connection Method', 'Frequency'],
    [
        ['AI Glasses (Mentra Live)', 'Food photos, audio, activity detection', 'BLE/WiFi \u2192 Phone SDK', 'Every 5-30 seconds'],
        ['Smartwatch (Galaxy/Apple)', 'Heart rate, steps, activity, sleep', 'Health Connect / HealthKit', 'Real-time'],
        ['Smart Ring (Oura/Galaxy)', 'HRV, SpO2, body temperature, sleep stages', 'Oura API V2 / Health Connect', 'Nightly + real-time'],
        ['CGM Sensor (Dexcom/Libre)', 'Blood glucose, trend direction', 'Dexcom API V3', 'Every 5 minutes'],
        ['Smartphone', 'GPS location, screen time, app usage', 'Android/iOS APIs', 'Continuous'],
        ['Smart Home Devices', 'Room temperature, humidity, air quality, light', 'IoT APIs (SmartThings, HomeKit)', 'Every 15 minutes'],
        ['Connected Car', 'Driving patterns, stress indicators, commute data', 'Car API / OBD-II', 'During driving'],
        ['Blood Pressure Monitor', 'Systolic/diastolic BP, pulse', 'Bluetooth', 'On measurement'],
        ['Body Scale', 'Weight, body fat %, muscle mass', 'Bluetooth / WiFi', 'On measurement'],
        ['DNA/Genetic Test (Future)', 'Polygenic risk scores, genetic markers', 'Manual upload or API', 'One-time'],
    ])

doc.add_heading('3.2 What the Data Collector Agent Does', level=2)

add_table(
    ['Function', 'Description'],
    [
        ['Collection', 'Connects to all device APIs, receives data in various formats'],
        ['Validation', 'Checks if data makes sense (e.g., heart rate 300 = error, reject it)'],
        ['Normalization', 'Converts all formats to unified schema before storing'],
        ['Deduplication', 'If watch and phone both report heart rate, store only once'],
        ['Quality Scoring', 'Rates data quality (sensor drift, gaps, noise) before storage'],
        ['Conflict Resolution', 'When two devices disagree, picks the more reliable source'],
        ['Upload', 'Sends clean, validated data to correct Supabase tables'],
        ['Gap Detection', 'Alerts user when data is missing (e.g., "no sleep data last 3 days")'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 4. MONTE CARLO FOR HEALTH
# ═══════════════════════════════════════════════════════════
doc.add_heading('4. Monte Carlo Simulation for Health Prediction (New \u2014 From Today\'s Meeting)', level=1)

doc.add_paragraph(
    'The original v3 plan uses LSTM-Transformer for health prediction, which outputs single '
    'point predictions. Monte Carlo simulation adds probability ranges, giving users and '
    'doctors confidence intervals instead of just one number.'
)

doc.add_heading('4.1 Before vs After Adding Monte Carlo', level=2)

add_table(
    ['', 'Before (LSTM only)', 'After (LSTM + Monte Carlo)'],
    [
        ['Glucose prediction', '"Your glucose will be 130 in 5 years"', '"Your glucose will be 115\u2013145 in 5 years (90% confidence). Most likely: 130"'],
        ['Diabetes risk', '"22% risk"', '"15\u201328% risk (90% confidence). Most likely: 22%"'],
        ['User confidence', 'Single number \u2014 seems precise but uncertain', 'Range \u2014 honestly shows uncertainty, builds trust'],
        ['Clinical value', 'Useful but incomplete', 'Matches how doctors think (ranges, not exact numbers)'],
    ])

doc.add_heading('4.2 How It Works', level=2)

bullet('LSTM-Transformer predicts health metrics (BMI, glucose, BP, cholesterol) as before')
bullet('Monte Carlo Dropout: run the SAME prediction 20 times with random dropout enabled')
bullet('Each run produces a slightly different prediction \u2192 collect all 20 results')
bullet('Calculate mean (most likely), standard deviation, and 90% confidence interval')
bullet('Store in simulation_result table (confidence_bounds_json column already exists)')

doc.add_paragraph(
    'This approach requires NO additional training or model changes. Monte Carlo Dropout '
    'uses the existing trained model and adds uncertainty estimation at inference time. '
    'Cost: 20x inference time (acceptable \u2014 20 predictions take ~2 seconds on GPU).'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 5. DNA / FAMILY HISTORY
# ═══════════════════════════════════════════════════════════
doc.add_heading('5. DNA-Based Family Health History (New \u2014 From Today\'s Meeting)', level=1)

doc.add_heading('5.1 The Problem: New Users Have No Data', level=2)

doc.add_paragraph(
    'When a new user registers, they have zero health history. The AI cannot make meaningful '
    'predictions because there is no data to learn from. This "cold start" problem means new '
    'users get generic population-average predictions that feel impersonal and inaccurate.'
)

doc.add_heading('5.2 The Solution: Use Family Health Trajectories', level=2)

doc.add_paragraph(
    'If a new user\'s father, mother, or siblings already have health data in the system, '
    'their health trajectories can be used as a starting point for the new user\'s predictions. '
    'Family members share approximately 50% of their DNA, meaning their health patterns are '
    'partially predictive of each other.'
)

add_table(
    ['Family Relationship', 'DNA Similarity', 'Weight in Prediction'],
    [
        ['Parent (father/mother)', '~50%', 'High \u2014 direct genetic inheritance'],
        ['Sibling (brother/sister)', '~50%', 'High \u2014 same genetic pool + similar environment'],
        ['Grandparent', '~25%', 'Medium \u2014 partial genetic inheritance'],
        ['Uncle/Aunt', '~25%', 'Medium \u2014 shared family traits'],
        ['Cousin', '~12.5%', 'Low \u2014 distant genetic similarity'],
    ])

doc.add_heading('5.3 How It Works', level=2)

bullet('Step 1: New user Kim registers, has no health data')
bullet('Step 2: Kim links family members who already have data in the system (Family Agent, 1st degree permission)')
bullet('Step 3: System analyzes family health patterns:')
bullet('  \u2014 Father got diabetes at age 55 \u2192 Kim\'s diabetes risk increases 30%')
bullet('  \u2014 Brother\'s BMI trend: 22\u219225\u219227 between age 30-35 \u2192 Kim may follow similar pattern')
bullet('  \u2014 Mother has no hypertension \u2192 Kim\'s blood pressure risk is average')
bullet('Step 4: System creates initial prediction for Kim using weighted family patterns')
bullet('Step 5: As Kim collects his OWN data, the system gradually shifts from family-based to personal prediction')

doc.add_heading('5.4 Transition From Family Data to Personal Data', level=2)

add_table(
    ['Time Since Registration', 'Family Data Weight', 'Personal Data Weight', 'Prediction Source'],
    [
        ['Day 1 (no data)', '80%', '20% (population average)', 'Mostly family patterns'],
        ['Month 1', '70%', '30%', 'Family + some personal'],
        ['Month 6', '50%', '50%', 'Balanced'],
        ['Year 1', '30%', '70%', 'Mostly personal'],
        ['Year 2+', '10%', '90%', 'Almost entirely personal (family as background risk only)'],
    ])

doc.add_heading('5.5 Database Support (Already Exists)', level=2)

add_table(
    ['Feature', 'Database Table/Column', 'Status'],
    [
        ['Family history field', 'users.family_history (TEXT[])', 'EXISTS \u2014 stores family medical conditions'],
        ['Family data sharing', 'agent_relationship_permissions (1st degree)', 'EXISTS \u2014 controls who can see whose data'],
        ['Family Agent', 'agents table (role=Family Agent)', 'PLANNED \u2014 agent defined, code not built'],
        ['Family Risk Calculator', 'New service needed', 'NEW \u2014 must be built'],
        ['Cold Start Model', 'New ML model needed', 'NEW \u2014 must be built'],
    ])

doc.add_heading('5.6 Future Enhancement: DNA Test Integration', level=2)

doc.add_paragraph(
    'As an optional premium feature, users could upload results from commercial DNA tests '
    '(23andMe, Ancestry, etc.) to get more precise genetic risk scores. This would provide '
    'Polygenic Risk Scores (PRS) for specific diseases like diabetes, heart disease, and cancer. '
    'Cost per user: $100\u2013300 for the test. This is a future enhancement, not required for MVP.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 6. HEALTH SIMULATION OVERVIEW
# ═══════════════════════════════════════════════════════════
doc.add_heading('6. Health Simulation System', level=1)

doc.add_heading('6.1 What the Simulation Predicts', level=2)

doc.add_paragraph('The simulation produces two levels of predictions:')

doc.add_heading('Level 1: Health Metrics (Direct Prediction by LSTM-Transformer)', level=3)

add_table(
    ['Metric', 'Example Today', '1 Year Prediction', '5 Year Prediction'],
    [
        ['BMI', '24.5', '25.3', '28.5'],
        ['Fasting Glucose (mg/dL)', '102', '110', '130'],
        ['Blood Pressure (SBP/DBP)', '125/82', '132/86', '145/95'],
        ['Total Cholesterol (mg/dL)', '190', '205', '235'],
        ['LDL Cholesterol', '120', '135', '160'],
        ['Body Fat %', '22', '24', '28'],
    ])

doc.add_heading('Level 2: Disease Risk (Calculated from Predicted Metrics)', level=3)

add_table(
    ['Disease', 'Risk Today', '5 Year Risk (Current Lifestyle)', '5 Year Risk (Role Model Lifestyle)'],
    [
        ['Type 2 Diabetes', '5.3%', '22.0%', '4.0%'],
        ['Hypertension', '8.0%', '35.0%', '6.0%'],
        ['Obesity', '10.0%', '45.0%', '5.0%'],
        ['Heart Disease', '3.0%', '15.0%', '2.5%'],
        ['Stroke', '1.0%', '8.0%', '0.8%'],
        ['Fatty Liver', '5.0%', '20.0%', '3.0%'],
        ['Kidney Disease', '2.0%', '7.0%', '1.5%'],
        ['Sarcopenia', '1.0%', '5.0%', '0.5%'],
    ])

doc.add_heading('6.2 Digital Twin Comparison (Patent Core)', level=2)

doc.add_paragraph(
    'The system runs TWO simulations for every user: one with their current lifestyle, '
    'one with the ideal "role model" lifestyle from our standard plans (std_lifestyle_plan). '
    'The gap between the two shows the user exactly what they could improve and by how much. '
    'This is the core innovation of Patent 10-2025-0145274.'
)

doc.add_heading('6.3 Forecasting Models (5 Models to Test)', level=2)

add_table(
    ['Model', 'Type', 'Parameters', 'Approach', 'Status'],
    [
        ['LSTM-Transformer (Custom)', 'Train on our data', '~10M', 'Hybrid model designed for health data', 'Ready to train'],
        ['MIRA (Microsoft)', 'Medical foundation model', '455M', 'Pre-trained on 454B medical time points', 'Weights available (HuggingFace)'],
        ['TimesFM 2.5 (Google)', 'General foundation model', '200M', 'Zero-shot prediction, no training needed', 'Weights available'],
        ['Chronos-Bolt (Amazon)', 'General foundation model', '200M', 'Zero-shot with confidence intervals', 'Weights available'],
        ['TFT (Temporal Fusion)', 'Train on our data', '~5M', 'Interpretable \u2014 shows which features matter', 'Ready to train'],
    ])

doc.add_paragraph(
    'Strategy: Test all 5 models, compare accuracy on KNHANES data, then ensemble the best '
    'performers for production. All models fit on our RTX 4070 SUPER (12GB VRAM) GPU server.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 7. DATA COLLECTED
# ═══════════════════════════════════════════════════════════
doc.add_heading('7. Training Data Collected', level=1)

add_table(
    ['Dataset', 'Records', 'Purpose'],
    [
        ['KNHANES 2018-2024 (Diagnosis)', '49,288', 'Korean health checkup data \u2014 BMI, BP, glucose, cholesterol for 50K+ people across 7 years'],
        ['KNHANES 2018-2024 (Nutrition)', '45,377', 'Daily food intake data \u2014 calories, protein, fat, carbs, sodium for Korean population'],
        ['KNHANES 2018-2024 (Lifestyle)', '50,742', 'Exercise, sleep, smoking, alcohol patterns of Korean population'],
        ['MFDS Korean Food DB', '275,856', 'Every Korean food with full nutrition data \u2014 for AI glasses food recognition lookup'],
        ['USDA International Food DB', '13,591', 'International foods (pizza, steak, pasta) \u2014 fallback when Korean DB has no match'],
        ['AI Hub Medical QA', '17,280', 'Korean doctor-patient Q&A pairs \u2014 for fine-tuning the AI health agent to answer like a Korean doctor'],
        ['AI Hub Medical Corpus', '52,125', 'Korean medical textbooks and guidelines \u2014 for medical knowledge in the AI agent'],
        ['Korean Food Images', '~4-6K (free)', 'Found on Kaggle/Roboflow \u2014 for training food recognition model on Korean dishes'],
    ])

doc.add_paragraph(
    'Why Korean-specific data: Health standards differ by population. Korean BMI overweight '
    'threshold is 23 (international is 25). Korean diet is high-sodium (kimchi, doenjang). '
    'AI must learn Korean health patterns, Korean food, and Korean medical practices to give '
    'accurate predictions for Korean users.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 8. NEXT STEPS
# ═══════════════════════════════════════════════════════════
doc.add_heading('8. Next Steps and Timeline', level=1)

add_table(
    ['Priority', 'Task', 'Timeline', 'Details'],
    [
        ['1', 'Purchase Mentra Live AI glasses', 'This week', '$349 + $30 shipping via US forwarding service. 12MP camera, open SDK.'],
        ['2', 'Start forecasting model experiments', 'This week', 'Run TimesFM/Chronos zero-shot on KNHANES \u2192 instant baselines. Begin LSTM training.'],
        ['3', 'Build Data Collector Agent', '2 weeks', 'New 12th agent. Connect to glasses, smartwatch, CGM APIs. Validate + upload to Supabase.'],
        ['4', 'Add Monte Carlo to health simulation', '1 week', '20x dropout inference for confidence intervals. Uses existing model.'],
        ['5', 'Build Family Health History cold-start model', '3 weeks', 'Family risk calculator + weighted prediction for new users with no data.'],
        ['6', 'Build OpenClaw agent skills (12 skills)', '4-6 weeks', 'SOUL.md personas + skill backends for all 12 agents.'],
        ['7', 'Follow up on NHIS cohort data', 'Ongoing', 'Application sent to Korean colleague. 2-4 week approval. Critical for LSTM quality.'],
        ['8', 'LLM fine-tuning (Qwen/Meditron)', '2-3 weeks', 'SFT + DPO on AI Hub medical data. Healthcare-specific AI agent conversations.'],
    ])

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | Healthcare AI Agent Development Plan\n'
                'Updated April 15, 2026 | Patent No. 10-2025-0145274\n'
                'Prepared for VP and President Review')
run.font.size = Pt(9)
run.font.color.rgb = RGBColor(0x75, 0x75, 0x75)

output_path = r'C:\Users\tripleh\projects\healthcare-ai-agent\docs\Healthcare_AI_Agent_Plan_Updated_Apr15.docx'
doc.save(output_path)
print(f'Saved: {output_path}')
