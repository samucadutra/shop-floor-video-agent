"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import EventCard from "@/components/EventCard";
import EventTimeline from "@/components/EventTimeline";
import Spinner from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import SummaryCard from "@/components/SummaryCard";
import VideoPlayer, { type VideoPlayerHandle } from "@/components/VideoPlayer";
import { usePolling } from "@/hooks/usePolling";
import { analyzeVideo, ApiError, getEvents, getVideo } from "@/lib/api";
import { formatSeconds } from "@/lib/format";
import type { Event, Video } from "@/lib/types";

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export default function VideoDetailPage({ params }: PageProps<"/videos/[id]">) {
  const { id } = use(params);
  const player = useRef<VideoPlayerHandle>(null);
  const [video, setVideo] = useState<Video | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  // State is only set in the promise callbacks, so this is safe to start from an effect.
  const load = useCallback(
    () =>
      Promise.all([getVideo(id), getEvents(id)]).then(
        ([v, e]) => {
          setVideo(v);
          setEvents(e);
          setLoadError(null);
        },
        (e: unknown) => setLoadError(message(e, "Could not load the video.")),
      ),
    [id],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const processing = video?.status === "processing";
  usePolling(load, { enabled: processing });

  const analyze = async () => {
    setStarting(true);
    setActionError(null);
    try {
      await analyzeVideo(id);
      await load();
    } catch (e) {
      setActionError(message(e, "Could not start the analysis."));
    } finally {
      setStarting(false);
    }
  };

  const seek = (seconds: number) => player.current?.seekTo(seconds);

  if (!video) {
    return loadError ? (
      <div className="flex flex-col gap-4">
        <ErrorState message={loadError} onRetry={load} />
        <Link href="/videos" className="text-sm font-medium underline">
          Back to videos
        </Link>
      </div>
    ) : (
      <Spinner />
    );
  }

  const run = video.current_run;
  const label = video.status === "uploaded" ? "Analyze" : "Re-analyze";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <Link href="/videos" className="text-sm text-zinc-500 hover:text-zinc-900">
            ← Videos
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <h1 className="min-w-0 truncate text-2xl font-semibold tracking-tight">
              {video.original_name}
            </h1>
            <StatusBadge status={video.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            {formatSeconds(video.duration_s)} · {video.width}×{video.height} ·{" "}
            {Math.round(video.fps)} fps
          </p>
        </div>
        <button
          type="button"
          onClick={analyze}
          disabled={processing || starting}
          className="shrink-0 rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {processing ? "Analyzing…" : starting ? "Starting…" : label}
        </button>
      </div>

      {loadError && <ErrorState message={loadError} onRetry={load} />}
      {actionError && <ErrorState message={actionError} />}
      {video.status === "failed" && video.error_message && (
        <ErrorState
          message={`The last analysis failed: ${video.error_message}`}
          onRetry={starting ? undefined : analyze}
        />
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <VideoPlayer ref={player} src={video.file_url} />
          <EventTimeline events={events} durationS={video.duration_s} onSeek={seek} />
        </div>

        <div className="flex flex-col gap-4">
          {processing && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <Spinner label="The agent is analyzing the video. This page updates by itself." />
            </div>
          )}
          {run ? (
            <>
              <SummaryCard run={run} />
              <section className="flex flex-col gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
                  Events ({events.length})
                </h2>
                {events.length === 0 ? (
                  <EmptyState title="No events found" />
                ) : (
                  events.map((e) => <EventCard key={e.id} event={e} onSeek={seek} />)
                )}
              </section>
            </>
          ) : (
            !processing && (
              <EmptyState title="Not analyzed yet">
                Click {label} to let the agent look for safety events.
              </EmptyState>
            )
          )}
        </div>
      </div>
    </div>
  );
}
