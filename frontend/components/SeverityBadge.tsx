import type { Severity } from "@/lib/types";

export const SEVERITY_COLORS: Record<Severity, { badge: string; marker: string }> = {
  low: { badge: "bg-yellow-50 text-yellow-800 ring-yellow-300", marker: "bg-yellow-400" },
  medium: { badge: "bg-orange-50 text-orange-800 ring-orange-300", marker: "bg-orange-500" },
  high: { badge: "bg-red-50 text-red-800 ring-red-300", marker: "bg-red-600" },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${SEVERITY_COLORS[severity].badge}`}
    >
      {severity}
    </span>
  );
}
