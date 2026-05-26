"""Dashboard visualization — modern professional design."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Healthcare AI Agent</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', system-ui, sans-serif;
            background: #f8f9fb;
            color: #1e293b;
            -webkit-font-smoothing: antialiased;
        }

        /* ── Sidebar ── */
        .sidebar {
            position: fixed; left: 0; top: 0; bottom: 0; width: 240px;
            background: white; border-right: 1px solid #e8ecf1;
            padding: 24px 16px; z-index: 10;
            display: flex; flex-direction: column;
        }
        .sidebar-logo {
            display: flex; align-items: center; gap: 10px;
            padding: 0 8px 24px; border-bottom: 1px solid #f1f3f5;
        }
        .sidebar-logo .icon {
            width: 36px; height: 36px; background: linear-gradient(135deg, #0ea5e9, #06b6d4);
            border-radius: 10px; display: flex; align-items: center; justify-content: center;
            color: white; font-size: 18px; font-weight: 700;
        }
        .sidebar-logo span { font-weight: 700; font-size: 15px; color: #0f172a; }
        .sidebar-logo small { display: block; font-size: 10px; color: #94a3b8; font-weight: 400; }

        .sidebar-nav { margin-top: 20px; flex: 1; }
        .nav-section { font-size: 10px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; padding: 0 12px; margin: 16px 0 8px; }
        .nav-item {
            display: flex; align-items: center; gap: 10px;
            padding: 9px 12px; border-radius: 8px; cursor: pointer;
            font-size: 13px; color: #64748b; transition: all 0.15s;
            margin-bottom: 2px;
        }
        .nav-item:hover { background: #f1f5f9; color: #1e293b; }
        .nav-item.active { background: #eff6ff; color: #2563eb; font-weight: 500; }
        .nav-item .dot { width: 6px; height: 6px; border-radius: 50%; }
        .dot-green { background: #22c55e; }
        .dot-yellow { background: #eab308; }
        .dot-gray { background: #d1d5db; }

        .sidebar-footer { padding-top: 16px; border-top: 1px solid #f1f3f5; }
        .sidebar-footer small { font-size: 10px; color: #94a3b8; display: block; padding: 0 12px; line-height: 1.6; }

        /* ── Main Content ── */
        .main { margin-left: 240px; padding: 28px 32px; }

        .top-bar {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 28px;
        }
        .top-bar h1 { font-size: 22px; font-weight: 700; color: #0f172a; }
        .top-bar .meta { display: flex; align-items: center; gap: 16px; }
        .status-pill {
            display: flex; align-items: center; gap: 6px;
            padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 500;
        }
        .status-online { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
        .status-dot { width: 7px; height: 7px; background: #22c55e; border-radius: 50%; animation: pulse 2s infinite; }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
        .date-text { font-size: 13px; color: #94a3b8; }

        /* ── Cards ── */
        .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
        .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
        .grid-2-1 { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 24px; }
        .grid-1-2 { display: grid; grid-template-columns: 1fr 2fr; gap: 16px; margin-bottom: 24px; }

        .card {
            background: white; border-radius: 12px; padding: 20px;
            border: 1px solid #e8ecf1;
            transition: box-shadow 0.2s;
        }
        .card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.04); }
        .card-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 16px;
        }
        .card-header h3 { font-size: 14px; font-weight: 600; color: #374151; }
        .card-header .badge {
            font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 6px;
        }
        .badge-blue { background: #eff6ff; color: #2563eb; }
        .badge-green { background: #f0fdf4; color: #16a34a; }
        .badge-amber { background: #fffbeb; color: #d97706; }

        /* ── Stat Cards ── */
        .stat-card { padding: 20px; }
        .stat-label { font-size: 12px; color: #94a3b8; font-weight: 500; margin-bottom: 8px; }
        .stat-row { display: flex; align-items: baseline; gap: 8px; }
        .stat-value { font-size: 32px; font-weight: 700; color: #0f172a; line-height: 1; }
        .stat-unit { font-size: 13px; color: #94a3b8; }
        .stat-sub { font-size: 11px; color: #94a3b8; margin-top: 8px; line-height: 1.5; }
        .stat-trend { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; font-weight: 500; padding: 2px 6px; border-radius: 4px; }
        .trend-up { background: #f0fdf4; color: #16a34a; }
        .trend-neutral { background: #f8fafc; color: #64748b; }

        /* ── Architecture Flow ── */
        .arch-flow {
            display: flex; align-items: center; gap: 0; padding: 16px 0;
            overflow-x: auto;
        }
        .arch-node {
            flex: 1; min-width: 140px; text-align: center;
            padding: 16px 12px; border-radius: 10px; position: relative;
        }
        .arch-node .icon-circle {
            width: 44px; height: 44px; border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 10px; font-size: 20px;
        }
        .arch-node h4 { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
        .arch-node p { font-size: 10px; color: #94a3b8; line-height: 1.4; }
        .arch-arrow { color: #d1d5db; font-size: 16px; margin: 0 2px; flex-shrink: 0; }

        .n1 .icon-circle { background: #fef3c7; }
        .n2 .icon-circle { background: #dbeafe; }
        .n3 .icon-circle { background: #e0e7ff; }
        .n4 .icon-circle { background: #fce7f3; }
        .n5 .icon-circle { background: #d1fae5; }

        /* ── Table ── */
        .data-table { width: 100%; border-collapse: separate; border-spacing: 0; }
        .data-table th {
            text-align: left; padding: 10px 14px; font-size: 11px; font-weight: 600;
            color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px;
            border-bottom: 1px solid #f1f3f5; background: #fafbfc;
        }
        .data-table th:first-child { border-radius: 8px 0 0 0; }
        .data-table th:last-child { border-radius: 0 8px 0 0; }
        .data-table td { padding: 10px 14px; font-size: 13px; border-bottom: 1px solid #f8f9fb; }
        .data-table tr:hover td { background: #f8fafc; }
        .pill { padding: 3px 10px; border-radius: 6px; font-size: 11px; font-weight: 500; }
        .pill-blue { background: #eff6ff; color: #3b82f6; }
        .pill-emerald { background: #ecfdf5; color: #059669; }
        .pill-rose { background: #fff1f2; color: #e11d48; }
        .pill-violet { background: #f5f3ff; color: #7c3aed; }
        .pill-amber { background: #fffbeb; color: #d97706; }

        /* ── Progress ── */
        .progress-track { background: #f1f5f9; border-radius: 6px; height: 6px; margin-top: 6px; }
        .progress-fill { height: 100%; border-radius: 6px; transition: width 0.6s ease; }

        /* ── Timeline ── */
        .timeline-item {
            display: flex; gap: 14px; padding: 12px 0;
            border-bottom: 1px solid #f8f9fb;
        }
        .timeline-item:last-child { border: none; }
        .tl-icon {
            width: 32px; height: 32px; border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            font-size: 14px; flex-shrink: 0;
        }
        .tl-done { background: #f0fdf4; }
        .tl-active { background: #fffbeb; }
        .tl-pending { background: #f8fafc; }
        .tl-text h4 { font-size: 13px; font-weight: 500; }
        .tl-text p { font-size: 11px; color: #94a3b8; margin-top: 2px; }

        /* ── Disease Cards ── */
        .disease-card {
            background: white; border-radius: 10px; padding: 14px;
            border: 1px solid #e8ecf1;
        }
        .disease-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
        .disease-icon { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; }
        .disease-name { font-size: 13px; font-weight: 600; }
        .disease-factors { font-size: 11px; color: #94a3b8; }
        .factor-bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin-top: 8px; gap: 1px; }
        .factor-seg { height: 100%; transition: width 0.3s; }

        /* ── Chart Container ── */
        .chart-container { position: relative; height: 220px; }
        .chart-container-sm { position: relative; height: 180px; }

        /* ── Cost Comparison ── */
        .cost-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f8f9fb; }
        .cost-item:last-child { border: none; }
        .cost-label { font-size: 13px; color: #64748b; }
        .cost-value { font-size: 14px; font-weight: 600; }
        .cost-save { font-size: 11px; color: #16a34a; background: #f0fdf4; padding: 2px 8px; border-radius: 4px; }

        /* ── Responsive ── */
        @media (max-width: 1200px) { .grid-4 { grid-template-columns: repeat(2, 1fr); } }
    </style>
</head>
<body>
    <!-- Sidebar -->
    <div class="sidebar">
        <div class="sidebar-logo">
            <div class="icon">H</div>
            <div>
                <span>Health Agent</span>
                <small>Triple-H Co., Ltd.</small>
            </div>
        </div>
        <div class="sidebar-nav">
            <div class="nav-section">Overview</div>
            <div class="nav-item active">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>
                Dashboard
            </div>

            <div class="nav-section">Infrastructure</div>
            <div class="nav-item"><div class="dot dot-green"></div> Database (14 tables)</div>
            <div class="nav-item"><div class="dot dot-green"></div> API (23 endpoints)</div>
            <div class="nav-item"><div class="dot dot-gray"></div> Kafka Pipeline</div>
            <div class="nav-item"><div class="dot dot-gray"></div> Airflow DAGs</div>

            <div class="nav-section">AI Models</div>
            <div class="nav-item"><div class="dot dot-yellow"></div> LSTM-Transformer</div>
            <div class="nav-item"><div class="dot dot-gray"></div> Qwen 2.5 7B</div>
            <div class="nav-item"><div class="dot dot-gray"></div> Food Recognition</div>

            <div class="nav-section">Agents</div>
            <div class="nav-item"><div class="dot dot-gray"></div> HealthCore Agent</div>
            <div class="nav-item"><div class="dot dot-gray"></div> Nutrition Agent</div>
            <div class="nav-item"><div class="dot dot-gray"></div> Exercise Agent</div>
            <div class="nav-item"><div class="dot dot-gray"></div> Glasses Agent</div>
        </div>
        <div class="sidebar-footer">
            <small>Patent 10-2025-0145274<br>v0.1.0 &middot; April 2026</small>
        </div>
    </div>

    <!-- Main -->
    <div class="main">
        <div class="top-bar">
            <h1>Project Dashboard</h1>
            <div class="meta">
                <span class="date-text" id="currentDate"></span>
                <div class="status-pill status-online"><div class="status-dot"></div> System Online</div>
            </div>
        </div>

        <!-- Stat Cards -->
        <div class="grid-4">
            <div class="card stat-card">
                <div class="stat-label">Database Tables</div>
                <div class="stat-row">
                    <div class="stat-value">14</div>
                    <span class="stat-trend trend-up">All deployed</span>
                </div>
                <div class="stat-sub">4 Standard + 10 Personal HRT<br>42 indexes &middot; 24 RLS policies</div>
            </div>
            <div class="card stat-card">
                <div class="stat-label">API Endpoints</div>
                <div class="stat-row">
                    <div class="stat-value">23</div>
                    <span class="stat-trend trend-up">Operational</span>
                </div>
                <div class="stat-sub">REST API with Swagger docs<br>Users, Biometric, Events, Simulation</div>
            </div>
            <div class="card stat-card">
                <div class="stat-label">Training Records</div>
                <div class="stat-row">
                    <div class="stat-value">79.5K</div>
                </div>
                <div class="stat-sub">KNHANES 2021-2024<br>Diagnosis + Nutrition + Lifestyle</div>
            </div>
            <div class="card stat-card">
                <div class="stat-label">Medical QA Data</div>
                <div class="stat-row">
                    <div class="stat-value">17.3K</div>
                </div>
                <div class="stat-sub">AI Hub Big 5 Hospital QA pairs<br>+ 52K medical corpus segments</div>
            </div>
        </div>

        <!-- Architecture -->
        <div class="card" style="margin-bottom: 24px;">
            <div class="card-header">
                <h3>System Architecture</h3>
                <span class="badge badge-blue">5-Layer Pipeline</span>
            </div>
            <div class="arch-flow">
                <div class="arch-node n1">
                    <div class="icon-circle">&#x1F453;</div>
                    <h4>Edge Device</h4>
                    <p>AI Glasses &middot; Watch<br>CGM Sensor</p>
                </div>
                <div class="arch-arrow">&rarr;</div>
                <div class="arch-node n2">
                    <div class="icon-circle">&#x26A1;</div>
                    <h4>FastAPI Backend</h4>
                    <p>23 REST APIs<br>Data Ingestion</p>
                </div>
                <div class="arch-arrow">&rarr;</div>
                <div class="arch-node n3">
                    <div class="icon-circle">&#x1F5C4;</div>
                    <h4>Supabase DB</h4>
                    <p>PostgreSQL 17<br>14 Tables + pgvector</p>
                </div>
                <div class="arch-arrow">&rarr;</div>
                <div class="arch-node n4">
                    <div class="icon-circle">&#x1F9E0;</div>
                    <h4>AI Engine</h4>
                    <p>LSTM-Transformer<br>Qwen 2.5 7B</p>
                </div>
                <div class="arch-arrow">&rarr;</div>
                <div class="arch-node n5">
                    <div class="icon-circle">&#x1F916;</div>
                    <h4>Health Agent</h4>
                    <p>OpenClaw<br>7 Agents &middot; 12 Skills</p>
                </div>
            </div>
        </div>

        <!-- Charts Row -->
        <div class="grid-2">
            <!-- Training Data Chart -->
            <div class="card">
                <div class="card-header">
                    <h3>Training Data Distribution</h3>
                    <span class="badge badge-green">KNHANES + AI Hub</span>
                </div>
                <div class="chart-container">
                    <canvas id="trainingChart"></canvas>
                </div>
            </div>

            <!-- Disease Coverage Donut -->
            <div class="card">
                <div class="card-header">
                    <h3>Disease Risk Models</h3>
                    <span class="badge badge-blue">8 Diseases</span>
                </div>
                <div class="chart-container">
                    <canvas id="diseaseChart"></canvas>
                </div>
            </div>
        </div>

        <!-- DB + Roadmap -->
        <div class="grid-2">
            <!-- Database Schema -->
            <div class="card">
                <div class="card-header">
                    <h3>Database Schema</h3>
                    <span class="badge badge-green">14 Tables</span>
                </div>
                <table class="data-table">
                    <thead><tr><th>Table</th><th>Type</th><th>Records</th><th>Status</th></tr></thead>
                    <tbody>
                        <tr><td>std_population_category</td><td><span class="pill pill-blue">Standard</span></td><td>26</td><td><span class="pill pill-emerald">Populated</span></td></tr>
                        <tr><td>std_diagnosis_norm</td><td><span class="pill pill-blue">Standard</span></td><td>298</td><td><span class="pill pill-emerald">Populated</span></td></tr>
                        <tr><td>std_lifestyle_plan</td><td><span class="pill pill-blue">Standard</span></td><td>56</td><td><span class="pill pill-emerald">Populated</span></td></tr>
                        <tr><td>std_disease_risk_weight</td><td><span class="pill pill-blue">Standard</span></td><td>44</td><td><span class="pill pill-emerald">Populated</span></td></tr>
                        <tr><td>users</td><td><span class="pill pill-violet">Personal</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>user_biometric</td><td><span class="pill pill-violet">Personal</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>user_diagnosis</td><td><span class="pill pill-violet">Personal</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>user_lifestyle</td><td><span class="pill pill-violet">Personal</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>user_activity_event</td><td><span class="pill pill-rose">AI Glasses</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>user_health_level</td><td><span class="pill pill-violet">Personal</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>user_multimodal</td><td><span class="pill pill-violet">Personal</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>agent_conversation_log</td><td><span class="pill pill-amber">Agent</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                        <tr><td>simulation_result</td><td><span class="pill pill-amber">Agent</span></td><td>&mdash;</td><td><span class="pill pill-emerald">Ready</span></td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Roadmap -->
            <div class="card">
                <div class="card-header">
                    <h3>Development Roadmap</h3>
                    <span class="badge badge-amber">21% Complete</span>
                </div>
                <div style="margin-bottom: 16px;">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; margin-bottom: 4px;">
                        <span>Overall Progress</span><span style="color: #2563eb; font-weight: 600;">3 / 14 phases</span>
                    </div>
                    <div class="progress-track"><div class="progress-fill" style="width: 21.4%; background: linear-gradient(90deg, #3b82f6, #06b6d4);"></div></div>
                </div>
                <div>
                    <div class="timeline-item">
                        <div class="tl-icon tl-done">&#x2705;</div>
                        <div class="tl-text"><h4>Phase 0: Foundation</h4><p>Supabase DB (14 tables) + FastAPI (23 endpoints)</p></div>
                    </div>
                    <div class="timeline-item">
                        <div class="tl-icon tl-done">&#x2705;</div>
                        <div class="tl-text"><h4>Phase 0.5: Standard HRT Data</h4><p>424 reference records (norms, plans, risk weights)</p></div>
                    </div>
                    <div class="timeline-item">
                        <div class="tl-icon tl-done">&#x2705;</div>
                        <div class="tl-text"><h4>Data Collection</h4><p>KNHANES 79.5K + AI Hub 17.3K QA + 52K corpus</p></div>
                    </div>
                    <div class="timeline-item">
                        <div class="tl-icon tl-active">&#x1F504;</div>
                        <div class="tl-text"><h4>Phase 4: LSTM-Transformer</h4><p>Health prediction model &mdash; training on RTX 4070 SUPER</p></div>
                    </div>
                    <div class="timeline-item">
                        <div class="tl-icon tl-pending">&#x23F3;</div>
                        <div class="tl-text"><h4>Phase 6: LLM Fine-tuning</h4><p>Qwen 2.5 7B + Llama 3.1 8B (SFT + DPO)</p></div>
                    </div>
                    <div class="timeline-item">
                        <div class="tl-icon tl-pending">&#x23F3;</div>
                        <div class="tl-text"><h4>Phase 7: OpenClaw Agents</h4><p>7 health agents with 12 skills</p></div>
                    </div>
                    <div class="timeline-item">
                        <div class="tl-icon tl-pending">&#x23F3;</div>
                        <div class="tl-text"><h4>Phase 11-13: Launch</h4><p>100 &rarr; 1K &rarr; 10K &rarr; 100K users</p></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Cost + Disease Detail -->
        <div class="grid-2">
            <!-- Cost Model -->
            <div class="card">
                <div class="card-header">
                    <h3>Cost Model at Scale</h3>
                    <span class="badge badge-green">86% savings vs API</span>
                </div>
                <div class="chart-container-sm">
                    <canvas id="costChart"></canvas>
                </div>
                <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #f1f3f5;">
                    <div class="cost-item">
                        <span class="cost-label">Commercial API (Claude/GPT)</span>
                        <span class="cost-value" style="color: #ef4444;">$250K/mo</span>
                    </div>
                    <div class="cost-item">
                        <span class="cost-label">Our approach (self-hosted fine-tuned)</span>
                        <div><span class="cost-value" style="color: #16a34a;">$36K/mo</span> <span class="cost-save">-86%</span></div>
                    </div>
                </div>
            </div>

            <!-- QA by Department -->
            <div class="card">
                <div class="card-header">
                    <h3>Medical QA by Department</h3>
                    <span class="badge badge-blue">AI Hub Big 5 Hospitals</span>
                </div>
                <div class="chart-container-sm">
                    <canvas id="qaChart"></canvas>
                </div>
                <div style="margin-top: 12px; font-size: 11px; color: #94a3b8; text-align: center;">
                    Source: Seoul National Univ, Samsung Seoul, Severance, Seoul St. Mary's, Boramae Hospital
                </div>
            </div>
        </div>

        <!-- Disease Risk Models Detail -->
        <div class="card" style="margin-bottom: 24px;">
            <div class="card-header">
                <h3>Disease Risk Factor Weights</h3>
                <span class="badge badge-blue">ICD-11 Classification</span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #fef2f2;">&#x1FA78;</div>
                        <div><div class="disease-name">Type 2 Diabetes</div><div class="disease-factors">6 factors &middot; ICD 5A11</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:30%; background:#ef4444;" title="FBG 30%"></div>
                        <div class="factor-seg" style="width:25%; background:#f97316;" title="HbA1c 25%"></div>
                        <div class="factor-seg" style="width:20%; background:#eab308;" title="BMI 20%"></div>
                        <div class="factor-seg" style="width:10%; background:#84cc16;" title="WC 10%"></div>
                        <div class="factor-seg" style="width:10%; background:#22c55e;" title="TG 10%"></div>
                        <div class="factor-seg" style="width:5%; background:#06b6d4;" title="BF 5%"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">FBG 30% &middot; HbA1c 25% &middot; BMI 20%</div>
                </div>
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #fef3c7;">&#x2764;</div>
                        <div><div class="disease-name">Heart Disease</div><div class="disease-factors">8 factors &middot; ICD BA80</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:20%; background:#ef4444;"></div>
                        <div class="factor-seg" style="width:20%; background:#f97316;"></div>
                        <div class="factor-seg" style="width:15%; background:#eab308;"></div>
                        <div class="factor-seg" style="width:10%; background:#84cc16;"></div>
                        <div class="factor-seg" style="width:10%; background:#22c55e;"></div>
                        <div class="factor-seg" style="width:10%; background:#06b6d4;"></div>
                        <div class="factor-seg" style="width:10%; background:#8b5cf6;"></div>
                        <div class="factor-seg" style="width:5%; background:#d1d5db;"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">SBP 20% &middot; LDL 20% &middot; HDL 15%</div>
                </div>
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #ede9fe;">&#x1F4A8;</div>
                        <div><div class="disease-name">Hypertension</div><div class="disease-factors">4 factors &middot; ICD BA00</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:40%; background:#7c3aed;"></div>
                        <div class="factor-seg" style="width:30%; background:#a78bfa;"></div>
                        <div class="factor-seg" style="width:15%; background:#c4b5fd;"></div>
                        <div class="factor-seg" style="width:15%; background:#ddd6fe;"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">SBP 40% &middot; DBP 30% &middot; BMI 15%</div>
                </div>
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #fce7f3;">&#x2696;</div>
                        <div><div class="disease-name">Obesity</div><div class="disease-factors">5 factors &middot; ICD 5B81</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:35%; background:#ec4899;"></div>
                        <div class="factor-seg" style="width:25%; background:#f472b6;"></div>
                        <div class="factor-seg" style="width:20%; background:#f9a8d4;"></div>
                        <div class="factor-seg" style="width:10%; background:#fbcfe8;"></div>
                        <div class="factor-seg" style="width:10%; background:#fce7f3;"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">BMI 35% &middot; Body Fat 25% &middot; WC 20%</div>
                </div>
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #d1fae5;">&#x1F9EA;</div>
                        <div><div class="disease-name">Fatty Liver</div><div class="disease-factors">6 factors &middot; ICD DB92</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:25%; background:#059669;"></div>
                        <div class="factor-seg" style="width:20%; background:#10b981;"></div>
                        <div class="factor-seg" style="width:20%; background:#34d399;"></div>
                        <div class="factor-seg" style="width:15%; background:#6ee7b7;"></div>
                        <div class="factor-seg" style="width:10%; background:#a7f3d0;"></div>
                        <div class="factor-seg" style="width:10%; background:#d1fae5;"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">ALT 25% &middot; GGT 20% &middot; BMI 20%</div>
                </div>
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #e0e7ff;">&#x1F9F7;</div>
                        <div><div class="disease-name">Kidney Disease</div><div class="disease-factors">4 factors &middot; ICD GB60</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:35%; background:#4f46e5;"></div>
                        <div class="factor-seg" style="width:25%; background:#6366f1;"></div>
                        <div class="factor-seg" style="width:20%; background:#818cf8;"></div>
                        <div class="factor-seg" style="width:20%; background:#a5b4fc;"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">Creatinine 35% &middot; Protein 25%</div>
                </div>
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #fff7ed;">&#x1F9E0;</div>
                        <div><div class="disease-name">Stroke</div><div class="disease-factors">6 factors &middot; ICD 8B20</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:30%; background:#ea580c;"></div>
                        <div class="factor-seg" style="width:15%; background:#f97316;"></div>
                        <div class="factor-seg" style="width:15%; background:#fb923c;"></div>
                        <div class="factor-seg" style="width:15%; background:#fdba74;"></div>
                        <div class="factor-seg" style="width:15%; background:#fed7aa;"></div>
                        <div class="factor-seg" style="width:10%; background:#ffedd5;"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">SBP 30% &middot; DBP 15% &middot; LDL 15%</div>
                </div>
                <div class="disease-card">
                    <div class="disease-header">
                        <div class="disease-icon" style="background: #faf5ff;">&#x1F4AA;</div>
                        <div><div class="disease-name">Sarcopenia</div><div class="disease-factors">5 factors &middot; ICD FB32.1</div></div>
                    </div>
                    <div class="factor-bar">
                        <div class="factor-seg" style="width:30%; background:#9333ea;"></div>
                        <div class="factor-seg" style="width:25%; background:#a855f7;"></div>
                        <div class="factor-seg" style="width:20%; background:#c084fc;"></div>
                        <div class="factor-seg" style="width:15%; background:#d8b4fe;"></div>
                        <div class="factor-seg" style="width:10%; background:#e9d5ff;"></div>
                    </div>
                    <div style="font-size:10px; color:#94a3b8; margin-top:6px;">Body Fat 30% &middot; BMI 25% &middot; HB 20%</div>
                </div>
            </div>
        </div>

        <div style="text-align: center; padding: 16px; color: #cbd5e1; font-size: 11px;">
            Triple-H Co., Ltd. &middot; Healthcare AI Agent v0.1.0 &middot; Patent 10-2025-0145274
        </div>
    </div>

    <script>
        // Date
        document.getElementById('currentDate').textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

        // Training Data Bar Chart
        new Chart(document.getElementById('trainingChart'), {
            type: 'bar',
            data: {
                labels: ['Diagnosis', 'Lifestyle', 'Nutrition', 'Medical QA', 'Med Corpus'],
                datasets: [{
                    label: 'Records',
                    data: [26893, 27281, 25358, 17280, 52125],
                    backgroundColor: ['#3b82f6', '#06b6d4', '#8b5cf6', '#10b981', '#f59e0b'],
                    borderRadius: 6,
                    borderSkipped: false,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false },
                    datalabels: { display: true, color: '#64748b', anchor: 'end', align: 'top', font: { size: 11, weight: 500 },
                        formatter: v => v >= 1000 ? (v/1000).toFixed(1)+'K' : v
                    }
                },
                scales: {
                    y: { display: false },
                    x: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#94a3b8' } }
                }
            },
            plugins: [ChartDataLabels]
        });

        // Disease Donut
        new Chart(document.getElementById('diseaseChart'), {
            type: 'doughnut',
            data: {
                labels: ['Diabetes', 'Heart Disease', 'Hypertension', 'Obesity', 'Fatty Liver', 'Kidney', 'Stroke', 'Sarcopenia'],
                datasets: [{
                    data: [6, 8, 4, 5, 6, 4, 6, 5],
                    backgroundColor: ['#ef4444','#f59e0b','#7c3aed','#ec4899','#10b981','#4f46e5','#ea580c','#9333ea'],
                    borderWidth: 2, borderColor: '#fff',
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '60%',
                plugins: {
                    legend: { position: 'right', labels: { boxWidth: 10, padding: 12, font: { size: 11 }, color: '#64748b' } },
                    datalabels: { display: false }
                }
            }
        });

        // Cost Chart
        new Chart(document.getElementById('costChart'), {
            type: 'bar',
            data: {
                labels: ['1K Users', '10K Users', '50K Users', '100K Users'],
                datasets: [{
                    label: 'Monthly Cost ($)',
                    data: [4600, 14500, 27200, 36000],
                    backgroundColor: '#3b82f6',
                    borderRadius: 6, borderSkipped: false,
                }, {
                    label: 'Per User (KRW)',
                    data: [5900, 1900, 700, 400],
                    backgroundColor: '#e2e8f0',
                    borderRadius: 6, borderSkipped: false,
                    hidden: true,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false },
                    datalabels: { display: true, color: '#fff', font: { size: 10, weight: 600 }, anchor: 'center',
                        formatter: v => '$'+(v/1000).toFixed(1)+'K'
                    }
                },
                scales: {
                    y: { display: false },
                    x: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#94a3b8' } }
                }
            },
            plugins: [ChartDataLabels]
        });

        // QA by Department
        new Chart(document.getElementById('qaChart'), {
            type: 'bar',
            data: {
                labels: ['Internal Med', 'Pediatrics', 'OB/GYN', 'Emergency'],
                datasets: [{
                    label: 'Training',
                    data: [10299, 2421, 1991, 649],
                    backgroundColor: '#3b82f6', borderRadius: 6, borderSkipped: false,
                }, {
                    label: 'Validation',
                    data: [1248, 340, 259, 73],
                    backgroundColor: '#93c5fd', borderRadius: 6, borderSkipped: false,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 11 }, color: '#64748b' } }, datalabels: { display: false } },
                scales: {
                    y: { display: false },
                    x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#94a3b8' }, stacked: true }
                },
                datasets: { bar: {} }
            }
        });
    </script>
</body>
</html>
"""
