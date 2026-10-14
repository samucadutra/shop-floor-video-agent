"use client";

import { useCallback, useEffect, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, getTrace } from "@/lib/api";
import type { RunTrace } from "@/lib/types";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import Spinner from "./Spinner";
import TraceStep from "./TraceStep";

/**
 * The agent trace of one run. While `live` (the run is queued or running) it refreshes every
 * 3 s, so new steps appear as the agent records them.
 */
export default function TracePanel({ runId, live }: { runId: string | null; live: boolean }) {
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  // State is only set in the promise callbacks, so this is safe to start from an effect.
  const load = useCallback(
    () =>
      runId
        ? getTrace(runId).then(
            (t) => {
              setTrace(t);
              setError(null);
            },
            (e: unknown) =>
              setError(e instanceof ApiError ? e.message : "Could not load the agent trace."),
          )
        : undefined,
    [runId],
  );

  // `live` is a dependency so the trace is fetched once more when the run finishes.
  useEffect(() => {
    void load();
  }, [load, live]);

  usePolling(load, { enabled: live && runId !== null });

  // A trace from a previous run is not shown while the new one loads.
  const current = trace && trace.run_id === runId ? trace : null;

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
        Agent trace{current && ` (${current.steps.length} steps)`}
      </h2>
      {error && <ErrorState message={error} onRetry={load} />}
      {!runId ? (
        <EmptyState title="No trace yet">
          The agent trace appears once an analysis starts.
        </EmptyState>
      ) : !current ? (
        !error && <Spinner />
      ) : (
        <>
          {current.is_partial && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Stopped early by a guardrail: {current.stop_reason.replace(/_/g, " ")}. The report is
              partial.
            </p>
          )}
          {current.steps.length === 0 ? (
            <EmptyState title="No steps yet">
              {live ? "Waiting for the agent's first step…" : "This run recorded no steps."}
            </EmptyState>
          ) : (
            <ol className="flex flex-col gap-2">
              {current.steps.map((step) => (
                <li key={step.id}>
                  <TraceStep step={step} />
                </li>
              ))}
            </ol>
          )}
          {live && <Spinner label="The agent is working…" />}
        </>
      )}
    </section>
  );
}
