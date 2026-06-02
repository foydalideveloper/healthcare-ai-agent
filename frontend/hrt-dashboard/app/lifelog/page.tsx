"use client";

// Daily Lifelog page — boss-facing browser for AI-glasses extracted events.
// Shows EVERY event extracted by Gemma 4 (or Qwen 3.5 if --compare was used).
// Reads directly from Supabase `lifelog_event` table.
//
// Source-model column lets you filter Gemma-only / Qwen-only / both.
// Category filter narrows to food / interaction / conversation / etc.
//
// URL: /lifelog?user=1&date=2026-05-11&source=both&category=all

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";

const API_BASE = "http://localhost:8888/api/v1";

interface LifelogRow {
  lifelog_id: number;
  user_id: number;
  observed_at: string;
  duration_sec: number | null;
  category: string | null;
  description: string;
  people: string[] | null;
  people_count: number | null;
  location: string | null;
  indoor_outdoor: string | null;
  posture: string | null;
  mood: string | null;
  energy_signs: string | null;
  objects: string[] | null;
  screen: string | null;
  topic: string | null;
  decision: string | null;
  audio_heard: string | null;
  numbers_mentioned: string | null;
  kcal: number | null;
  amount_ml: number | null;
  source_model: string;
  source_video: string | null;
  chunk_idx: number | null;
  // ── v2 schema additions (all optional — present only on rows from the
  //    v2 pipeline; older rows leave them null/undefined and the More
  //    Details panel renders only the sections it has data for).
  confidence?: number | null;
  importance?: string | null;
  memory_relevance?: number | string | null;
  observed_facts?: string[] | null;
  inferred_context?: string[] | null;
  attention_target?: string | null;
  screen_analysis?: Record<string, unknown> | null;
  technical_analysis?: Record<string, unknown> | null; // finance events
  macro?: Record<string, unknown> | null;              // finance events
  conversation_detail?: Record<string, unknown> | null;
  // Clip-level fields — may be duplicated across all events from the same clip.
  cognitive_state?: Record<string, unknown> | string | null;
  anomalies?: unknown[] | null;
  agent_tasks?: unknown[] | null;
  // ── v3 schema additions (migration 007). All optional; older rows leave
  //    them null/undefined and the 3 modality panels render their empty state.
  video_extraction?: VideoExtraction | null;
  audio_extraction?: AudioExtraction | null;
  combined_analysis?: CombinedAnalysis | null;
  ocr_text_full?: string | null;
  recall_estimate?: number | null;
  broadcast_mode?: boolean | null;
  // ── v3.1 schema additions (migration 008). Also optional.
  frame_sampling_rate?: number | null;
  panels_detected?: Array<[number, number, number, number]> | null;
  value_updates?: ValueUpdate[] | null;
  timeline?: TimelineWindow[] | null;
  // ── v3.2 (migration 009): detailed per-item enumeration. One plain-English
  //    sentence per captured item — rendered under Observed Facts.
  enumerated_observations?: string[] | null;
}

// ── v3 modality types ───────────────────────────────────────────────
type VideoExtraction = {
  ocr_text_full?: string[];
  visual_objects?: string[];
  screen_content?: {
    app_or_source?: string;
    ui_elements?: string[];
    charts?: string[];
    headlines?: string[];
  };
  broadcast_mode?: boolean;
  // v3.1 (migration 008)
  panels_detected?: Array<[number, number, number, number]>;
  frame_sampling_rate?: number;
};

type AudioExtraction = {
  transcript_full?: string;
  speaker_count_estimate?: number;
  audio_events?: string[];
  language_detected?: string;
  audio_quality?: "good" | "partial" | "poor";
};

// v3.1 Fix 3 — metric value change record
type ValueUpdate = {
  label: string;
  values: Array<{ value: string; frame_idx: number; timestamp_sec: number }>;
  change_count: number;
  first_seen_sec: number;
  last_seen_sec: number;
};

// v3.1 Fix 4 — per-sub-window narrative entry
type TimelineWindow = {
  window_sec: string;
  summary: string;
  key_items: string[];
};

type CombinedAnalysis = {
  what_is_happening?: string;
  cross_modal_confidence?: number;
  user_activity_inferred?: string;
  importance_score?: number;
  recall_estimate?: number;
  // v3.1 (migration 008)
  value_updates?: ValueUpdate[];
  timeline?: TimelineWindow[];
};

// ── More Details panel helpers ───────────────────────────────────────
// All styles use CSS variables from globals.css so the panel inherits
// the dashboard theme (surface, border, text-primary/secondary/muted).

const detailsPanelStyle: React.CSSProperties = {
  background: "var(--surface)",
  borderTop: "1px solid var(--border)",
  padding: 12,
  fontSize: 12,
  color: "var(--text-secondary)",
};

const detailsSectionTitleStyle: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: "var(--text-muted)",
  textTransform: "uppercase",
  letterSpacing: 0.5,
  marginBottom: 4,
  marginTop: 12,
};

function renderInlineValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(x => renderInlineValue(x)).join(", ");
  try { return JSON.stringify(v); } catch { return String(v); }
}

function KeyValueBlock({ title, data }: { title: string; data: unknown }) {
  if (data == null) return null;
  if (typeof data === "string" || typeof data === "number" || typeof data === "boolean") {
    return (
      <div>
        <div style={detailsSectionTitleStyle}>{title}</div>
        <div>{String(data)}</div>
      </div>
    );
  }
  if (Array.isArray(data)) return <ListBlock title={title} items={data} />;
  const entries = Object.entries(data as Record<string, unknown>);
  if (entries.length === 0) return null;
  return (
    <div>
      <div style={detailsSectionTitleStyle}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "2px 12px" }}>
        {entries.map(([k, v]) => (
          <Fragment key={k}>
            <div style={{ color: "var(--text-muted)" }}>{k}</div>
            <div style={{ color: "var(--text-primary)" }}>{renderInlineValue(v)}</div>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: unknown[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <div style={detailsSectionTitleStyle}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: 16 }}>
        {items.map((item, i) => (
          <li key={i} style={{ color: "var(--text-primary)" }}>{renderInlineValue(item)}</li>
        ))}
      </ul>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// v2 More Details — financial-dashboard-style section renderers
// ─────────────────────────────────────────────────────────────────────
// Replaces the generic key/value dump for the four v2 sections
// (screen_analysis, technical_analysis, macro, conversation_detail)
// with custom components inspired by TradingView / Bloomberg / Linear.
// Tailwind-only; no extra npm deps. Inline SVG icons.

type Tone = "neutral" | "bull" | "bear" | "info" | "warn" | "action";

const TONE_BG: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700 border-slate-200",
  bull:    "bg-emerald-50 text-emerald-700 border-emerald-200",
  bear:    "bg-rose-50 text-rose-700 border-rose-200",
  info:    "bg-blue-50 text-blue-700 border-blue-200",
  warn:    "bg-amber-50 text-amber-700 border-amber-200",
  action:  "bg-indigo-50 text-indigo-700 border-indigo-200",
};

const TONE_GRAD: Record<Tone, string> = {
  neutral: "from-slate-50 to-slate-100",
  bull:    "from-emerald-50 to-emerald-100",
  bear:    "from-rose-50 to-rose-100",
  info:    "from-blue-50 to-blue-100",
  warn:    "from-amber-50 to-amber-100",
  action:  "from-indigo-50 to-indigo-100",
};

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-slate-700",
  bull:    "text-emerald-700",
  bear:    "text-rose-700",
  info:    "text-blue-700",
  warn:    "text-amber-700",
  action:  "text-indigo-700",
};

const TONE_FILL: Record<Tone, string> = {
  neutral: "bg-slate-400",
  bull:    "bg-emerald-500",
  bear:    "bg-rose-500",
  info:    "bg-blue-500",
  warn:    "bg-amber-500",
  action:  "bg-indigo-500",
};

function asString(v: unknown): string { return v == null ? "" : String(v); }
function asArray<T = unknown>(v: unknown): T[] { return Array.isArray(v) ? (v as T[]) : []; }
function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const m = v.match(/-?\d+(\.\d+)?/);
    if (m) { const n = parseFloat(m[0]); return Number.isFinite(n) ? n : null; }
  }
  return null;
}

// Inline SVG icons — currentColor for stroke so they inherit tone.
function Icon({ name, size = 14, className = "" }: { name: string; size?: number; className?: string }) {
  const paths: Record<string, React.ReactNode> = {
    monitor:   (<><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></>),
    phone:     (<><rect x="6" y="2" width="12" height="20" rx="2"/><circle cx="12" cy="18" r="1"/></>),
    chart:     (<><polyline points="3 17 9 11 13 15 21 7"/><polyline points="14 7 21 7 21 14"/></>),
    globe:     (<><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/></>),
    message:   (<><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/></>),
    arrowUp:   (<><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></>),
    arrowDown: (<><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></>),
    arrowRight:(<><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></>),
    check:     (<><polyline points="20 6 9 17 4 12"/></>),
    x:         (<><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></>),
    alert:     (<><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><circle cx="12" cy="17" r="1"/></>),
    copy:      (<><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></>),
    user:      (<><circle cx="12" cy="7" r="4"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/></>),
    activity:  (<><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></>),
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         className={className} aria-hidden="true">
      {paths[name] ?? null}
    </svg>
  );
}

function Pill({ children, tone = "neutral", icon, className = "" }:
              { children: React.ReactNode; tone?: Tone; icon?: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-md border ${TONE_BG[tone]} ${className}`}>
      {icon && <Icon name={icon} size={12} />}
      <span>{children}</span>
    </span>
  );
}

function SectionCard({ title, icon, accent = "neutral", children }:
                     { title: string; icon: string; accent?: Tone; children: React.ReactNode }) {
  return (
    <div className="mt-3 bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className={`px-3 py-2 flex items-center gap-2 border-b border-gray-100 bg-gradient-to-r ${TONE_GRAD[accent]}`}>
        <span className={TONE_TEXT[accent]}><Icon name={icon} size={14} /></span>
        <h4 className={`text-[11px] font-semibold tracking-wider uppercase ${TONE_TEXT[accent]}`}>{title}</h4>
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}

function TrendArrow({ direction, strength }: { direction: string; strength?: string }) {
  const d = direction.toLowerCase();
  const tone: Tone = (d.includes("up") || d.includes("bull")) ? "bull"
                   : (d.includes("down") || d.includes("bear")) ? "bear" : "neutral";
  const iconName = tone === "bull" ? "arrowUp" : tone === "bear" ? "arrowDown" : "arrowRight";
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r ${TONE_GRAD[tone]} border ${tone === "bull" ? "border-emerald-200" : tone === "bear" ? "border-rose-200" : "border-slate-200"}`}>
      <span className={TONE_TEXT[tone]}><Icon name={iconName} size={20} /></span>
      <div>
        <div className={`text-xs font-bold uppercase tracking-wide ${TONE_TEXT[tone]}`}>{direction.replace(/_/g, " ")}</div>
        {strength && <div className="text-[10px] text-gray-500 capitalize">{strength.replace(/_/g, " ")} strength</div>}
      </div>
    </div>
  );
}

function Gauge({ value, levels, label }: { value: string; levels: string[]; label?: string }) {
  const v = value.toLowerCase();
  const idx = levels.findIndex(l => v.includes(l));
  const reached = idx >= 0 ? idx + 1 : 0;
  const colorFor = (i: number) => {
    if (i >= reached) return "bg-gray-200";
    const ratio = (i + 1) / levels.length;
    if (ratio > 0.66) return "bg-emerald-500";
    if (ratio > 0.33) return "bg-amber-400";
    return "bg-slate-400";
  };
  return (
    <div className="inline-flex flex-col gap-1">
      {label && <span className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</span>}
      <div className="flex items-center gap-1">
        {levels.map((_, i) => (
          <span key={i} className={`h-2 w-6 rounded-sm ${colorFor(i)}`} />
        ))}
        <span className="ml-2 text-xs font-medium text-gray-700 capitalize">{value.replace(/_/g, " ")}</span>
      </div>
    </div>
  );
}

function ProgressBar({ value, label, tone = "info" }:
                     { value: number; label?: string; tone?: Tone }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="space-y-1">
      {label && (
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</span>
          <span className="text-xs font-semibold text-gray-700">{pct.toFixed(0)}%</span>
        </div>
      )}
      <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${TONE_FILL[tone]} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function ScreenAnalysisSection({ data }: { data: Record<string, unknown> }) {
  const app = asString(data.app_visible);
  const device = asString(data.device_type).toLowerCase();
  const text = asString(data.text_detected);
  const ui = asArray<unknown>(data.ui_elements);
  const charts = asArray<unknown>(data.charts_detected);
  if (!app && !device && !text && ui.length === 0 && charts.length === 0) return null;
  const deviceIcon = device.includes("phone") ? "phone" : "monitor";
  return (
    <SectionCard title="Screen Analysis" icon={deviceIcon} accent="info">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        {device && <Pill tone="neutral" icon={deviceIcon}>{device}</Pill>}
        {app && <Pill tone="info">{app}</Pill>}
        {charts.map((c, i) => <Pill key={`c${i}`} tone="info" icon="chart">{String(c)}</Pill>)}
      </div>
      {ui.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {ui.map((u, i) => (
            <span key={i} className="inline-block px-2 py-0.5 text-[10px] rounded-full bg-gray-100 text-gray-600 border border-gray-200">
              {String(u)}
            </span>
          ))}
        </div>
      )}
      {text && (
        <pre className="font-mono text-[11px] bg-gray-50 border border-gray-200 rounded p-2 whitespace-pre-wrap break-words text-gray-700 max-h-32 overflow-y-auto">{text}</pre>
      )}
    </SectionCard>
  );
}

function TechnicalAnalysisSection({ data }: { data: Record<string, unknown> }) {
  const trend = asString(data.trend);
  const momentum = asString(data.momentum);
  const strength = asString(data.trend_strength);
  const patterns = asArray<unknown>(data.patterns);
  const indicators = (data.indicators && typeof data.indicators === "object")
    ? (data.indicators as Record<string, unknown>) : {};
  const volume = asString(data.volume_confirmation);
  const breakoutRaw = asNumber(data.breakout_probability);
  const hasAnything = trend || momentum || strength || patterns.length
    || Object.keys(indicators).length || volume || breakoutRaw != null;
  if (!hasAnything) return null;
  const vTone: Tone = /yes|true|confirm|strong/i.test(volume) ? "bull"
    : /no|false|weak|absent/i.test(volume) ? "bear" : "neutral";
  const breakoutPct = breakoutRaw == null ? null : (breakoutRaw <= 1 ? breakoutRaw * 100 : breakoutRaw);
  return (
    <SectionCard title="Technical Analysis" icon="chart" accent="bull">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="flex flex-col gap-2">
          {trend && <TrendArrow direction={trend} strength={strength} />}
          {momentum && <Gauge value={momentum} levels={["weak", "moderate", "strong"]} label="Momentum" />}
          {volume && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-500 uppercase tracking-wider text-[10px]">Volume</span>
              <Pill tone={vTone} icon={vTone === "bull" ? "check" : vTone === "bear" ? "x" : "arrowRight"}>{volume}</Pill>
            </div>
          )}
          {breakoutPct != null && (
            <ProgressBar value={breakoutPct} label="Breakout probability" tone={breakoutPct >= 60 ? "bull" : "info"} />
          )}
        </div>
        <div className="flex flex-col gap-3">
          {patterns.length > 0 && (
            <div>
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Patterns</div>
              <div className="flex flex-wrap gap-1">
                {patterns.map((p, i) => <Pill key={i} tone="bull" icon="activity">{String(p)}</Pill>)}
              </div>
            </div>
          )}
          {Object.keys(indicators).length > 0 && (
            <div>
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Indicators</div>
              <div className="grid grid-cols-2 gap-1">
                {Object.entries(indicators).map(([k, v]) => {
                  const s = typeof v === "string" || typeof v === "number" ? String(v) : JSON.stringify(v);
                  const tone: Tone = /overbought|bear|sell/i.test(s) ? "bear"
                    : /oversold|bull|buy/i.test(s) ? "bull" : "neutral";
                  return (
                    <div key={k} className={`px-2 py-1 rounded border ${TONE_BG[tone]}`}>
                      <div className="text-[10px] uppercase tracking-wider opacity-70">{k}</div>
                      <div className="text-xs font-semibold">{s}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </SectionCard>
  );
}

function MacroSection({ data }: { data: Record<string, unknown> }) {
  const regime = asString(data.market_regime);
  const vol = asString(data.volatility_state);
  const strength = asArray<unknown>(data.sector_strength);
  const weakness = asArray<unknown>(data.sector_weakness);
  const risks = asArray<unknown>(data.risk_factors);
  const macros = asArray<unknown>(data.macro_factors);
  if (!regime && !vol && !strength.length && !weakness.length && !risks.length && !macros.length) return null;
  const regimeTone: Tone = /risk[_ ]?on|bull/i.test(regime) ? "bull"
    : /risk[_ ]?off|bear/i.test(regime) ? "bear" : "neutral";
  return (
    <SectionCard title="Macro" icon="globe" accent="warn">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        {regime && (
          <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider border ${TONE_BG[regimeTone]}`}>
            {regime.replace(/_/g, " ")}
          </span>
        )}
        {vol && <Gauge value={vol} levels={["subdued", "normal", "elevated"]} label="Volatility" />}
      </div>
      {(strength.length > 0 || weakness.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
          {strength.length > 0 && (
            <div>
              <div className="text-[10px] text-emerald-700 uppercase tracking-wider mb-1 flex items-center gap-1">
                <Icon name="arrowUp" size={12}/> Sector strength
              </div>
              <div className="flex flex-wrap gap-1">
                {strength.map((s, i) => <Pill key={i} tone="bull" icon="arrowUp">{String(s)}</Pill>)}
              </div>
            </div>
          )}
          {weakness.length > 0 && (
            <div>
              <div className="text-[10px] text-rose-700 uppercase tracking-wider mb-1 flex items-center gap-1">
                <Icon name="arrowDown" size={12}/> Sector weakness
              </div>
              <div className="flex flex-wrap gap-1">
                {weakness.map((s, i) => <Pill key={i} tone="bear" icon="arrowDown">{String(s)}</Pill>)}
              </div>
            </div>
          )}
        </div>
      )}
      {risks.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] text-amber-700 uppercase tracking-wider mb-1 flex items-center gap-1">
            <Icon name="alert" size={12}/> Risk factors
          </div>
          <ul className="space-y-1">
            {risks.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <span className="text-amber-600 mt-0.5"><Icon name="alert" size={12}/></span>
                <span>{String(r)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {macros.length > 0 && (
        <div>
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Macro factors</div>
          <ul className="space-y-1">
            {macros.map((m, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <span className="text-blue-500 mt-0.5"><Icon name="globe" size={12}/></span>
                <span>{String(m)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function ConversationDetailSection({ data }: { data: Record<string, unknown> }) {
  const participants = asArray<unknown>(data.participants);
  const keyPoints = asArray<unknown>(data.key_points);
  const questions = asArray<unknown>(data.questions_asked);
  const requests = asArray<unknown>(data.requests_received);
  const agreements = asArray<unknown>(data.agreements);
  const actions = asArray<unknown>(data.action_items);
  if (!participants.length && !keyPoints.length && !questions.length
      && !requests.length && !agreements.length && !actions.length) return null;
  return (
    <SectionCard title="Conversation" icon="message" accent="action">
      {participants.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {participants.map((p, i) => <Pill key={i} tone="action" icon="user">{String(p)}</Pill>)}
        </div>
      )}
      {keyPoints.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Key points</div>
          <ol className="space-y-1">
            {keyPoints.map((kp, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <span className="text-violet-600 font-semibold w-5 flex-shrink-0">{i + 1}.</span>
                <span>{String(kp)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {questions.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] text-blue-700 uppercase tracking-wider mb-1">Questions asked</div>
          <ul className="space-y-1">
            {questions.map((q, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="text-blue-500 mt-0.5 flex-shrink-0">?</span>
                <span className="text-gray-700">{String(q)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {requests.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] text-amber-700 uppercase tracking-wider mb-1">Requests received</div>
          <ul className="space-y-1">
            {requests.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="text-amber-600 mt-0.5 flex-shrink-0">→</span>
                <span className="text-gray-700">{String(r)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {agreements.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] text-emerald-700 uppercase tracking-wider mb-1">Agreements</div>
          <ul className="space-y-1">
            {agreements.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <span className="text-emerald-600 mt-0.5 flex-shrink-0"><Icon name="check" size={14}/></span>
                <span>{String(a)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {actions.length > 0 && (
        <div>
          <div className="text-[10px] text-indigo-700 uppercase tracking-wider mb-1">Action items</div>
          <ul className="space-y-1">
            {actions.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <input type="checkbox" className="mt-0.5 h-3.5 w-3.5 rounded border-gray-300" aria-label={`mark action item ${i + 1} done`} />
                <span>{String(a)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function rowToMarkdown(row: LifelogRow): string {
  const lines: string[] = [];
  lines.push(`# ${row.category || "event"} @ ${row.observed_at}`);
  lines.push("");
  if (row.description) lines.push(row.description, "");
  if (row.confidence != null) lines.push(`- confidence: ${(row.confidence * 100).toFixed(0)}%`);
  if (row.importance != null) lines.push(`- importance: ${row.importance}`);
  if (row.memory_relevance != null) lines.push(`- memory_relevance: ${row.memory_relevance}`);
  if (row.attention_target) lines.push(`- attention: ${row.attention_target}${row.duration_sec ? ` · ${row.duration_sec}s` : ""}`);
  const facts = row.observed_facts || [];
  if (facts.length) { lines.push("", "## Observed facts"); facts.forEach(f => lines.push(`- ${f}`)); }
  const ctx = row.inferred_context || [];
  if (ctx.length) { lines.push("", "## Inferred context"); ctx.forEach(c => lines.push(`- ${c}`)); }
  const dumpObj = (title: string, o: unknown) => {
    if (!o || typeof o !== "object") return;
    lines.push("", `## ${title}`, "```json", JSON.stringify(o, null, 2), "```");
  };
  dumpObj("Screen analysis", row.screen_analysis);
  dumpObj("Technical analysis", row.technical_analysis);
  dumpObj("Macro", row.macro);
  dumpObj("Conversation detail", row.conversation_detail);
  if (row.cognitive_state) dumpObj("Cognitive state", row.cognitive_state);
  if (Array.isArray(row.anomalies) && row.anomalies.length) {
    lines.push("", "## Anomalies"); row.anomalies.forEach(a => lines.push(`- ${String(a)}`));
  }
  if (Array.isArray(row.agent_tasks) && row.agent_tasks.length) {
    lines.push("", "## Agent tasks"); row.agent_tasks.forEach(a => lines.push(`- ${typeof a === "string" ? a : JSON.stringify(a)}`));
  }
  return lines.join("\n");
}

function CopyMarkdownButton({ row }: { row: LifelogRow }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(rowToMarkdown(row)).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        }).catch(() => {});
      }}
      className="inline-flex items-center gap-1 px-2 py-1 text-[10px] text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded border border-gray-200 transition-colors"
      title="Copy this event as Markdown"
    >
      <Icon name="copy" size={11} /> {copied ? "Copied" : "Copy as Markdown"}
    </button>
  );
}

// v3.2 — the "359 items problem" fix. The model now emits one plain-English
// sentence per captured item in `enumerated_observations`; render them as a
// scrollable, filterable list under Observed Facts so the user can SEE every
// captured item (not just the 6-12 high-level bullets).
function EnumeratedObservations({ items }: { items: string[] }) {
  const [q, setQ] = useState("");
  const clean = items.filter((s) => typeof s === "string" && s.trim().length > 0);
  if (clean.length === 0) return null;
  const needle = q.trim().toLowerCase();
  const filtered = needle ? clean.filter((s) => s.toLowerCase().includes(needle)) : clean;
  return (
    <div style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <div style={{ ...detailsSectionTitleStyle, marginTop: 0 }}>
          Detailed observations · {filtered.length === clean.length ? clean.length : `${filtered.length}/${clean.length}`} items
        </div>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filter…"
          aria-label="filter detailed observations"
          style={{
            fontSize: 11, padding: "2px 8px", borderRadius: 6,
            border: "1px solid var(--border)", background: "var(--surface)",
            color: "var(--text-primary)", width: 140,
          }}
        />
      </div>
      <ul style={{ margin: 0, paddingLeft: 16, maxHeight: 384, overflowY: "auto" }}>
        {filtered.map((obs, i) => (
          <li key={i} style={{ color: "var(--text-primary)", lineHeight: 1.5, marginBottom: 2 }}>
            {obs}
          </li>
        ))}
        {filtered.length === 0 && (
          <li style={{ color: "var(--text-muted)", listStyle: "none", marginLeft: -16 }}>
            no matches for “{q}”
          </li>
        )}
      </ul>
    </div>
  );
}

function DetailsPanel({ row }: { row: LifelogRow }) {
  const facts = row.observed_facts || [];
  const context = row.inferred_context || [];
  const hasAttention = (row.attention_target && row.attention_target !== "") || row.duration_sec != null;

  return (
    <div style={detailsPanelStyle}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {row.confidence != null && (
            <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-medium rounded-md border bg-slate-100 text-slate-700 border-slate-200">
              confidence&nbsp;<strong>{(row.confidence * 100).toFixed(0)}%</strong>
            </span>
          )}
          {row.importance != null && row.importance !== "" && (
            <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-medium rounded-md border bg-blue-50 text-blue-700 border-blue-200">
              importance&nbsp;<strong>{String(row.importance)}</strong>
            </span>
          )}
          {row.memory_relevance != null && (
            <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-medium rounded-md border bg-violet-50 text-violet-700 border-violet-200">
              memory&nbsp;<strong>{String(row.memory_relevance)}</strong>
            </span>
          )}
        </div>
        <CopyMarkdownButton row={row} />
      </div>
      {hasAttention && (
        <div className="mt-2 text-xs" style={{ color: "var(--text-secondary)" }}>
          {row.attention_target && (
            <span>
              <strong style={{ color: "var(--text-primary)" }}>Attention:</strong> {row.attention_target}
            </span>
          )}
          {row.attention_target && row.duration_sec != null && <span> · </span>}
          {row.duration_sec != null && <span>{row.duration_sec}s</span>}
        </div>
      )}

      {(facts.length > 0 || context.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
          <div>
            <div style={{ ...detailsSectionTitleStyle, marginTop: 0 }}>Observed facts</div>
            {facts.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {facts.map((f, i) => (
                  <li key={i} style={{ color: "var(--text-primary)" }}>{String(f)}</li>
                ))}
              </ul>
            ) : (
              <div style={{ color: "var(--text-muted)" }}>—</div>
            )}
          </div>
          <div>
            <div style={{ ...detailsSectionTitleStyle, marginTop: 0 }}>Inferred context</div>
            {context.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {context.map((c, i) => (
                  <li key={i} style={{ color: "var(--text-primary)" }}>{String(c)}</li>
                ))}
              </ul>
            ) : (
              <div style={{ color: "var(--text-muted)" }}>—</div>
            )}
          </div>
        </div>
      )}

      {Array.isArray(row.enumerated_observations) && row.enumerated_observations.length > 0 && (
        <EnumeratedObservations items={row.enumerated_observations} />
      )}

      {row.screen_analysis && <ScreenAnalysisSection data={row.screen_analysis} />}
      {row.technical_analysis && <TechnicalAnalysisSection data={row.technical_analysis} />}
      {row.macro && <MacroSection data={row.macro} />}
      {row.conversation_detail && <ConversationDetailSection data={row.conversation_detail} />}
      {row.cognitive_state != null && <KeyValueBlock title="Cognitive state" data={row.cognitive_state} />}
      {Array.isArray(row.anomalies) && row.anomalies.length > 0 && (
        <ListBlock title="Anomalies" items={row.anomalies} />
      )}
      {Array.isArray(row.agent_tasks) && row.agent_tasks.length > 0 && (
        <ListBlock title="Agent tasks" items={row.agent_tasks} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// v3 — modality-separated panels (Video / Audio / Combined)
// ─────────────────────────────────────────────────────────────────────

const panelEmptyStyle: React.CSSProperties = {
  background: "var(--surface)",
  borderTop: "1px solid var(--border)",
  padding: 24,
  textAlign: "center",
  color: "var(--text-muted)",
  fontSize: 12,
};

function PanelEmptyState({ modality }: { modality: "video" | "audio" | "combined" }) {
  const msg = modality === "combined"
    ? "No cross-modal synthesis available for this clip. The watcher may not have completed a v3 extraction pass yet."
    : `No data extracted from this modality. This clip may have insufficient ${modality} input.`;
  return (
    <div style={panelEmptyStyle}>
      <div style={{ maxWidth: 360, margin: "0 auto" }}>{msg}</div>
    </div>
  );
}

// Cached count helpers — used both inside panels and on the button badges.
function videoBadgeCount(row: LifelogRow): number {
  const v = row.video_extraction || undefined;
  const ocrFromText = (row.ocr_text_full || "").split("\n").filter(Boolean).length;
  const ocrFromArr  = v?.ocr_text_full?.length ?? 0;
  const visObjs     = v?.visual_objects?.length ?? 0;
  return Math.max(ocrFromText, ocrFromArr) + visObjs;
}

function audioBadgeCount(row: LifelogRow): number {
  const a = row.audio_extraction || undefined;
  const transcriptWords = (a?.transcript_full || "").split(/\s+/).filter(Boolean).length;
  const events = a?.audio_events?.length ?? 0;
  return Math.max(Math.floor(transcriptWords / 50), events);
}

function combinedBadgeMark(row: LifelogRow): string {
  const r = row.combined_analysis?.recall_estimate ?? row.recall_estimate ?? null;
  if (r == null) return "";
  if (r > 0.7) return " ✓";
  if (r < 0.4) return " ⚠";
  return "";
}

function VideoPanel({ row }: { row: LifelogRow }) {
  const v = row.video_extraction;
  const ocrTextFlat = row.ocr_text_full || "";
  const ocrItems = v?.ocr_text_full ?? (ocrTextFlat ? ocrTextFlat.split("\n").filter(Boolean) : []);
  const visObjs  = v?.visual_objects ?? [];
  const sc       = v?.screen_content ?? {};
  const broadcast = (v?.broadcast_mode ?? row.broadcast_mode) === true;
  const hasAny = ocrItems.length > 0 || visObjs.length > 0
    || (sc.app_or_source || (sc.ui_elements?.length || 0) + (sc.charts?.length || 0) + (sc.headlines?.length || 0) > 0);
  if (!hasAny) return <PanelEmptyState modality="video" />;
  return (
    <div className="border-t border-gray-100 bg-gray-50 p-3 space-y-3">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Visible on screen</div>

      {ocrItems.length > 0 && (
        <div>
          <div className="text-[10px] text-blue-700 uppercase tracking-wider mb-1">
            OCR Text · {ocrItems.length} item{ocrItems.length === 1 ? "" : "s"} (verbatim)
          </div>
          <pre className="font-mono text-[11px] bg-white border border-gray-200 rounded p-2 whitespace-pre-wrap break-words text-gray-700 max-h-48 overflow-y-auto">
            {ocrItems.join("\n")}
          </pre>
        </div>
      )}

      {visObjs.length > 0 && (
        <div>
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Visual objects</div>
          <div className="flex flex-wrap gap-1">
            {visObjs.map((o, i) => (
              <span key={i} className="inline-block px-2 py-0.5 text-[11px] rounded-md border bg-slate-100 text-slate-700 border-slate-200">
                {String(o)}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {sc.app_or_source && (
          <div className="bg-white border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">App / source</div>
            <div className="text-xs text-gray-800 font-medium">{sc.app_or_source}</div>
          </div>
        )}
        {(sc.ui_elements?.length ?? 0) > 0 && (
          <div className="bg-white border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">UI elements</div>
            <div className="flex flex-wrap gap-1">
              {sc.ui_elements!.map((u, i) => (
                <span key={i} className="inline-block px-1.5 py-0.5 text-[10px] rounded bg-gray-100 text-gray-600 border border-gray-200">
                  {String(u)}
                </span>
              ))}
            </div>
          </div>
        )}
        {(sc.charts?.length ?? 0) > 0 && (
          <div className="bg-white border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Charts</div>
            <div className="flex flex-wrap gap-1">
              {sc.charts!.map((c, i) => (
                <span key={i} className="inline-block px-1.5 py-0.5 text-[10px] rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  {String(c)}
                </span>
              ))}
            </div>
          </div>
        )}
        {(sc.headlines?.length ?? 0) > 0 && (
          <div className="bg-white border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Headlines</div>
            <ul className="text-[11px] text-gray-800 space-y-0.5 list-disc list-inside">
              {sc.headlines!.map((h, i) => (<li key={i}>{String(h)}</li>))}
            </ul>
          </div>
        )}
      </div>

      {/* v3.1 Fix 2: multi-panel detection */}
      {(() => {
        const panels = (v?.panels_detected ?? row.panels_detected) || [];
        if (panels.length === 0) return null;
        return (
          <div>
            <div className="text-[10px] text-blue-700 uppercase tracking-wider mb-1">
              Multi-panel detection · {panels.length} region{panels.length === 1 ? "" : "s"}
            </div>
            <div className="flex flex-wrap gap-1">
              {panels.slice(0, 12).map((p, i) => {
                const [x1, y1, x2, y2] = p;
                return (
                  <span key={i}
                        className="inline-block px-1.5 py-0.5 text-[10px] rounded bg-blue-50 text-blue-700 border border-blue-200 font-mono"
                        title={`bbox: (${x1},${y1})-(${x2},${y2})`}>
                    #{i + 1}: {x2 - x1}×{y2 - y1}
                  </span>
                );
              })}
            </div>
          </div>
        );
      })()}

      <div className="flex items-center gap-3 text-[10px] text-gray-500 flex-wrap">
        <span>Broadcast mode: <strong className={broadcast ? "text-emerald-700" : "text-gray-700"}>{broadcast ? "yes" : "no"}</strong></span>
        <span>· OCR items: {ocrItems.length}</span>
        <span>· Visual objects: {visObjs.length}</span>
        {(() => {
          const fsr = v?.frame_sampling_rate ?? row.frame_sampling_rate;
          return fsr ? <span>· Frames sampled: <strong className="text-gray-700">{fsr}</strong></span> : null;
        })()}
      </div>
    </div>
  );
}

function AudioPanel({ row }: { row: LifelogRow }) {
  const a = row.audio_extraction;
  if (!a || (
    !a.transcript_full
    && !(a.audio_events?.length)
    && !a.language_detected
    && !a.audio_quality
  )) return <PanelEmptyState modality="audio" />;
  const quality = a.audio_quality ?? "—";
  const qualityClass = quality === "good"
    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : quality === "partial"
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : quality === "poor"
        ? "bg-rose-50 text-rose-700 border-rose-200"
        : "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <div className="border-t border-gray-100 bg-gray-50 p-3 space-y-3">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Heard in audio</div>

      {a.transcript_full && (
        <div>
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
            Transcript · {a.transcript_full.split(/\s+/).filter(Boolean).length} words
          </div>
          <div className="bg-white border border-gray-200 rounded p-2 text-xs text-gray-800 whitespace-pre-wrap max-h-48 overflow-y-auto">
            {a.transcript_full}
          </div>
        </div>
      )}

      {(a.audio_events?.length ?? 0) > 0 && (
        <div>
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Audio events</div>
          <div className="flex flex-wrap gap-1">
            {a.audio_events!.map((ev, i) => (
              <span key={i} className="inline-block px-2 py-0.5 text-[11px] rounded-md border bg-violet-50 text-violet-700 border-violet-200">
                {String(ev)}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 text-[10px] text-gray-500 flex-wrap">
        <span>
          Quality:&nbsp;
          <span className={`inline-block px-1.5 py-0.5 rounded border ${qualityClass}`}>
            {quality}
          </span>
        </span>
        {a.language_detected && (
          <span>Language: <strong className="text-gray-700">{a.language_detected}</strong></span>
        )}
        {typeof a.speaker_count_estimate === "number" && (
          <span>Speakers (est): <strong className="text-gray-700">{a.speaker_count_estimate}</strong></span>
        )}
      </div>
    </div>
  );
}

function CombinedPanel({ row }: { row: LifelogRow }) {
  const c = row.combined_analysis;
  const recallTop = row.recall_estimate;
  if (!c && recallTop == null) return <PanelEmptyState modality="combined" />;
  const what = c?.what_is_happening ?? "";
  const who  = c?.user_activity_inferred ?? "";
  const conf = typeof c?.cross_modal_confidence === "number" ? c!.cross_modal_confidence : null;
  const recall = typeof c?.recall_estimate === "number" ? c!.recall_estimate
    : (typeof recallTop === "number" ? recallTop : null);
  const importance = typeof c?.importance_score === "number" ? c!.importance_score : null;
  const pct = (n: number) => `${Math.round(Math.max(0, Math.min(1, n)) * 100)}%`;
  const barFill = (n: number, good: boolean): string => {
    const v = Math.max(0, Math.min(1, n));
    if (good) {
      if (v >= 0.7) return "bg-emerald-500";
      if (v >= 0.4) return "bg-amber-500";
      return "bg-rose-500";
    }
    if (v >= 0.7) return "bg-blue-500";
    if (v >= 0.4) return "bg-slate-400";
    return "bg-rose-500";
  };
  return (
    <div className="border-t border-gray-100 bg-gray-50 p-3 space-y-3">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Synthesis</div>

      {what && (
        <div className="bg-white border border-gray-200 rounded p-3">
          <div className="text-sm text-gray-900 font-medium">{what}</div>
          {who && <div className="text-xs text-gray-600 mt-1">User activity: <span className="italic">{who}</span></div>}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {conf != null && (
          <div className="bg-white border border-gray-200 rounded p-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">Cross-modal confidence</span>
              <span className="text-xs font-semibold text-gray-700">{pct(conf)}</span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden mt-1">
              <div className={`h-full ${barFill(conf, false)}`} style={{ width: pct(conf) }} />
            </div>
          </div>
        )}
        {recall != null && (
          <div className="bg-white border border-gray-200 rounded p-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">Recall estimate</span>
              <span className="text-xs font-semibold text-gray-700">{pct(recall)}</span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden mt-1">
              <div className={`h-full ${barFill(recall, true)}`} style={{ width: pct(recall) }} />
            </div>
          </div>
        )}
      </div>

      {importance != null && (
        <div className="text-[10px] text-gray-500">
          Importance score: <strong className="text-gray-700">{pct(importance)}</strong>
        </div>
      )}

      {/* v3.1 Fix 3 — value updates across frames */}
      {(() => {
        const vu = (c?.value_updates ?? row.value_updates) || [];
        if (vu.length === 0) return null;
        return (
          <div>
            <div className="text-[10px] text-amber-700 uppercase tracking-wider mb-1">
              Value updates · {vu.length}
            </div>
            <ul className="space-y-1">
              {vu.slice(0, 20).map((u, i) => {
                const first = u.values?.[0];
                const last  = u.values?.[u.values.length - 1];
                if (!first || !last) return null;
                return (
                  <li key={i} className="text-xs text-gray-800 bg-white border border-amber-200 rounded p-2 flex items-baseline gap-2 flex-wrap">
                    <span className="text-amber-700">⚠</span>
                    <strong>{u.label}</strong>
                    <span className="font-mono">{first.value}</span>
                    <span className="text-[10px] text-gray-500">({first.timestamp_sec}s)</span>
                    <span className="text-gray-400">→</span>
                    <span className="font-mono">{last.value}</span>
                    <span className="text-[10px] text-gray-500">({last.timestamp_sec}s)</span>
                    {u.change_count > 2 && (
                      <span className="text-[10px] text-gray-500">· {u.change_count} updates</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })()}

      {/* v3.1 Fix 4 — timeline mini-table */}
      {(() => {
        const tl = (c?.timeline ?? row.timeline) || [];
        if (tl.length === 0) return null;
        return (
          <div>
            <div className="text-[10px] text-emerald-700 uppercase tracking-wider mb-1">
              Timeline · {tl.length} window{tl.length === 1 ? "" : "s"}
            </div>
            <div className="bg-white border border-gray-200 rounded overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="text-left px-2 py-1 text-[10px] text-gray-500 uppercase tracking-wider w-16">Window</th>
                    <th className="text-left px-2 py-1 text-[10px] text-gray-500 uppercase tracking-wider">Summary</th>
                    <th className="text-left px-2 py-1 text-[10px] text-gray-500 uppercase tracking-wider w-1/3">Key items</th>
                  </tr>
                </thead>
                <tbody>
                  {tl.map((w, i) => (
                    <tr key={i} className="border-t border-gray-100">
                      <td className="px-2 py-1 font-mono text-emerald-700">{w.window_sec}s</td>
                      <td className="px-2 py-1 text-gray-800">{w.summary || <span className="text-gray-400">—</span>}</td>
                      <td className="px-2 py-1 text-gray-600">
                        {(w.key_items || []).slice(0, 8).join(", ") || <span className="text-gray-400">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

// Folder name "lifelog icons" contains a space — URL-encoded as %20 so
// the browser fetches /icons/lifelog%20icons/<file>.png correctly.
const ICON_BASE = "/icons/lifelog%20icons";

// Map category → icon PNG (in public/icons/lifelog icons/). Categories not
// listed here fall back to the CATEGORY_EMOJI map below.
const CATEGORY_ICON_FILE: Record<string, string> = {
  activity:         "activity.jpg",
  interaction:      "interaction.jpeg",
  conversation:     "conversation.png",
  food:             "food.png",
  drink:            "drink.png",
  exercise:         "exercise.png",
  medication:       "medication.png",
  task_received:    "task.png",
  commitment_made:  "commitment done.png",
  purchase:         "purchase.svg",
  location_change:  "location.png",
  object_use:       "object use.png",
  screen_content:   "screen content.png",
  observation:      "observation.png",
};

// Fallback emojis (currently empty — every known category has a PNG/SVG/JPG).
// Kept so unknown categories from future schema additions still render.
const CATEGORY_EMOJI: Record<string, string> = {};

function CategoryIcon({ category, size = 28 }: { category: string | null; size?: number }) {
  if (!category) return <span style={{ fontSize: size }}>•</span>;
  const file = CATEGORY_ICON_FILE[category];
  if (file) {
    return (
      <img
        src={`${ICON_BASE}/${encodeURIComponent(file)}`}
        alt={category}
        width={size}
        height={size}
        style={{ objectFit: "contain" }}
      />
    );
  }
  const emoji = CATEGORY_EMOJI[category] || "•";
  return <span style={{ fontSize: size * 0.85, lineHeight: 1 }}>{emoji}</span>;
}

// Source-model tags come from _model_to_source_tag() — they encode the actual
// model id. Both legacy hardcoded values and current dynamic values are listed
// so historical rows still display correctly after the dynamic-tag migration.
const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  // ── Gemma 4 ──
  gemma4_31b:             { label: "Gemma 4 31B", cls: "bg-blue-100 text-blue-700 border-blue-200" },
  gemma4_26b_a4b_it_q8_0: { label: "Gemma 4 26B A4B", cls: "bg-blue-100 text-blue-700 border-blue-200" },
  gemma_4_e4b:            { label: "Gemma 4 E4B", cls: "bg-blue-100 text-blue-700 border-blue-200" }, // legacy
  // ── Qwen 3.5 VLM ──
  qwen3_5_397b_a17b:      { label: "Qwen 3.5 VLM", cls: "bg-purple-100 text-purple-700 border-purple-200" },
  qwen_3_5_vlm:           { label: "Qwen 3.5 VLM", cls: "bg-purple-100 text-purple-700 border-purple-200" }, // legacy
  // ── Llama 4 Maverick ──
  llama_4_maverick_17b_128e_inst: { label: "Llama 4 Maverick", cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  llama_4_maverick:               { label: "Llama 4 Maverick", cls: "bg-emerald-100 text-emerald-700 border-emerald-200" }, // legacy
  // ── Gemini 2.5 Pro ──
  gemini_2_5_pro:         { label: "Gemini 2.5 Pro", cls: "bg-amber-100 text-amber-700 border-amber-200" },
  // ── Merged ──
  merged:                 { label: "Merged", cls: "bg-gray-100 text-gray-700 border-gray-200" },
};

// Dropdown / askModel selectable tags — only the CURRENT dynamic tags
// (legacy values still render via SOURCE_BADGE but you can't filter to them).
const SELECTABLE_SOURCES = [
  "gemma4_26b_a4b_it_q8_0",
  "qwen3_5_397b_a17b",
  "llama_4_maverick_17b_128e_inst",
  "gemini_2_5_pro",
] as const;
type SelectableSource = typeof SELECTABLE_SOURCES[number];

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch {
    return iso;
  }
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return iso;
  }
}

// ─────────────────────────────────────────────────────────────────────
// Full Report — consolidated view of ALL events for one source_video
// ─────────────────────────────────────────────────────────────────────
type FullReport = {
  source_video: string;
  source_model: string;
  event_count: number;
  video_date: string;
  video_time_range: { start_sec: number; end_sec: number };
  duration_sec: number;
  overview: string;
  topics_covered: string[];
  all_observed_facts: string[];
  all_enumerated_observations: string[];
  all_ocr_text: string[];
  ocr_appendix_full: string[];
  audio_transcript_full: string;
  audio_quality: string;
  audio_events: string[];
  language_detected: string;
  timeline: Array<{ window_sec: string; summary: string; key_items: string[] }>;
  value_updates: Array<{ label: string; values: Array<{ value: string; timestamp_sec: number }>; change_count: number }>;
  visual_summary: {
    visual_objects: string[]; ui_elements: string[]; charts_detected: string[];
    headlines: string[]; panels_detected_count: number; broadcast_mode: boolean;
  };
  metrics: {
    total_ocr_items_captured: number; total_enumerated_observations: number;
    recall_estimate_avg: number; frame_sampling_rate_used: number;
    meaningful_ocr_items?: number; filtered_ocr_items?: number;
    meaningful_observations?: number; filtered_observations?: number;
  };
  metadata: { generated_at: string; schema_version: string };
};

function FRSection({ title, count, children, open = false }:
  { title: string; count?: number; children: React.ReactNode; open?: boolean }) {
  return (
    <details open={open} className="border-b border-gray-200 group">
      <summary className="cursor-pointer select-none px-4 py-2 font-semibold text-sm text-gray-800 hover:bg-gray-50 flex items-center justify-between">
        <span>{title}{count != null ? <span className="text-gray-400 font-normal"> · {count}</span> : null}</span>
        <span className="text-gray-300 text-xs group-open:rotate-90 transition-transform">▶</span>
      </summary>
      <div className="px-4 py-3 text-sm text-gray-700">{children}</div>
    </details>
  );
}

function FullReportModal({
  report, loading, error, onClose, onDownloadDocx,
}: {
  report: FullReport | null; loading: boolean; error: string | null;
  onClose: () => void; onDownloadDocx: () => void;
}) {
  const r = report;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
         onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden"
           onClick={e => e.stopPropagation()}>
        {/* sticky header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-bold text-gray-900 truncate">📄 Full Report</div>
            {r && (
              <div className="text-xs text-gray-500 truncate">
                {r.source_video} · {r.video_date} · {r.event_count} events · {r.source_model}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={onDownloadDocx} disabled={!r}
              className="text-sm px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40">
              📥 Download as Word
            </button>
            <button onClick={onClose} aria-label="close"
              className="text-gray-400 hover:text-gray-700 text-xl leading-none px-2">×</button>
          </div>
        </div>

        <div className="overflow-y-auto">
          {loading && <div className="p-8 text-center text-gray-500">Aggregating events…</div>}
          {error && <div className="p-8 text-center text-rose-600">Failed to load report: {error}</div>}
          {r && (
            <>
              <FRSection title="Key Findings" open>
                {r.overview ? <p className="leading-relaxed">{r.overview}</p>
                  : <p className="italic text-gray-400">No overview.</p>}
                {r.topics_covered.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {r.topics_covered.map((t, i) => (
                      <span key={i} className="px-2 py-0.5 text-xs rounded-full bg-blue-50 text-blue-700 border border-blue-200">{t}</span>
                    ))}
                  </div>
                )}
              </FRSection>

              <FRSection title="Observed Facts" count={r.all_observed_facts.length} open>
                {r.all_observed_facts.length > 0 ? (
                  <ol className="list-decimal list-inside space-y-1">
                    {r.all_observed_facts.map((f, i) => <li key={i}>{f}</li>)}
                  </ol>
                ) : <p className="italic text-gray-400">No observed facts.</p>}
              </FRSection>

              <FRSection title="Audio Transcript">
                <div className="text-xs text-gray-500 mb-1">
                  Quality: {r.audio_quality || "—"} · Language: {r.language_detected || "—"}
                  {r.audio_events.length > 0 ? ` · ${r.audio_events.join(", ")}` : ""}
                </div>
                {r.audio_transcript_full
                  ? <p className="whitespace-pre-wrap leading-relaxed">{r.audio_transcript_full}</p>
                  : <p className="italic text-gray-400">No audio captured for this clip.</p>}
              </FRSection>

              <FRSection title="Timeline" count={r.timeline.length}>
                {r.timeline.length > 0 ? (
                  <table className="w-full text-xs border-collapse">
                    <thead><tr className="bg-gray-50 text-gray-500">
                      <th className="text-left p-1 border border-gray-200 w-16">Window</th>
                      <th className="text-left p-1 border border-gray-200">Summary</th>
                      <th className="text-left p-1 border border-gray-200 w-1/3">Key items</th>
                    </tr></thead>
                    <tbody>
                      {r.timeline.map((w, i) => (
                        <tr key={i}>
                          <td className="p-1 border border-gray-200 font-mono">{w.window_sec}s</td>
                          <td className="p-1 border border-gray-200">{w.summary || "—"}</td>
                          <td className="p-1 border border-gray-200 text-gray-500">{(w.key_items || []).join(", ") || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : <p className="italic text-gray-400">No timeline windows.</p>}
              </FRSection>

              <FRSection title="Value Updates" count={r.value_updates.length}>
                {r.value_updates.length > 0 ? (
                  <ul className="space-y-1">
                    {r.value_updates.map((v, i) => (
                      <li key={i}><strong>{v.label}</strong>: {v.values.map(x => x.value).join(" → ")}
                        {v.change_count > 1 ? <span className="text-gray-400"> ({v.change_count} changes)</span> : null}</li>
                    ))}
                  </ul>
                ) : <p className="italic text-gray-400">No metric value changes detected.</p>}
              </FRSection>

              <FRSection title="Visual Content">
                {r.visual_summary.headlines.length > 0 && (
                  <div className="mb-2"><div className="text-xs text-gray-500 uppercase">Headlines</div>
                    <ul className="list-disc list-inside">{r.visual_summary.headlines.map((h, i) => <li key={i}>{h}</li>)}</ul></div>
                )}
                <div className="flex flex-wrap gap-1">
                  {r.visual_summary.visual_objects.map((o, i) =>
                    <span key={i} className="px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-700 border border-slate-200">{o}</span>)}
                </div>
                <div className="text-xs text-gray-500 mt-2">
                  Panels: {r.visual_summary.panels_detected_count} · Broadcast: {r.visual_summary.broadcast_mode ? "yes" : "no"}
                </div>
              </FRSection>

              <FRSection title="Key Terms Captured" count={r.all_ocr_text.length}>
                <p className="text-xs text-gray-500 mb-1">Filtered OCR — numbers, prices, names, headlines.</p>
                <p className="text-[11px] text-gray-700 leading-relaxed break-words">{r.all_ocr_text.join(" · ") || "—"}</p>
              </FRSection>

              <FRSection title="Technical OCR Reference (raw)" count={r.ocr_appendix_full.length}>
                <p className="text-xs italic text-gray-400 mb-1">For technical verification only — raw items that did not pass quality filtering.</p>
                <p className="text-[10px] text-gray-400 leading-snug break-words">{r.ocr_appendix_full.join(" · ") || "—"}</p>
              </FRSection>

              <div className="px-4 py-2 text-[10px] text-gray-400 border-t border-gray-100">
                schema {r.metadata.schema_version} · recall est {r.metrics.recall_estimate_avg} ·
                OCR {r.metrics.total_ocr_items_captured} captured · generated {r.metadata.generated_at?.slice(0, 19)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function LifelogPage() {
  const [userId, setUserId] = useState(1);
  const [date, setDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [sourceFilter, setSourceFilter] = useState<"all" | SelectableSource>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [rows, setRows] = useState<LifelogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Unified "which inline panel is open on which event" state — only ONE
  // panel can be open at a time across the 5 possible kinds. Clicking a
  // different button on the same event swaps the kind; clicking the same
  // button again closes it.
  type PanelKind = "ask" | "details" | "video" | "audio" | "combined";
  const [openPanel, setOpenPanel] = useState<{ id: number; kind: PanelKind } | null>(null);
  // Full Report modal (keyed by source_video; scoped by the source dropdown).
  const [fullReportSource, setFullReportSource] = useState<string | null>(null);
  const [fullReport, setFullReport] = useState<FullReport | null>(null);
  const [fullReportLoading, setFullReportLoading] = useState(false);
  const [fullReportError, setFullReportError] = useState<string | null>(null);
  const togglePanel = (id: number, kind: PanelKind) => {
    setOpenPanel(prev => (prev && prev.id === id && prev.kind === kind ? null : { id, kind }));
  };
  const isOpen = (id: number, kind: PanelKind) =>
    openPanel != null && openPanel.id === id && openPanel.kind === kind;
  const [askQuestion, setAskQuestion] = useState("");
  const [askModel, setAskModel] = useState<SelectableSource>("llama_4_maverick_17b_128e_inst");
  const [askLoading, setAskLoading] = useState(false);
  const [askAnswer, setAskAnswer] = useState<{ answer: string; model: string; latency_ms: number; frames_used: number; transcript_excerpt: string } | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  async function reanalyze(sourceVideo: string) {
    if (!askQuestion.trim() || askLoading) return;
    setAskLoading(true);
    setAskError(null);
    setAskAnswer(null);
    try {
      const r = await fetch(`${API_BASE}/lifelog/reanalyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          model: askModel,
          source_video: sourceVideo,
          question: askQuestion.trim(),
          frames: 8,
        }),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`HTTP ${r.status}: ${body.slice(0, 240)}`);
      }
      setAskAnswer(await r.json());
    } catch (e: any) {
      setAskError(e?.message || String(e));
    } finally {
      setAskLoading(false);
    }
  }

  // Restore filters from URL on mount
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const u = parseInt(sp.get("user") || "1", 10);
    if (!isNaN(u)) setUserId(u);
    const d = sp.get("date");
    if (d) setDate(d);
    const src = sp.get("source");
    if (src && (SELECTABLE_SOURCES as readonly string[]).includes(src)) setSourceFilter(src as SelectableSource);
    const cat = sp.get("category");
    if (cat) setCategoryFilter(cat);
  }, []);

  // Persist filters to URL
  useEffect(() => {
    const sp = new URLSearchParams();
    sp.set("user", String(userId));
    sp.set("date", date);
    if (sourceFilter !== "all") sp.set("source", sourceFilter);
    if (categoryFilter !== "all") sp.set("category", categoryFilter);
    window.history.replaceState(null, "", `?${sp.toString()}`);
  }, [userId, date, sourceFilter, categoryFilter]);

  // Fetch lifelog events for the day, via FastAPI (same pattern as the
  // main HRT dashboard).
  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    params.set("user_id", String(userId));
    params.set("date", date);
    fetch(`${API_BASE}/lifelog/events?${params.toString()}`)
      .then(async r => {
        if (!r.ok) throw new Error(`HTTP ${r.status} — backend not running?`);
        return r.json();
      })
      .then((data: { events?: LifelogRow[] }) => {
        setRows(Array.isArray(data.events) ? data.events : []);
      })
      .catch(e => {
        setError(`Fetch failed: ${e?.message || String(e)}. Make sure FastAPI is running on :8888.`);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [userId, date]);

  // Full Report: fetch the consolidated aggregation when a video is selected.
  // Scoped by the source dropdown (specific arm, or all arms when "all").
  useEffect(() => {
    if (!fullReportSource) return;
    setFullReportLoading(true);
    setFullReportError(null);
    setFullReport(null);
    const p = new URLSearchParams();
    p.set("source_video", fullReportSource);
    p.set("user_id", String(userId));
    if (sourceFilter !== "all") p.set("source_model", sourceFilter);
    fetch(`${API_BASE}/lifelog/full-report?${p.toString()}`)
      .then(r => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then((d) => { if (d.error) throw new Error(d.error); setFullReport(d); })
      .catch(e => setFullReportError(String(e)))
      .finally(() => setFullReportLoading(false));
  }, [fullReportSource, userId, sourceFilter]);

  function handleDownloadDocx() {
    if (!fullReportSource) return;
    const p = new URLSearchParams();
    p.set("source_video", fullReportSource);
    p.set("user_id", String(userId));
    if (sourceFilter !== "all") p.set("source_model", sourceFilter);
    // server sets Content-Disposition: attachment → browser downloads
    window.location.href = `${API_BASE}/lifelog/full-report.docx?${p.toString()}`;
  }

  // Apply client-side filters
  const filtered = useMemo(() => rows.filter(r =>
    (sourceFilter === "all" || r.source_model === sourceFilter) &&
    (categoryFilter === "all" || r.category === categoryFilter)
  ), [rows, sourceFilter, categoryFilter]);

  // KPI summary (computed over filtered rows)
  const kpi = useMemo(() => {
    const peopleSeen = new Set<string>();
    let totalKcal = 0;
    let totalExerciseSec = 0;
    let totalEvents = filtered.length;
    let conversationCount = 0;
    for (const r of filtered) {
      (r.people || []).forEach(p => peopleSeen.add(p));
      if (r.kcal) totalKcal += r.kcal;
      if (r.category === "exercise" && r.duration_sec) totalExerciseSec += r.duration_sec;
      if (r.category === "interaction" || r.category === "conversation") conversationCount++;
    }
    return {
      events: totalEvents,
      people: peopleSeen.size,
      kcal: totalKcal,
      exerciseMin: Math.round(totalExerciseSec / 60),
      conversations: conversationCount,
    };
  }, [filtered]);

  const allCategories = useMemo(() => {
    const s = new Set<string>();
    rows.forEach(r => r.category && s.add(r.category));
    return Array.from(s).sort();
  }, [rows]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Link href="/" className="text-sm text-gray-500 hover:text-gray-800">← HRT Dashboard</Link>
              <span className="text-gray-300">|</span>
              <h1 className="text-2xl font-bold text-gray-900">Daily Lifelog</h1>
              <span className="text-gray-300">|</span>
              <Link
                href="/lifelog/ask"
                className="text-sm font-semibold text-blue-600 hover:text-blue-800"
              >
                💬 Ask your day →
              </Link>
            </div>
            <p className="text-xs text-gray-500">
              Every event AI-glasses pipeline extracted from your video.
              Triple-H Co., Ltd. | Patent No. 10-2025-0145274
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-600">User ID:</label>
              <input type="number" value={userId} onChange={e => setUserId(parseInt(e.target.value) || 1)}
                className="px-2 py-1.5 border border-gray-300 rounded-md text-sm w-20" />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-600">Date:</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)}
                className="px-2 py-1.5 border border-gray-300 rounded-md text-sm" />
            </div>
          </div>
        </div>
      </header>

      {/* Filter bar */}
      <div className="bg-gray-100 border-b border-gray-200 px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-700">Source:</label>
          <select value={sourceFilter} onChange={e => setSourceFilter(e.target.value as any)}
            className="px-2 py-1 border border-gray-300 rounded text-xs">
            <option value="all">All sources</option>
            {SELECTABLE_SOURCES.map(k => (
              <option key={k} value={k}>{SOURCE_BADGE[k]?.label || k} only</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-700">Category:</label>
          <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}
            className="px-2 py-1 border border-gray-300 rounded text-xs">
            <option value="all">All categories</option>
            {allCategories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="ml-auto text-xs text-gray-500">
          {loading ? "Loading..." : `${filtered.length} / ${rows.length} events`}
        </div>
      </div>

      {/* KPI strip */}
      <div className="px-6 py-4 grid grid-cols-2 sm:grid-cols-5 gap-3">
        {[
          { file: "events.png",       label: "Events",         value: kpi.events.toLocaleString() },
          { file: "colleagues.png",   label: "People seen",    value: kpi.people.toString() },
          { file: "kcal.png",         label: "Total kcal",     value: kpi.kcal.toLocaleString() },
          { file: "exercise.png",     label: "Exercise (min)", value: kpi.exerciseMin.toString() },
          { file: "conversation.png", label: "Conversations",  value: kpi.conversations.toString() },
        ].map((k, i) => (
          <div key={i} className="bg-white border border-gray-200 rounded-lg p-4 flex items-center gap-3">
            <img
              src={`${ICON_BASE}/${encodeURIComponent(k.file)}`}
              alt={k.label}
              width={32}
              height={32}
              style={{ objectFit: "contain" }}
            />
            <div>
              <div className="text-xs text-gray-500 uppercase tracking-wider">{k.label}</div>
              <div className="text-xl font-bold text-gray-900">{k.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Timeline */}
      <div className="px-6 pb-12">
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-700 text-sm">
            {error}
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center text-gray-500">
            <p className="text-lg mb-2">No events for {date}</p>
            <p className="text-sm">
              Run <code className="px-1.5 py-0.5 bg-gray-100 rounded text-xs">_lifelog_test.py</code> on a video
              file to populate this view.
            </p>
          </div>
        )}

        <div className="space-y-2">
          {filtered.map((r) => {
            const src = SOURCE_BADGE[r.source_model] || { label: r.source_model, cls: "bg-gray-100 text-gray-700" };
            const inlineIconSize = 14;
            const inlineIcon = (file: string, alt: string) => (
              <img
                src={`${ICON_BASE}/${encodeURIComponent(file)}`}
                alt={alt}
                width={inlineIconSize}
                height={inlineIconSize}
                style={{ display: "inline-block", verticalAlign: "-2px", objectFit: "contain" }}
              />
            );
            return (
              <div key={r.lifelog_id} className="bg-white border border-gray-200 rounded-lg">
              <div className="p-3 flex gap-3">
                {/* Time */}
                <div className="flex-shrink-0 w-16 text-right">
                  <div className="text-sm font-mono text-gray-700">{fmtTime(r.observed_at)}</div>
                  {r.duration_sec && (
                    <div className="text-xs text-gray-400">{r.duration_sec}s</div>
                  )}
                </div>
                {/* Icon */}
                <div className="flex-shrink-0 pt-0.5">
                  <CategoryIcon category={r.category} size={28} />
                </div>
                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      {r.category || "—"}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${src.cls}`}>
                      {src.label}
                    </span>
                    {r.location && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200 inline-flex items-center gap-1">
                        {inlineIcon("location.png", "location")} {r.location}
                      </span>
                    )}
                    {r.mood && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-50 text-yellow-700 border border-yellow-200">
                        {r.mood}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-900 mt-1">{r.description}</div>
                  {(r.topic || r.decision) && (
                    <div className="mt-1 text-xs text-gray-600 space-y-0.5">
                      {r.topic && (
                        <div>
                          {inlineIcon("topic.png", "topic")} <span className="font-medium">Topic:</span> {r.topic}
                        </div>
                      )}
                      {r.decision && (
                        <div>
                          ✅ <span className="font-medium">Decision:</span> {r.decision}
                        </div>
                      )}
                    </div>
                  )}
                  {(r.people && r.people.length > 0) && (
                    <div className="mt-1 text-xs text-gray-500 inline-flex items-center gap-1">
                      {inlineIcon("colleagues.png", "people")} {r.people.join(", ")} {r.people_count ? `(${r.people_count} visible)` : ""}
                    </div>
                  )}
                  {r.objects && r.objects.length > 0 && (
                    <div className="mt-1 text-xs text-gray-500 inline-flex items-center gap-1">
                      {inlineIcon("object use.png", "objects")} {r.objects.join(", ")}
                    </div>
                  )}
                  {r.screen && (
                    <div className="mt-1 text-xs text-gray-500 inline-flex items-center gap-1">
                      {inlineIcon("screen content.png", "screen")} {r.screen}
                    </div>
                  )}
                  {(r.kcal || r.amount_ml) && (
                    <div className="mt-1 text-xs text-gray-500">
                      {r.kcal ? `${r.kcal} kcal ` : ""}
                      {r.amount_ml ? `${r.amount_ml} ml` : ""}
                    </div>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2 items-center">
                    {r.source_video && (
                      <button
                        onClick={() => {
                          const opening = !isOpen(r.lifelog_id, "ask");
                          togglePanel(r.lifelog_id, "ask");
                          if (opening) { setAskQuestion(""); setAskAnswer(null); setAskError(null); }
                        }}
                        className={`text-xs px-2 py-1 rounded border transition-colors ${
                          isOpen(r.lifelog_id, "ask")
                            ? "bg-blue-600 text-white border-blue-600"
                            : "bg-white text-blue-700 border-blue-200 hover:bg-blue-50"
                        }`}
                      >
                        {isOpen(r.lifelog_id, "ask") ? "× Close Ask" : "🔍 Ask about this clip"}
                      </button>
                    )}
                    <button
                      onClick={() => togglePanel(r.lifelog_id, "details")}
                      className={`text-xs px-2 py-1 rounded border transition-colors ${
                        isOpen(r.lifelog_id, "details")
                          ? "bg-gray-700 text-white border-gray-700"
                          : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
                      }`}
                    >
                      {isOpen(r.lifelog_id, "details") ? "× Hide details" : "📋 More details"}
                    </button>
                    <button
                      onClick={() => togglePanel(r.lifelog_id, "video")}
                      className={`text-xs px-2 py-1 rounded border transition-colors ${
                        isOpen(r.lifelog_id, "video")
                          ? "bg-blue-600 text-white border-blue-600"
                          : "bg-white text-blue-700 border-blue-200 hover:bg-blue-50"
                      }`}
                      title="Visible on screen — OCR + visual objects"
                    >
                      🎥 Video/Frames {videoBadgeCount(r) > 0 ? `(${videoBadgeCount(r)})` : ""}
                    </button>
                    <button
                      onClick={() => togglePanel(r.lifelog_id, "audio")}
                      className={`text-xs px-2 py-1 rounded border transition-colors ${
                        isOpen(r.lifelog_id, "audio")
                          ? "bg-violet-600 text-white border-violet-600"
                          : "bg-white text-violet-700 border-violet-200 hover:bg-violet-50"
                      }`}
                      title="Heard in audio — transcript + audio events"
                    >
                      🎤 Audio {audioBadgeCount(r) > 0 ? `(${audioBadgeCount(r)})` : ""}
                    </button>
                    <button
                      onClick={() => togglePanel(r.lifelog_id, "combined")}
                      className={`text-xs px-2 py-1 rounded border transition-colors ${
                        isOpen(r.lifelog_id, "combined")
                          ? "bg-emerald-600 text-white border-emerald-600"
                          : "bg-white text-emerald-700 border-emerald-200 hover:bg-emerald-50"
                      }`}
                      title="Cross-modal synthesis"
                    >
                      🧠 Combined{combinedBadgeMark(r)}
                    </button>
                    {r.source_video && (
                      <button
                        onClick={() => setFullReportSource(r.source_video!)}
                        className="text-xs px-2 py-1 rounded border transition-colors bg-white text-blue-700 border-blue-300 hover:bg-blue-50 font-medium"
                        title="Consolidated report across all events for this video"
                      >
                        📄 Full Report
                      </button>
                    )}
                  </div>
                </div>
              </div>
              {isOpen(r.lifelog_id, "details") && <DetailsPanel row={r} />}
              {isOpen(r.lifelog_id, "video")    && <VideoPanel    row={r} />}
              {isOpen(r.lifelog_id, "audio")    && <AudioPanel    row={r} />}
              {isOpen(r.lifelog_id, "combined") && <CombinedPanel row={r} />}
              {isOpen(r.lifelog_id, "ask") && r.source_video && (
                <div className="border-t border-gray-100 bg-gray-50 p-3 space-y-2">
                  <div className="text-[10px] text-gray-500">
                    Re-analysing clip <code className="px-1 bg-white border border-gray-200 rounded">{r.source_video}</code> with the model below.
                    Frames + audio are re-sampled from the original file.
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {SELECTABLE_SOURCES.map(k => {
                      const active = askModel === k;
                      return (
                        <button
                          key={k}
                          onClick={() => setAskModel(k)}
                          className={`px-2 py-1 rounded border text-xs ${
                            active
                              ? (SOURCE_BADGE[k]?.cls || "bg-blue-100 text-blue-700 border-blue-200") + " font-semibold"
                              : "bg-white border-gray-300 text-gray-700 hover:bg-gray-100"
                          }`}
                        >
                          {SOURCE_BADGE[k]?.label || k}
                        </button>
                      );
                    })}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={askQuestion}
                      onChange={e => setAskQuestion(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") reanalyze(r.source_video!); }}
                      placeholder="e.g. What was the book on the desk? What brand was the coffee cup?"
                      className="flex-1 px-2 py-1 text-xs border border-gray-300 rounded"
                      disabled={askLoading}
                    />
                    <button
                      onClick={() => reanalyze(r.source_video!)}
                      disabled={askLoading || !askQuestion.trim()}
                      className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300"
                    >
                      {askLoading ? "…" : "Ask"}
                    </button>
                  </div>
                  {askError && (
                    <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2">{askError}</div>
                  )}
                  {askAnswer && (
                    <div className="bg-white border border-gray-200 rounded p-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${SOURCE_BADGE[askAnswer.model]?.cls || "bg-gray-100 text-gray-700 border-gray-200"}`}>
                          {SOURCE_BADGE[askAnswer.model]?.label || askAnswer.model}
                        </span>
                        <span className="text-[10px] text-gray-400">{(askAnswer.latency_ms / 1000).toFixed(1)}s · {askAnswer.frames_used} frames</span>
                      </div>
                      <div className="text-sm text-gray-900 whitespace-pre-wrap">{askAnswer.answer}</div>
                      {askAnswer.transcript_excerpt && (
                        <details className="mt-2">
                          <summary className="text-[10px] text-gray-500 cursor-pointer">audio transcript</summary>
                          <div className="text-[10px] text-gray-600 mt-1 whitespace-pre-wrap">{askAnswer.transcript_excerpt}</div>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              )}
              </div>
            );
          })}
        </div>
      </div>

      <footer className="border-t border-gray-200 py-4 px-6 text-xs text-gray-500 flex justify-between">
        <span>© 2025 Triple-H Co., Ltd. All rights reserved.</span>
        <span>Daily Lifelog v1.0 · reads <code>lifelog_event</code> table</span>
      </footer>

      {fullReportSource && (
        <FullReportModal
          report={fullReport}
          loading={fullReportLoading}
          error={fullReportError}
          onClose={() => { setFullReportSource(null); setFullReport(null); setFullReportError(null); }}
          onDownloadDocx={handleDownloadDocx}
        />
      )}
    </div>
  );
}
