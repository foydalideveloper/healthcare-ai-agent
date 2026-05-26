"""
Generate AI Glasses Data Collection — Tools, Models & DB Structure Guide as .docx
Triple-H Co., Ltd. | April 15, 2026
SCOPE: Only tools related to AI glasses data collection pipeline + database storage
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
# COVER PAGE
# ═══════════════════════════════════════════════════════════
for _ in range(5):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('AI Glasses Data Collection\nTools, Models & DB Structure')
run.font.size = Pt(28)
run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)
run.bold = True

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('For HRT (Healthcare) + LRT (Lifetime) Projects')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x42, 0x42, 0x42)

doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | April 2026')
run.font.size = Pt(14)
run.bold = True
run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 1. ML MODELS (Glasses Pipeline Only)
# ═══════════════════════════════════════════════════════════
doc.add_heading('1. ML Models for Glasses Data Processing', level=1)

doc.add_paragraph(
    'These models run on the user\'s phone to process photos and audio captured by AI glasses. '
    'They turn raw camera frames into structured health and life data.'
)

add_table(
    ['Model', 'What It Is', 'Why We Use It', 'Role in Glasses Pipeline', 'Runs On', 'Size'],
    [
        [
            'YOLO-Face',
            'A face detection model that finds and blurs human faces in photos.',
            'Privacy law (HIPAA, PIPA, GDPR) requires that bystander faces are never stored or uploaded.',
            'Runs FIRST on every glasses photo. Blurs all faces before any other processing. This is mandatory \u2014 no photo leaves the phone with visible faces.',
            'Phone (TFLite)',
            '~3 MB',
        ],
        [
            'MobileNetV2-Food',
            'An image classification model that recognizes 2,024 types of food from a photo.',
            'When glasses capture a photo of a meal, we need to know WHAT food it is.',
            'Takes a glasses photo as input, outputs food name + confidence score. Example: input=photo \u2192 output="kimchi jjigae" (confidence: 0.85).',
            'Phone (TFLite)',
            '~8 MB',
        ],
        [
            'YOLOv8n',
            'An object detection model that draws boxes around food and estimates its size on the plate.',
            'Knowing the food name is not enough \u2014 we also need to know HOW MUCH the user is eating.',
            'Takes a glasses photo, detects food area in pixels, estimates portion: small (0.75x), medium (1.0x), or large (1.5x). Portion multiplied with nutrition values.',
            'Phone (TFLite)',
            '~12 MB',
        ],
        [
            'Whisper-tiny',
            'A speech-to-text model that converts spoken words into written text. Supports Korean + 25 languages.',
            'Glasses have microphones. User may talk about health, describe what they\'re eating, or mention medication.',
            'Transcribes audio captured by glasses mic into searchable text. Stored in multimodal_inputs table. AI agents can read and reference it later.',
            'Phone (TFLite)',
            '~39 MB',
        ],
    ])

doc.add_paragraph()
doc.add_paragraph(
    'Total model size on phone: ~62 MB. All models use INT8 quantization via TensorFlow Lite '
    'for fast inference on phone GPU/NPU.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 2. FOOD DATABASES (Glasses Pipeline Only)
# ═══════════════════════════════════════════════════════════
doc.add_heading('2. Food Nutrition Databases', level=1)

doc.add_paragraph(
    'After the ML model identifies WHAT food the user is eating, we need to look up its '
    'nutritional content (calories, protein, fat, etc.). These databases run locally on the phone '
    'for instant offline lookup.'
)

add_table(
    ['Database', 'What It Contains', 'Why We Use It', 'Role in Glasses Pipeline', 'Size'],
    [
        [
            'MFDS SQLite\n(Korean Food DB)',
            '275,856 Korean food items with 40+ nutrient fields: calories, protein, fat, carbs, sodium, vitamins, minerals.',
            'PRIMARY lookup for Korean food. When model detects "\uae40\uce58\ucc0c\uac1c", we look up: 61 kcal, 3.8g protein, 491mg sodium per 100g.',
            'Phone receives food name from MobileNetV2 \u2192 queries this SQLite DB \u2192 gets full nutrition data \u2192 includes in upload to Supabase.',
            '108 MB',
        ],
        [
            'USDA SQLite\n(International Food DB)',
            '13,591 international food items (American, European, Asian) with 50+ nutrients per food.',
            'FALLBACK for non-Korean food. Users also eat pizza, pasta, steak, sushi. These are not in the Korean MFDS database.',
            'If food name NOT found in MFDS \u2192 search USDA. Example: "chicken breast" not in MFDS \u2192 found in USDA \u2192 165 kcal, 31g protein.',
            '62 MB',
        ],
    ])

doc.add_paragraph()
doc.add_paragraph(
    'Total food database: 289,447 foods. Both databases are stored on the phone as SQLite files. '
    'No internet needed for nutrition lookup \u2014 works completely offline.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 3. TRANSPORT & UPLOAD
# ═══════════════════════════════════════════════════════════
doc.add_heading('3. Data Transport & Upload', level=1)

doc.add_paragraph(
    'These tools move data from the glasses \u2192 phone \u2192 cloud database.'
)

add_table(
    ['Tool', 'What It Is', 'Why We Use It', 'Role in Glasses Pipeline'],
    [
        [
            'BLE (Bluetooth Low Energy)',
            'Wireless protocol for short-range communication between glasses and phone.',
            'Glasses need to send photos and audio to the phone for processing. BLE is the standard way smart glasses communicate.',
            'Glasses capture photo \u2192 send via BLE to phone (~200ms transfer time for one photo). Always-on connection while glasses are worn.',
        ],
        [
            'WiFi (Direct)',
            'High-speed wireless connection for larger data transfers.',
            'Some glasses (Omi Glass) support WiFi for faster bulk transfers. Used when BLE is too slow for video clips.',
            'Alternative to BLE for larger files. Also used for phone \u2192 cloud upload (thumbnails + JSON events to Supabase).',
        ],
        [
            'Supabase Storage',
            'Cloud file storage service (S3-compatible) built into Supabase.',
            'Thumbnails and video clips need to be stored in the cloud, not just the database. Supabase Storage handles file uploads.',
            'Phone uploads WebP thumbnails (100 KB each) and selective video clips (5 MB each, only for low-confidence events) to Supabase Storage buckets.',
        ],
        [
            'TensorFlow Lite',
            'Lightweight ML runtime that executes AI models on mobile phones.',
            'All 4 ML models (YOLO-Face, MobileNetV2, YOLOv8n, Whisper) need a runtime engine to execute on the phone.',
            'Loads .tflite model files into phone memory, runs inference using phone GPU/NPU. Processes each glasses frame in ~75ms total.',
        ],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 4. DATABASE STRUCTURE
# ═══════════════════════════════════════════════════════════
doc.add_heading('4. Database Structure for Glasses Data', level=1)

doc.add_paragraph(
    'When glasses capture an event (meal, drink, medication, exercise, purchase), the processed '
    'data is stored in these Supabase tables. Each table has a specific role.'
)

doc.add_heading('4.1 Tables That Receive Glasses Data', level=2)

add_table(
    ['Table', 'What It Stores', 'When Data Is Written', 'Example Row'],
    [
        [
            'user_activity_event',
            'Every individual event detected by glasses: what happened, when, confidence score, nutrition data, thumbnail link.',
            'Every time glasses detect a meal, drink, medication, exercise, or purchase.',
            'event_type="meal", food="kimchi jjigae", calories=91, confidence=0.85, thumbnail_ref="s3://thumb_001.webp", source="ai_glasses"',
        ],
        [
            'user_lifestyle',
            'Daily summary: total calories, protein, fat, carbs, sodium, meal count, exercise minutes, sleep hours.',
            'End of day \u2014 aggregated from all user_activity_event rows for that day.',
            'date="2026-04-15", total_calories=1850, protein_g=72, fat_g=65, meal_count=3, data_source="ai_glasses"',
        ],
        [
            'multimodal_inputs',
            'Audio transcripts, image embeddings, emotion tags from glasses captures.',
            'When glasses capture audio or when embeddings are generated for a photo.',
            'input_type="AUDIO", feature_vector=[0.12, -0.34, ...], emotion_tags={"stress": 0.3}, health_metrics={"context": "lunch"}',
        ],
        [
            'personal_lrt_activities\n(LRT only)',
            'Purchase and life activity data: predicted vs actual spending, behavior patterns.',
            'When glasses detect a store visit, purchase, or social event (LRT domain).',
            'activity_type="grocery_purchase", predicted_spend=50000, actual_spend=62000, product_category="food"',
        ],
    ])

doc.add_heading('4.2 Key Columns in user_activity_event', level=2)

doc.add_paragraph(
    'This is the PRIMARY table for all glasses data. Every glasses event becomes one row here.'
)

add_table(
    ['Column', 'Type', 'What It Stores', 'Example Value'],
    [
        ['event_id', 'BIGINT (PK)', 'Unique event identifier, auto-generated', '194'],
        ['user_id', 'BIGINT (FK)', 'Which user this event belongs to', '12345'],
        ['detected_at', 'TIMESTAMPTZ', 'When the event was detected', '2026-04-15 12:30:00+09'],
        ['event_type', 'VARCHAR', 'Type of event: meal, drink, medication, exercise, purchase, social', '"meal"'],
        ['source_device', 'VARCHAR', 'Which device captured this: ai_glasses, smartwatch, phone', '"ai_glasses"'],
        ['confidence_score', 'NUMERIC (0\u20131)', 'How confident the ML model is about the detection', '0.85'],
        ['structured_data', 'JSONB', 'Full event details: food items, nutrients, portions, audio transcript', '{"food_items": [{"name": "\uae40\uce58\ucc0c\uac1c", "confidence": 0.85}], "nutrients": {"energy_kcal": 91, "protein_g": 3.8, "sodium_mg": 491}}'],
        ['thumbnail_ref', 'VARCHAR', 'URL to the WebP thumbnail image in Supabase Storage', '"https://...supabase.co/storage/thumbnails/thumb_001.webp"'],
        ['clip_ref', 'VARCHAR', 'URL to video clip (only if confidence < 0.7)', 'NULL (most events) or "https://...clip_001.mp4"'],
        ['edge_model_version', 'VARCHAR', 'Which ML model version produced this detection', '"mobilenetv2-food-kr-v1.2"'],
        ['verified', 'BOOLEAN', 'Has the user confirmed or corrected this detection?', 'false'],
        ['correction_data', 'JSONB', 'If user corrected: original vs corrected food name and calories', 'NULL or {"original": "\ube44\ube54\ubc25", "corrected": "\ubd88\uace0\uae30\ub355\ubc25"}'],
        ['processing_status', 'VARCHAR', 'Processing stage: edge_only, cloud_refined, user_verified', '"edge_only"'],
    ])

doc.add_heading('4.3 Key Columns in user_lifestyle (Daily Summary)', level=2)

add_table(
    ['Column', 'Type', 'What It Stores', 'Example Value'],
    [
        ['ls_id', 'BIGINT (PK)', 'Unique record identifier', '1'],
        ['user_id', 'BIGINT (FK)', 'Which user', '12345'],
        ['recorded_date', 'DATE', 'Which day this summary covers', '2026-04-15'],
        ['total_calories', 'SMALLINT', 'Sum of all meal calories detected by glasses today', '1850'],
        ['protein_g', 'SMALLINT', 'Total protein in grams', '72'],
        ['fat_g', 'SMALLINT', 'Total fat in grams', '65'],
        ['carb_g', 'SMALLINT', 'Total carbohydrates in grams', '210'],
        ['sodium_mg', 'SMALLINT', 'Total sodium in milligrams', '3200'],
        ['meal_count', 'SMALLINT', 'Number of meals detected by glasses', '3'],
        ['exercise_min', 'SMALLINT', 'Minutes of exercise detected', '30'],
        ['sleep_hours', 'NUMERIC', 'Hours of sleep (from wearable, not glasses)', '7.5'],
        ['medication_json', 'JSONB', 'Medications detected by glasses', '[{"name": "metformin", "dose": "500mg", "time": "19:30"}]'],
        ['data_source', 'VARCHAR', 'Source of this data', '"ai_glasses"'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 5. DATA FLOW DIAGRAM
# ═══════════════════════════════════════════════════════════
doc.add_heading('5. How Data Flows: Glasses \u2192 Phone \u2192 Database', level=1)

doc.add_paragraph('Step-by-step flow showing which tool is used at each stage:')

add_table(
    ['Step', 'What Happens', 'Tool Used', 'Output'],
    [
        ['1', 'Glasses camera captures photo of food', 'Omi Glass / Android XR camera', 'JPEG photo (~500 KB)'],
        ['2', 'Photo sent from glasses to phone', 'BLE or WiFi', 'Photo arrives on phone'],
        ['3', 'Blur all bystander faces in photo', 'YOLO-Face (TFLite, 3 MB)', 'Photo with faces blurred'],
        ['4', 'Identify what food is in the photo', 'MobileNetV2-Food (TFLite, 8 MB)', '"kimchi jjigae" (confidence: 0.85)'],
        ['5', 'Estimate how much food (portion size)', 'YOLOv8n (TFLite, 12 MB)', 'Portion: medium (1.0x multiplier)'],
        ['6', 'Look up nutrition for that food', 'MFDS SQLite (108 MB) or USDA SQLite (62 MB)', '61 kcal, 3.8g protein, 491mg sodium'],
        ['7', 'Transcribe audio if speech detected', 'Whisper-tiny (TFLite, 39 MB)', 'Text: "this is really salty"'],
        ['8', 'Generate WebP thumbnail', 'Image resizer (phone)', 'Thumbnail: 100 KB WebP'],
        ['9', 'Upload event to database', 'Supabase REST API (HTTPS)', 'New row in user_activity_event'],
        ['10', 'Upload thumbnail to storage', 'Supabase Storage (HTTPS)', 'File in thumbnails/ bucket'],
        ['11', 'Aggregate daily totals (end of day)', 'Backend aggregation job', 'New/updated row in user_lifestyle'],
    ])

doc.add_paragraph()
doc.add_paragraph(
    'Total processing time per event: ~75ms on phone (Steps 3\u20137). '
    'Upload time: ~1\u20132 seconds (Steps 9\u201310). '
    'User sees notification within 2 seconds of glasses capturing the photo.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 6. QUICK REFERENCE
# ═══════════════════════════════════════════════════════════
doc.add_heading('6. Quick Reference', level=1)

add_table(
    ['Category', 'Tool', 'One-Line Purpose', 'Size'],
    [
        ['ML Model', 'YOLO-Face', 'Blur bystander faces (privacy/HIPAA)', '3 MB'],
        ['ML Model', 'MobileNetV2-Food', 'Identify food name from photo', '8 MB'],
        ['ML Model', 'YOLOv8n', 'Estimate food portion size', '12 MB'],
        ['ML Model', 'Whisper-tiny', 'Convert speech to text (Korean)', '39 MB'],
        ['ML Runtime', 'TensorFlow Lite', 'Execute ML models on phone GPU', 'Built-in'],
        ['', '', '', ''],
        ['Food DB', 'MFDS SQLite', '275,856 Korean foods with nutrition', '108 MB'],
        ['Food DB', 'USDA SQLite', '13,591 international foods (fallback)', '62 MB'],
        ['', '', '', ''],
        ['Transport', 'BLE / WiFi', 'Glasses \u2192 Phone data transfer', 'N/A'],
        ['Upload', 'Supabase REST API', 'Phone \u2192 Database (JSON events)', 'N/A'],
        ['Upload', 'Supabase Storage', 'Phone \u2192 Cloud (thumbnails, clips)', 'N/A'],
        ['', '', '', ''],
        ['Database', 'user_activity_event', 'Individual glasses events (meals, drinks, etc.)', '13 columns'],
        ['Database', 'user_lifestyle', 'Daily aggregated nutrition summary', '13 columns'],
        ['Database', 'multimodal_inputs', 'Audio transcripts + image embeddings', '11 columns'],
        ['Database', 'personal_lrt_activities', 'Purchase/life events (LRT only)', '12 columns'],
    ])

doc.add_paragraph()
doc.add_paragraph(
    'Total phone storage needed for glasses pipeline: ~232 MB '
    '(62 MB models + 170 MB food databases).'
)

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | AI Glasses Data Collection \u2014 Tools, Models & DB Structure | April 2026')
run.font.size = Pt(9)
run.font.color.rgb = RGBColor(0x75, 0x75, 0x75)

# Save
output_path = r'C:\Users\tripleh\projects\healthcare-ai-agent\docs\HRT_LRT_Dev_Tools_and_Models_Guide.docx'
doc.save(output_path)
print(f'Saved: {output_path}')
