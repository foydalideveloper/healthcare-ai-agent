"use client";

const MONTH_NAMES: Record<number, string> = {
  1: "January",
  2: "February",
  3: "March",
  4: "April",
  5: "May",
  6: "June",
  7: "July",
  8: "August",
  9: "September",
  10: "October",
  11: "November",
  12: "December",
};

interface BreadcrumbProps {
  level: number;
  year?: number;
  month?: number;
  day?: number;
  onNavigate: (level: number, params?: { year?: number; month?: number; day?: number }) => void;
}

export default function Breadcrumb({ level, year, month, day, onNavigate }: BreadcrumbProps) {
  const crumbs: { label: string; onClick: () => void; active: boolean }[] = [];

  crumbs.push({
    label: "Lifetime Overview",
    onClick: () => onNavigate(1),
    active: level === 1,
  });

  if (level >= 2 && year) {
    crumbs.push({
      label: `${year}`,
      onClick: () => onNavigate(2, { year }),
      active: level === 2,
    });
  }

  if (level >= 3 && year && month) {
    crumbs.push({
      label: MONTH_NAMES[month] || `Month ${month}`,
      onClick: () => onNavigate(3, { year, month }),
      active: level === 3,
    });
  }

  if (level >= 4 && year && month && day) {
    crumbs.push({
      label: `Day ${day}`,
      onClick: () => onNavigate(4, { year, month, day }),
      active: level === 4,
    });
  }

  return (
    <nav className="flex items-center gap-1 text-sm">
      <button
        onClick={() => {
          if (level > 1) {
            const prevLevel = level - 1;
            if (prevLevel === 1) onNavigate(1);
            else if (prevLevel === 2) onNavigate(2, { year });
            else if (prevLevel === 3) onNavigate(3, { year, month });
          }
        }}
        disabled={level === 1}
        className="mr-3 px-3 py-1.5 rounded-md text-xs font-medium
          bg-gray-100 text-gray-600 border border-gray-200
          hover:bg-gray-200 hover:text-gray-900
          disabled:opacity-30 disabled:cursor-not-allowed
          transition-colors"
      >
        &larr; Back
      </button>

      {crumbs.map((crumb, i) => (
        <span key={i} className="flex items-center">
          {i > 0 && <span className="mx-2 text-gray-300">&gt;</span>}
          <button
            onClick={crumb.onClick}
            className={`px-2.5 py-1 rounded transition-colors ${
              crumb.active
                ? "text-white font-semibold bg-red-600 shadow-sm"
                : "text-gray-500 hover:text-gray-900 hover:bg-gray-100"
            }`}
          >
            {crumb.label}
          </button>
        </span>
      ))}
    </nav>
  );
}
