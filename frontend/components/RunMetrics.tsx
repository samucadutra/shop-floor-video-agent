import { formatCost, formatDuration, formatNumber } from "@/lib/format";
import type { Run } from "@/lib/types";

export default function RunMetrics({ run }: { run: Run }) {
  const metrics = [
    { label: "Duration", value: formatDuration(run.duration_ms) },
    { label: "Frames", value: formatNumber(run.frames_analyzed) },
    { label: "LLM calls", value: formatNumber(run.llm_calls) },
    { label: "Iterations", value: formatNumber(run.iterations) },
    { label: "Input tokens", value: formatNumber(run.input_tokens) },
    { label: "Output tokens", value: formatNumber(run.output_tokens) },
    { label: "Est. cost", value: formatCost(run.estimated_cost_usd) },
    { label: "Result", value: run.is_partial ? "Partial" : "Complete" },
  ];

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Run metrics</h2>
        <span className="min-w-0 truncate font-mono text-xs text-zinc-500">
          {run.provider}
          {run.model && ` / ${run.model}`}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        {metrics.map((m) => (
          <div key={m.label}>
            <dt className="text-xs text-zinc-500">{m.label}</dt>
            <dd className="font-medium tabular-nums">{m.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
