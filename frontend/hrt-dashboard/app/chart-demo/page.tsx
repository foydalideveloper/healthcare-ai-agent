"use client";

import { LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ComposedChart } from "recharts";

// Sample data - yearly food data
const yearlyFood = [
  { name: "2020", value: 1020, exercise: 3200, sleep: 6.8 },
  { name: "2021", value: 1050, exercise: 3800, sleep: 6.9 },
  { name: "2022", value: 1070, exercise: 4200, sleep: 7.0 },
  { name: "2023", value: 1080, exercise: 4800, sleep: 7.1 },
  { name: "2024", value: 1090, exercise: 5100, sleep: 7.1 },
  { name: "2025", value: 1095, exercise: 5400, sleep: 7.2 },
  { name: "2026", value: 1095, exercise: 5475, sleep: 7.2 },
];

const monthlyExercise = [
  { name: "Jan", value: 480 },
  { name: "Feb", value: 420 },
  { name: "Mar", value: 465 },
  { name: "Apr", value: 450 },
  { name: "May", value: 460 },
  { name: "Jun", value: 455 },
  { name: "Jul", value: 470 },
  { name: "Aug", value: 440 },
  { name: "Sep", value: 465 },
  { name: "Oct", value: 475 },
  { name: "Nov", value: 450 },
  { name: "Dec", value: 445 },
];

const dailySleep = [
  { name: "1", value: 7.0 }, { name: "2", value: 7.2 }, { name: "3", value: 6.8 },
  { name: "4", value: 7.3 }, { name: "5", value: 7.0 }, { name: "6", value: 7.5 },
  { name: "7", value: 7.1 }, { name: "8", value: 6.9 }, { name: "9", value: 7.2 },
  { name: "10", value: 7.0 }, { name: "11", value: 7.3 }, { name: "12", value: 7.4 },
  { name: "13", value: 6.8 }, { name: "14", value: 7.1 }, { name: "15", value: 7.5 },
  { name: "16", value: 7.2 }, { name: "17", value: 7.0 }, { name: "18", value: 6.9 },
  { name: "19", value: 7.3 }, { name: "20", value: 7.1 }, { name: "21", value: 7.4 },
  { name: "22", value: 7.0 }, { name: "23", value: 7.2 }, { name: "24", value: 6.8 },
  { name: "25", value: 7.5 }, { name: "26", value: 7.1 }, { name: "27", value: 7.3 },
  { name: "28", value: 7.0 }, { name: "29", value: 7.2 }, { name: "30", value: 7.4 },
];

export default function ChartDemo() {
  return (
    <div className="min-h-screen bg-white p-8">
      <h1 className="text-2xl font-bold text-gray-800 mb-2">HRT Chart Options - Choose the Best One</h1>
      <p className="text-gray-500 mb-8">Below are 3 different chart styles. Each shows the same data differently.</p>

      {/* ═══════════════════════════════════════════════ */}
      {/* OPTION 1: Clean Line Chart */}
      {/* ═══════════════════════════════════════════════ */}
      <div className="mb-12 border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-bold text-gray-800 mb-1">Option 1: Clean Line Chart</h2>
        <p className="text-sm text-gray-500 mb-4">Simple lines with dots. Clean and professional.</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Yearly - Food */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/food.png" alt="" className="w-4 h-4 inline mr-1" />
              Food & Nutrition — Yearly Trend (meals)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={yearlyFood}>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={["dataMin - 20", "dataMax + 20"]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                  labelStyle={{ fontWeight: "bold" }}
                />
                <Line type="monotone" dataKey="value" stroke="#EF4444" strokeWidth={2} dot={{ fill: "#EF4444", r: 4 }} activeDot={{ r: 6 }} name="Meals" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Monthly - Exercise */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/exercise.webp" alt="" className="w-4 h-4 inline mr-1" />
              Exercise — Monthly Trend (minutes)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={monthlyExercise}>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={["dataMin - 20", "dataMax + 20"]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Line type="monotone" dataKey="value" stroke="#F87171" strokeWidth={2} dot={{ fill: "#F87171", r: 3 }} name="Minutes" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Daily - Sleep */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30 md:col-span-2">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/Sleep.svg.png" alt="" className="w-4 h-4 inline mr-1" />
              Sleep — Daily Trend (hours) — 30 days
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={dailySleep}>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={[6.5, 8]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Line type="monotone" dataKey="value" stroke="#DC2626" strokeWidth={2} dot={{ fill: "#DC2626", r: 2 }} name="Hours" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════ */}
      {/* OPTION 2: Filled Area Chart */}
      {/* ═══════════════════════════════════════════════ */}
      <div className="mb-12 border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-bold text-gray-800 mb-1">Option 2: Filled Area Chart</h2>
        <p className="text-sm text-gray-500 mb-4">Line with gradient fill underneath. Shows volume/magnitude better.</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Yearly - Food */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/food.png" alt="" className="w-4 h-4 inline mr-1" />
              Food & Nutrition — Yearly Trend (meals)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={yearlyFood}>
                <defs>
                  <linearGradient id="foodGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#EF4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#EF4444" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={["dataMin - 20", "dataMax + 20"]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Area type="monotone" dataKey="value" stroke="#EF4444" strokeWidth={2} fill="url(#foodGrad)" name="Meals" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Monthly - Exercise */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/exercise.webp" alt="" className="w-4 h-4 inline mr-1" />
              Exercise — Monthly Trend (minutes)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={monthlyExercise}>
                <defs>
                  <linearGradient id="exGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#F87171" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#F87171" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={["dataMin - 20", "dataMax + 20"]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Area type="monotone" dataKey="value" stroke="#F87171" strokeWidth={2} fill="url(#exGrad)" name="Minutes" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Daily - Sleep */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30 md:col-span-2">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/Sleep.svg.png" alt="" className="w-4 h-4 inline mr-1" />
              Sleep — Daily Trend (hours) — 30 days
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={dailySleep}>
                <defs>
                  <linearGradient id="sleepGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#DC2626" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#DC2626" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={[6.5, 8]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Area type="monotone" dataKey="value" stroke="#DC2626" strokeWidth={2} fill="url(#sleepGrad)" name="Hours" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════ */}
      {/* OPTION 3: Combined (Bar + Line + Multiple categories) */}
      {/* ═══════════════════════════════════════════════ */}
      <div className="mb-12 border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-bold text-gray-800 mb-1">Option 3: Combined Bar + Line (Multiple Categories)</h2>
        <p className="text-sm text-gray-500 mb-4">Bars for main value, lines for secondary. Shows multiple categories at once.</p>

        <div className="grid grid-cols-1 gap-6">
          {/* Yearly - All categories combined */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              All Categories — Yearly Trend (Food meals as bars, Exercise minutes as line)
            </h3>
            <ResponsiveContainer width="100%" height={250}>
              <ComposedChart data={yearlyFood}>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#999" />
                <YAxis yAxisId="left" tick={{ fontSize: 12 }} stroke="#EF4444" domain={[900, 1200]} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} stroke="#F97316" domain={[2000, 6000]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Legend wrapperStyle={{ fontSize: "12px" }} />
                <Bar yAxisId="left" dataKey="value" fill="#FECACA" stroke="#EF4444" strokeWidth={1} name="Meals" radius={[4, 4, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="exercise" stroke="#F97316" strokeWidth={2} dot={{ fill: "#F97316", r: 3 }} name="Exercise (min)" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Monthly Exercise as bar */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/exercise.webp" alt="" className="w-4 h-4 inline mr-1" />
              Exercise — Monthly (Bar Chart)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={monthlyExercise}>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={[300, 500]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Bar dataKey="value" fill="#FECACA" stroke="#EF4444" strokeWidth={1} name="Minutes" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Daily Sleep as area with target line */}
          <div className="border border-red-100 rounded-lg p-4 bg-red-50/30">
            <h3 className="text-sm font-semibold text-red-700 mb-3">
              <img src="/icons/Sleep.svg.png" alt="" className="w-4 h-4 inline mr-1" />
              Sleep — Daily with Target Line (7h recommended)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={dailySleep.map(d => ({ ...d, target: 7.0 }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#FFE0E0" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="#999" />
                <YAxis tick={{ fontSize: 12 }} stroke="#999" domain={[6.3, 8]} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #FFD0D0", borderRadius: "8px", fontSize: "12px" }}
                />
                <Legend wrapperStyle={{ fontSize: "12px" }} />
                <Area type="monotone" dataKey="value" stroke="#DC2626" strokeWidth={2} fill="#FECACA" fillOpacity={0.3} name="Actual Sleep" />
                <Line type="monotone" dataKey="target" stroke="#999" strokeWidth={1} strokeDasharray="5 5" dot={false} name="Target (7h)" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="text-center text-gray-400 text-sm py-8">
        Choose the style you like best and tell me!
      </div>
    </div>
  );
}
