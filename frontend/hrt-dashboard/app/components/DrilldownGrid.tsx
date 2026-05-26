"use client";

import { useState, useEffect, useCallback, useRef } from "react";

// ── Types ──────────────────────────────────────────────────────────
export interface CategoryInfo {
  id: string;
  name_en: string;
  name_ko: string;
  icon: string;
  unit: string;
}

export interface CellData {
  value: string;
  count: number;
  intensity: number; // 0-5
  details?: string[];
}

export interface DrilldownResponse {
  level: number;
  columns: { key: string; label: string }[];
  rows: {
    category_id: string;
    category_name: string;
    category_icon?: string;
    cells: Record<string, CellData>;
  }[];
}

interface DetailSelection {
  categoryId: string;
  categoryName: string;
  colKey: string;
  colLabel: string;
  value: string;
  details?: string[];
}

interface DrilldownGridProps {
  userId: number;
  level: number;
  year?: number;
  month?: number;
  day?: number;
  onDrillDown: (params: { year?: number; month?: number; day?: number }) => void;
  onCellDetail?: (detail: DetailSelection) => void;
}

interface HoveredCell {
  x: number;
  y: number;
  category: string;
  categoryId: string;
  label: string;
  value: string;
  count?: number;
  details?: string[];
  level: number;
}

// ── Default categories ──────────────────────────────────────────────
export const DEFAULT_CATEGORIES: CategoryInfo[] = [
  { id: "food",       name_en: "Food & Nutrition", name_ko: "식이/영양",  icon: "/icons/food.png", unit: "meals" },
  { id: "exercise",   name_en: "Exercise",         name_ko: "운동",       icon: "/icons/exercise.webp", unit: "min" },
  { id: "sleep",      name_en: "Sleep",            name_ko: "수면",       icon: "/icons/Sleep.svg.png", unit: "hrs" },
  { id: "medicine",   name_en: "Medicine",         name_ko: "약물",       icon: "/icons/medicine1.webp", unit: "doses" },
  { id: "biometrics", name_en: "Biometrics",       name_ko: "생체",       icon: "/icons/biometrics.webp", unit: "readings" },
  { id: "mental",     name_en: "Mental Health",    name_ko: "정신건강",   icon: "/icons/mental health.png", unit: "entries" },
  { id: "hydration",  name_en: "Hydration",        name_ko: "수분",       icon: "/icons/hydration.png", unit: "ml" },
];

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// ── Intensity color helper ─────────────────────────────────────────
function getIntensityClass(intensity: number): string {
  const clamped = Math.min(5, Math.max(0, intensity));
  return `intensity-${clamped}`;
}

// Recalculate all cell intensities in a row
// Highest value = 5 (darkest), lowest = 1 (lightest), empty = 0
// EQUAL values get EQUAL intensity
function recalcRowIntensity(cells: Record<string, CellData>): void {
  const entries: { key: string; num: number }[] = [];
  for (const [key, cell] of Object.entries(cells)) {
    if (cell.value === "-" || cell.count === 0) continue;
    const match = cell.value.match(/([\d,]+\.?\d*)/);
    if (match) {
      entries.push({ key, num: parseFloat(match[1].replace(/,/g, "")) });
    } else {
      cells[key].intensity = 2;
    }
  }
  if (entries.length === 0) return;
  if (entries.length === 1) {
    cells[entries[0].key].intensity = 3;
    return;
  }
  const min = Math.min(...entries.map(e => e.num));
  const max = Math.max(...entries.map(e => e.num));
  if (max === min) {
    // All values are the same — uniform color
    entries.forEach(e => { cells[e.key].intensity = 2; });
    return;
  }
  // Linear mapping: min=1, max=5, equal values get equal intensity
  entries.forEach(entry => {
    const ratio = (entry.num - min) / (max - min); // 0 to 1
    cells[entry.key].intensity = Math.round(ratio * 4) + 1; // 1 to 5
  });
}

// ══════════════════════════════════════════════════════════════════════
// CONSISTENT MOCK DATA for user_id=1, year 2026
// All numbers are mathematically consistent across levels.
// ══════════════════════════════════════════════════════════════════════

// ── LEVEL 1: YEARLY TOTALS ────────────────────────────────────────
const MONTHLY_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const MONTHLY_FOOD_KCAL_AVG = [1820, 1790, 1810, 1800, 1780, 1800, 1810, 1790, 1800, 1810, 1800, 1790];
const MONTHLY_EXERCISE_MIN = [480, 420, 465, 450, 460, 455, 470, 440, 465, 475, 450, 445];
const MONTHLY_SLEEP_AVG = [7.3, 7.0, 7.1, 7.1, 7.2, 7.3, 7.2, 7.1, 7.3, 7.2, 7.1, 7.4];
const MONTHLY_MEDICINE_DOSES = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const MONTHLY_BP_SYS = [124, 123, 121, 120, 122, 121, 123, 122, 121, 122, 123, 120];
const MONTHLY_BP_DIA = [79, 78, 77, 78, 78, 77, 79, 78, 77, 78, 79, 77];
const MONTHLY_STRESS = [4.5, 4.3, 4.1, 4.0, 4.2, 4.1, 4.3, 4.2, 4.0, 4.2, 4.3, 4.1];
const MONTHLY_HYDRATION_AVG = [1750, 1780, 1800, 1750, 1820, 1830, 1810, 1790, 1820, 1800, 1780, 1770];

// ── LEVEL 3: DAILY DATA for April 2026 ───────────────────────────
const APRIL_DAILY_KCAL = [
  1780, 1820, 1790, 1810, 1800, 1850, 1760,
  1830, 1780, 1800, 1790, 1810, 1820, 1770,
  1800, 1810, 1935, 1780, 1790, 1820, 1800,
  1760, 1810, 1800, 1790, 1830, 1780, 1815,
  1840, 1830,
];

const APRIL_DAILY_EX_MIN = [
  30, 0, 25, 0, 30, 0, 20,
  30, 0, 25, 0, 30, 0, 20,
  30, 0, 30, 0, 25, 0, 20,
  30, 0, 25, 0, 30, 0, 20,
  30, 0,
];

const APRIL_DAILY_EXERCISE_TYPE = [
  "Jogging", null, "Yoga", null, "Jogging", null, "Stretching",
  "Jogging", null, "Cycling", null, "Jogging", null, "Yoga",
  "Jogging", null, "Jogging", null, "Cycling", null, "Stretching",
  "Jogging", null, "Yoga", null, "Jogging", null, "Stretching",
  "Jogging", null,
];

const APRIL_DAILY_SLEEP = [
  7.0, 7.2, 6.8, 7.3, 7.0, 7.5, 7.1,
  6.9, 7.2, 7.0, 7.3, 6.8, 7.4, 7.1,
  7.0, 7.3, 7.2, 6.9, 7.1, 7.5, 7.0,
  7.2, 6.8, 7.3, 7.0, 7.1, 7.4, 7.0,
  7.2, 6.9,
];

const APRIL_DAILY_HYDRATION = [
  1700, 1800, 1650, 1850, 1700, 1900, 1750,
  1680, 1800, 1750, 1850, 1700, 1800, 1720,
  1750, 1800, 1700, 1650, 1800, 1850, 1750,
  1700, 1800, 1750, 1700, 1850, 1800, 1680,
  1800, 1750,
];

const APRIL_DAILY_BP_SYS = [
  121, 120, 122, 119, 121, 118, 120,
  122, 121, 119, 120, 122, 119, 121,
  120, 118, 121, 122, 120, 119, 121,
  120, 122, 119, 121, 118, 120, 122,
  119, 121,
];

const APRIL_DAILY_BP_DIA = [
  78, 77, 79, 76, 78, 77, 78,
  79, 78, 76, 77, 79, 76, 78,
  77, 76, 78, 79, 77, 76, 78,
  77, 79, 76, 78, 76, 77, 79,
  76, 78,
];

const APRIL_DAILY_STRESS = [
  4.2, 3.8, 4.5, 3.6, 4.0, 3.5, 4.1,
  4.3, 3.9, 3.7, 4.0, 4.4, 3.6, 4.0,
  3.8, 3.5, 4.2, 4.3, 3.9, 3.4, 4.1,
  4.0, 4.5, 3.7, 4.0, 3.6, 3.8, 4.2,
  3.9, 4.0,
];

// ── LEVEL 4: HOURLY DATA for April 17, 2026 ──────────────────────
interface HourlyEvent {
  food?: { value: string; kcal: number; details: string[] };
  exercise?: { value: string; min: number; details: string[] };
  sleep?: { value: string; details: string[] };
  medicine?: { value: string; details: string[] };
  biometrics?: { value: string; details: string[] };
  mental?: { value: string; details: string[] };
  hydration?: { value: string; ml: number; details: string[] };
}

const HOURLY_DAY17: Record<number, HourlyEvent> = {
  0:  { sleep: { value: "Deep sleep", details: ["Stage: Deep sleep", "Duration: 1h"] } },
  1:  { sleep: { value: "Deep sleep", details: ["Stage: Deep sleep", "Duration: 1h"] } },
  2:  { sleep: { value: "Deep sleep", details: ["Stage: Deep sleep", "Duration: 1h"] } },
  3:  { sleep: { value: "REM", details: ["Stage: REM sleep", "Duration: 1h"] } },
  4:  { sleep: { value: "Light sleep", details: ["Stage: Light sleep", "Duration: 1h"] } },
  5:  { sleep: { value: "Light sleep", details: ["Stage: Light sleep", "Duration: 1h"] } },
  6:  { sleep: { value: "Wake up", details: ["Woke at 06:50", "Total: 7.2h"] } },
  7:  {
    food: { value: "Breakfast 450 kcal", kcal: 450, details: ["Breakfast at 07:00", "- Rice", "- Kimchi soup", "- Fried egg", "Total: 450 kcal"] },
    hydration: { value: "200ml", ml: 200, details: ["Water with breakfast", "200ml"] },
  },
  8:  {
    food: { value: "Coffee 5 kcal", kcal: 5, details: ["Black coffee at 08:00", "5 kcal"] },
    hydration: { value: "250ml", ml: 250, details: ["Coffee + water", "250ml"] },
  },
  9:  {
    biometrics: { value: "BP 121/78", details: ["BP: 121/78 mmHg", "HR: 72 bpm", "Morning reading"] },
    mental: { value: "Focused", details: ["Mood: Focused", "Stress: 3.8/10", "Morning check-in"] },
    hydration: { value: "200ml", ml: 200, details: ["Water", "200ml"] },
  },
  10: {
    hydration: { value: "150ml", ml: 150, details: ["Water", "150ml"] },
  },
  11: {
    hydration: { value: "200ml", ml: 200, details: ["Water before lunch", "200ml"] },
  },
  12: {
    food: { value: "Lunch 550 kcal", kcal: 550, details: ["Lunch at 12:30", "- Bibimbap (mixed rice bowl)", "- Side dishes", "Total: 550 kcal"] },
    hydration: { value: "200ml", ml: 200, details: ["Water with lunch", "200ml"] },
  },
  13: {
    hydration: { value: "150ml", ml: 150, details: ["Water", "150ml"] },
  },
  14: {},
  15: {
    food: { value: "Apple 80 kcal", kcal: 80, details: ["Afternoon snack", "- Apple (1 medium)", "80 kcal"] },
    hydration: { value: "200ml", ml: 200, details: ["Water", "200ml"] },
  },
  16: {},
  17: {
    exercise: { value: "Jogging 30 min", min: 30, details: ["Jogging at 17:00", "Duration: 30 min", "~250 kcal burned"] },
    hydration: { value: "300ml", ml: 300, details: ["Post-exercise water", "300ml"] },
  },
  18: {
    food: { value: "Dinner 850 kcal", kcal: 850, details: ["Dinner at 18:30", "- Samgyeopsal (grilled pork belly)", "- Soju (2 glasses)", "- Rice", "- Lettuce wraps", "Total: 850 kcal"] },
    biometrics: { value: "BP 119/76", details: ["BP: 119/76 mmHg", "HR: 68 bpm", "Evening reading"] },
    hydration: { value: "150ml", ml: 150, details: ["Water with dinner", "150ml"] },
  },
  19: {
    hydration: { value: "100ml", ml: 100, details: ["Evening water", "100ml"] },
  },
  20: {
    medicine: { value: "Vitamin D", details: ["Vitamin D 1000IU", "Daily dose"] },
    mental: { value: "Calm", details: ["Mood: Calm", "Stress: 4.2/10", "Evening check-in"] },
  },
  21: {},
  22: {
    sleep: { value: "Sleep start", details: ["Bedtime: 22:00", "Target: 7h+"] },
  },
  23: {
    sleep: { value: "Light sleep", details: ["Stage: Light sleep", "Duration: 1h"] },
  },
};

export function generateConsistentMockData(
  level: number,
  year?: number,
  month?: number,
  day?: number,
): DrilldownResponse {
  let columns: { key: string; label: string }[] = [];

  // ── LEVEL 1: YEARLY ─────────────────────────────────────────────
  if (level === 1) {
    for (let y = 2020; y <= 2026; y++) {
      columns.push({ key: String(y), label: String(y) });
    }

    const yearlyValues: Record<number, Record<string, CellData>> = {
      2020: {
        food:       { value: "1,020 meals", count: 1020, intensity: 3, details: ["Avg 1,750 kcal/day", "~639,750 kcal total", "Top: Rice 280x, Kimchi 260x"] },
        exercise:   { value: "3,200 min", count: 3200, intensity: 2, details: ["~8.8 min/day avg", "Main: Walking, Yoga", "Total 53h"] },
        sleep:      { value: "6.8h avg", count: 365, intensity: 4, details: ["Best: 8.5h", "Worst: 4.5h"] },
        medicine:   { value: "280 doses", count: 280, intensity: 3, details: ["Vitamin D", "23 avg/mo"] },
        biometrics: { value: "BP 128/82", count: 180, intensity: 4, details: ["180 readings", "Avg HR: 76 bpm"] },
        mental:     { value: "85 entries", count: 85, intensity: 3, details: ["Mood: Mixed", "Stress avg: 5.1/10"] },
        hydration:  { value: "1,550ml avg", count: 365, intensity: 4, details: ["Target: 2000ml", "Days met: 120"] },
      },
      2021: {
        food:       { value: "1,050 meals", count: 1050, intensity: 3, details: ["Avg 1,780 kcal/day", "~649,700 kcal total", "Top: Rice 290x, Kimchi 270x"] },
        exercise:   { value: "3,800 min", count: 3800, intensity: 2, details: ["~10.4 min/day avg", "Main: Walking, Jogging", "Total 63h"] },
        sleep:      { value: "6.9h avg", count: 365, intensity: 3, details: ["Best: 8.8h", "Worst: 4.2h"] },
        medicine:   { value: "310 doses", count: 310, intensity: 3, details: ["Vitamin D", "26 avg/mo"] },
        biometrics: { value: "BP 126/80", count: 200, intensity: 3, details: ["200 readings", "Avg HR: 74 bpm"] },
        mental:     { value: "95 entries", count: 95, intensity: 3, details: ["Mood: Improving", "Stress avg: 4.8/10"] },
        hydration:  { value: "1,620ml avg", count: 365, intensity: 4, details: ["Target: 2000ml", "Days met: 145"] },
      },
      2022: {
        food:       { value: "1,070 meals", count: 1070, intensity: 3, details: ["Avg 1,790 kcal/day", "~653,350 kcal total", "Top: Rice 295x, Kimchi 275x"] },
        exercise:   { value: "4,200 min", count: 4200, intensity: 3, details: ["~11.5 min/day avg", "Main: Jogging, Cycling", "Total 70h"] },
        sleep:      { value: "7.0h avg", count: 365, intensity: 3, details: ["Best: 9.0h", "Worst: 5.0h"] },
        medicine:   { value: "340 doses", count: 340, intensity: 3, details: ["Vitamin D", "28 avg/mo"] },
        biometrics: { value: "BP 125/79", count: 240, intensity: 3, details: ["240 readings", "Avg HR: 73 bpm"] },
        mental:     { value: "110 entries", count: 110, intensity: 3, details: ["Mood: Good", "Stress avg: 4.5/10"] },
        hydration:  { value: "1,680ml avg", count: 365, intensity: 3, details: ["Target: 2000ml", "Days met: 170"] },
      },
      2023: {
        food:       { value: "1,080 meals", count: 1080, intensity: 3, details: ["Avg 1,800 kcal/day", "~657,000 kcal total", "Top: Rice 300x, Kimchi 280x"] },
        exercise:   { value: "4,800 min", count: 4800, intensity: 3, details: ["~13.2 min/day avg", "Main: Jogging, Yoga", "Total 80h"] },
        sleep:      { value: "7.1h avg", count: 365, intensity: 3, details: ["Best: 8.9h", "Worst: 5.2h"] },
        medicine:   { value: "355 doses", count: 355, intensity: 3, details: ["Vitamin D", "30 avg/mo"] },
        biometrics: { value: "BP 124/79", count: 300, intensity: 3, details: ["300 readings", "Avg HR: 72 bpm"] },
        mental:     { value: "130 entries", count: 130, intensity: 3, details: ["Mood: Good", "Stress avg: 4.3/10"] },
        hydration:  { value: "1,720ml avg", count: 365, intensity: 3, details: ["Target: 2000ml", "Days met: 190"] },
      },
      2024: {
        food:       { value: "1,090 meals", count: 1090, intensity: 3, details: ["Avg 1,800 kcal/day", "~657,000 kcal total", "Top: Rice 305x, Kimchi 285x"] },
        exercise:   { value: "5,100 min", count: 5100, intensity: 3, details: ["~14 min/day avg", "Main: Jogging, Cycling", "Total 85h"] },
        sleep:      { value: "7.1h avg", count: 366, intensity: 3, details: ["Best: 9.1h", "Worst: 5.0h"] },
        medicine:   { value: "360 doses", count: 360, intensity: 3, details: ["Vitamin D 1000IU daily", "30 avg/mo"] },
        biometrics: { value: "BP 123/78", count: 350, intensity: 3, details: ["350 readings", "Avg HR: 71 bpm"] },
        mental:     { value: "150 entries", count: 150, intensity: 3, details: ["Mood: Good", "Stress avg: 4.2/10"] },
        hydration:  { value: "1,760ml avg", count: 366, intensity: 3, details: ["Target: 2000ml", "Days met: 210"] },
      },
      2025: {
        food:       { value: "1,095 meals", count: 1095, intensity: 3, details: ["Avg 1,800 kcal/day", "~657,000 kcal total", "Top: Rice 310x, Kimchi 290x"] },
        exercise:   { value: "5,400 min", count: 5400, intensity: 3, details: ["~14.8 min/day avg", "Main: Jogging", "Total 90h"] },
        sleep:      { value: "7.2h avg", count: 365, intensity: 3, details: ["Best: 9.0h", "Worst: 5.1h"] },
        medicine:   { value: "365 doses", count: 365, intensity: 3, details: ["Vitamin D 1000IU daily", "30 avg/mo"] },
        biometrics: { value: "BP 122/78", count: 365, intensity: 3, details: ["365 readings", "Avg HR: 70 bpm"] },
        mental:     { value: "160 entries", count: 160, intensity: 3, details: ["Mood: Good", "Stress avg: 4.2/10"] },
        hydration:  { value: "1,790ml avg", count: 365, intensity: 3, details: ["Target: 2000ml", "Days met: 225"] },
      },
      2026: {
        food:       { value: "1,095 meals", count: 1095, intensity: 3, details: ["Avg 1,800 kcal/day", "~657,000 kcal total", "Top: Rice 310x, Kimchi 290x"] },
        exercise:   { value: "5,475 min", count: 5475, intensity: 3, details: ["15 min/day avg", "Main: Jogging", "Total 91h"] },
        sleep:      { value: "7.2h avg", count: 365, intensity: 3, details: ["Best: 9.0h", "Worst: 5.0h"] },
        medicine:   { value: "365 doses", count: 365, intensity: 3, details: ["Vitamin D 1000IU daily", "1 dose/day"] },
        biometrics: { value: "BP 122/78", count: 730, intensity: 3, details: ["730 readings (2/day)", "Avg HR: 70 bpm"] },
        mental:     { value: "170 entries", count: 170, intensity: 3, details: ["Daily check-ins", "Avg stress: 4.2/10", "Mood: Generally calm"] },
        hydration:  { value: "1,800ml avg", count: 365, intensity: 3, details: ["Target: 2000ml", "Days met: 230"] },
      },
    };

    const rows = DEFAULT_CATEGORIES.map((cat) => {
      const cells: Record<string, CellData> = {};
      columns.forEach((col) => {
        const yr = parseInt(col.key);
        const yv = yearlyValues[yr];
        if (yv && yv[cat.id]) {
          cells[col.key] = { ...yv[cat.id] };
        } else {
          cells[col.key] = { value: "-", count: 0, intensity: 0 };
        }
      });
      // Recalculate intensity: highest value in row = darkest, lowest = lightest
      recalcRowIntensity(cells);
      return { category_id: cat.id, category_name: cat.name_en + " (" + cat.name_ko + ")", category_icon: cat.icon, cells };
    });

    return { level: 1, columns, rows };
  }

  // ── LEVEL 2: MONTHLY (for year=2026) ────────────────────────────
  if (level === 2) {
    for (let m = 1; m <= 12; m++) {
      columns.push({ key: String(m), label: MONTH_NAMES[m - 1] });
    }

    const rows = DEFAULT_CATEGORIES.map((cat) => {
      const cells: Record<string, CellData> = {};
      columns.forEach((col) => {
        const m = parseInt(col.key) - 1;
        const days = MONTHLY_DAYS[m];

        if (cat.id === "food") {
          const avgKcal = MONTHLY_FOOD_KCAL_AVG[m];
          const totalKcal = avgKcal * days;
          const meals = days * 3;
          cells[col.key] = {
            value: `${avgKcal.toLocaleString()} kcal/day avg`,
            count: meals,
            intensity: Math.min(5, Math.ceil(meals / 25)),
            details: [
              `${meals} meals total (3/day)`,
              `${totalKcal.toLocaleString()} kcal total`,
              `Avg ${avgKcal} kcal/day`,
              `Top: Rice, Kimchi, Bibimbap`,
            ],
          };
        } else if (cat.id === "exercise") {
          const totalMin = MONTHLY_EXERCISE_MIN[m];
          const avgPerDay = (totalMin / days).toFixed(1);
          cells[col.key] = {
            value: `${totalMin} min total`,
            count: totalMin,
            intensity: totalMin > 470 ? 4 : totalMin > 450 ? 3 : 2,
            details: [
              `${totalMin} min total`,
              `${avgPerDay} min/day avg`,
              `~${Math.round(totalMin / 30)} sessions`,
              `Main: Jogging, Yoga, Cycling`,
            ],
          };
        } else if (cat.id === "sleep") {
          const avg = MONTHLY_SLEEP_AVG[m];
          cells[col.key] = {
            value: `${avg}h avg`,
            count: days,
            intensity: avg >= 7.3 ? 2 : avg >= 7.0 ? 3 : 4,
            details: [
              `Average: ${avg}h/night`,
              `Quality: 7.5/10`,
              `Best: ${(avg + 1.5).toFixed(1)}h`,
              `Worst: ${(avg - 1.8).toFixed(1)}h`,
            ],
          };
        } else if (cat.id === "medicine") {
          const doses = MONTHLY_MEDICINE_DOSES[m];
          cells[col.key] = {
            value: `${doses} doses`,
            count: doses,
            intensity: 2,
            details: [
              `Vitamin D 1000IU daily`,
              `${doses}/${days} days (100%)`,
            ],
          };
        } else if (cat.id === "biometrics") {
          const sys = MONTHLY_BP_SYS[m];
          const dia = MONTHLY_BP_DIA[m];
          cells[col.key] = {
            value: `BP ${sys}/${dia}`,
            count: days * 2,
            intensity: sys > 125 ? 4 : sys > 122 ? 3 : 2,
            details: [
              `Avg BP: ${sys}/${dia} mmHg`,
              `${days * 2} readings (2/day)`,
              `Avg HR: 70 bpm`,
              `SpO2: 97%`,
            ],
          };
        } else if (cat.id === "mental") {
          const stress = MONTHLY_STRESS[m];
          cells[col.key] = {
            value: `stress ${stress}/10`,
            count: days,
            intensity: stress > 4.5 ? 4 : stress > 4.0 ? 3 : 2,
            details: [
              `Avg stress: ${stress}/10`,
              `${days} check-ins`,
              `Mood: ${stress > 4.3 ? "Mixed" : "Calm"}`,
            ],
          };
        } else if (cat.id === "hydration") {
          const avg = MONTHLY_HYDRATION_AVG[m];
          cells[col.key] = {
            value: `${avg.toLocaleString()}ml avg/day`,
            count: days,
            intensity: avg >= 1820 ? 2 : avg >= 1750 ? 3 : 4,
            details: [
              `Avg: ${avg}ml/day`,
              `Target: 2000ml`,
              `Met target: ${Math.floor(days * 0.6)} days`,
            ],
          };
        }
      });
      // Recalculate intensity: highest value in row = darkest, lowest = lightest
      recalcRowIntensity(cells);
      return { category_id: cat.id, category_name: cat.name_en + " (" + cat.name_ko + ")", category_icon: cat.icon, cells };
    });

    return { level: 2, columns, rows };
  }

  // ── LEVEL 3: DAILY (for April 2026) ─────────────────────────────
  if (level === 3) {
    const daysInMonth = month ? new Date(year || 2026, month, 0).getDate() : 30;
    for (let d = 1; d <= daysInMonth; d++) {
      columns.push({ key: String(d), label: String(d) });
    }

    const monthSeed = ((year || 2026) * 12 + (month || 1)) % 100;

    const rows = DEFAULT_CATEGORIES.map((cat) => {
      const cells: Record<string, CellData> = {};
      columns.forEach((col) => {
        const d = parseInt(col.key) - 1;
        if (d >= daysInMonth) {
          cells[col.key] = { value: "-", count: 0, intensity: 0 };
          return;
        }
        const idx = d % 30;

        if (cat.id === "food") {
          const kcal = APRIL_DAILY_KCAL[idx] + (monthSeed % 50) - 25;
          cells[col.key] = {
            value: `${kcal.toLocaleString()} kcal`,
            count: 3,
            intensity: kcal > 1900 ? 4 : kcal > 1820 ? 3 : kcal > 1780 ? 2 : 1,
            details: [
              `${kcal} kcal (3 meals)`,
              `Breakfast: ~450 kcal`,
              `Lunch: ~550 kcal`,
              `Dinner: ~${kcal - 1000} kcal`,
            ],
          };
        } else if (cat.id === "exercise") {
          const min = APRIL_DAILY_EX_MIN[idx];
          const exType = APRIL_DAILY_EXERCISE_TYPE[idx];
          if (min === 0) {
            cells[col.key] = { value: "-", count: 0, intensity: 0, details: ["Rest day"] };
          } else {
            cells[col.key] = {
              value: `${exType} ${min}min`,
              count: 1,
              intensity: min >= 30 ? 3 : 2,
              details: [`${exType}: ${min} min`, `~${Math.floor(min * 8)} kcal burned`],
            };
          }
        } else if (cat.id === "sleep") {
          const h = APRIL_DAILY_SLEEP[idx];
          cells[col.key] = {
            value: `${h}h`,
            count: 1,
            intensity: h >= 7.4 ? 2 : h >= 7.0 ? 3 : 4,
            details: [`Duration: ${h}h`, `Quality: ${h >= 7.2 ? "Good" : "Fair"}`],
          };
        } else if (cat.id === "medicine") {
          cells[col.key] = {
            value: "Vitamin D",
            count: 1,
            intensity: 2,
            details: ["Vitamin D 1000IU", "Daily dose taken"],
          };
        } else if (cat.id === "biometrics") {
          const sys = APRIL_DAILY_BP_SYS[idx];
          const dia = APRIL_DAILY_BP_DIA[idx];
          cells[col.key] = {
            value: `BP ${sys}/${dia}`,
            count: 2,
            intensity: sys > 122 ? 3 : 2,
            details: [`BP: ${sys}/${dia} mmHg`, `HR: ${68 + (d % 5)} bpm`, `2 readings`],
          };
        } else if (cat.id === "mental") {
          const stress = APRIL_DAILY_STRESS[idx];
          cells[col.key] = {
            value: `${stress}/10`,
            count: 1,
            intensity: stress > 4.3 ? 4 : stress > 3.8 ? 3 : 2,
            details: [`Stress: ${stress}/10`, `Mood: ${stress > 4.2 ? "Tense" : "Calm"}`],
          };
        } else if (cat.id === "hydration") {
          const ml = APRIL_DAILY_HYDRATION[idx];
          cells[col.key] = {
            value: `${ml}ml`,
            count: Math.floor(ml / 200),
            intensity: ml < 1700 ? 4 : ml < 1800 ? 3 : 2,
            details: [`${ml}ml total`, `${Math.floor(ml / 200)} glasses`, ml >= 2000 ? "Goal met!" : `Short by ${2000 - ml}ml`],
          };
        }
      });
      // Recalculate intensity: highest value in row = darkest, lowest = lightest
      recalcRowIntensity(cells);
      return { category_id: cat.id, category_name: cat.name_en + " (" + cat.name_ko + ")", category_icon: cat.icon, cells };
    });

    return { level: 3, columns, rows };
  }

  // ── LEVEL 4: HOURLY (for April 17, 2026) ────────────────────────
  if (level === 4) {
    for (let h = 0; h < 24; h++) {
      columns.push({ key: String(h), label: `${String(h).padStart(2, "0")}:00` });
    }

    const rows = DEFAULT_CATEGORIES.map((cat) => {
      const cells: Record<string, CellData> = {};
      columns.forEach((col) => {
        const h = parseInt(col.key);
        const hourData = HOURLY_DAY17[h];
        const catData = hourData?.[cat.id as keyof HourlyEvent];

        if (!catData) {
          cells[col.key] = { value: "-", count: 0, intensity: 0 };
          return;
        }

        let intensity = 0;
        if (cat.id === "food") {
          const fd = catData as { kcal: number };
          intensity = fd.kcal > 600 ? 4 : fd.kcal > 400 ? 3 : fd.kcal > 50 ? 2 : 1;
        } else if (cat.id === "exercise") {
          const ed = catData as { min: number };
          intensity = ed.min >= 30 ? 3 : 2;
        } else if (cat.id === "sleep") {
          const sv = catData.value;
          intensity = sv.includes("Deep") ? 4 : sv.includes("REM") ? 3 : 2;
        } else if (cat.id === "medicine") {
          intensity = 2;
        } else if (cat.id === "biometrics") {
          intensity = 3;
        } else if (cat.id === "mental") {
          intensity = 2;
        } else if (cat.id === "hydration") {
          const hd = catData as { ml: number };
          intensity = hd.ml >= 250 ? 3 : 2;
        }

        cells[col.key] = {
          value: catData.value,
          count: 1,
          intensity,
          details: catData.details,
        };
      });
      return { category_id: cat.id, category_name: cat.name_en + " (" + cat.name_ko + ")", category_icon: cat.icon, cells };
    });

    return { level: 4, columns, rows };
  }

  // Fallback
  return { level, columns: [], rows: [] };
}

// ── Fixed-position Tooltip Component ──────────────────────────────
function FixedTooltip({ hoveredCell }: { hoveredCell: HoveredCell }) {
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: hoveredCell.x, y: hoveredCell.y });

  useEffect(() => {
    if (!tooltipRef.current) return;
    const rect = tooltipRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let nx = hoveredCell.x + 12;
    let ny = hoveredCell.y - rect.height - 8;

    // If tooltip would go above viewport, show below cursor
    if (ny < 4) {
      ny = hoveredCell.y + 16;
    }
    // If tooltip would go below viewport, show above cursor
    if (ny + rect.height > vh - 4) {
      ny = hoveredCell.y - rect.height - 8;
    }
    // If tooltip would overflow right edge
    if (nx + rect.width > vw - 8) {
      nx = hoveredCell.x - rect.width - 12;
    }
    // If tooltip would overflow left edge
    if (nx < 4) {
      nx = 4;
    }

    setPos({ x: nx, y: ny });
  }, [hoveredCell.x, hoveredCell.y]);

  const isLevel4 = hoveredCell.level === 4;
  const displayDetails = hoveredCell.details?.slice(0, 5) || [];

  return (
    <div
      ref={tooltipRef}
      className="fixed z-[9999] pointer-events-none"
      style={{ left: pos.x, top: pos.y }}
    >
      <div className="bg-white border border-gray-200 rounded-lg shadow-xl px-4 py-3 min-w-[220px] max-w-[340px] text-left">
        <div className="text-xs text-gray-400 mb-1">{hoveredCell.category}</div>
        <div className="text-sm font-semibold text-gray-800 mb-1">{hoveredCell.label}</div>
        <div className="text-lg font-bold text-red-600">{hoveredCell.value}</div>
        {hoveredCell.count !== undefined && (
          <div className="text-xs text-gray-500 mt-1">{hoveredCell.count} records</div>
        )}
        {displayDetails.length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-100">
            {displayDetails.map((d, i) => (
              <div key={i} className="text-xs text-gray-600 leading-relaxed whitespace-normal">
                {d}
              </div>
            ))}
          </div>
        )}
        {isLevel4 ? (
          <div className="text-[10px] text-red-500 font-medium mt-2">Click for full details</div>
        ) : hoveredCell.level < 4 ? (
          <div className="text-[10px] text-gray-400 mt-2">Click to drill down</div>
        ) : null}
      </div>
    </div>
  );
}

// ── Demo mode: merge mock history with real AI-glasses data ────────
// TODAY = 2026-04-22. Rules:
//   • Before today: mock (demo data)
//   • 2026-04-16 and 2026-04-17: REAL AIMB-G1 data (preserve, don't overwrite)
//   • Today and after: empty
// Exported so ChartPanel.tsx (Trend Charts) can reuse the same merge logic.
// Dynamic — re-evaluates each time the module loads so the cutoff
// always tracks the actual current date instead of going stale.
const _today = new Date();
export const TODAY_YEAR  = _today.getFullYear();
export const TODAY_MONTH = _today.getMonth() + 1;
export const TODAY_DAY   = _today.getDate();
// User started recording real data on this date. Anything before is demo/mock.
const REAL_START_YEAR = 2026;
const REAL_START_MONTH = 4;
const REAL_START_DAY = 16;
const REAL_START_DATE_NUM = REAL_START_YEAR * 10000 + REAL_START_MONTH * 100 + REAL_START_DAY;
const TODAY_DATE_NUM = TODAY_YEAR * 10000 + TODAY_MONTH * 100 + TODAY_DAY;

export type CellMode = "real" | "mock" | "empty";

export function determineCellMode(
  level: number,
  year: number | undefined,
  month: number | undefined,
  day: number | undefined,
  colKey: string,
): CellMode {
  // L1 (yearly): all past years → mock demo data.
  if (level === 1) return "mock";

  // L2 (monthly for a year)
  if (level === 2) {
    if (year === undefined) return "mock";
    if (year < TODAY_YEAR) return "mock";       // past years entirely mock
    if (year > TODAY_YEAR) return "empty";      // future years
    // year === TODAY_YEAR
    const m = parseInt(colKey, 10);
    if (m > TODAY_MONTH) return "empty";        // future months in this year
    if (m < REAL_START_MONTH) return "mock";    // months entirely before real-data start
    return "real";                               // current and past months with real coverage
  }

  // L3 (daily for a year+month)
  if (level === 3) {
    if (year === undefined || month === undefined) return "mock";
    if (year < TODAY_YEAR) return "mock";
    if (year > TODAY_YEAR) return "empty";
    if (month > TODAY_MONTH) return "empty";    // future months
    const d = parseInt(colKey, 10);
    const dateNum = year * 10000 + month * 100 + d;
    if (dateNum > TODAY_DATE_NUM) return "empty";       // future days
    if (dateNum < REAL_START_DATE_NUM) return "mock";   // before real-data start
    return "real";                                       // real (empty cells if nothing logged that day)
  }

  // L4 (hourly for a day)
  if (level === 4) {
    if (year === undefined || month === undefined || day === undefined) return "mock";
    const dateNum = year * 10000 + month * 100 + day;
    if (dateNum > TODAY_DATE_NUM) return "empty";
    if (dateNum < REAL_START_DATE_NUM) return "mock";
    return "real";
  }

  return "mock";
}

export function mergeRealWithMock(
  real: DrilldownResponse,
  mock: DrilldownResponse,
  level: number,
  year?: number,
  month?: number,
  day?: number,
): DrilldownResponse {
  const realCellsByCat = new Map<string, Record<string, CellData>>();
  real.rows.forEach(r => realCellsByCat.set(r.category_id, r.cells || {}));

  const mergedRows = mock.rows.map(mockRow => {
    const realCells = realCellsByCat.get(mockRow.category_id) || {};
    const merged: Record<string, CellData> = {};

    for (const col of mock.columns) {
      const mode = determineCellMode(level, year, month, day, col.key);
      if (mode === "real") {
        if (realCells[col.key]) merged[col.key] = realCells[col.key];
      } else if (mode === "mock") {
        if (mockRow.cells[col.key]) merged[col.key] = mockRow.cells[col.key];
      }
      // "empty": omit — renders as blank cell
    }

    return { ...mockRow, cells: merged };
  });

  return { ...mock, rows: mergedRows };
}

// ── Component ──────────────────────────────────────────────────────
export default function DrilldownGrid({
  userId,
  level,
  year,
  month,
  day,
  onDrillDown,
  onCellDetail,
}: DrilldownGridProps) {
  const [data, setData] = useState<DrilldownResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredCell, setHoveredCell] = useState<HoveredCell | null>(null);

  // isInitialFetch: only show loading state on first load.
  // Subsequent polling is SILENT — no loading spinner, no flash,
  // existing data stays rendered until the new data arrives.
  const fetchData = useCallback(async (isInitialFetch: boolean) => {
    if (isInitialFetch) {
      setLoading(true);
      setError(null);
    }

    const mock = generateConsistentMockData(level, year, month, day);

    try {
      const params = new URLSearchParams();
      params.set("user_id", String(userId));
      params.set("level", String(level));
      if (year) params.set("year", String(year));
      if (month) params.set("month", String(month));
      if (day) params.set("day", String(day));

      const res = await fetch(`http://localhost:8000/api/v1/hrt/drilldown?${params.toString()}`);
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const real: DrilldownResponse = await res.json();
      const next = mergeRealWithMock(real, mock, level, year, month, day);
      // Skip state update if data is identical — prevents table/chart flicker
      // on background polls when nothing has changed.
      setData(prev => {
        if (prev && JSON.stringify(prev) === JSON.stringify(next)) return prev;
        return next;
      });
    } catch {
      // Silent on background polls — don't spam console.
      if (isInitialFetch) {
        console.warn("API unavailable, rendering demo mock with cutoff filter");
        // Apply the cell-mode cutoff filter even on fallback so future
        // months/days stay blank. Without this, setData(mock) would render
        // the entire year (Jan-Dec) filled with mock values, violating the
        // "real after Apr 16" contract.
        const emptyReal: DrilldownResponse = {
          ...mock,
          rows: mock.rows.map(r => ({ ...r, cells: {} })),
        };
        setData(mergeRealWithMock(emptyReal, mock, level, year, month, day));
      }
    } finally {
      if (isInitialFetch) setLoading(false);
    }
  }, [userId, level, year, month, day]);

  useEffect(() => {
    fetchData(true);  // initial: show loading
    // Poll every 15s silently — no loading flash, existing data stays visible.
    const intervalId = setInterval(() => fetchData(false), 15_000);
    return () => clearInterval(intervalId);
  }, [fetchData]);

  const handleCellClick = (colKey: string, cellData: CellData, categoryId?: string, categoryName?: string, colLabel?: string) => {
    if (cellData.count === 0) return;

    if (level === 4) {
      if (onCellDetail && categoryId && categoryName && colLabel) {
        onCellDetail({
          categoryId,
          categoryName,
          colKey,
          colLabel,
          value: cellData.value,
          details: cellData.details,
        });
      }
      return;
    }

    const colNum = parseInt(colKey, 10);
    if (level === 1) {
      onDrillDown({ year: colNum });
    } else if (level === 2) {
      onDrillDown({ year, month: colNum });
    } else if (level === 3) {
      onDrillDown({ year, month, day: colNum });
    }
  };

  const handleCellMouseEnter = (
    e: React.MouseEvent,
    cell: CellData,
    category: string,
    categoryId: string,
    colLabel: string,
  ) => {
    if (cell.count === 0) return;
    setHoveredCell({
      x: e.clientX,
      y: e.clientY,
      category,
      categoryId,
      label: colLabel,
      value: cell.value,
      count: cell.count,
      details: cell.details,
      level,
    });
  };

  const handleCellMouseLeave = () => {
    setHoveredCell(null);
  };

  // Loading skeleton
  if (loading) {
    return (
      <div className="p-4">
        <div className="grid gap-1">
          {Array.from({ length: 7 }).map((_, r) => (
            <div key={r} className="flex gap-1">
              <div className="w-48 h-12 bg-gray-100 rounded loading-pulse" />
              {Array.from({ length: 12 }).map((_, c) => (
                <div key={c} className="flex-1 h-12 bg-gray-50 rounded loading-pulse"
                  style={{ animationDelay: `${(r * 12 + c) * 40}ms` }}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-500">
        <div className="text-center">
          <div className="text-2xl mb-2">!</div>
          <div>{error}</div>
          <button
            onClick={fetchData}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const levelLabel = level === 1 ? "Yearly Overview (Lifetime)" :
    level === 2 ? `${year} - Monthly View` :
    level === 3 ? `${year} ${MONTH_NAMES[(month || 1) - 1]} - Daily View` :
    `${year} ${MONTH_NAMES[(month || 1) - 1]} ${day} - Hourly View`;

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-gray-600 font-medium">
          {levelLabel} &mdash; {data.columns.length} columns &times; {data.rows.length} categories
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <span>Data density:</span>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className={`w-4 h-4 rounded-sm border border-gray-200 ${getIntensityClass(i)}`} />
          ))}
          <span>High</span>
        </div>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden shadow-sm">
        <div className="grid-scroll-wrapper" style={{ maxWidth: "100%", overflowX: "auto" }}>
          <table className="hrt-table" style={{ minWidth: `${220 + data.columns.length * 120}px` }}>
            <thead>
              <tr>
                <th className="sticky-col z-20 bg-gray-50 px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b-2 border-gray-200"
                    style={{ minWidth: "220px", width: "220px" }}>
                  Category
                </th>
                {data.columns.map((col) => (
                  <th
                    key={col.key}
                    className="px-2 py-3 text-center text-xs font-semibold text-gray-600 bg-gray-50 border-b-2 border-gray-200 whitespace-nowrap"
                    style={{ minWidth: "110px" }}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, rowIdx) => (
                <tr key={row.category_id} className={rowIdx % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                  <td className="sticky-col bg-white px-4 py-3 text-sm font-medium text-gray-800 border-b border-gray-100 whitespace-nowrap"
                      style={{ minWidth: "220px", width: "220px" }}>
                    <span className="flex items-center gap-2">
                      {row.category_icon && (
                        <img src={row.category_icon} alt="" className="w-5 h-5 object-contain" />
                      )}
                      {row.category_name}
                    </span>
                  </td>
                  {data.columns.map((col) => {
                    const cell = row.cells[col.key] || { value: "-", count: 0, intensity: 0 };
                    const isClickable = cell.count > 0 && (level < 4 || (level === 4 && onCellDetail));
                    const catInfo = DEFAULT_CATEGORIES.find((c) => c.id === row.category_id);

                    return (
                      <td
                        key={col.key}
                        className="border-b border-gray-100 p-0"
                      >
                        <button
                          onClick={() => handleCellClick(
                            col.key,
                            cell,
                            row.category_id,
                            catInfo ? `${catInfo.name_en} (${catInfo.name_ko})` : row.category_name,
                            col.label,
                          )}
                          onMouseEnter={(e) => handleCellMouseEnter(
                            e,
                            cell,
                            catInfo ? `${catInfo.name_en} (${catInfo.name_ko})` : row.category_name,
                            row.category_id,
                            col.label,
                          )}
                          onMouseLeave={handleCellMouseLeave}
                          disabled={!isClickable}
                          className={`grid-cell w-full px-2 py-3 text-center text-xs leading-snug
                            ${getIntensityClass(cell.intensity)}
                            ${isClickable ? "cursor-pointer hover:brightness-95 hover:shadow-md" : "cursor-default"}
                            ${cell.count === 0 ? "text-gray-300" : "text-gray-800"}
                            disabled:cursor-default
                          `}
                        >
                          <span className="block truncate">
                            {cell.value}
                          </span>
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Fixed-position tooltip rendered outside the table */}
      {hoveredCell && <FixedTooltip hoveredCell={hoveredCell} />}
    </div>
  );
}
