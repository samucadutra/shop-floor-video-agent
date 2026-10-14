import { formatCost, formatNumber } from "@/lib/format";
import type { AgentStep, StepStatus } from "@/lib/types";

const STATUS_STYLES: Record<StepStatus, string> = {
  ok: "bg-green-50 text-green-700 ring-green-200",
  retried: "bg-amber-50 text-amber-800 ring-amber-200",
  error: "bg-red-50 text-red-700 ring-red-200",
};

/** One agent step. The decision is always visible; the details open on click. */
export default function TraceStep({ step }: { step: AgentStep }) {
  return (
    <details className="group rounded-lg border border-zinc-200 bg-white shadow-sm">
      <summary className="cursor-pointer list-none p-3 hover:bg-zinc-50 [&::-webkit-details-marker]:hidden">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-mono text-xs text-zinc-400">#{step.index}</span>
          <span className="font-medium capitalize">{step.node}</span>
          <span className="text-xs text-zinc-500">iteration {step.iteration}</span>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[step.status]}`}
          >
            {step.status}
          </span>
          <span className="ml-auto text-xs tabular-nums text-zinc-500">
            {formatNumber(step.input_tokens + step.output_tokens)} tok · {step.latency_ms} ms
          </span>
          <span className="text-zinc-400 transition-transform group-open:rotate-90" aria-hidden>
            ›
          </span>
        </div>
        <p className="mt-1 whitespace-pre-line break-words text-sm text-zinc-700">
          {step.decision || "No decision recorded."}
        </p>
      </summary>

      <div className="flex flex-col gap-3 border-t border-zinc-100 p-3 text-sm">
        {step.error_message && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-red-800">{step.error_message}</p>
        )}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Input</h4>
          <p className="mt-1 whitespace-pre-line break-words text-zinc-700">
            {step.input_summary || "–"}
          </p>
        </div>
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Tool calls ({step.tool_calls.length})
          </h4>
          {step.tool_calls.length === 0 ? (
            <p className="mt-1 text-zinc-500">None (deterministic step).</p>
          ) : (
            <ul className="mt-1 flex flex-col gap-2">
              {step.tool_calls.map((call, i) => (
                <li key={i} className="rounded-md bg-zinc-50 p-2">
                  <span className="font-mono text-xs font-medium">{call.tool}</span>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs text-zinc-600">
                    {JSON.stringify(call.args)}
                  </pre>
                  <p className="mt-1 text-xs text-zinc-700">→ {call.output_summary}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div>
            <dt className="text-zinc-500">Input tokens</dt>
            <dd className="tabular-nums">{formatNumber(step.input_tokens)}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Output tokens</dt>
            <dd className="tabular-nums">{formatNumber(step.output_tokens)}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Latency</dt>
            <dd className="tabular-nums">{formatNumber(step.latency_ms)} ms</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Est. cost</dt>
            <dd className="tabular-nums">{formatCost(step.estimated_cost_usd)}</dd>
          </div>
        </dl>
      </div>
    </details>
  );
}
