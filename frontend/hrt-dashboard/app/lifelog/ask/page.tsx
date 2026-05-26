"use client";

// /lifelog/ask — chat with one of three LLMs about your day.
// Backend: POST /api/v1/lifelog/chat. Text-RAG over the lifelog_event table.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

const API_BASE = "http://localhost:8000/api/v1";

type ModelKey = "gemma_4_e4b" | "qwen_3_5_vlm" | "llama_4_maverick";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  model?: ModelKey;
  latency_ms?: number;
  events_in_context?: number;
  escalated?: boolean;
  first_pass_answer?: string;
  escalation_reason?: string;
  reanalyze_source_video?: string;
  reanalyze_frames_used?: number;
  reanalyze_latency_ms?: number;
  reanalyze_transcript_excerpt?: string;
  escalation_error?: string;
}

const MODEL_INFO: Record<ModelKey, { label: string; tag: string; cls: string; hint: string }> = {
  gemma_4_e4b: {
    label: "Gemma 4",
    tag: "Mac mini · fast · free",
    cls: "border-blue-500 bg-blue-50 text-blue-700",
    hint: "Local — fastest, no NIM credits used.",
  },
  qwen_3_5_vlm: {
    label: "Qwen 3.5",
    tag: "NIM · 397B · deep",
    cls: "border-purple-500 bg-purple-50 text-purple-700",
    hint: "Large NIM model — good for long-context reasoning over the day.",
  },
  llama_4_maverick: {
    label: "Llama 4",
    tag: "NIM · 400B · strong",
    cls: "border-emerald-500 bg-emerald-50 text-emerald-700",
    hint: "Maverick — strongest reasoning. Burns NIM credits fastest.",
  },
};

const SAMPLE_QUESTIONS = [
  "What did I eat yesterday?",
  "Who did I meet today?",
  "Where was I on Saturday morning?",
  "Did I make any decisions in meetings this week?",
  "Summarize my day in 3 sentences.",
];

export default function LifelogAskPage() {
  const [userId, setUserId] = useState(1);
  const [model, setModel] = useState<ModelKey>("gemma_4_e4b");
  const [lookbackDays, setLookbackDays] = useState(7);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMsg: ChatMessage = { role: "user", content: trimmed };
    const history = messages.map(m => ({ role: m.role, content: m.content }));
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const r = await fetch(`${API_BASE}/lifelog/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          model,
          message: trimmed,
          history,
          lookback_days: lookbackDays,
        }),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`HTTP ${r.status}: ${body.slice(0, 240)}`);
      }
      const data = await r.json();
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "(empty response)",
          model: data.model,
          latency_ms: data.latency_ms,
          events_in_context: data.events_in_context,
          escalated: data.escalated,
          first_pass_answer: data.first_pass_answer,
          escalation_reason: data.escalation_reason,
          reanalyze_source_video: data.reanalyze_source_video,
          reanalyze_frames_used: data.reanalyze_frames_used,
          reanalyze_latency_ms: data.reanalyze_latency_ms,
          reanalyze_transcript_excerpt: data.reanalyze_transcript_excerpt,
          escalation_error: data.escalation_error,
        },
      ]);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  function clearChat() {
    setMessages([]);
    setError(null);
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Link href="/lifelog" className="text-sm text-gray-500 hover:text-gray-800">
                ← Daily Lifelog
              </Link>
              <span className="text-gray-300">|</span>
              <h1 className="text-2xl font-bold text-gray-900">Ask your day</h1>
            </div>
            <p className="text-xs text-gray-500">
              Chat with Gemma 4 / Qwen 3.5 / Llama 4 about everything your AI glasses recorded.
              Triple-H Co., Ltd. | Patent No. 10-2025-0145274
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-600">User ID:</label>
              <input
                type="number"
                value={userId}
                onChange={e => setUserId(parseInt(e.target.value) || 1)}
                className="px-2 py-1.5 border border-gray-300 rounded-md text-sm w-20"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-600">Lookback:</label>
              <select
                value={lookbackDays}
                onChange={e => setLookbackDays(parseInt(e.target.value))}
                className="px-2 py-1.5 border border-gray-300 rounded-md text-sm"
              >
                <option value={1}>1 day</option>
                <option value={3}>3 days</option>
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={30}>30 days</option>
              </select>
            </div>
            <button
              onClick={clearChat}
              className="px-3 py-1.5 text-xs text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Clear
            </button>
          </div>
        </div>
      </header>

      {/* Model selector */}
      <div className="bg-gray-100 border-b border-gray-200 px-6 py-3 flex items-center gap-3 flex-wrap">
        <span className="text-xs font-medium text-gray-700">Model:</span>
        {(Object.keys(MODEL_INFO) as ModelKey[]).map(k => {
          const info = MODEL_INFO[k];
          const active = model === k;
          return (
            <button
              key={k}
              onClick={() => setModel(k)}
              className={`px-3 py-1.5 rounded-md border text-xs transition-colors ${
                active ? info.cls + " font-semibold" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
              }`}
              title={info.hint}
            >
              {info.label} <span className="opacity-60 ml-1">· {info.tag}</span>
            </button>
          );
        })}
        <span className="ml-auto text-xs text-gray-500">{MODEL_INFO[model].hint}</span>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="max-w-2xl mx-auto bg-white border border-gray-200 rounded-lg p-6">
            <p className="text-sm text-gray-600 mb-3">
              Ask the AI anything about what you did, ate, said, saw, or decided.
              Answers are grounded in your <code className="px-1 bg-gray-100 rounded text-xs">lifelog_event</code> rows
              for the last {lookbackDays} day{lookbackDays === 1 ? "" : "s"}.
            </p>
            <div className="text-xs text-gray-500 mb-2">Try:</div>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="px-2 py-1 bg-gray-50 border border-gray-200 rounded text-xs text-gray-700 hover:bg-gray-100"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="max-w-3xl mx-auto space-y-3">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-3 ${
                  m.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-white border border-gray-200 text-gray-900"
                }`}
              >
                {m.role === "assistant" && m.model && (
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded border ${MODEL_INFO[m.model].cls}`}
                    >
                      {MODEL_INFO[m.model].label}
                    </span>
                    {m.escalated && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-200">
                        🔍 looked at the clip
                      </span>
                    )}
                    {typeof m.latency_ms === "number" && (
                      <span className="text-[10px] text-gray-400">
                        {((m.latency_ms + (m.reanalyze_latency_ms || 0)) / 1000).toFixed(1)}s
                      </span>
                    )}
                    {typeof m.events_in_context === "number" && (
                      <span className="text-[10px] text-gray-400">
                        · {m.events_in_context} event{m.events_in_context === 1 ? "" : "s"}
                      </span>
                    )}
                    {m.reanalyze_frames_used && (
                      <span className="text-[10px] text-gray-400">
                        · {m.reanalyze_frames_used} frames
                      </span>
                    )}
                  </div>
                )}
                <div className="text-sm whitespace-pre-wrap">{m.content}</div>
                {m.role === "assistant" && m.escalated && (
                  <details className="mt-2 text-[10px] text-gray-500">
                    <summary className="cursor-pointer hover:text-gray-700">
                      how this answer was found
                    </summary>
                    <div className="mt-1 space-y-1 bg-gray-50 border border-gray-200 rounded p-2">
                      {m.first_pass_answer && (
                        <div>
                          <span className="font-medium text-gray-600">First pass (events only):</span>{" "}
                          <span className="italic">{m.first_pass_answer}</span>
                        </div>
                      )}
                      {m.reanalyze_source_video && (
                        <div>
                          <span className="font-medium text-gray-600">Then re-looked at clip:</span>{" "}
                          <code className="px-1 bg-white border border-gray-200 rounded">{m.reanalyze_source_video}</code>
                        </div>
                      )}
                      {m.reanalyze_transcript_excerpt && (
                        <div>
                          <span className="font-medium text-gray-600">Clip audio:</span>{" "}
                          <span className="italic">{m.reanalyze_transcript_excerpt}</span>
                        </div>
                      )}
                    </div>
                  </details>
                )}
                {m.role === "assistant" && m.escalation_error && (
                  <div className="mt-2 text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                    Tried to re-look at the original clip but it failed: {m.escalation_error}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 text-sm text-gray-500">
                <span className="inline-block animate-pulse">{MODEL_INFO[model].label} is thinking…</span>
              </div>
            </div>
          )}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3 text-red-700 text-sm">
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="bg-white border-t border-gray-200 px-6 py-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask anything about your day… (Enter to send, Shift+Enter for newline)"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm resize-none"
            rows={2}
            disabled={loading}
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:bg-gray-300"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
