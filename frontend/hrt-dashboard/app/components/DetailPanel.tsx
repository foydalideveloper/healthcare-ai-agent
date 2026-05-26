"use client";

import { useEffect, useState } from "react";

interface DetailPanelProps {
  day: number;
  categoryId: string;
  categoryName: string;
  hour: number;
  value: string;
  details?: string[];
  onClose: () => void;
  isRealDate?: boolean;  // true for 2026-04-16+ — hide demo timeline
  userId?: number;
  year?: number;
  month?: number;
}

interface RealEvent {
  time: string;
  label: string;
  detail?: string;
  value: string;
}

// ── Category theme colors ─────────────────────────────────────────
const CATEGORY_THEMES: Record<string, {
  bg: string;
  bgLight: string;
  border: string;
  accent: string;
  accentBg: string;
  icon: string;
  title: string;
}> = {
  food: {
    bg: "bg-red-50",
    bgLight: "bg-red-100/50",
    border: "border-red-200",
    accent: "text-red-700",
    accentBg: "bg-red-100",
    icon: "/icons/food.png",
    title: "Food Record",
  },
  exercise: {
    bg: "bg-red-50",
    bgLight: "bg-red-100/50",
    border: "border-red-200",
    accent: "text-red-700",
    accentBg: "bg-red-100",
    icon: "/icons/exercise.webp",
    title: "Exercise Record",
  },
  sleep: {
    bg: "bg-red-50",
    bgLight: "bg-red-100/50",
    border: "border-red-200",
    accent: "text-red-700",
    accentBg: "bg-red-100",
    icon: "/icons/Sleep.svg.png",
    title: "Sleep Record",
  },
  medicine: {
    bg: "bg-red-50",
    bgLight: "bg-red-100/50",
    border: "border-red-200",
    accent: "text-red-700",
    accentBg: "bg-red-100",
    icon: "/icons/medicine1.webp",
    title: "Medicine Record",
  },
  biometrics: {
    bg: "bg-red-50",
    bgLight: "bg-red-100/50",
    border: "border-red-200",
    accent: "text-red-700",
    accentBg: "bg-red-100",
    icon: "/icons/biometrics.webp",
    title: "Biometrics Record",
  },
  mental: {
    bg: "bg-red-50",
    bgLight: "bg-red-100/50",
    border: "border-red-200",
    accent: "text-red-700",
    accentBg: "bg-red-100",
    icon: "/icons/mental health.png",
    title: "Mental Health Record",
  },
  hydration: {
    bg: "bg-red-50",
    bgLight: "bg-red-100/50",
    border: "border-red-200",
    accent: "text-red-700",
    accentBg: "bg-red-100",
    icon: "/icons/hydration.png",
    title: "Hydration Record",
  },
};

// ── Food Panel ────────────────────────────────────────────────────
function FoodPanel({ day }: { day: number }) {
  const meals = [
    { time: "07:00", type: "Breakfast", items: "Rice, Kimchi soup, Egg", kcal: 450, color: "bg-red-400" },
    { time: "08:00", type: "Coffee", items: "Americano", kcal: 5, color: "bg-red-300" },
    { time: "12:30", type: "Lunch", items: "Bibimbap", kcal: 550, color: "bg-red-500" },
    { time: "15:00", type: "Snack", items: "Apple", kcal: 80, color: "bg-red-300" },
    { time: "18:30", type: "Dinner", items: "Samgyeopsal, Rice, Soju", kcal: 850, color: "bg-red-600" },
  ];

  const totalKcal = meals.reduce((s, m) => s + m.kcal, 0);

  return (
    <div className="space-y-5">
      {/* Meal Timeline */}
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">
          Meal Timeline
        </h4>
        <div className="space-y-0">
          {meals.map((meal, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 relative">
              {/* Timeline dot and line */}
              <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                <div className={`w-3 h-3 rounded-full ${meal.color} ring-2 ring-white shadow-sm`} />
                {i < meals.length - 1 && (
                  <div className="w-0.5 h-full bg-red-200 absolute top-5 left-[5px]" style={{ height: "calc(100% - 4px)" }} />
                )}
              </div>
              {/* Content */}
              <div className="flex-1 flex items-center justify-between min-w-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-red-500">{meal.time}</span>
                    <span className="text-sm font-semibold text-gray-800">{meal.type}</span>
                  </div>
                  <span className="text-xs text-gray-500 block truncate">{meal.items}</span>
                </div>
                <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">{meal.kcal} kcal</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Nutritional Summary Cards */}
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">
          Nutritional Summary
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <NutrientCard label="Total" value={`${totalKcal.toLocaleString()}`} unit="kcal" color={DARK_RED} />
          <NutrientCard label="Carbs" value="245" unit="g" color={LIGHT_RED} />
          <NutrientCard label="Protein" value="68" unit="g" color={LIGHT_RED} />
          <NutrientCard label="Fat" value="52" unit="g" color={LIGHT_RED} />
        </div>
      </div>
    </div>
  );
}

// Dark red for most important metric, light red for others
const DARK_RED = "bg-red-200 text-red-900 border-red-300";
const LIGHT_RED = "bg-red-50 text-red-700 border-red-100";

function NutrientCard({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  return (
    <div className={`rounded-lg border px-3 py-2.5 text-center ${color}`}>
      <div className="text-[10px] font-medium uppercase tracking-wider opacity-70">{label}</div>
      <div className="text-lg font-bold leading-tight">{value}<span className="text-xs font-normal ml-0.5">{unit}</span></div>
    </div>
  );
}

// ── Exercise Panel (timeline format like Food) ──
function ExercisePanel() {
  const activities = [
    { time: "06:30", type: "Morning Stretch", items: "Full body stretching", value: "10 min", color: "bg-red-300" },
    { time: "07:00", type: "Walking", items: "Walk to office", value: "15 min", color: "bg-red-300" },
    { time: "17:00", type: "Jogging", items: "Outdoor running, ~4km", value: "30 min", color: "bg-red-600" },
    { time: "17:30", type: "Cool Down", items: "Stretching + breathing", value: "5 min", color: "bg-red-300" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Activity Timeline</h4>
        <div className="space-y-0">
          {activities.map((a, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 relative">
              <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                <div className={`w-3 h-3 rounded-full ${a.color} ring-2 ring-white shadow-sm`} />
                {i < activities.length - 1 && <div className="w-0.5 h-full bg-red-200 absolute top-5 left-[5px]" style={{ height: "calc(100% - 4px)" }} />}
              </div>
              <div className="flex-1 flex items-center justify-between min-w-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-red-500">{a.time}</span>
                    <span className="text-sm font-semibold text-gray-800">{a.type}</span>
                  </div>
                  <span className="text-xs text-gray-500 block">{a.items}</span>
                </div>
                <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">{a.value}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Exercise Summary</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <NutrientCard label="Total Time" value="60" unit="min" color={DARK_RED} />
          <NutrientCard label="Calories" value="250" unit="kcal" color={LIGHT_RED} />
          <NutrientCard label="Avg HR" value="135" unit="bpm" color={LIGHT_RED} />
          <NutrientCard label="Distance" value="~4" unit="km" color={LIGHT_RED} />
        </div>
      </div>
    </div>
  );
}

// ── Sleep Panel (timeline format like Food) ──
function SleepPanel() {
  const stages = [
    { time: "22:00", type: "Sleep Start", items: "Bedtime, lights off", value: "Start", color: "bg-red-400" },
    { time: "22:30", type: "Light Sleep", items: "Stage 1-2, body relaxing", value: "1.0h", color: "bg-red-300" },
    { time: "23:30", type: "Deep Sleep", items: "Stage 3-4, body restoration", value: "2.5h", color: "bg-red-600" },
    { time: "02:00", type: "REM Sleep", items: "Dreaming, brain processing", value: "1.2h", color: "bg-red-500" },
    { time: "03:15", type: "Light Sleep", items: "Stage 1-2, brief awakening", value: "1.8h", color: "bg-red-300" },
    { time: "05:00", type: "Deep Sleep", items: "Final deep cycle", value: "0.8h", color: "bg-red-600" },
    { time: "05:50", type: "REM Sleep", items: "Final dream cycle", value: "0.6h", color: "bg-red-500" },
    { time: "06:50", type: "Wake Up", items: "Natural awakening", value: "End", color: "bg-red-400" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Sleep Timeline</h4>
        <div className="space-y-0">
          {stages.map((s, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 relative">
              <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                <div className={`w-3 h-3 rounded-full ${s.color} ring-2 ring-white shadow-sm`} />
                {i < stages.length - 1 && <div className="w-0.5 h-full bg-red-200 absolute top-5 left-[5px]" style={{ height: "calc(100% - 4px)" }} />}
              </div>
              <div className="flex-1 flex items-center justify-between min-w-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-red-500">{s.time}</span>
                    <span className="text-sm font-semibold text-gray-800">{s.type}</span>
                  </div>
                  <span className="text-xs text-gray-500 block">{s.items}</span>
                </div>
                <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">{s.value}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Sleep Summary</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <NutrientCard label="Total" value="7.2" unit="h" color={DARK_RED} />
          <NutrientCard label="Deep" value="3.3" unit="h" color={LIGHT_RED} />
          <NutrientCard label="REM" value="1.8" unit="h" color={LIGHT_RED} />
          <NutrientCard label="Quality" value="8" unit="/10" color={LIGHT_RED} />
        </div>
      </div>
    </div>
  );
}

// ── Medicine Panel (timeline format like Food) ──
function MedicinePanel() {
  const meds = [
    { time: "07:30", type: "Vitamin D", items: "1000 IU, 1 tablet, with breakfast", value: "Taken ✓", color: "bg-red-400" },
    { time: "08:00", type: "Omega-3", items: "1000mg, 2 capsules, with food", value: "Taken ✓", color: "bg-red-400" },
    { time: "13:00", type: "Probiotics", items: "1 capsule, after lunch", value: "Taken ✓", color: "bg-red-300" },
    { time: "20:00", type: "Magnesium", items: "400mg, 1 tablet, before bed", value: "Taken ✓", color: "bg-red-300" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Medication Timeline</h4>
        <div className="space-y-0">
          {meds.map((m, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 relative">
              <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                <div className={`w-3 h-3 rounded-full ${m.color} ring-2 ring-white shadow-sm`} />
                {i < meds.length - 1 && <div className="w-0.5 h-full bg-red-200 absolute top-5 left-[5px]" style={{ height: "calc(100% - 4px)" }} />}
              </div>
              <div className="flex-1 flex items-center justify-between min-w-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-red-500">{m.time}</span>
                    <span className="text-sm font-semibold text-gray-800">{m.type}</span>
                  </div>
                  <span className="text-xs text-gray-500 block">{m.items}</span>
                </div>
                <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">{m.value}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Medicine Summary</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <NutrientCard label="Compliance" value="100" unit="%" color={DARK_RED} />
          <NutrientCard label="Total Taken" value="4" unit="pills" color={LIGHT_RED} />
          <NutrientCard label="Streak" value="30" unit="days" color={LIGHT_RED} />
          <NutrientCard label="Missed" value="0" unit="today" color={LIGHT_RED} />
        </div>
      </div>
    </div>
  );
}

// ── Biometrics Panel (timeline format like Food) ──
function BiometricsPanel() {
  const readings = [
    { time: "07:00", type: "Morning Check", items: "Resting, before breakfast", value: "BP 118/76", color: "bg-red-300" },
    { time: "09:00", type: "Office Arrival", items: "Seated, after commute", value: "BP 121/78", color: "bg-red-400" },
    { time: "12:00", type: "Midday Check", items: "Before lunch, relaxed", value: "HR 68 bpm", color: "bg-red-300" },
    { time: "17:30", type: "Post-Exercise", items: "After 30min jogging", value: "HR 142 bpm", color: "bg-red-600" },
    { time: "18:00", type: "Recovery", items: "15min after exercise", value: "BP 125/82", color: "bg-red-500" },
    { time: "21:00", type: "Evening Check", items: "Before bed, relaxed", value: "BP 119/76", color: "bg-red-300" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Biometrics Timeline</h4>
        <div className="space-y-0">
          {readings.map((r, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 relative">
              <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                <div className={`w-3 h-3 rounded-full ${r.color} ring-2 ring-white shadow-sm`} />
                {i < readings.length - 1 && <div className="w-0.5 h-full bg-red-200 absolute top-5 left-[5px]" style={{ height: "calc(100% - 4px)" }} />}
              </div>
              <div className="flex-1 flex items-center justify-between min-w-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-red-500">{r.time}</span>
                    <span className="text-sm font-semibold text-gray-800">{r.type}</span>
                  </div>
                  <span className="text-xs text-gray-500 block">{r.items}</span>
                </div>
                <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">{r.value}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Biometrics Summary</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <NutrientCard label="Avg BP" value="121/78" unit="mmHg" color={DARK_RED} />
          <NutrientCard label="Avg HR" value="72" unit="bpm" color={LIGHT_RED} />
          <NutrientCard label="SpO2" value="98" unit="%" color={LIGHT_RED} />
          <NutrientCard label="Glucose" value="95" unit="mg/dL" color={LIGHT_RED} />
        </div>
      </div>
    </div>
  );
}

// ── Mental Health Panel (timeline format like Food) ──
function MentalPanel() {
  const entries = [
    { time: "07:00", type: "Morning Check-in", items: "Mood: Refreshed, Energy: High", value: "Stress 3.2", color: "bg-red-300" },
    { time: "10:00", type: "Work Session", items: "Mood: Focused, Productivity: High", value: "Stress 3.8", color: "bg-red-300" },
    { time: "13:00", type: "After Lunch", items: "Mood: Relaxed, slight drowsiness", value: "Stress 3.5", color: "bg-red-300" },
    { time: "16:00", type: "Afternoon Slump", items: "Mood: Tired, low energy", value: "Stress 4.8", color: "bg-red-500" },
    { time: "18:00", type: "Post-Exercise", items: "Mood: Energized, endorphin boost", value: "Stress 2.5", color: "bg-red-300" },
    { time: "21:00", type: "Evening Wind-down", items: "Mood: Calm, ready for sleep", value: "Stress 3.0", color: "bg-red-300" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Mental Health Timeline</h4>
        <div className="space-y-0">
          {entries.map((e, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 relative">
              <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                <div className={`w-3 h-3 rounded-full ${e.color} ring-2 ring-white shadow-sm`} />
                {i < entries.length - 1 && <div className="w-0.5 h-full bg-red-200 absolute top-5 left-[5px]" style={{ height: "calc(100% - 4px)" }} />}
              </div>
              <div className="flex-1 flex items-center justify-between min-w-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-red-500">{e.time}</span>
                    <span className="text-sm font-semibold text-gray-800">{e.type}</span>
                  </div>
                  <span className="text-xs text-gray-500 block">{e.items}</span>
                </div>
                <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">{e.value}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Mental Health Summary</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <NutrientCard label="Avg Stress" value="3.5" unit="/10" color={DARK_RED} />
          <NutrientCard label="Mood" value="Good" unit="" color={LIGHT_RED} />
          <NutrientCard label="Energy" value="High" unit="" color={LIGHT_RED} />
          <NutrientCard label="Focus" value="85" unit="%" color={LIGHT_RED} />
        </div>
      </div>
    </div>
  );
}

// ── Hydration Panel (timeline format like Food) ──
function HydrationPanel() {
  const drinks = [
    { time: "07:00", type: "Breakfast", items: "Water with morning meal", value: "200ml", color: "bg-red-300" },
    { time: "08:00", type: "Coffee", items: "Americano at office", value: "250ml", color: "bg-red-400" },
    { time: "09:00", type: "Water", items: "Desk, filtered water", value: "200ml", color: "bg-red-300" },
    { time: "10:00", type: "Water", items: "Mid-morning hydration", value: "150ml", color: "bg-red-300" },
    { time: "11:00", type: "Water", items: "Before lunch prep", value: "200ml", color: "bg-red-300" },
    { time: "12:30", type: "Lunch", items: "Water with meal", value: "200ml", color: "bg-red-300" },
    { time: "13:00", type: "Water", items: "Post-lunch", value: "150ml", color: "bg-red-300" },
    { time: "15:00", type: "Water", items: "Afternoon break", value: "200ml", color: "bg-red-300" },
    { time: "17:00", type: "Post-Exercise", items: "Rehydration after jogging", value: "300ml", color: "bg-red-600" },
    { time: "18:30", type: "Dinner", items: "Water with dinner", value: "150ml", color: "bg-red-300" },
    { time: "19:00", type: "Water", items: "Evening hydration", value: "100ml", color: "bg-red-300" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Hydration Timeline</h4>
        <div className="space-y-0">
          {drinks.map((d, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 relative">
              <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                <div className={`w-3 h-3 rounded-full ${d.color} ring-2 ring-white shadow-sm`} />
                {i < drinks.length - 1 && <div className="w-0.5 h-full bg-red-200 absolute top-5 left-[5px]" style={{ height: "calc(100% - 4px)" }} />}
              </div>
              <div className="flex-1 flex items-center justify-between min-w-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-red-500">{d.time}</span>
                    <span className="text-sm font-semibold text-gray-800">{d.type}</span>
                  </div>
                  <span className="text-xs text-gray-500 block">{d.items}</span>
                </div>
                <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">{d.value}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">Hydration Summary</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <NutrientCard label="Total" value="2,100" unit="ml" color={DARK_RED} />
          <NutrientCard label="Target" value="2,000" unit="ml" color={LIGHT_RED} />
          <NutrientCard label="Glasses" value="11" unit="cups" color={LIGHT_RED} />
          <NutrientCard label="Status" value="Goal Met" unit="✓" color={LIGHT_RED} />
        </div>
      </div>
    </div>
  );
}

// ── Main Detail Panel ─────────────────────────────────────────────
export default function DetailPanel({
  day,
  categoryId,
  categoryName,
  hour,
  value,
  details,
  onClose,
  isRealDate = false,
  userId = 1,
  year,
  month,
}: DetailPanelProps) {
  const [visible, setVisible] = useState(false);
  const [realEvents, setRealEvents] = useState<RealEvent[] | null>(null);
  const theme = CATEGORY_THEMES[categoryId] || CATEGORY_THEMES.food;

  useEffect(() => {
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  // Fetch real event timeline for real dates (2026-04-16+).
  useEffect(() => {
    if (!isRealDate || !year || !month) return;
    const url = `http://localhost:8000/api/v1/hrt/detail?user_id=${userId}`
      + `&category=${categoryId}&year=${year}&month=${month}&day=${day}&hour=${hour}`;
    fetch(url)
      .then(r => r.ok ? r.json() : { events: [] })
      .then(j => setRealEvents(j.events || []))
      .catch(() => setRealEvents([]));
  }, [isRealDate, userId, year, month, day, hour, categoryId]);

  const handleClose = () => {
    setVisible(false);
    setTimeout(onClose, 200);
  };

  // Render category-specific content
  function renderContent() {
    switch (categoryId) {
      case "food": return <FoodPanel day={day} />;
      case "exercise": return <ExercisePanel />;
      case "sleep": return <SleepPanel />;
      case "medicine": return <MedicinePanel />;
      case "biometrics": return <BiometricsPanel />;
      case "mental": return <MentalPanel />;
      case "hydration": return <HydrationPanel />;
      default: return (
        <div className="text-sm text-gray-500">
          {details?.map((d, i) => <div key={i}>{d}</div>)}
        </div>
      );
    }
  }

  return (
    <div
      className={`mx-4 mb-4 rounded-xl shadow-lg border overflow-hidden transition-all duration-200 ease-out
        ${theme.border} ${theme.bg}
        ${visible ? "opacity-100 translate-y-0 max-h-[2000px]" : "opacity-0 -translate-y-2 max-h-0"}`}
    >
      {/* Header */}
      <div className={`flex items-center justify-between px-6 py-4 ${theme.bgLight} border-b ${theme.border}`}>
        <div>
          <h3 className="text-lg font-bold text-gray-900">
            <img src={theme.icon} alt="" className="w-6 h-6 object-contain inline-block mr-1" />
            Day {day} &mdash; {theme.title}
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {categoryName} | {String(hour).padStart(2, "0")}:00 &mdash; {value}
          </p>
        </div>
        <button
          onClick={handleClose}
          className="w-8 h-8 flex items-center justify-center rounded-full
            bg-white/80 border border-gray-200 text-gray-400
            hover:bg-white hover:text-gray-700 hover:border-gray-300
            transition-all shadow-sm"
          aria-label="Close"
        >
          <span className="text-lg leading-none">&times;</span>
        </button>
      </div>

      {/* Content */}
      <div className="px-6 py-5 max-h-[500px] overflow-y-auto">
        {/* Real data summary (always at top — from the cell the user clicked) */}
        <div className="mb-5 p-4 rounded-lg bg-white/70 border border-red-200">
          <h4 className="text-xs font-semibold text-red-700 uppercase tracking-wider mb-2">
            This hour — actual data
          </h4>
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-bold text-gray-900">{value}</span>
            <span className="text-xs text-gray-500">at {String(hour).padStart(2, "0")}:00 KST</span>
          </div>
          {/* Per-item pills. When `realEvents` is populated (hrt_event_detail
              returned per-item rows), use that so each pill shows the item's
              own kcal, e.g. "양념치킨 (399 kcal)". Otherwise fall back to the
              drilldown's comma-joined `details` (names only) — preserves the
              old summary view if the per-item endpoint is unavailable. */}
          {isRealDate && realEvents && realEvents.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {realEvents.map((ev, i) => (
                <span
                  key={i}
                  className="inline-block px-2 py-1 bg-red-50 border border-red-200 rounded text-xs text-red-700 font-medium"
                  title={ev.detail || ""}
                >
                  {ev.label}
                  {ev.value ? <span className="ml-1 text-red-500">({ev.value})</span> : null}
                </span>
              ))}
            </div>
          ) : (
            details && details.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {details.map((d, i) => (
                  <span
                    key={i}
                    className="inline-block px-2 py-1 bg-red-50 border border-red-200 rounded text-xs text-red-700 font-medium"
                  >
                    {d}
                  </span>
                ))}
              </div>
            )
          )}
        </div>

        {/* Demo timeline for pre-April-16 dates */}
        {!isRealDate && (
          <>
            <div className="mb-3 p-2.5 rounded-md bg-yellow-50 border border-yellow-200">
              <p className="text-xs text-yellow-800">
                <span className="font-semibold">📋 Demo preview</span> — sample timeline
                illustrating what a fully-logged day looks like.
              </p>
            </div>
            {renderContent()}
          </>
        )}

        {/* Real event timeline for April 16+ — fetched from API */}
        {isRealDate && realEvents !== null && realEvents.length > 0 && (
          <>
            <h4 className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-3">
              {categoryName.replace(/\s*\(.*\)/, "")} Timeline
            </h4>
            <div className="space-y-0 mb-4">
              {realEvents.map((ev, i) => (
                <div key={i} className="flex items-start gap-3 py-2.5 relative">
                  <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                    <div className="w-3 h-3 rounded-full bg-red-400 ring-2 ring-white shadow-sm" />
                    {i < realEvents.length - 1 && (
                      <div className="w-0.5 bg-red-200 absolute top-5 left-[5px]"
                           style={{ height: "calc(100% - 4px)" }} />
                    )}
                  </div>
                  <div className="flex-1 flex items-center justify-between min-w-0">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-red-500">{ev.time}</span>
                        <span className="text-sm font-semibold text-gray-800">{ev.label}</span>
                      </div>
                      {ev.detail && (
                        <span className="text-xs text-gray-500 block truncate">{ev.detail}</span>
                      )}
                    </div>
                    <span className="text-sm font-bold text-red-700 flex-shrink-0 ml-3">
                      {ev.value}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 pt-3 border-t border-red-100">
              <NutrientCard label="Events" value={String(realEvents.length)} unit="logged" color={DARK_RED} />
              <NutrientCard label="This hour" value={value.split(" ")[0]} unit={value.split(" ").slice(1).join(" ") || ""} color={LIGHT_RED} />
              <NutrientCard label="Source" value="AI Glasses" unit="" color={LIGHT_RED} />
            </div>
          </>
        )}

        {isRealDate && realEvents !== null && realEvents.length === 0 && (
          <p className="text-xs text-gray-400 italic">
            No events logged for this hour yet.
          </p>
        )}
        {isRealDate && realEvents === null && (
          <p className="text-xs text-gray-400 italic">Loading timeline…</p>
        )}
      </div>
    </div>
  );
}
