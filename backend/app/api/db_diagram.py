"""Interactive database schema diagram visualization."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])


@router.get("/db-diagram", response_class=HTMLResponse)
async def db_diagram():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Healthcare AI Agent — Database Architecture</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, sans-serif; background: #f8f9fb; color: #1e293b; padding: 32px; }

        h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
        .subtitle { font-size: 13px; color: #94a3b8; margin-bottom: 32px; }

        /* ── Overall Architecture ── */
        .arch-section { margin-bottom: 40px; }
        .arch-section h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #374151; }

        .infra-grid {
            display: grid;
            grid-template-columns: 200px 1fr 200px;
            gap: 20px;
            align-items: start;
        }

        .infra-box {
            background: white; border-radius: 12px; padding: 18px;
            border: 1px solid #e8ecf1;
        }
        .infra-box h3 {
            font-size: 11px; font-weight: 600; text-transform: uppercase;
            letter-spacing: 0.8px; margin-bottom: 12px; padding-bottom: 8px;
            border-bottom: 1px solid #f1f3f5;
        }

        .db-node {
            display: flex; align-items: center; gap: 8px;
            padding: 8px 10px; border-radius: 8px; margin-bottom: 6px;
            font-size: 12px; cursor: pointer; transition: all 0.15s;
            border: 1px solid transparent;
        }
        .db-node:hover { border-color: #3b82f6; background: #eff6ff; }
        .db-node.active { border-color: #3b82f6; background: #eff6ff; }
        .db-icon {
            width: 28px; height: 28px; border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
            font-size: 13px; flex-shrink: 0;
        }
        .db-name { font-weight: 500; }
        .db-count { font-size: 10px; color: #94a3b8; margin-left: auto; }

        /* ── Center Diagram ── */
        .center-diagram {
            background: white; border-radius: 16px; padding: 24px;
            border: 1px solid #e8ecf1; min-height: 600px;
        }

        .svg-container { width: 100%; height: 580px; }
        .svg-container svg { width: 100%; height: 100%; }

        /* ── Detail Panel ── */
        .detail-panel {
            background: white; border-radius: 12px; padding: 18px;
            border: 1px solid #e8ecf1;
        }
        .detail-panel h3 {
            font-size: 14px; font-weight: 600; margin-bottom: 12px;
            padding-bottom: 8px; border-bottom: 1px solid #f1f3f5;
        }
        .detail-table { width: 100%; }
        .detail-table td {
            padding: 5px 0; font-size: 11px; border-bottom: 1px solid #f8f9fb;
            vertical-align: top;
        }
        .detail-table td:first-child { font-weight: 500; color: #374151; width: 45%; }
        .detail-table td:last-child { color: #64748b; }

        .col-pill {
            display: inline-block; padding: 1px 6px; border-radius: 4px;
            font-size: 10px; font-weight: 500; margin: 1px;
        }
        .col-pk { background: #fef3c7; color: #92400e; }
        .col-fk { background: #dbeafe; color: #1e40af; }
        .col-idx { background: #f0fdf4; color: #166534; }
        .col-ts { background: #fce7f3; color: #9d174d; }

        /* ── Flow Section ── */
        .flow-section { margin-top: 40px; }
        .flow-row {
            display: flex; align-items: center; gap: 0;
            justify-content: center; flex-wrap: wrap;
        }
        .flow-box {
            background: white; border: 1px solid #e8ecf1; border-radius: 10px;
            padding: 14px 18px; text-align: center; min-width: 150px;
        }
        .flow-box h4 { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
        .flow-box p { font-size: 10px; color: #94a3b8; }
        .flow-arrow { padding: 0 6px; color: #cbd5e1; font-size: 18px; }
        .flow-label {
            font-size: 9px; color: #94a3b8; text-align: center;
            margin-top: 2px;
        }

        .legend {
            display: flex; gap: 16px; margin-top: 20px; justify-content: center; flex-wrap: wrap;
        }
        .legend-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: #64748b; }
        .legend-dot { width: 10px; height: 10px; border-radius: 3px; }

        /* Color coding */
        .c-standard { background: #dbeafe; }
        .c-personal { background: #e0e7ff; }
        .c-glasses { background: #fce7f3; }
        .c-agent { background: #d1fae5; }
        .c-infra { background: #fef3c7; }

        .tab-row { display: flex; gap: 8px; margin-bottom: 20px; }
        .tab {
            padding: 8px 16px; border-radius: 8px; font-size: 12px; font-weight: 500;
            cursor: pointer; border: 1px solid #e8ecf1; background: white; color: #64748b;
        }
        .tab.active { background: #1e293b; color: white; border-color: #1e293b; }
    </style>
</head>
<body>
    <h1>Database Architecture</h1>
    <div class="subtitle">Healthcare AI Agent — 14 Tables · 42 Indexes · 24 RLS Policies · PostgreSQL 17 + pgvector</div>

    <div class="tab-row">
        <div class="tab active" onclick="showView('schema')">Schema Diagram</div>
        <div class="tab" onclick="showView('flow')">Data Flow</div>
        <div class="tab" onclick="showView('infra')">Infrastructure</div>
    </div>

    <!-- ═══ Schema Diagram View ═══ -->
    <div id="view-schema">
        <div class="infra-grid">
            <!-- Left: Table List -->
            <div>
                <div class="infra-box">
                    <h3 style="color: #2563eb;">Standard HRT (Reference)</h3>
                    <div class="db-node" onclick="showDetail('std_population_category')">
                        <div class="db-icon c-standard">👥</div>
                        <span class="db-name">population_category</span>
                        <span class="db-count">26</span>
                    </div>
                    <div class="db-node" onclick="showDetail('std_diagnosis_norm')">
                        <div class="db-icon c-standard">📊</div>
                        <span class="db-name">diagnosis_norm</span>
                        <span class="db-count">298</span>
                    </div>
                    <div class="db-node" onclick="showDetail('std_lifestyle_plan')">
                        <div class="db-icon c-standard">📋</div>
                        <span class="db-name">lifestyle_plan</span>
                        <span class="db-count">56</span>
                    </div>
                    <div class="db-node" onclick="showDetail('std_disease_risk_weight')">
                        <div class="db-icon c-standard">⚖️</div>
                        <span class="db-name">disease_risk_weight</span>
                        <span class="db-count">44</span>
                    </div>
                </div>

                <div class="infra-box" style="margin-top: 16px;">
                    <h3 style="color: #7c3aed;">Personal HRT (User Data)</h3>
                    <div class="db-node" onclick="showDetail('users')">
                        <div class="db-icon c-personal">👤</div>
                        <span class="db-name">users</span>
                    </div>
                    <div class="db-node" onclick="showDetail('user_demographic')">
                        <div class="db-icon c-personal">📄</div>
                        <span class="db-name">user_demographic</span>
                    </div>
                    <div class="db-node" onclick="showDetail('user_biometric')">
                        <div class="db-icon c-personal">💓</div>
                        <span class="db-name">user_biometric</span>
                    </div>
                    <div class="db-node" onclick="showDetail('user_diagnosis')">
                        <div class="db-icon c-personal">🩺</div>
                        <span class="db-name">user_diagnosis</span>
                    </div>
                    <div class="db-node" onclick="showDetail('user_lifestyle')">
                        <div class="db-icon c-personal">🥗</div>
                        <span class="db-name">user_lifestyle</span>
                    </div>
                    <div class="db-node" onclick="showDetail('user_activity_event')">
                        <div class="db-icon c-glasses">👓</div>
                        <span class="db-name">activity_event</span>
                    </div>
                    <div class="db-node" onclick="showDetail('user_health_level')">
                        <div class="db-icon c-personal">📈</div>
                        <span class="db-name">health_level</span>
                    </div>
                    <div class="db-node" onclick="showDetail('user_multimodal')">
                        <div class="db-icon c-personal">🎙️</div>
                        <span class="db-name">user_multimodal</span>
                    </div>
                    <div class="db-node" onclick="showDetail('agent_conversation_log')">
                        <div class="db-icon c-agent">💬</div>
                        <span class="db-name">conversation_log</span>
                    </div>
                    <div class="db-node" onclick="showDetail('simulation_result')">
                        <div class="db-icon c-agent">🔮</div>
                        <span class="db-name">simulation_result</span>
                    </div>
                </div>
            </div>

            <!-- Center: SVG Diagram -->
            <div class="center-diagram">
                <div class="svg-container">
                    <svg viewBox="0 0 600 560" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                                <path d="M0,0 L8,3 L0,6" fill="#94a3b8"/>
                            </marker>
                            <filter id="shadow"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.08"/></filter>
                        </defs>

                        <!-- Standard HRT Group -->
                        <rect x="20" y="10" width="260" height="170" rx="12" fill="#eff6ff" stroke="#bfdbfe" stroke-width="1"/>
                        <text x="35" y="32" font-size="10" font-weight="600" fill="#2563eb">STANDARD HRT (Reference Data)</text>

                        <rect x="35" y="42" width="108" height="56" rx="8" fill="white" stroke="#bfdbfe" filter="url(#shadow)"/>
                        <text x="89" y="62" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">population</text>
                        <text x="89" y="75" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">_category</text>
                        <text x="89" y="90" text-anchor="middle" font-size="8" fill="#64748b">26 rows · PK: category_id</text>

                        <rect x="157" y="42" width="108" height="56" rx="8" fill="white" stroke="#bfdbfe" filter="url(#shadow)"/>
                        <text x="211" y="62" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">diagnosis</text>
                        <text x="211" y="75" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">_norm</text>
                        <text x="211" y="90" text-anchor="middle" font-size="8" fill="#64748b">298 rows · FK→category</text>

                        <rect x="35" y="108" width="108" height="56" rx="8" fill="white" stroke="#bfdbfe" filter="url(#shadow)"/>
                        <text x="89" y="128" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">lifestyle</text>
                        <text x="89" y="141" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">_plan</text>
                        <text x="89" y="156" text-anchor="middle" font-size="8" fill="#64748b">56 rows · FK→category</text>

                        <rect x="157" y="108" width="108" height="56" rx="8" fill="white" stroke="#bfdbfe" filter="url(#shadow)"/>
                        <text x="211" y="128" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">disease_risk</text>
                        <text x="211" y="141" text-anchor="middle" font-size="9" font-weight="600" fill="#1e40af">_weight</text>
                        <text x="211" y="156" text-anchor="middle" font-size="8" fill="#64748b">44 rows · FK→category</text>

                        <!-- FK arrows within Standard -->
                        <line x1="143" y1="70" x2="157" y2="70" stroke="#94a3b8" stroke-width="1" marker-end="url(#arrow)"/>
                        <line x1="143" y1="136" x2="157" y2="136" stroke="#94a3b8" stroke-width="1" marker-end="url(#arrow)"/>
                        <line x1="89" y1="98" x2="89" y2="108" stroke="#94a3b8" stroke-width="1" marker-end="url(#arrow)"/>
                        <line x1="211" y1="98" x2="211" y2="108" stroke="#94a3b8" stroke-width="1" marker-end="url(#arrow)"/>

                        <!-- Users (Central Hub) -->
                        <rect x="340" y="10" width="240" height="78" rx="12" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="1.5"/>
                        <text x="460" y="35" text-anchor="middle" font-size="13" font-weight="700" fill="#6d28d9">👤 users</text>
                        <text x="460" y="52" text-anchor="middle" font-size="9" fill="#7c3aed">PK: user_id (UUID)</text>
                        <text x="460" y="66" text-anchor="middle" font-size="8" fill="#94a3b8">Central hub — all tables FK to this</text>
                        <text x="460" y="80" text-anchor="middle" font-size="8" fill="#94a3b8">De-identified via user_hash (SHA-256)</text>

                        <!-- Personal Tables -->
                        <!-- user_demographic -->
                        <rect x="310" y="110" width="130" height="50" rx="8" fill="white" stroke="#c4b5fd" filter="url(#shadow)"/>
                        <text x="375" y="132" text-anchor="middle" font-size="9" font-weight="600" fill="#6d28d9">📄 demographic</text>
                        <text x="375" y="148" text-anchor="middle" font-size="8" fill="#94a3b8">age, history, family hx</text>
                        <line x1="375" y1="88" x2="375" y2="110" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- user_biometric -->
                        <rect x="455" y="110" width="130" height="50" rx="8" fill="white" stroke="#c4b5fd" filter="url(#shadow)"/>
                        <text x="520" y="132" text-anchor="middle" font-size="9" font-weight="600" fill="#6d28d9">💓 biometric</text>
                        <text x="520" y="148" text-anchor="middle" font-size="8" fill="#94a3b8">HR, SpO2, glucose, steps</text>
                        <line x1="520" y1="88" x2="520" y2="110" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- user_diagnosis -->
                        <rect x="310" y="175" width="130" height="50" rx="8" fill="white" stroke="#c4b5fd" filter="url(#shadow)"/>
                        <text x="375" y="197" text-anchor="middle" font-size="9" font-weight="600" fill="#6d28d9">🩺 diagnosis</text>
                        <text x="375" y="213" text-anchor="middle" font-size="8" fill="#94a3b8">BMI, BP, cholesterol, labs</text>
                        <line x1="375" y1="160" x2="375" y2="175" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- user_lifestyle -->
                        <rect x="455" y="175" width="130" height="50" rx="8" fill="white" stroke="#c4b5fd" filter="url(#shadow)"/>
                        <text x="520" y="197" text-anchor="middle" font-size="9" font-weight="600" fill="#6d28d9">🥗 lifestyle</text>
                        <text x="520" y="213" text-anchor="middle" font-size="8" fill="#94a3b8">diet, exercise, sleep, meds</text>
                        <line x1="520" y1="160" x2="520" y2="175" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- user_activity_event (AI Glasses - highlighted) -->
                        <rect x="310" y="242" width="130" height="56" rx="8" fill="#fff1f2" stroke="#fda4af" stroke-width="1.5" filter="url(#shadow)"/>
                        <text x="375" y="261" text-anchor="middle" font-size="9" font-weight="700" fill="#e11d48">👓 activity_event</text>
                        <text x="375" y="275" text-anchor="middle" font-size="8" fill="#f43f5e">AI Glasses events</text>
                        <text x="375" y="288" text-anchor="middle" font-size="7" fill="#94a3b8">food, drink, exercise, meds</text>
                        <line x1="375" y1="225" x2="375" y2="242" stroke="#fda4af" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- user_health_level -->
                        <rect x="455" y="242" width="130" height="56" rx="8" fill="white" stroke="#c4b5fd" filter="url(#shadow)"/>
                        <text x="520" y="261" text-anchor="middle" font-size="9" font-weight="600" fill="#6d28d9">📈 health_level</text>
                        <text x="520" y="275" text-anchor="middle" font-size="8" fill="#94a3b8">HCI score (0-100)</text>
                        <text x="520" y="288" text-anchor="middle" font-size="7" fill="#94a3b8">Disease Risk Index</text>
                        <line x1="520" y1="225" x2="520" y2="242" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- user_multimodal -->
                        <rect x="310" y="315" width="130" height="50" rx="8" fill="white" stroke="#c4b5fd" filter="url(#shadow)"/>
                        <text x="375" y="337" text-anchor="middle" font-size="9" font-weight="600" fill="#6d28d9">🎙️ multimodal</text>
                        <text x="375" y="353" text-anchor="middle" font-size="8" fill="#94a3b8">voice, image, embeddings</text>
                        <line x1="375" y1="298" x2="375" y2="315" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- Agent Tables -->
                        <rect x="310" y="385" width="275" height="165" rx="12" fill="#ecfdf5" stroke="#86efac" stroke-width="1"/>
                        <text x="325" y="405" font-size="10" font-weight="600" fill="#059669">AI AGENT LAYER</text>

                        <!-- conversation_log -->
                        <rect x="325" y="415" width="120" height="50" rx="8" fill="white" stroke="#86efac" filter="url(#shadow)"/>
                        <text x="385" y="437" text-anchor="middle" font-size="9" font-weight="600" fill="#059669">💬 conversation</text>
                        <text x="385" y="453" text-anchor="middle" font-size="8" fill="#94a3b8">agent chat history</text>

                        <!-- simulation_result -->
                        <rect x="455" y="415" width="120" height="50" rx="8" fill="white" stroke="#86efac" filter="url(#shadow)"/>
                        <text x="515" y="437" text-anchor="middle" font-size="9" font-weight="600" fill="#059669">🔮 simulation</text>
                        <text x="515" y="453" text-anchor="middle" font-size="8" fill="#94a3b8">predictions + twin</text>

                        <!-- Connection from Standard to Simulation -->
                        <path d="M265 140 C290 140, 290 440, 310 440" stroke="#94a3b8" stroke-width="1" fill="none" stroke-dasharray="4,4" marker-end="url(#arrow)"/>
                        <text x="275" y="300" font-size="7" fill="#94a3b8" transform="rotate(-90, 275, 300)">role-model plans feed simulation</text>

                        <!-- Simulation uses diagnosis + lifestyle -->
                        <line x1="520" y1="298" x2="520" y2="385" stroke="#059669" stroke-width="1" stroke-dasharray="3,3" marker-end="url(#arrow)"/>

                        <!-- Label: LSTM input -->
                        <rect x="325" y="478" width="250" height="32" rx="6" fill="#f0fdf4" stroke="#bbf7d0"/>
                        <text x="450" y="498" text-anchor="middle" font-size="9" fill="#059669" font-weight="500">LSTM-Transformer Input: diagnosis + lifestyle + demographic</text>

                        <!-- Label: Twin uses std_lifestyle_plan -->
                        <rect x="325" y="518" width="250" height="28" rx="6" fill="#eff6ff" stroke="#bfdbfe"/>
                        <text x="450" y="536" text-anchor="middle" font-size="9" fill="#2563eb" font-weight="500">Digital Twin uses std_lifestyle_plan as role-model</text>
                    </svg>
                </div>
            </div>

            <!-- Right: Detail Panel -->
            <div>
                <div class="detail-panel" id="detailPanel">
                    <h3 id="detailTitle">Click a table to see details</h3>
                    <div id="detailContent">
                        <p style="font-size: 12px; color: #94a3b8; padding: 20px 0; text-align: center;">
                            Select any table from the left panel to view its columns, indexes, and relationships.
                        </p>
                    </div>
                </div>

                <div class="infra-box" style="margin-top: 16px;">
                    <h3 style="color: #374151;">Legend</h3>
                    <div style="display: flex; flex-direction: column; gap: 6px;">
                        <div class="legend-item"><div class="legend-dot" style="background: #bfdbfe;"></div> Standard (reference)</div>
                        <div class="legend-item"><div class="legend-dot" style="background: #c4b5fd;"></div> Personal (user data)</div>
                        <div class="legend-item"><div class="legend-dot" style="background: #fda4af;"></div> AI Glasses (new)</div>
                        <div class="legend-item"><div class="legend-dot" style="background: #86efac;"></div> Agent layer</div>
                        <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #f1f3f5;">
                            <div class="legend-item" style="margin-bottom: 4px;"><span class="col-pill col-pk">PK</span> Primary Key</div>
                            <div class="legend-item" style="margin-bottom: 4px;"><span class="col-pill col-fk">FK</span> Foreign Key</div>
                            <div class="legend-item" style="margin-bottom: 4px;"><span class="col-pill col-ts">TS</span> Time-series partition</div>
                            <div class="legend-item"><span class="col-pill col-idx">IDX</span> Indexed column</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ═══ Data Flow View ═══ -->
    <div id="view-flow" style="display: none;">
        <div class="infra-box" style="padding: 30px;">
            <h3 style="font-size: 14px; margin-bottom: 20px;">Data Flow: From Device to Prediction</h3>
            <div style="display: flex; flex-direction: column; gap: 24px;">

                <div class="flow-row">
                    <div class="flow-box" style="border-top: 3px solid #f59e0b;">
                        <h4>👓 AI Glasses</h4>
                        <p>Detects food, exercise<br>Blurs faces on-device<br>Sends JSON + thumbnail</p>
                    </div>
                    <div><div class="flow-arrow">→</div><div class="flow-label">~30 MB/day</div></div>
                    <div class="flow-box" style="border-top: 3px solid #06b6d4;">
                        <h4>📱 Phone App</h4>
                        <p>SQLite cache<br>Syncs to server<br>Shows corrections</p>
                    </div>
                    <div><div class="flow-arrow">→</div><div class="flow-label">WiFi/LTE</div></div>
                    <div class="flow-box" style="border-top: 3px solid #3b82f6;">
                        <h4>⚡ FastAPI</h4>
                        <p>23 REST endpoints<br>/activity-events/<br>/biometric/</p>
                    </div>
                    <div><div class="flow-arrow">→</div><div class="flow-label">Kafka</div></div>
                    <div class="flow-box" style="border-top: 3px solid #8b5cf6;">
                        <h4>🗄️ Supabase</h4>
                        <p>user_activity_event<br>user_biometric<br>user_lifestyle</p>
                    </div>
                </div>

                <div class="flow-row">
                    <div class="flow-box" style="border-top: 3px solid #10b981; margin-left: 200px;">
                        <h4>⌚ Smartwatch</h4>
                        <p>HR, HRV, SpO2<br>Steps, stress<br>Every 30 seconds</p>
                    </div>
                    <div><div class="flow-arrow">→</div><div class="flow-label">BLE</div></div>
                    <div class="flow-box" style="border-top: 3px solid #06b6d4;">
                        <h4>📱 Health Connect</h4>
                        <p>Samsung / Apple<br>Oura Ring<br>On-device aggregation</p>
                    </div>
                    <div><div class="flow-arrow">→</div></div>
                    <div class="flow-box" style="border-top: 3px solid #3b82f6;">
                        <h4>⚡ /biometric/batch</h4>
                        <p>Batch upload<br>every 5 minutes</p>
                    </div>
                    <div><div class="flow-arrow">→</div></div>
                    <div class="flow-box" style="border-top: 3px solid #8b5cf6;">
                        <h4>🗄️ user_biometric</h4>
                        <p>TimescaleDB<br>hypertable</p>
                    </div>
                </div>

                <div style="border-top: 2px dashed #e2e8f0; padding-top: 20px;">
                    <div class="flow-row">
                        <div class="flow-box" style="border-top: 3px solid #8b5cf6;">
                            <h4>🗄️ user_diagnosis<br>+ user_lifestyle</h4>
                            <p>Current health state<br>+ daily habits</p>
                        </div>
                        <div><div class="flow-arrow">→</div><div class="flow-label">Input (65 dims)</div></div>
                        <div class="flow-box" style="border-top: 3px solid #ec4899;">
                            <h4>🧠 LSTM-Transformer</h4>
                            <p>Predicts future health<br>1mo / 1yr / 10yr</p>
                        </div>
                        <div><div class="flow-arrow">→</div><div class="flow-label">Predictions</div></div>
                        <div class="flow-box" style="border-top: 3px solid #8b5cf6;">
                            <h4>🗄️ simulation_result</h4>
                            <p>Current scenario<br>Twin scenario<br>Confidence intervals</p>
                        </div>
                        <div><div class="flow-arrow">→</div></div>
                        <div class="flow-box" style="border-top: 3px solid #10b981;">
                            <h4>🤖 AI Agent</h4>
                            <p>OpenClaw<br>"Your BMI will be 25.3<br>in 1 year if..."</p>
                        </div>
                    </div>
                </div>

                <div style="border-top: 2px dashed #e2e8f0; padding-top: 20px;">
                    <div class="flow-row">
                        <div class="flow-box" style="border-top: 3px solid #2563eb;">
                            <h4>📊 std_diagnosis_norm</h4>
                            <p>Normal/Warning/Critical<br>ranges per age/gender</p>
                        </div>
                        <div><div class="flow-arrow">→</div><div class="flow-label">Compare</div></div>
                        <div class="flow-box" style="border-top: 3px solid #f59e0b;">
                            <h4>📈 Healthcare Index</h4>
                            <p>HCI = T formula<br>Score 0-100<br>5 clinical tiers</p>
                        </div>
                        <div><div class="flow-arrow">→</div></div>
                        <div class="flow-box" style="border-top: 3px solid #8b5cf6;">
                            <h4>🗄️ user_health_level</h4>
                            <p>HCI + DRI stored<br>per user per day</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ═══ Infrastructure View ═══ -->
    <div id="view-infra" style="display: none;">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="infra-box">
                <h3 style="font-size: 14px;">Case I: Local Deployment</h3>
                <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 12px;">
                    <div class="db-node" style="background: #eff6ff;"><div class="db-icon c-standard">🗄️</div><span class="db-name">PostgreSQL 16 + TimescaleDB</span><span class="db-count">1 Primary + 3 Replicas</span></div>
                    <div class="db-node" style="background: #fef3c7;"><div class="db-icon c-infra">🔗</div><span class="db-name">PgBouncer (connection pool)</span><span class="db-count">2 instances (HA)</span></div>
                    <div class="db-node" style="background: #fce7f3;"><div class="db-icon c-glasses">🔍</div><span class="db-name">pgvector (HNSW index)</span><span class="db-count">On Primary + R2</span></div>
                    <div class="db-node" style="background: #fef3c7;"><div class="db-icon c-infra">⚡</div><span class="db-name">Redis Cluster</span><span class="db-count">6 nodes (3 shards x 2)</span></div>
                    <div class="db-node" style="background: #fef3c7;"><div class="db-icon c-infra">📨</div><span class="db-name">Apache Kafka (KRaft)</span><span class="db-count">5-15 brokers</span></div>
                    <div class="db-node" style="background: #fef3c7;"><div class="db-icon c-infra">📦</div><span class="db-name">MinIO (S3-compatible)</span><span class="db-count">4 nodes</span></div>
                    <div class="db-node" style="background: #ecfdf5;"><div class="db-icon c-agent">🏥</div><span class="db-name">HAPI FHIR Server</span><span class="db-count">1 + replica</span></div>
                    <div style="padding: 8px; font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #f1f3f5; margin-top: 4px;">
                        Total: <b>18-22 database instances</b>
                    </div>
                </div>
            </div>
            <div class="infra-box">
                <h3 style="font-size: 14px;">Case II: SaaS (AWS)</h3>
                <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 12px;">
                    <div class="db-node" style="background: #eff6ff;"><div class="db-icon c-standard">🗄️</div><span class="db-name">Supabase / Timescale Cloud</span><span class="db-count">Primary + 3 Replicas</span></div>
                    <div class="db-node" style="background: #fef3c7;"><div class="db-icon c-infra">⚡</div><span class="db-name">Amazon ElastiCache Redis</span><span class="db-count">6 nodes (managed)</span></div>
                    <div class="db-node" style="background: #fef3c7;"><div class="db-icon c-infra">📨</div><span class="db-name">Amazon MSK Serverless</span><span class="db-count">Auto-scaled</span></div>
                    <div class="db-node" style="background: #fef3c7;"><div class="db-icon c-infra">📦</div><span class="db-name">AWS S3 (4-tier lifecycle)</span><span class="db-count">Standard→IA→Glacier→Archive</span></div>
                    <div class="db-node" style="background: #ecfdf5;"><div class="db-icon c-agent">🏥</div><span class="db-name">AWS HealthLake (FHIR R4)</span><span class="db-count">Managed</span></div>
                    <div style="padding: 8px; font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #f1f3f5; margin-top: 4px;">
                        Total: <b>5 managed services</b> (no server management)
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
    const tableDetails = {
        std_population_category: { title: "std_population_category", desc: "Population groups for health benchmarking", records: "26", cols: [
            {n:"category_id",t:"SERIAL",tag:"pk"}, {n:"age_group",t:"VARCHAR(20)",tag:""}, {n:"gender",t:"CHAR(1)",tag:""},
            {n:"disability_yn",t:"BOOLEAN",tag:""}, {n:"income_decile",t:"SMALLINT",tag:""}, {n:"country_code",t:"CHAR(3)",tag:""}, {n:"created_at",t:"TIMESTAMPTZ",tag:""}
        ]},
        std_diagnosis_norm: { title: "std_diagnosis_norm", desc: "Normal/warning/critical ranges per metric", records: "298", cols: [
            {n:"norm_id",t:"SERIAL",tag:"pk"}, {n:"category_id",t:"INT",tag:"fk"}, {n:"metric_code",t:"VARCHAR(50)",tag:"idx"},
            {n:"unit",t:"VARCHAR(20)",tag:""}, {n:"normal_min/max",t:"NUMERIC(10,4)",tag:""}, {n:"warning_min/max",t:"NUMERIC(10,4)",tag:""},
            {n:"critical_min/max",t:"NUMERIC(10,4)",tag:""}, {n:"source",t:"VARCHAR(200)",tag:""}
        ]},
        std_lifestyle_plan: { title: "std_lifestyle_plan", desc: "Role-model diet/exercise/sleep/medication plans", records: "56", cols: [
            {n:"plan_id",t:"SERIAL",tag:"pk"}, {n:"category_id",t:"INT",tag:"fk"}, {n:"plan_type",t:"VARCHAR(20)",tag:"idx"},
            {n:"plan_name",t:"VARCHAR(200)",tag:""}, {n:"detail_json",t:"JSONB",tag:""}, {n:"evidence_level",t:"VARCHAR(10)",tag:""}
        ]},
        std_disease_risk_weight: { title: "std_disease_risk_weight", desc: "Disease risk contribution weights (ICD-11)", records: "44", cols: [
            {n:"weight_id",t:"SERIAL",tag:"pk"}, {n:"disease_code",t:"VARCHAR(20)",tag:"idx"}, {n:"metric_code",t:"VARCHAR(50)",tag:""},
            {n:"weight_value",t:"NUMERIC(5,4)",tag:""}, {n:"category_id",t:"INT",tag:"fk"}, {n:"formula_type",t:"VARCHAR(20)",tag:""}
        ]},
        users: { title: "users", desc: "User profiles (de-identified, no PII)", records: "—", cols: [
            {n:"user_id",t:"UUID",tag:"pk"}, {n:"user_hash",t:"VARCHAR(64)",tag:"idx"}, {n:"age_group",t:"VARCHAR(20)",tag:""},
            {n:"gender",t:"CHAR(1)",tag:""}, {n:"disability_yn",t:"BOOLEAN",tag:""}, {n:"income_decile",t:"SMALLINT",tag:""},
            {n:"is_active",t:"BOOLEAN",tag:""}
        ]},
        user_demographic: { title: "user_demographic", desc: "Sociodemographic data (time-series)", records: "—", cols: [
            {n:"demo_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"recorded_at",t:"TIMESTAMPTZ",tag:"ts"},
            {n:"age",t:"SMALLINT",tag:""}, {n:"past_history",t:"TEXT[]",tag:""}, {n:"family_history",t:"TEXT[]",tag:""}
        ]},
        user_biometric: { title: "user_biometric", desc: "Real-time wearable + CGM data", records: "—", cols: [
            {n:"bio_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"measured_at",t:"TIMESTAMPTZ",tag:"ts"},
            {n:"device_type",t:"VARCHAR(50)",tag:"idx"}, {n:"heart_rate",t:"SMALLINT",tag:""}, {n:"hrv",t:"SMALLINT",tag:""},
            {n:"spo2",t:"NUMERIC(4,1)",tag:""}, {n:"glucose_mgdl",t:"NUMERIC(5,1)",tag:""}, {n:"glucose_trend",t:"VARCHAR(20)",tag:""},
            {n:"step_count",t:"INT",tag:""}, {n:"stress_index",t:"NUMERIC(4,1)",tag:""}
        ]},
        user_diagnosis: { title: "user_diagnosis", desc: "Periodic health checkup results", records: "—", cols: [
            {n:"diag_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"period_start",t:"DATE",tag:"ts"},
            {n:"bmi",t:"NUMERIC(4,1)",tag:""}, {n:"sbp/dbp",t:"SMALLINT",tag:""}, {n:"fasting_glucose",t:"SMALLINT",tag:""},
            {n:"total_chol/hdl/ldl",t:"SMALLINT",tag:""}, {n:"alt/ast/ggt",t:"SMALLINT",tag:""}, {n:"body_fat_pct",t:"NUMERIC(4,1)",tag:""}
        ]},
        user_lifestyle: { title: "user_lifestyle", desc: "Daily diet, exercise, sleep, medication", records: "—", cols: [
            {n:"ls_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"recorded_date",t:"DATE",tag:"ts"},
            {n:"total_calories",t:"SMALLINT",tag:""}, {n:"carb/protein/fat_g",t:"SMALLINT",tag:""}, {n:"exercise_min",t:"SMALLINT",tag:""},
            {n:"sleep_hours",t:"NUMERIC(4,1)",tag:""}, {n:"medication_json",t:"JSONB",tag:"idx"}
        ]},
        user_activity_event: { title: "user_activity_event ★ NEW", desc: "AI Glasses detected events (food, exercise, meds)", records: "—", cols: [
            {n:"event_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"detected_at",t:"TIMESTAMPTZ",tag:"ts"},
            {n:"event_type",t:"VARCHAR(30)",tag:"idx"}, {n:"source_device",t:"VARCHAR(30)",tag:""}, {n:"confidence_score",t:"NUMERIC(4,2)",tag:""},
            {n:"structured_data",t:"JSONB",tag:"idx"}, {n:"thumbnail_ref",t:"VARCHAR(500)",tag:""}, {n:"verified",t:"BOOLEAN",tag:""},
            {n:"correction_data",t:"JSONB",tag:""}
        ]},
        user_health_level: { title: "user_health_level", desc: "Healthcare Index (HCI 0-100) + Disease Risk", records: "—", cols: [
            {n:"hl_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"measured_at",t:"TIMESTAMPTZ",tag:"ts"},
            {n:"healthcare_index",t:"NUMERIC(5,2)",tag:""}, {n:"dri",t:"NUMERIC(5,2)",tag:""}, {n:"disease_risk_json",t:"JSONB",tag:"idx"},
            {n:"predicted",t:"BOOLEAN",tag:"idx"}, {n:"sim_scenario",t:"VARCHAR(50)",tag:""}, {n:"confidence_interval",t:"JSONB",tag:""}
        ]},
        user_multimodal: { title: "user_multimodal", desc: "Voice/image/video metadata + embeddings", records: "—", cols: [
            {n:"mm_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"captured_at",t:"TIMESTAMPTZ",tag:"ts"},
            {n:"modal_type",t:"VARCHAR(20)",tag:""}, {n:"emotion_state",t:"VARCHAR(50)",tag:""}, {n:"storage_ref",t:"VARCHAR(500)",tag:""},
            {n:"embedding_vec",t:"vector(1536)",tag:"idx"}
        ]},
        agent_conversation_log: { title: "agent_conversation_log", desc: "AI agent chat history (all channels)", records: "—", cols: [
            {n:"log_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"created_at",t:"TIMESTAMPTZ",tag:"ts"},
            {n:"agent_name",t:"VARCHAR(50)",tag:"idx"}, {n:"channel",t:"VARCHAR(30)",tag:""}, {n:"role",t:"VARCHAR(10)",tag:""},
            {n:"content",t:"TEXT",tag:""}, {n:"tokens_used",t:"INT",tag:""}, {n:"model_used",t:"VARCHAR(30)",tag:""}
        ]},
        simulation_result: { title: "simulation_result", desc: "LSTM-Transformer predictions + Digital Twin", records: "—", cols: [
            {n:"sim_id",t:"BIGSERIAL",tag:"pk"}, {n:"user_id",t:"UUID",tag:"fk"}, {n:"run_at",t:"TIMESTAMPTZ",tag:"ts"},
            {n:"scenario",t:"VARCHAR(50)",tag:"idx"}, {n:"horizon_days",t:"INT",tag:""}, {n:"predicted_diag_json",t:"JSONB",tag:""},
            {n:"hci_series_json",t:"JSONB",tag:""}, {n:"confidence_bounds_json",t:"JSONB",tag:""}, {n:"rmse",t:"NUMERIC(8,4)",tag:""}
        ]}
    };

    function showDetail(tableName) {
        const t = tableDetails[tableName];
        if (!t) return;
        document.querySelectorAll('.db-node').forEach(n => n.classList.remove('active'));
        event.currentTarget.classList.add('active');

        const tagMap = { pk: '<span class="col-pill col-pk">PK</span>', fk: '<span class="col-pill col-fk">FK</span>',
                         ts: '<span class="col-pill col-ts">TS</span>', idx: '<span class="col-pill col-idx">IDX</span>' };

        let html = `<p style="font-size:11px; color:#64748b; margin-bottom:12px;">${t.desc}</p>`;
        if (t.records !== "—") html += `<p style="font-size:11px; margin-bottom:12px;"><b>${t.records}</b> records</p>`;
        html += '<table class="detail-table">';
        t.cols.forEach(c => {
            const tag = c.tag ? tagMap[c.tag] || '' : '';
            html += `<tr><td>${c.n} ${tag}</td><td>${c.t}</td></tr>`;
        });
        html += '</table>';

        document.getElementById('detailTitle').textContent = t.title;
        document.getElementById('detailContent').innerHTML = html;
    }

    function showView(view) {
        ['schema','flow','infra'].forEach(v => {
            document.getElementById('view-'+v).style.display = v === view ? 'block' : 'none';
        });
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        event.currentTarget.classList.add('active');
    }
    </script>
</body>
</html>
"""
