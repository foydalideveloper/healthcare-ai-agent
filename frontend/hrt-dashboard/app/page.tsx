"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import Breadcrumb from "./components/Breadcrumb";
import DrilldownGrid from "./components/DrilldownGrid";
import ChartPanel from "./components/ChartPanel";
import DetailPanel from "./components/DetailPanel";

interface NavState {
  level: number;
  year?: number;
  month?: number;
  day?: number;
}

interface SelectedDetail {
  categoryId: string;
  categoryName: string;
  colKey: string;
  colLabel: string;
  value: string;
  details?: string[];
}

// ── URL state persistence ─────────────────────────────────────────
// On mount (CLIENT-ONLY), read ?level=3&year=2026&month=4 from URL so
// refreshing the page doesn't reset the user's drill-down position.
// We must NOT read window during initial useState — that causes an SSR
// hydration mismatch (server has no URL, client does).
function writeNavToUrl(nav: NavState, userId: number) {
  if (typeof window === "undefined") return;
  const sp = new URLSearchParams();
  sp.set("user", String(userId));
  sp.set("level", String(nav.level));
  if (nav.year)  sp.set("year",  String(nav.year));
  if (nav.month) sp.set("month", String(nav.month));
  if (nav.day)   sp.set("day",   String(nav.day));
  window.history.replaceState(null, "", `?${sp.toString()}`);
}

export default function Home() {
  // Initial state MUST match server render (level 1, no params) to avoid
  // hydration mismatch. URL is read after mount in the useEffect below.
  const [userId, setUserId] = useState(1);
  const [nav, setNav] = useState<NavState>({ level: 1 });
  const [hydrated, setHydrated] = useState(false);
  const [selectedDetail, setSelectedDetail] = useState<SelectedDetail | null>(null);

  // Restore state from URL AFTER hydration is complete.
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const u = parseInt(sp.get("user") || "1", 10) || 1;
    const level = parseInt(sp.get("level") || "1", 10);
    const year  = sp.get("year")  ? parseInt(sp.get("year")!,  10) : undefined;
    const month = sp.get("month") ? parseInt(sp.get("month")!, 10) : undefined;
    const day   = sp.get("day")   ? parseInt(sp.get("day")!,   10) : undefined;
    setUserId(u);
    setNav({ level: level >= 1 && level <= 4 ? level : 1, year, month, day });
    setHydrated(true);
  }, []);

  // After hydration, keep URL in sync with current nav + userId.
  useEffect(() => {
    if (hydrated) writeNavToUrl(nav, userId);
  }, [nav, userId, hydrated]);

  const handleDrillDown = useCallback(
    (params: { year?: number; month?: number; day?: number }) => {
      setSelectedDetail(null);
      if (nav.level === 1 && params.year) {
        setNav({ level: 2, year: params.year });
      } else if (nav.level === 2 && params.month) {
        setNav({ level: 3, year: params.year, month: params.month });
      } else if (nav.level === 3 && params.day) {
        setNav({ level: 4, year: params.year, month: params.month, day: params.day });
      }
    },
    [nav.level]
  );

  const handleBreadcrumbNav = useCallback(
    (level: number, params?: { year?: number; month?: number; day?: number }) => {
      setSelectedDetail(null);
      setNav({ level, ...params });
    },
    []
  );

  const handleCellDetail = useCallback(
    (detail: SelectedDetail) => {
      setSelectedDetail(detail);
    },
    []
  );

  const rangeLabel =
    nav.level === 1 ? "All Years" :
    nav.level === 2 ? `${nav.year}` :
    nav.level === 3 ? `${nav.year}-${String(nav.month).padStart(2, "0")}` :
    `${nav.year}-${String(nav.month).padStart(2, "0")}-${String(nav.day).padStart(2, "0")}`;

  const axisLabel =
    nav.level === 1 ? "Yearly" :
    nav.level === 2 ? "Monthly" :
    nav.level === 3 ? "Daily" :
    "Hourly";

  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* Header - clean white */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-[1800px] mx-auto">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
                Healthcare Record Table (HRT)
                <span className="text-gray-400 font-normal text-base ml-3">
                  Lifetime Health Dashboard
                </span>
              </h1>
              <p className="text-xs text-gray-400 mt-1">
                Triple-H Co., Ltd. | Patent No. 10-2025-0145274
              </p>
            </div>

            <div className="flex items-center gap-4">
              {/* User selector */}
              <div className="flex items-center gap-2">
                <label className="text-xs text-gray-500">User ID:</label>
                <select
                  value={userId}
                  onChange={(e) => {
                    setUserId(Number(e.target.value));
                    setNav({ level: 1 });
                    setSelectedDetail(null);
                  }}
                  className="bg-white border border-gray-300 rounded-md px-3 py-1.5
                    text-sm text-gray-800 focus:outline-none focus:ring-1 focus:ring-red-400"
                >
                  {[1, 2, 3, 4, 5].map((id) => (
                    <option key={id} value={id}>
                      User {id}
                    </option>
                  ))}
                </select>
              </div>

              {/* Daily Lifelog page link — browse every event AI-glasses extracted */}
              <Link
                href="/lifelog"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-md text-xs font-semibold text-blue-700 transition-colors"
              >
                <span>📖</span>
                <span>Daily Lifelog</span>
              </Link>

              {/* Predictions page link (patent 도4 / 도5) */}
              <Link
                href="/predictions"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 hover:bg-red-100 border border-red-200 rounded-md text-xs font-semibold text-red-700 transition-colors"
              >
                <img src="/icons/prediction.png" alt="" className="w-4 h-4 object-contain" />
                <span>Predictions</span>
              </Link>

              {/* Status indicator */}
              <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 rounded-md border border-gray-200">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-xs text-gray-500">Live</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Breadcrumb bar */}
      <div className="bg-gray-50 border-b border-gray-200 px-6 py-3">
        <div className="max-w-[1800px] mx-auto">
          <Breadcrumb
            level={nav.level}
            year={nav.year}
            month={nav.month}
            day={nav.day}
            onNavigate={handleBreadcrumbNav}
          />
        </div>
      </div>

      {/* Summary stats bar */}
      <div className="bg-white border-b border-gray-200 px-6 py-2.5">
        <div className="max-w-[1800px] mx-auto flex items-center gap-6">
          <StatBadge label="Level" value={`L${nav.level}`} />
          <StatBadge label="Range" value={rangeLabel} />
          <StatBadge label="Categories" value="7" />
          <StatBadge label="Axis" value={axisLabel} />
        </div>
      </div>

      {/* Main grid */}
      <main className="flex-1 overflow-hidden bg-white">
        <div className="max-w-[1800px] mx-auto">
          <DrilldownGrid
            key={`${userId}-${nav.level}-${nav.year}-${nav.month}-${nav.day}`}
            userId={userId}
            level={nav.level}
            year={nav.year}
            month={nav.month}
            day={nav.day}
            onDrillDown={handleDrillDown}
            onCellDetail={handleCellDetail}
          />

          {/* Chart Panel - area charts for all categories */}
          <ChartPanel
            key={`chart-${userId}-${nav.level}-${nav.year}-${nav.month}-${nav.day}`}
            userId={userId}
            level={nav.level}
            year={nav.year}
            month={nav.month}
            day={nav.day}
          />

          {/* Detail Panel - real timeline for 2026-04-16+, demo before. */}
          {selectedDetail && nav.level === 4 && nav.day && (
            <DetailPanel
              day={nav.day}
              categoryId={selectedDetail.categoryId}
              categoryName={selectedDetail.categoryName}
              hour={parseInt(selectedDetail.colKey, 10)}
              value={selectedDetail.value}
              details={selectedDetail.details}
              onClose={() => setSelectedDetail(null)}
              isRealDate={
                // Real-data window starts 2026-04-16 and continues forward.
                // Any date on or after that → show real timeline, not demo.
                (nav.year * 10000 + nav.month * 100 + nav.day) >=
                  (2026 * 10000 + 4 * 100 + 16)
              }
              userId={userId}
              year={nav.year}
              month={nav.month}
            />
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-gray-50 px-6 py-3">
        <div className="max-w-[1800px] mx-auto flex items-center justify-between text-xs text-gray-400">
          <span>&copy; 2025 Triple-H Co., Ltd. All rights reserved.</span>
          <span>HRT Multi-Dimensional Drill-Down Dashboard v2.0</span>
        </div>
      </footer>
    </div>
  );
}

function StatBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-gray-400">{label}</span>
      <span className="px-2 py-0.5 bg-gray-100 border border-gray-200 rounded text-gray-700 font-mono font-medium">
        {value}
      </span>
    </div>
  );
}
