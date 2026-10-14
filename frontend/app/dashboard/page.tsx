"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import BarChartCard, { type BarDatum } from "@/components/BarChartCard";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import Spinner from "@/components/Spinner";
import StatTile from "@/components/StatTile";
import { ApiError, getStats } from "@/lib/api";
import { eventLabel } from "@/lib/eventTypes";
import { formatCost, formatDuration, formatNumber } from "@/lib/format";
import type { Severity, Stats } from "@/lib/types";

const SEVERITIES: { key: Severity; fillClass: string }[] = [
  { key: "high", fillClass: "fill-red-600" },
  { key: "medium", fillClass: "fill-orange-500" },
  { key: "low", fillClass: "fill-yellow-400" },
];

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  // State is only set in the promise callbacks, so this is safe to start from an effect.
  const load = useCallback(
    () =>
      getStats().then(
        (s) => {
          setStats(s);
          setError(null);
        },
        (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load the stats."),
      ),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const hasRuns = stats !== null && stats.runs_succeeded + stats.runs_failed > 0;

  const byType: BarDatum[] =
    stats?.events_by_type.map((r) => ({ label: eventLabel(r.event_type), count: r.count })) ?? [];
  // Always the three severities, in a fixed order and with their badge colors.
  const bySeverity: BarDatum[] = SEVERITIES.map(({ key, fillClass }) => ({
    label: key,
    count: stats?.events_by_severity.find((r) => r.severity === key)?.count ?? 0,
    fillClass,
  }));
  // The same file can be uploaded twice, so repeated names get a short id suffix.
  const names = stats?.events_per_video.map((r) => r.name) ?? [];
  const perVideo: BarDatum[] =
    stats?.events_per_video.map((r) => ({
      label:
        names.indexOf(r.name) === names.lastIndexOf(r.name)
          ? r.name
          : `${r.name} · ${r.video_id.slice(0, 4)}`,
      count: r.count,
    })) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>

      {error && <ErrorState message={error} onRetry={load} />}
      {!stats && !error && <Spinner />}

      {stats && !hasRuns && (
        <EmptyState title="No analyses yet">
          <Link href="/upload" className="font-medium text-zinc-900 underline">
            Upload a video
          </Link>{" "}
          and analyze it to see totals here.
        </EmptyState>
      )}

      {stats && hasRuns && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Avg. processing" value={formatDuration(stats.avg_processing_ms)} />
            <StatTile label="Total tokens" value={formatNumber(stats.total_tokens)} />
            <StatTile label="Est. total cost" value={formatCost(stats.total_estimated_cost_usd)} />
            <StatTile
              label="Runs ok / failed"
              value={`${stats.runs_succeeded} / ${stats.runs_failed}`}
            />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <BarChartCard title="Events by type" data={byType} emptyText="No events found yet." />
            <BarChartCard
              title="Events by severity"
              data={bySeverity}
              emptyText="No events found yet."
            />
            <div className="lg:col-span-2">
              <BarChartCard
                title="Events per video"
                data={perVideo}
                emptyText="No events found yet."
              />
            </div>
          </div>
          <p className="text-xs text-zinc-500">
            Event counts use the latest successful run of each video. Token and cost totals cover
            every stored run.
          </p>
        </>
      )}
    </div>
  );
}
