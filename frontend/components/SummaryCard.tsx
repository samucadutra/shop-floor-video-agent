import type { Run } from "@/lib/types";

export default function SummaryCard({ run }: { run: Run }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Summary</h2>
      {run.is_partial && (
        <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Partial result: {run.stop_reason.replace(/_/g, " ")}
        </p>
      )}
      <p className="mt-2 whitespace-pre-line text-zinc-800">{run.summary || "No summary."}</p>
      <p className="mt-3 text-xs text-zinc-500">
        AI-generated. A person should review each event before acting on it.
      </p>
    </section>
  );
}
