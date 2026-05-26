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

const API_BASE = "http://localhost:8000/api/v1";

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
}

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

const detailsBadgeStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 6px",
  border: "1px solid var(--border)",
  borderRadius: 4,
  background: "var(--background)",
  color: "var(--text-primary)",
  fontSize: 11,
  marginRight: 6,
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

function DetailsPanel({ row }: { row: LifelogRow }) {
  const facts = row.observed_facts || [];
  const context = row.inferred_context || [];
  const hasBadges =
    row.confidence != null || (row.importance != null && row.importance !== "") || row.memory_relevance != null;
  const hasAttention = (row.attention_target && row.attention_target !== "") || row.duration_sec != null;

  return (
    <div style={detailsPanelStyle}>
      {hasBadges && (
        <div>
          {row.confidence != null && (
            <span style={detailsBadgeStyle}>
              confidence: {(row.confidence * 100).toFixed(0)}%
            </span>
          )}
          {row.importance && (
            <span style={detailsBadgeStyle}>importance: {String(row.importance)}</span>
          )}
          {row.memory_relevance != null && (
            <span style={detailsBadgeStyle}>memory: {String(row.memory_relevance)}</span>
          )}
        </div>
      )}

      {hasAttention && (
        <div style={{ marginTop: hasBadges ? 8 : 0 }}>
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

      {row.screen_analysis && <KeyValueBlock title="Screen analysis" data={row.screen_analysis} />}
      {row.technical_analysis && <KeyValueBlock title="Technical analysis" data={row.technical_analysis} />}
      {row.macro && <KeyValueBlock title="Macro" data={row.macro} />}
      {row.conversation_detail && <KeyValueBlock title="Conversation detail" data={row.conversation_detail} />}
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

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  gemma_4_e4b: { label: "Gemma 4", cls: "bg-blue-100 text-blue-700 border-blue-200" },
  qwen_3_5_vlm: { label: "Qwen 3.5", cls: "bg-purple-100 text-purple-700 border-purple-200" },
  llama_4_maverick: { label: "Llama 4", cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  gemini_2_5_pro: { label: "Gemini 2.5 Pro", cls: "bg-amber-100 text-amber-700 border-amber-200" },
  merged: { label: "Merged", cls: "bg-gray-100 text-gray-700 border-gray-200" },
};

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

export default function LifelogPage() {
  const [userId, setUserId] = useState(1);
  const [date, setDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [sourceFilter, setSourceFilter] = useState<"all" | "gemma_4_e4b" | "qwen_3_5_vlm" | "llama_4_maverick" | "gemini_2_5_pro">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [rows, setRows] = useState<LifelogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // "Ask about this clip" inline-panel state (per event)
  const [askExpandedId, setAskExpandedId] = useState<number | null>(null);
  // "More details" inline-panel state (per event, independent of Ask)
  const [detailsExpandedId, setDetailsExpandedId] = useState<number | null>(null);
  const [askQuestion, setAskQuestion] = useState("");
  const [askModel, setAskModel] = useState<"gemma_4_e4b" | "qwen_3_5_vlm" | "llama_4_maverick">("llama_4_maverick");
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
    if (src === "gemma_4_e4b" || src === "qwen_3_5_vlm" || src === "llama_4_maverick" || src === "gemini_2_5_pro") setSourceFilter(src);
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
        setError(`Fetch failed: ${e?.message || String(e)}. Make sure FastAPI is running on :8000.`);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [userId, date]);

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
            <option value="gemma_4_e4b">Gemma 4 only</option>
            <option value="qwen_3_5_vlm">Qwen 3.5 only</option>
            <option value="llama_4_maverick">Llama 4 only</option>
            <option value="gemini_2_5_pro">Gemini 2.5 Pro only</option>
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
                  <div className="mt-2 flex flex-wrap gap-3 items-center">
                    {r.source_video && (
                      <button
                        onClick={() => {
                          if (askExpandedId === r.lifelog_id) {
                            setAskExpandedId(null);
                          } else {
                            setAskExpandedId(r.lifelog_id);
                            setAskQuestion("");
                            setAskAnswer(null);
                            setAskError(null);
                          }
                        }}
                        className="text-xs text-blue-600 hover:text-blue-800 hover:underline"
                      >
                        {askExpandedId === r.lifelog_id ? "× Close" : "🔍 Ask about this clip"}
                      </button>
                    )}
                    <button
                      onClick={() =>
                        setDetailsExpandedId(detailsExpandedId === r.lifelog_id ? null : r.lifelog_id)
                      }
                      className="text-xs hover:underline"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {detailsExpandedId === r.lifelog_id ? "× Hide details" : "📋 More details"}
                    </button>
                  </div>
                </div>
              </div>
              {detailsExpandedId === r.lifelog_id && <DetailsPanel row={r} />}
              {askExpandedId === r.lifelog_id && r.source_video && (
                <div className="border-t border-gray-100 bg-gray-50 p-3 space-y-2">
                  <div className="text-[10px] text-gray-500">
                    Re-analysing clip <code className="px-1 bg-white border border-gray-200 rounded">{r.source_video}</code> with the model below.
                    Frames + audio are re-sampled from the original file.
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(["gemma_4_e4b", "qwen_3_5_vlm", "llama_4_maverick"] as const).map(k => {
                      const labelMap: Record<string, string> = {
                        gemma_4_e4b: "Gemma 4",
                        qwen_3_5_vlm: "Qwen 3.5",
                        llama_4_maverick: "Llama 4",
                      };
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
                          {labelMap[k]}
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
    </div>
  );
}
