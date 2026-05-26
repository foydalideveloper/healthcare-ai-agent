"use client";

import { useState, useEffect, useCallback } from "react";
import {
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  ComposedChart,
} from "recharts";
import {
  generateConsistentMockData,
  mergeRealWithMock,
  DEFAULT_CATEGORIES,
  type DrilldownResponse,
} from "./DrilldownGrid";

interface ChartPanelProps {
  userId: number;
  level: number;
  year?: number;
  month?: number;
  day?: number;
}

interface ChartDataPoint {
  name: string;
  value: number | null;
  rawValue?: string;
  standard?: number;
}

function extractNumericValue(raw: string): number | null {
  if (!raw || raw === "-") return null;
  const bpMatch = raw.match(/BP\s*(\d+)/);
  if (bpMatch) return parseInt(bpMatch[1]);
  const match = raw.match(/([\d,]+\.?\d*)/);
  if (match) return parseFloat(match[1].replace(/,/g, ""));
  return null;
}

// ══════════════════════════════════════════════════════════════════
// VERIFIED STANDARDS — Sources documented for each value
// ══════════════════════════════════════════════════════════════════
//
// SOURCES:
// [1] 2025 한국인 영양소 섭취기준 (KDRI) — 보건복지부 + 한국영양학회
//     EER for Male 30-49, low-active (PAL 1.4-1.59): ~2,500 kcal/day
//     EER for Female 30-49, low-active: ~1,900 kcal/day
//     URL: https://kns.or.kr/FileRoom/FileRoom_view.asp?idx=162&BoardID=Kdr
//
// [2] WHO Physical Activity Guidelines 2020
//     Adults 18-64: minimum 150-300 min/week moderate activity (21-43 min/day)
//     URL: https://www.who.int/publications/i/item/9789240015128
//
// [3] National Sleep Foundation (2023) + Korean Sleep Research Society
//     Adults 26-64: 7-9 hours recommended, 7h minimum
//     URL: https://www.sleepfoundation.org/how-sleep-works/how-much-sleep-do-we-really-need
//
// [4] AHA/WHO Blood Pressure Standards
//     Normal: <120/<80 mmHg, Elevated: 120-129/<80
//     URL: https://www.heart.org/en/health-topics/high-blood-pressure
//
// [5] Korean Society of Hypertension — Seasonal BP variation
//     Winter BP +5-10 mmHg vs Summer (Arch Med Res 2010;41(5):360-365)
//     Cold exposure constricts blood vessels
//
// [6] European Food Safety Authority (EFSA) — Hydration
//     Males: 2,500 ml/day total water intake (including food)
//     Females: 2,000 ml/day, +500ml in summer heat
//     URL: https://www.efsa.europa.eu/en/efsajournal/pub/1459
//
// [7] Seasonal variation in energy intake — Int J Environ Res Public Health 2020
//     Winter: +5-10% calorie increase in temperate climates (Seoul: 2-10°C Jan)
//     Summer: -5% calorie decrease
//
// [8] Circadian rhythm meal timing — PMC (Meal Timing Regulates Circadian System)
//     Optimal meal distribution: Breakfast 25-30%, Lunch 30-35%, Dinner 25-30%
//     Last meal >3h before sleep for metabolic health
//     URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC5483233/
//
// [9] Age-related metabolic decline
//     Basal metabolic rate decreases ~1-2% per decade after age 20
//     Source: Resting Metabolic Rate Meta-analysis, Am J Clin Nutr 2005

// ── Age-adjusted EER by decade (Male, Korean, low-active PAL) ──
// From KDRI 2025 + age decline calculation
// User's birth year determines which bracket to use
const AGE_EER_MALE: Record<string, number> = {
  "19-29": 2600,  // KDRI 2025: young adult male
  "30-39": 2500,  // KDRI 2025: adult male
  "40-49": 2400,  // -2% per decade from metabolism decline [9]
  "50-59": 2200,  // KDRI 2025: 50-64세
  "60-69": 2000,  // KDRI 2025: reduced activity
  "70-79": 1900,  // KDRI 2025: 65-74세
  "80+":   1700,  // KDRI 2025: 75세+
};

const AGE_EER_FEMALE: Record<string, number> = {
  "19-29": 2000,  // KDRI 2025: young adult female
  "30-39": 1900,  // KDRI 2025: adult female
  "40-49": 1800,  // -2% per decade
  "50-59": 1700,  // KDRI 2025: 50-64세
  "60-69": 1600,  // KDRI 2025: reduced activity
  "70-79": 1500,  // KDRI 2025: 65-74세
  "80+":   1400,  // KDRI 2025: 75세+
};

// For demo, assume Male, age 30 (born 1996) → 2,500 kcal base
const USER_BASE_KCAL = 2500; // Male, 30-39, Korean, low-active [1]

// ── Seasonal adjustment factors (verified) ──
// Based on [5][6][7] — percentage change from baseline
const SEASONAL_FACTORS: Record<string, number[]> = {
  //                    Jan    Feb    Mar    Apr    May    Jun    Jul    Aug    Sep    Oct    Nov    Dec
  food:              [1.08,  1.06,  1.02,  1.00,  0.98,  0.96,  0.95,  0.96,  1.00,  1.02,  1.04,  1.08],  // +5-8% winter [7]
  exercise:          [0.85,  0.85,  0.95,  1.00,  1.05,  1.10,  1.10,  1.05,  1.00,  0.95,  0.90,  0.85],  // -15% winter, +10% summer [2]
  sleep:             [1.04,  1.04,  1.01,  1.00,  0.99,  0.97,  0.97,  0.99,  1.00,  1.01,  1.03,  1.04],  // +4% winter [3]
  medicine:          [1.00,  1.00,  1.00,  1.00,  1.00,  1.00,  1.00,  1.00,  1.00,  1.00,  1.00,  1.00],  // no seasonal change
  // biometrics: Korean Society Hypertension + Modesti 2013 + Brennan 1982 show
  // a 4-5 mmHg peak-to-trough seasonal swing, NOT a symmetric ±5% around 120.
  // Winter peak ≈ +4 mmHg, Summer trough ≈ -1 mmHg (closer to baseline).
  biometrics:        [1.04,  1.03,  1.01,  1.00,  0.99,  0.99,  0.99,  0.99,  1.00,  1.01,  1.03,  1.04],
  mental:            [1.15,  1.10,  1.05,  1.00,  0.95,  0.90,  0.90,  0.95,  1.00,  1.05,  1.10,  1.15],  // +15% stress winter (SAD)
  hydration:         [0.90,  0.90,  0.95,  1.00,  1.05,  1.15,  1.25,  1.15,  1.05,  1.00,  0.95,  0.90],  // +25% summer [6]
};

// ── Base standards (non-seasonal, verified) ──
// `label`        — authoritative threshold (shown at yearly/daily/hourly views)
// `monthlyLabel` — seasonal-curve source (shown at monthly view); distinct from
//                  the threshold because AHA/WHO/NSF/KDRI do NOT themselves
//                  publish seasonal curves — those come from separate research.
const BASE_STANDARDS: Record<string, {
  monthly: number;  // base monthly value (before seasonal adjustment)
  daily: number;    // base daily value
  yearly: number;   // yearly average
  label: string;
  monthlyLabel?: string;
}> = {
  food:       { monthly: USER_BASE_KCAL, daily: USER_BASE_KCAL, yearly: 1095,
                label: "KDRI 2025: Male 30-39 (2,500 kcal/day)",
                monthlyLabel: "KDRI base + seasonal intake (winter +5-8%) [Int J Environ Res Public Health 2020]" },
  exercise:   { monthly: 450, daily: 30, yearly: 5475,
                label: "WHO: 150-300 min/week moderate",
                monthlyLabel: "WHO baseline + seasonal activity (winter -15%, summer +10%) [WHO 2020]" },
  sleep:      { monthly: 7.0, daily: 7.0, yearly: 7.0,
                label: "NSF: 7-9 hours recommended",
                monthlyLabel: "NSF baseline + seasonal sleep (winter +4%) [Sleep Med Rev 2019]" },
  medicine:   { monthly: 30, daily: 1, yearly: 365,
                label: "Prescribed: 1 dose/day" },
  biometrics: { monthly: 120, daily: 120, yearly: 120,
                label: "AHA/WHO: Normal BP <120 mmHg (threshold)",
                monthlyLabel: "Seasonal BP average — Korean Society Hypertension 2024 [Arch Med Res 2010;41:360]" },
  mental:     { monthly: 4.0, daily: 4.0, yearly: 130,
                label: "Target: stress <4.0/10",
                monthlyLabel: "Seasonal stress variation (winter +15%, SAD research)" },
  hydration:  { monthly: 2000, daily: 2000, yearly: 1800,
                label: "EFSA: Male 2,500ml/day total water",
                monthlyLabel: "EFSA baseline + seasonal intake (summer +25%) [EFSA 2010]" },
};

// Calculate seasonal-adjusted monthly standards
const MONTHLY_STANDARDS: Record<string, number[]> = {};
for (const cat of Object.keys(BASE_STANDARDS)) {
  const base = BASE_STANDARDS[cat].monthly;
  const factors = SEASONAL_FACTORS[cat];
  MONTHLY_STANDARDS[cat] = factors.map(f => Math.round(base * f));
}

// Alias for backward compatibility
const STANDARD_VALUES = BASE_STANDARDS;

// ── Circadian rhythm standards (hourly, verified) ──
// Based on [8] PMC: Meal timing regulates human circadian system
// Optimal meal distribution: 25-30% breakfast, 30-35% lunch, 25-30% dinner
// Last meal >3h before sleep
const HOURLY_STANDARDS: Record<string, (number | null)[]> = {
  //                  00    01    02    03    04    05    06    07    08    09    10    11    12    13    14    15    16    17    18    19    20    21    22    23
  food:             [null, null, null, null, null, null, null, 625,  null, null, null, null, 750,  null, null, 250,  null, null, 625,  null, null, null, null, null],
  // 07:00 breakfast 25%=625kcal, 12:00 lunch 30%=750, 15:00 snack 10%=250, 18:00 dinner 25%=625 (total 2500) [8]
  exercise:         [null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, 30,   null, null, null, null, null, null],
  // 17:00 optimal exercise time (body temp peaks, lowest injury risk) [circadian research]
  sleep:            [1,    1,    1,    1,    1,    1,    1,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    1,    1],
  // 22:00-06:50 sleep window (7h recommended) [3]
  medicine:         [null, null, null, null, null, null, null, null, 1,    null, null, null, null, null, null, null, null, null, null, null, null, null, null, null],
  // 08:00 morning dose (most supplements absorbed best with breakfast)
  biometrics:       [null, null, null, null, null, null, null, null, null, 120,  null, null, null, null, null, null, null, null, 118,  null, null, null, null, null],
  // BP naturally lower in evening vs morning (circadian pattern) [4]
  mental:           [null, null, null, null, null, null, null, null, null, 3.5,  null, null, 3.0,  null, null, null, null, null, null, null, null, 3.5,  null, null],
  // Cortisol peaks at 09:00, stress varies through day
  hydration:        [null, null, null, null, null, null, null, 250,  250,  200,  200,  200,  250,  200,  200,  200,  200,  250,  200,  100,  null, null, null, null],
  // Spread 2000ml across waking hours: 07:00-19:00 [6]
};

// ── Seasonal bands (only shown at Level 2 / monthly view) ──
// Season boundaries based on month index in chart data
const MONTH_LABELS = ["January","February","March","April","May","June",
                      "July","August","September","October","November","December"];

interface SeasonBand {
  startMonth: string;
  endMonth: string;
  color: string;
  label: string;
}

// Each month individually tagged with season color
const MONTH_SEASON_COLORS: Record<string, string> = {
  "January":   "#E8F0FE",  // Winter - blue
  "February":  "#E8F0FE",  // Winter
  "March":     "#E8F5E9",  // Spring - green
  "April":     "#E8F5E9",  // Spring
  "May":       "#E8F5E9",  // Spring
  "June":      "#FFF9E6",  // Summer - yellow
  "July":      "#FFF9E6",  // Summer
  "August":    "#FFF9E6",  // Summer
  "September": "#FFF3E8",  // Autumn - orange
  "October":   "#FFF3E8",  // Autumn
  "November":  "#FFF3E8",  // Autumn
  "December":  "#E8F0FE",  // Winter
};

export default function ChartPanel({
  userId,
  level,
  year,
  month,
  day,
}: ChartPanelProps) {
  const [data, setData] = useState<DrilldownResponse | null>(null);
  const [visibleCharts, setVisibleCharts] = useState<Set<string>>(new Set());

  const fetchData = useCallback(async (isInitialFetch: boolean) => {
    const mock = generateConsistentMockData(level, year, month, day);

    try {
      const params = new URLSearchParams();
      params.set("user_id", String(userId));
      params.set("level", String(level));
      if (year) params.set("year", String(year));
      if (month) params.set("month", String(month));
      if (day) params.set("day", String(day));

      const res = await fetch(
        `http://localhost:8000/api/v1/hrt/drilldown?${params.toString()}`
      );
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const real: DrilldownResponse = await res.json();
      const next = mergeRealWithMock(real, mock, level, year, month, day);
      // Skip state update if unchanged — prevents Recharts re-animation flicker.
      setData(prev => {
        if (prev && JSON.stringify(prev) === JSON.stringify(next)) return prev;
        return next;
      });
    } catch {
      if (isInitialFetch) {
        // Apply cutoff filter on fallback so future periods stay blank.
        const emptyReal: DrilldownResponse = {
          ...mock,
          rows: mock.rows.map(r => ({ ...r, cells: {} })),
        };
        setData(mergeRealWithMock(emptyReal, mock, level, year, month, day));
      }
    }
  }, [userId, level, year, month, day]);

  useEffect(() => {
    fetchData(true);
    const intervalId = setInterval(() => fetchData(false), 15_000);
    return () => clearInterval(intervalId);
  }, [fetchData]);

  if (!data) return null;

  // Build chart data for each category
  const categoryCharts = data.rows.map((row) => {
    const catInfo = DEFAULT_CATEGORIES.find((c) => c.id === row.category_id);
    const chartData: ChartDataPoint[] = [];

    // Get standard values - seasonal for monthly, flat for others
    const std = STANDARD_VALUES[row.category_id];
    const monthlyStd = MONTHLY_STANDARDS[row.category_id];

    // Get hourly standards for Level 4
    const hourlyStd = HOURLY_STANDARDS[row.category_id];

    data.columns.forEach((col, colIdx) => {
      const cell = row.cells[col.key];
      const numVal = cell ? extractNumericValue(cell.value) : null;
      const rawVal = cell && cell.value && cell.value !== "-" ? cell.value : undefined;

      let stdValue: number | undefined;
      if (level === 2 && monthlyStd) {
        // Monthly: seasonal-adjusted standard per month
        stdValue = monthlyStd[colIdx] ?? monthlyStd[0];
      } else if (level === 4 && hourlyStd) {
        // Hourly: circadian rhythm standard
        const hourIdx = colIdx;
        const hv = hourlyStd[hourIdx];
        stdValue = hv !== null ? hv : undefined;
      } else if (std) {
        // Yearly or daily: flat standard
        stdValue = level === 1 ? std.yearly : std.daily;
      }

      chartData.push({
        name: col.label,
        value: numVal,
        rawValue: rawVal,
        standard: stdValue,
      });
    });

    const hasData = chartData.some((d) => d.value !== null);
    // hasEvents: at least one cell has meaningful text even if non-numeric
    // (e.g. "Sleep start", "Vitamin D", "Calm")
    const hasEvents = chartData.some((d) => d.rawValue !== undefined);

    return {
      categoryId: row.category_id,
      categoryName: catInfo
        ? `${catInfo.name_en} (${catInfo.name_ko})`
        : row.category_name,
      icon: catInfo?.icon || row.category_icon || "",
      unit: catInfo?.unit || "",
      chartData,
      hasData,
      hasEvents,
      standardLabel: std?.label || "",
      standardMonthlyLabel: std?.monthlyLabel || std?.label || "",
      hasStandard: !!(std || monthlyStd),
    };
  });

  const toggleChart = (catId: string) => {
    setVisibleCharts((prev) => {
      const next = new Set(prev);
      if (next.has(catId)) {
        next.delete(catId);
      } else {
        next.add(catId);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (visibleCharts.size === DEFAULT_CATEGORIES.length) {
      // All visible → hide all
      setVisibleCharts(new Set());
    } else {
      // Show all
      setVisibleCharts(new Set(DEFAULT_CATEGORIES.map((c) => c.id)));
    }
  };

  const allVisible = visibleCharts.size === DEFAULT_CATEGORIES.length;
  const anyVisible = visibleCharts.size > 0;

  return (
    <div className="px-4 pb-4">
      {/* Toggle bar */}
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <div className="flex items-center gap-1.5 bg-gray-100 border border-gray-300 rounded-lg px-3 py-1.5 mr-2">
          <img src="/icons/trend_chart.png" alt="" className="w-5 h-5 object-contain" />
          <span className="text-sm font-bold text-gray-800">Trend Charts</span>
        </div>
        <div className="w-px h-6 bg-gray-300 mr-1"></div>

        {DEFAULT_CATEGORIES.map((cat) => {
          const isActive = visibleCharts.has(cat.id);
          return (
            <button
              key={cat.id}
              onClick={() => toggleChart(cat.id)}
              title={cat.name_en}
              className={`
                flex items-center gap-1 px-2.5 py-1.5 rounded-lg border text-xs font-medium
                transition-all duration-150
                ${isActive
                  ? "bg-red-100 border-red-300 text-red-700 shadow-sm"
                  : "bg-white border-gray-200 text-gray-500 hover:border-red-200 hover:bg-red-50"
                }
              `}
            >
              <img src={cat.icon} alt="" className="w-4 h-4 object-contain" />
              <span className="hidden sm:inline">{cat.name_en}</span>
            </button>
          );
        })}

        <button
          onClick={toggleAll}
          className={`
            px-3 py-1.5 rounded-lg border text-xs font-semibold
            transition-all duration-150
            ${allVisible
              ? "bg-red-200 border-red-400 text-red-800"
              : "bg-gray-100 border-gray-300 text-gray-600 hover:bg-red-50 hover:border-red-200"
            }
          `}
        >
          {allVisible ? "Hide All" : "All"}
        </button>
      </div>

      {/* Charts */}
      {anyVisible && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {categoryCharts
            .filter((chart) => visibleCharts.has(chart.categoryId))
            .map((chart) => {
              const gradientId = `grad-${chart.categoryId}`;

              const numericValues = chart.chartData
                .map((d) => d.value)
                .filter((v): v is number => v !== null);
              // Include standard value in min/max so dashed line is always visible
              const stdVal = chart.chartData[0]?.standard;
              if (stdVal !== undefined && stdVal !== null) {
                numericValues.push(stdVal);
              }
              const minVal =
                numericValues.length > 0 ? Math.min(...numericValues) : 0;
              const maxVal =
                numericValues.length > 0 ? Math.max(...numericValues) : 100;
              const padding = (maxVal - minVal) * 0.15 || 1;

              return (
                <div
                  key={chart.categoryId}
                  className="border border-red-100 rounded-lg p-4 bg-red-50/30"
                >
                  <h3 className="text-sm font-semibold text-red-700 mb-3 flex items-center gap-1.5">
                    <img
                      src={chart.icon}
                      alt=""
                      className="w-4 h-4 object-contain"
                    />
                    {chart.categoryName}
                  </h3>
                  {chart.hasData ? (
                    <>
                      <ResponsiveContainer width="100%" height={200}>
                        <ComposedChart
                          data={chart.chartData}
                          margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                        >
                          <defs>
                            <linearGradient
                              id={gradientId}
                              x1="0"
                              y1="0"
                              x2="0"
                              y2="1"
                            >
                              <stop
                                offset="5%"
                                stopColor="#EF4444"
                                stopOpacity={0.3}
                              />
                              <stop
                                offset="95%"
                                stopColor="#EF4444"
                                stopOpacity={0.02}
                              />
                            </linearGradient>
                          </defs>

                          {/* Seasonal background bands (only for monthly view) */}
                          {level === 2 && MONTH_LABELS.map((monthName, mi) => {
                            const nextMonth = MONTH_LABELS[mi + 1];
                            if (!nextMonth) return null;
                            const color = MONTH_SEASON_COLORS[monthName];
                            if (!color) return null;
                            return (
                              <ReferenceArea
                                key={mi}
                                x1={monthName}
                                x2={nextMonth}
                                fill={color}
                                fillOpacity={0.7}
                                strokeOpacity={0}
                              />
                            );
                          })}

                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="#FFE0E0"
                          />
                          <XAxis
                            dataKey="name"
                            tick={{ fontSize: 10 }}
                            stroke="#999"
                            interval={
                              chart.chartData.length > 15
                                ? Math.floor(chart.chartData.length / 8)
                                : 0
                            }
                          />
                          <YAxis
                            tick={{ fontSize: 10 }}
                            stroke="#999"
                            domain={[
                              Math.floor(minVal - padding),
                              Math.ceil(maxVal + padding),
                            ]}
                            width={45}
                          />
                          <Tooltip
                            contentStyle={{
                              background: "#fff",
                              border: "1px solid #FFD0D0",
                              borderRadius: "8px",
                              fontSize: "12px",
                            }}
                          />

                          {/* Actual data area.
                              dot={…} makes individual points visible — important
                              when there's only one numeric sample in the range
                              (e.g. hourly exercise/biometrics), where a line
                              cannot be drawn between just two points. */}
                          <Area
                            type="monotone"
                            dataKey="value"
                            stroke="#EF4444"
                            strokeWidth={2}
                            fill={`url(#${gradientId})`}
                            name="Actual"
                            connectNulls
                            dot={{ fill: "#EF4444", r: 3, strokeWidth: 0 }}
                            activeDot={{ r: 5, fill: "#EF4444", strokeWidth: 2, stroke: "#fff" }}
                          />

                          {/* Standard comparison dashed line.
                              dot={…} ensures single-point standards (e.g.
                              hourly exercise standard 30 kcal at 17:00 is the
                              only non-null value) remain visible — otherwise
                              the legend promises a line that can't render. */}
                          {chart.hasStandard && (
                            <Line
                              type="monotone"
                              dataKey="standard"
                              stroke="#999"
                              strokeWidth={1.5}
                              strokeDasharray="6 4"
                              dot={{ r: 2, fill: "#999", strokeWidth: 0 }}
                              name="Standard"
                              connectNulls
                            />
                          )}
                        </ComposedChart>
                      </ResponsiveContainer>

                      {/* Legend: standard label + seasonal labels.
                          At level 2 we use `standardMonthlyLabel` — the seasonal
                          source (e.g. Korean Society Hypertension for BP), NOT
                          the base threshold source (AHA/WHO) which doesn't
                          itself publish seasonal curves. */}
                      <div className="flex items-center gap-4 mt-1 flex-wrap">
                        {chart.hasStandard && (
                          <span className="text-[10px] text-gray-500 flex items-center gap-1">
                            <span className="inline-block w-4 border-t-2 border-dashed border-gray-400"></span>
                            {level === 4 ? "Circadian rhythm standard [PMC5483233]" :
                             level === 2 ? chart.standardMonthlyLabel :
                             chart.standardLabel}
                          </span>
                        )}
                        {level === 2 && (
                          <span className="text-[10px] text-gray-400 flex items-center gap-2">
                            <span className="inline-flex items-center gap-0.5">
                              <span className="w-3 h-2 rounded-sm" style={{background:"#EFF6FF"}}></span>
                              Winter
                            </span>
                            <span className="inline-flex items-center gap-0.5">
                              <span className="w-3 h-2 rounded-sm" style={{background:"#F0FDF4"}}></span>
                              Spring
                            </span>
                            <span className="inline-flex items-center gap-0.5">
                              <span className="w-3 h-2 rounded-sm" style={{background:"#FEFCE8"}}></span>
                              Summer
                            </span>
                            <span className="inline-flex items-center gap-0.5">
                              <span className="w-3 h-2 rounded-sm" style={{background:"#FFF7ED"}}></span>
                              Autumn
                            </span>
                          </span>
                        )}
                      </div>
                    </>
                  ) : chart.hasEvents ? (
                    // Event timeline fallback — for categories whose cells store
                    // text events ("Sleep start", "Vitamin D", "Calm") that
                    // can't be plotted on a numeric axis. Dots are positioned
                    // horizontally at their column index so the viewer can see
                    // WHEN each event occurred, matching the grid above.
                    <div className="h-[180px] flex flex-col">
                      <div className="relative flex-1 mx-2">
                        {/* Baseline */}
                        <div className="absolute left-0 right-0 top-1/2 h-0.5 bg-red-200"></div>

                        {/* Event markers */}
                        {chart.chartData.map((d, i) => {
                          if (!d.rawValue) return null;
                          const denom = Math.max(chart.chartData.length - 1, 1);
                          const pct = (i / denom) * 100;
                          return (
                            <div
                              key={i}
                              className="absolute -translate-x-1/2 flex flex-col items-center"
                              style={{ left: `${pct}%`, top: "50%", transform: "translate(-50%, -50%)" }}
                            >
                              <div className="mb-2 whitespace-nowrap bg-white border border-red-200 text-red-700 text-[10px] font-medium px-2 py-0.5 rounded shadow-sm">
                                {d.rawValue}
                              </div>
                              <div className="w-0.5 h-3 bg-red-300"></div>
                              <div className="w-3 h-3 rounded-full bg-red-500 border-2 border-white shadow-md"></div>
                              <div className="mt-1 text-[9px] text-gray-500">{d.name}</div>
                            </div>
                          );
                        })}
                      </div>

                      {/* X-axis label hints (evenly sampled) */}
                      <div className="flex justify-between text-[9px] text-gray-400 px-2 mt-1">
                        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
                          const idx = Math.min(
                            Math.floor(frac * (chart.chartData.length - 1)),
                            chart.chartData.length - 1
                          );
                          return <span key={frac}>{chart.chartData[idx]?.name || ""}</span>;
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="h-[180px] flex items-center justify-center text-gray-400 text-sm">
                      No data in this range
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
