"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface BarDatum {
  label: string;
  count: number;
  /** Tailwind fill class for this bar, e.g. "fill-red-600". */
  fillClass?: string;
}

const ROW_HEIGHT = 36;
const MAX_LABEL = 22;

const shortLabel = (label: string) =>
  label.length > MAX_LABEL ? `${label.slice(0, MAX_LABEL - 1)}…` : label;

/** Horizontal bars (labels stay readable on a phone), in a card with a title and empty state. */
export default function BarChartCard({
  title,
  data,
  emptyText = "No data yet.",
}: {
  title: string;
  data: BarDatum[];
  emptyText?: string;
}) {
  const hasData = data.some((d) => d.count > 0);

  return (
    <section className="flex flex-col rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">{title}</h2>
      {hasData ? (
        <div className="mt-3" style={{ height: Math.max(120, data.length * ROW_HEIGHT + 40) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
            >
              <CartesianGrid horizontal={false} className="stroke-zinc-200" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="label"
                width={160}
                tick={{ fontSize: 12 }}
                tickFormatter={shortLabel}
              />
              <Tooltip cursor={{ fillOpacity: 0.05 }} />
              <Bar
                dataKey="count"
                name="Events"
                radius={[0, 4, 4, 0]}
                maxBarSize={24}
                isAnimationActive={false}
              >
                {data.map((d, i) => (
                  <Cell key={i} className={d.fillClass ?? "fill-zinc-700"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 flex flex-1 items-center justify-center rounded-md border border-dashed border-zinc-300 p-8 text-sm text-zinc-500">
          {emptyText}
        </p>
      )}
    </section>
  );
}
