"""
Generate Triple-H AI Glasses Shared Module Technical Specification as .docx
Triple-H Co., Ltd. | April 15, 2026
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.15

for level in range(1, 4):
    hs = doc.styles[f'Heading {level}']
    hs.font.color.rgb = RGBColor(0x1A, 0x23, 0x7E)
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


def bullet(text, level=0):
    p = doc.add_paragraph(text, style='List Bullet')
    p.paragraph_format.left_indent = Cm(1.27 + level * 1.27)


def code_block(code):
    p = doc.add_paragraph()
    run = p.add_run(code)
    run.font.name = 'Consolas'
    run.font.size = Pt(9)
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), 'F0F0F8')
    shading.set(qn('w:val'), 'clear')
    p.paragraph_format.element.get_or_add_pPr().append(shading)


# ═══════════════════════════════════════════════════════════
# COVER PAGE
# ═══════════════════════════════════════════════════════════
for _ in range(5):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H AI Glasses\nShared Module')
run.font.size = Pt(32)
run.font.color.rgb = RGBColor(0x1A, 0x23, 0x7E)
run.bold = True

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('One Capture Pipeline for All Projects\nTechnical Specification v1.0')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x42, 0x42, 0x42)

doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | April 2026')
run.font.size = Pt(14)
run.bold = True
run.font.color.rgb = RGBColor(0x1A, 0x23, 0x7E)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Projects: Healthcare (HRT) + Lifetime (LRT) + Real Estate')
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0x75, 0x75, 0x75)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ═══════════════════════════════════════════════════════════
doc.add_heading('Table of Contents', level=1)
toc = [
    '1. Why a Shared Module',
    '2. What Is Shared vs What Is Different',
    '3. Hardware Decision',
    '4. Shared Capture Pipeline (6 Stages)',
    '5. Domain Plugins',
    '   5.1 Healthcare + Lifetime (HRT/LRT) Plugin',
    '   5.2 Real Estate Plugin',
    '6. Developer Tools and Tech Stack',
    '7. Architecture: How the Code Is Organized',
    '8. Development Plan',
    '9. Summary',
]
for item in toc:
    p = doc.add_paragraph(item)
    p.paragraph_format.space_after = Pt(2)
    if not item.startswith('   '):
        for run in p.runs:
            run.bold = True

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 1. WHY A SHARED MODULE
# ═══════════════════════════════════════════════════════════
doc.add_heading('1. Why a Shared Module', level=1)

doc.add_paragraph(
    'Triple-H has three projects that all need AI glasses for data collection:'
)

add_table(
    ['Project', 'What Glasses Collect', 'Team'],
    [
        ['Healthcare (HRT)', 'Food, medication, exercise, drinks \u2192 nutrition tracking', 'Healthcare team'],
        ['Lifetime (LRT)', 'Purchases, social events, mobility \u2192 life prediction', 'LRT team'],
        ['Real Estate', 'Rooms, defects, features \u2192 property cards + 3D models', 'Real Estate team'],
    ])

doc.add_paragraph()
doc.add_paragraph(
    'Without a shared module, each team builds their own glasses pipeline independently. '
    'This means:'
)

bullet('3\u00d7 the development cost \u2014 three teams solving the same camera, BLE, privacy, and upload problems')
bullet('3\u00d7 the hardware purchases \u2014 each team buys and tests different glasses')
bullet('3\u00d7 the maintenance \u2014 three separate codebases for the same fundamental task')
bullet('Inconsistent quality \u2014 one team\'s face blur might miss faces that another team\'s catches')

doc.add_paragraph()
doc.add_paragraph(
    'With a shared module, we build the glasses capture pipeline ONCE. Each project adds only '
    'a thin domain-specific plugin on top. Development cost drops by roughly 60%, and all three '
    'projects benefit from improvements to the shared layer.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 2. WHAT IS SHARED VS DIFFERENT
# ═══════════════════════════════════════════════════════════
doc.add_heading('2. What Is Shared vs What Is Different', level=1)

add_table(
    ['Component', 'Shared (one codebase)', 'Domain-Specific (per project)'],
    [
        ['AI Glasses Hardware', '\u2713 Same device for all', ''],
        ['Camera capture', '\u2713 Same capture logic', ''],
        ['BLE/WiFi transfer to phone', '\u2713 Same transport layer', ''],
        ['Face blur (YOLO-Face)', '\u2713 Same privacy model', ''],
        ['Audio capture + STT (Whisper)', '\u2713 Same speech-to-text', ''],
        ['IMU sensor data', '\u2713 Same motion tracking', ''],
        ['Phone \u2192 Cloud upload', '\u2713 Same upload mechanism', ''],
        ['Thumbnail generation (WebP)', '\u2713 Same compression', ''],
        ['Offline queue + retry', '\u2713 Same reliability layer', ''],
        ['Food recognition (MobileNetV2)', '', 'HRT/LRT only'],
        ['Nutrition lookup (MFDS/USDA)', '', 'HRT/LRT only'],
        ['Portion estimation', '', 'HRT/LRT only'],
        ['Meal/medication/exercise detection', '', 'HRT/LRT only'],
        ['Purchase/life event detection', '', 'LRT only'],
        ['Room classification (MobileNetV3)', '', 'Real Estate only'],
        ['Defect detection (YOLOv8n)', '', 'Real Estate only'],
        ['3D reconstruction (COLMAP/NeRF)', '', 'Real Estate only'],
        ['Property card generation', '', 'Real Estate only'],
    ])

doc.add_paragraph()
doc.add_paragraph(
    'Key insight: 9 shared components vs 9 domain-specific components. Without the shared module, '
    'all 18 components would be built separately per project (54 total). With it, only 18 total.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 3. HARDWARE DECISION
# ═══════════════════════════════════════════════════════════
doc.add_heading('3. Hardware Decision', level=1)

doc.add_heading('3.1 Recommended Glasses', level=2)

add_table(
    ['', 'Omi Glass Dev Kit', 'Google Android XR', 'Vuzix M400'],
    [
        ['Use', 'Development + Testing (NOW)', 'Production (2026 launch)', 'Real Estate (continuous video)'],
        ['Camera', '12MP, auto-capture', '12MP Sony IMX681', '13MP, 4K video'],
        ['Open SDK', 'Yes \u2014 100% open source', 'Yes \u2014 standard Android', 'Yes \u2014 full Android'],
        ['Battery', '1,150 mAh (best)', '155 mAh', '~2 hrs + external pack'],
        ['Price', '\u20a9749,000 (~$560)', '~$300\u2013600', '$1,500\u20132,500'],
        ['Available', 'NOW (worldwide)', '2026 later', 'NOW'],
        ['Best for', 'HRT/LRT (all-day wear)', 'HRT/LRT (production)', 'Real Estate (4K video for 3D)'],
        ['HIPAA', 'Yes (SOC 2 + HIPAA)', 'TBD', 'No'],
    ])

doc.add_paragraph()
doc.add_heading('3.2 Hardware Strategy Per Project', level=2)

add_table(
    ['Project', 'Development Phase', 'Production Phase'],
    [
        ['Healthcare (HRT/LRT)', 'Omi Glass Dev Kit (\u20a9749K)', 'Android XR Glasses (~$400\u2013600)'],
        ['Real Estate', 'Vuzix M400 ($1,500) \u2014 needs 4K video for 3D', 'Vuzix M400 or Android XR with external storage'],
    ])

doc.add_paragraph(
    'Why different glasses for Real Estate: Real Estate needs continuous 4K video recording for '
    '3D reconstruction (COLMAP/NeRF). This requires higher camera resolution and more storage than '
    'healthcare\'s event-triggered capture. Vuzix M400 provides 4K video + full Android stack + '
    'external battery pack for 4+ hour recordings.'
)

doc.add_paragraph(
    'Why same glasses for HRT/LRT: Both use the same event-triggered pipeline (food, medication, '
    'purchases). No continuous video needed \u2014 auto-capture photos every few seconds is sufficient.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 4. SHARED CAPTURE PIPELINE
# ═══════════════════════════════════════════════════════════
doc.add_heading('4. Shared Capture Pipeline (6 Stages)', level=1)

doc.add_paragraph(
    'This pipeline is identical across all three projects. The shared module handles Stages 1\u20134. '
    'Stage 5 is shared upload. Stage 6 is domain-specific processing.'
)

add_table(
    ['Stage', 'Where', 'What Happens', 'Shared?'],
    [
        ['1. Capture', 'Glasses', 'Camera captures photo/video + mic records audio + IMU tracks motion. Stored in circular buffer (glasses) or local storage (phone).', 'SHARED'],
        ['2. Event Trigger', 'Glasses', 'IMU detects activity (eating motion, room entry, walking). Camera activates. User can also tap or say wake word.', 'SHARED'],
        ['3. Privacy Filter', 'Phone', 'YOLO-Face detects and blurs all bystander faces. No identifiable faces leave the device. This runs BEFORE any domain processing.', 'SHARED'],
        ['4. Audio Processing', 'Phone', 'Whisper STT transcribes speech to text. Korean 25+ language support. Health conversations (HRT) or property observations (Real Estate).', 'SHARED'],
        ['5. Upload', 'Phone \u2192 Cloud', 'Structured JSON + thumbnail/media uploaded to Supabase/S3. Offline queue with retry for poor connectivity.', 'SHARED'],
        ['6. Domain Processing', 'Phone or Cloud', 'Project-specific ML models and business logic. Food recognition (HRT/LRT) or room classification + 3D (Real Estate).', 'DOMAIN-SPECIFIC'],
    ])

doc.add_paragraph()
doc.add_heading('4.1 Capture Modes', level=2)
doc.add_paragraph(
    'The shared module supports two capture modes, configurable per domain:'
)

add_table(
    ['Mode', 'How It Works', 'Used By', 'Data Volume'],
    [
        ['Event-Triggered', 'Auto-capture photo every few seconds. Only health/life relevant photos processed. Light on battery and storage.', 'HRT/LRT', '~10\u201330 MB/user/day'],
        ['Continuous Recording', 'Full video recording (H.265) during session. Heavy on battery and storage. Used for 3D reconstruction.', 'Real Estate', '~2\u20135 GB/session (15\u201330 min)'],
    ])

doc.add_paragraph(
    'The capture mode is set when the app starts a session. HRT/LRT sessions are "all-day" with '
    'event-triggered mode. Real Estate sessions are "per-property" with continuous recording mode.'
)

doc.add_heading('4.2 Processing Modes', level=2)

add_table(
    ['Mode', 'When Processing Happens', 'Used By', 'Advantage'],
    [
        ['Real-Time', 'Each event processed immediately on phone. User gets instant notification.', 'HRT/LRT (default)', 'Immediate feedback, emergency alerts'],
        ['Batch (End of Day)', 'All day\'s data processed at night while phone charges. User gets morning report.', 'HRT/LRT (optional, boss\'s preference)', 'Better battery, bigger models, cheaper cloud'],
        ['Post-Session', 'Processing starts after recording session ends. Results in 10\u201315 minutes.', 'Real Estate', 'Heavy GPU processing (3D) happens in cloud after upload'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 5. DOMAIN PLUGINS
# ═══════════════════════════════════════════════════════════
doc.add_heading('5. Domain Plugins', level=1)

doc.add_heading('5.1 Healthcare + Lifetime (HRT/LRT) Plugin', level=2)

doc.add_paragraph('This plugin processes glasses data for health monitoring and life event tracking.')

add_table(
    ['Component', 'Model / Tool', 'Size', 'What It Does'],
    [
        ['Food Classification', 'MobileNetV2-Food (INT8 TFLite)', '~8 MB', 'Identifies food name from photo (2024 categories)'],
        ['Portion Estimation', 'YOLOv8n (TFLite)', '~12 MB', 'Detects food area, estimates small/medium/large'],
        ['Nutrition Lookup', 'MFDS SQLite (275K) + USDA SQLite (13K)', '~170 MB', 'Maps food name \u2192 calories, protein, fat, carbs, sodium'],
        ['Medication Detection', 'OCR + keyword matching', '~5 MB', 'Reads medication labels, logs adherence'],
        ['Exercise Classification', 'IMU activity classifier', '~1 MB', 'Detects walking, running, gym exercises from motion'],
        ['Health Audio', 'MedASR (cloud fallback)', 'Cloud', 'Healthcare-specific STT (4.6% WER vs Whisper 25% on medical terms)'],
    ])

doc.add_paragraph()
doc.add_paragraph('Data flow:')
bullet('Glasses capture \u2192 Phone receives photo \u2192 Face blur \u2192 Food classify \u2192 Nutrition lookup \u2192 Upload to HRT/LRT Supabase')
bullet('Tables written: user_activity_event, user_lifestyle (HRT) + personal_lrt_activities (LRT)')
bullet('Events: meal, drink, medication, exercise, purchase, social, mobility')

doc.add_heading('5.2 Real Estate Plugin', level=2)

doc.add_paragraph('This plugin processes glasses data for property documentation and 3D reconstruction.')

add_table(
    ['Component', 'Model / Tool', 'Size', 'What It Does'],
    [
        ['Room Classification', 'MobileNetV3 (Places365)', '~8 MB', 'Identifies room type: living room, kitchen, bathroom, bedroom'],
        ['Object/Defect Detection', 'YOLOv8n (custom trained)', '~6 MB', 'Detects windows, sinks, storage, wall stains, cracks'],
        ['Voice Transcription', 'Whisper (shared)', 'Shared', 'Transcribes realtor observations into searchable text'],
        ['Image Embeddings', 'OpenCLIP', 'Cloud', 'Generates vector embeddings for semantic property search'],
        ['3D Reconstruction', 'COLMAP + Nerfstudio', 'Cloud GPU', 'Structure-from-Motion \u2192 NeRF/Gaussian Splatting \u2192 3D model'],
        ['Property Description', 'LLaVA / GPT-4o', 'Cloud', 'Auto-generates listing text from photos + transcripts'],
    ])

doc.add_paragraph()
doc.add_paragraph('Data flow:')
bullet('Glasses record continuous video \u2192 Phone queues for upload \u2192 Face blur \u2192 Upload to Real Estate Supabase')
bullet('Cloud: Extract key frames \u2192 Room classify \u2192 Defect detect \u2192 3D reconstruct \u2192 Property card generated')
bullet('Tables written: property, capture_session, media_asset, scene_chunk, observation, transcript, reconstruction')
bullet('Target: Property card + navigable 3D draft within 10 minutes of session end')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 6. DEVELOPER TOOLS AND TECH STACK
# ═══════════════════════════════════════════════════════════
doc.add_heading('6. Developer Tools and Tech Stack', level=1)

doc.add_heading('6.1 Shared Module Stack', level=2)

add_table(
    ['Layer', 'Technology', 'Why This Choice'],
    [
        ['Glasses SDK', 'Omi Glass: Open-source firmware (ESP32 Arduino)\nAndroid XR: Jetpack XR SDK (Kotlin)\nVuzix: Android SDK', 'Open SDK required for camera access. All three support custom apps.'],
        ['Phone App Framework', 'React Native (TypeScript) or Kotlin (Android native)', 'Cross-platform for HRT/LRT. Native Android for Real Estate (heavier processing).'],
        ['ML Runtime (Phone)', 'TensorFlow Lite + GPU delegate', 'Runs all edge models on phone GPU/NPU. Standard across Android/iOS.'],
        ['Face Blur Model', 'YOLO-Face (INT8 TFLite, ~3 MB)', 'Fast (<5ms/frame), 95%+ face detection. Runs before any domain processing.'],
        ['Speech-to-Text', 'Whisper-tiny (phone, ~39 MB) + MedASR (cloud fallback)', 'Whisper for general STT. MedASR for healthcare-specific terms.'],
        ['Video Codec', 'H.265/HEVC (capture) \u2192 AV1 (archival)', 'Universal hardware encoder support. 40\u201350% savings over H.264.'],
        ['Image Format', 'WebP (thumbnails, quality 80)', '30% smaller than JPEG at same quality.'],
        ['Audio Codec', 'Opus (24\u201332 Kbps mono)', 'Royalty-free, excellent at low bitrates.'],
        ['Upload Client', 'httpx (Python) / fetch (TypeScript)', 'Async upload with offline queue and retry.'],
        ['Backend API', 'FastAPI (Python)', 'Lightweight, async, already used by HRT project.'],
        ['Database', 'Supabase (PostgreSQL + pgvector + Auth + Storage)', 'Each project has its own Supabase project. Shared module uploads to whichever project the domain plugin specifies.'],
        ['Object Storage', 'Supabase Storage / AWS S3 (4-tier lifecycle)', 'Thumbnails + selective clips. Tiered: hot \u2192 warm \u2192 cold \u2192 archive.'],
    ])

doc.add_heading('6.2 Domain-Specific Stacks', level=2)

add_table(
    ['', 'HRT/LRT', 'Real Estate'],
    [
        ['Food ML', 'MobileNetV2-Food (TFLite)', 'N/A'],
        ['Object ML', 'N/A', 'YOLOv8n custom-trained on property defects'],
        ['Room ML', 'N/A', 'MobileNetV3 (Places365)'],
        ['3D Pipeline', 'N/A', 'COLMAP + Nerfstudio (cloud GPU)'],
        ['Embeddings', 'pgvector (health multimodal)', 'OpenCLIP + pgvector (property search)'],
        ['Database', 'HRT/LRT unified Supabase (27 tables)', 'Real Estate Supabase (7 tables)'],
        ['LLM', 'Qwen 2.5 7B / Meditron-70B (health agent)', 'LLaVA / GPT-4o (listing generation)'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 7. ARCHITECTURE
# ═══════════════════════════════════════════════════════════
doc.add_heading('7. Architecture: How the Code Is Organized', level=1)

doc.add_heading('7.1 Module Structure', level=2)

code_block(
    'triple-h-glasses/                          \u2190 Shared module (Git repo)\n'
    '\u251c\u2500\u2500 core/                                    \u2190 Shared capture pipeline\n'
    '\u2502   \u251c\u2500\u2500 capture/                              \u2190 Camera + audio + IMU capture\n'
    '\u2502   \u251c\u2500\u2500 privacy/                              \u2190 YOLO-Face blur\n'
    '\u2502   \u251c\u2500\u2500 transport/                            \u2190 BLE/WiFi glasses \u2192 phone\n'
    '\u2502   \u251c\u2500\u2500 stt/                                  \u2190 Whisper STT\n'
    '\u2502   \u251c\u2500\u2500 upload/                               \u2190 Phone \u2192 Supabase/S3\n'
    '\u2502   \u251c\u2500\u2500 queue/                                \u2190 Offline queue + retry\n'
    '\u2502   \u2514\u2500\u2500 models/                               \u2190 Shared TFLite models (YOLO-Face, Whisper)\n'
    '\u2502\n'
    '\u251c\u2500\u2500 plugins/                                 \u2190 Domain-specific processing\n'
    '\u2502   \u251c\u2500\u2500 healthcare/                           \u2190 HRT/LRT plugin\n'
    '\u2502   \u2502   \u251c\u2500\u2500 food_classifier.py                \u2190 MobileNetV2-Food\n'
    '\u2502   \u2502   \u251c\u2500\u2500 portion_estimator.py              \u2190 YOLOv8n portion\n'
    '\u2502   \u2502   \u251c\u2500\u2500 nutrition_lookup.py               \u2190 MFDS/USDA SQLite\n'
    '\u2502   \u2502   \u251c\u2500\u2500 medication_detector.py            \u2190 OCR + keyword\n'
    '\u2502   \u2502   \u2514\u2500\u2500 models/                           \u2190 HRT/LRT specific TFLite models\n'
    '\u2502   \u2502\n'
    '\u2502   \u2514\u2500\u2500 realestate/                           \u2190 Real Estate plugin\n'
    '\u2502       \u251c\u2500\u2500 room_classifier.py                \u2190 MobileNetV3 Places365\n'
    '\u2502       \u251c\u2500\u2500 defect_detector.py                \u2190 YOLOv8n custom\n'
    '\u2502       \u251c\u2500\u2500 reconstruction_client.py          \u2190 COLMAP/NeRF API client\n'
    '\u2502       \u2514\u2500\u2500 models/                           \u2190 Real Estate specific TFLite models\n'
    '\u2502\n'
    '\u251c\u2500\u2500 apps/                                    \u2190 Phone applications\n'
    '\u2502   \u251c\u2500\u2500 healthcare_app/                       \u2190 React Native app for HRT/LRT\n'
    '\u2502   \u2514\u2500\u2500 realestate_app/                       \u2190 Android native app for Real Estate\n'
    '\u2502\n'
    '\u2514\u2500\u2500 docs/                                    \u2190 Documentation'
)

doc.add_paragraph()
doc.add_heading('7.2 How a Domain Plugin Works', level=2)

doc.add_paragraph(
    'Each domain plugin implements a simple interface. The shared module calls the plugin after '
    'completing Stages 1\u20135 (capture, trigger, privacy, STT, upload). The plugin receives the '
    'processed data and returns domain-specific results.'
)

code_block(
    'class DomainPlugin:\n'
    '    """Interface that every domain plugin must implement."""\n'
    '\n'
    '    def get_capture_mode(self) -> str:\n'
    '        """Return "event_triggered" or "continuous_recording"."""\n'
    '\n'
    '    def process_frame(self, frame, audio_text, metadata) -> dict:\n'
    '        """Process one captured frame. Return structured event data."""\n'
    '\n'
    '    def get_upload_config(self) -> dict:\n'
    '        """Return Supabase URL, table names, storage bucket."""\n'
    '\n'
    '    def on_batch_complete(self, events) -> dict:\n'
    '        """Called at end of day/session. Return daily summary."""'
)

doc.add_paragraph()
doc.add_paragraph(
    'The shared module does NOT need to know anything about food, medication, rooms, or defects. '
    'It captures, blurs faces, transcribes audio, and uploads. The plugin interprets what the '
    'captured data means for its specific domain.'
)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 8. DEVELOPMENT PLAN
# ═══════════════════════════════════════════════════════════
doc.add_heading('8. Development Plan', level=1)

doc.add_heading('8.1 Phase 1: Shared Core (Weeks 1\u20134)', level=2)
doc.add_paragraph('All three teams collaborate on the shared capture pipeline.')

add_table(
    ['Week', 'Deliverable', 'Owner'],
    [
        ['1', 'Glasses connection service (Omi + Android XR + Vuzix adapters)', 'All teams together'],
        ['1', 'Camera capture module (event-triggered + continuous modes)', 'All teams together'],
        ['2', 'BLE/WiFi transport layer (glasses \u2192 phone)', 'All teams together'],
        ['2', 'YOLO-Face privacy filter (face blur on phone)', 'Healthcare team'],
        ['3', 'Whisper STT integration (phone-side + cloud fallback)', 'Healthcare team'],
        ['3', 'Upload module (Supabase Storage + offline queue + retry)', 'LRT team'],
        ['4', 'Integration testing: capture \u2192 blur \u2192 STT \u2192 upload end-to-end', 'All teams together'],
        ['4', 'Plugin interface defined and documented', 'All teams together'],
    ])

doc.add_heading('8.2 Phase 2: Domain Plugins (Weeks 5\u20138)', level=2)
doc.add_paragraph('Each team builds their domain-specific plugin independently.')

add_table(
    ['Week', 'Healthcare (HRT/LRT) Plugin', 'Real Estate Plugin'],
    [
        ['5', 'MobileNetV2-Food integration + testing', 'MobileNetV3 room classifier integration'],
        ['6', 'Nutrition lookup (MFDS/USDA SQLite)', 'YOLOv8n defect detector training on property images'],
        ['7', 'Medication OCR + exercise IMU classifier', '3D reconstruction pipeline (COLMAP + Nerfstudio)'],
        ['8', 'Full pipeline test: glasses \u2192 food detect \u2192 nutrition \u2192 Supabase', 'Full pipeline test: glasses \u2192 video \u2192 3D model \u2192 property card'],
    ])

doc.add_heading('8.3 Phase 3: Phone Apps (Weeks 9\u201312)', level=2)

add_table(
    ['Week', 'Healthcare App', 'Real Estate App'],
    [
        ['9\u201310', 'React Native: home screen, event feed, daily summary, food correction UI', 'Android native: capture controls, room timeline, defect review'],
        ['11\u201312', 'Testing with Omi Glass: real meals, real medications, real exercise', 'Testing with Vuzix M400: real property walkthroughs, 3D output quality'],
    ])

doc.add_page_break()

# ═══════════════════════════════════════════════════════════
# 9. SUMMARY
# ═══════════════════════════════════════════════════════════
doc.add_heading('9. Summary', level=1)

add_table(
    ['Question', 'Answer'],
    [
        ['What is the shared module?', 'One codebase for glasses capture, face blur, STT, and upload \u2014 used by all three projects'],
        ['What is NOT shared?', 'Domain-specific ML models and business logic (food vs rooms vs defects)'],
        ['What glasses do we use?', 'Omi Glass (dev/testing, HRT/LRT), Vuzix M400 (Real Estate 4K video), Android XR (production 2026)'],
        ['How does each project use it?', 'Shared module captures data. Domain plugin processes it. Each project has its own Supabase.'],
        ['How is code organized?', 'triple-h-glasses/ repo with core/ (shared) and plugins/ (domain-specific)'],
        ['Development time?', '12 weeks total: 4 weeks shared core + 4 weeks plugins + 4 weeks apps'],
        ['Cost savings?', '~60% less development than three separate pipelines'],
        ['Who owns what?', 'Shared core: all teams. Healthcare plugin: HRT/LRT team. Real Estate plugin: RE team.'],
    ])

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Triple-H Co., Ltd. | AI Glasses Shared Module v1.0 | April 2026')
run.font.size = Pt(9)
run.font.color.rgb = RGBColor(0x75, 0x75, 0x75)

# Save
output_path = r'C:\Users\tripleh\projects\healthcare-ai-agent\docs\Triple-H_AI_Glasses_Shared_Module_v1.docx'
doc.save(output_path)
print(f'Saved: {output_path}')
