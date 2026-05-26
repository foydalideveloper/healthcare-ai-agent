"use client";

interface CellTooltipProps {
  category: string;
  categoryId: string;
  label: string;
  value: string;
  count?: number;
  details?: string[];
  level: number;
}

function getLevelSpecificContent(level: number, categoryId: string, value: string, details?: string[]): string[] {
  if (level === 1) {
    // Yearly summaries
    switch (categoryId) {
      case "food":
        return [
          details?.[0] || "Avg 1,800 kcal/day",
          details?.[1] || "~657,000 kcal total",
          details?.[2] || "Top: Rice, Kimchi, Samgyeopsal",
        ];
      case "exercise":
        return [
          details?.[0] || "5,475 min total",
          details?.[1] || "15 min/day avg",
          "78% active days",
        ];
      case "sleep":
        return [
          details?.[0] || "7.2h avg",
          "Quality: Good",
          "Consistency: 85%",
        ];
      default:
        return details?.slice(0, 4) || [];
    }
  }

  if (level === 2) {
    // Monthly summaries
    switch (categoryId) {
      case "food":
        return [
          details?.[0] || "90 meals",
          details?.[1] || "54,000 kcal",
          "Top: Rice, Kimchi, Samgyeopsal",
        ];
      case "exercise":
        return [
          details?.[0] || "450 min",
          "Running 12x, Gym 8x, Walk 10x",
        ];
      default:
        return details?.slice(0, 4) || [];
    }
  }

  if (level === 3) {
    // Daily summaries
    switch (categoryId) {
      case "food":
        return details?.slice(0, 4) || [
          "1,800 kcal",
          "Breakfast 450, Lunch 550, Dinner 800",
        ];
      case "exercise":
        return details?.slice(0, 3) || [
          "Jogging 30min",
          "240 kcal burned",
        ];
      case "sleep":
        return [
          details?.[0] || "7.5h",
          "Deep: 2.1h, REM: 1.8h",
          "Quality: 8/10",
        ];
      default:
        return details?.slice(0, 4) || [];
    }
  }

  if (level === 4) {
    // Hourly - show all details + click prompt
    switch (categoryId) {
      case "food":
        return [
          ...(details?.slice(0, 5) || []),
          "",
        ];
      default:
        return details?.slice(0, 5) || [];
    }
  }

  return details?.slice(0, 5) || [];
}

export default function CellTooltip({ category, categoryId, label, value, count, details, level }: CellTooltipProps) {
  const displayDetails = getLevelSpecificContent(level, categoryId, value, details);
  const isLevel4 = level === 4;

  return (
    <div className="tooltip-content">
      <div
        className="bg-white border border-gray-200 rounded-lg shadow-xl
          px-4 py-3 min-w-[240px] max-w-[360px] text-left"
      >
        <div className="text-xs text-gray-400 mb-1">{category}</div>
        <div className="text-sm font-semibold text-gray-800 mb-1">{label}</div>
        <div className="text-lg font-bold text-red-600">{value}</div>
        {count !== undefined && (
          <div className="text-xs text-gray-500 mt-1">{count} records</div>
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
        ) : level < 4 ? (
          <div className="text-[10px] text-gray-400 mt-2">Click to drill down</div>
        ) : null}
      </div>
    </div>
  );
}
