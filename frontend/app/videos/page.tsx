"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import Spinner from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, getVideos } from "@/lib/api";
import { formatDate, formatSeconds } from "@/lib/format";
import type { Paginated, VideoListItem } from "@/lib/types";

export default function VideosPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<VideoListItem> | null>(null);
  const [error, setError] = useState<string | null>(null);

  // State is only set in the promise callbacks, so this is safe to start from an effect.
  const load = useCallback(
    () =>
      getVideos(page).then(
        (result) => {
          setData(result);
          setError(null);
        },
        (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load the videos."),
      ),
    [page],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const processing = data?.results.some((v) => v.status === "processing") ?? false;
  usePolling(load, { enabled: processing });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Videos</h1>
        <Link
          href="/upload"
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700"
        >
          Upload
        </Link>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {!data && !error && <Spinner />}
      {data && data.count === 0 && (
        <EmptyState title="No videos yet">
          <Link href="/upload" className="font-medium text-zinc-900 underline">
            Upload a video
          </Link>{" "}
          to start.
        </EmptyState>
      )}

      {data && data.count > 0 && (
        <>
          {/* Cards on small screens */}
          <ul className="flex flex-col gap-3 md:hidden">
            {data.results.map((v) => (
              <li key={v.id}>
                <Link
                  href={`/videos/${v.id}`}
                  className="block rounded-lg border border-zinc-200 bg-white p-4 shadow-sm hover:border-zinc-400"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="min-w-0 truncate font-medium">{v.original_name}</span>
                    <StatusBadge status={v.status} />
                  </div>
                  <p className="mt-2 text-sm text-zinc-500">
                    {formatSeconds(v.duration_s)} · {v.event_count} event
                    {v.event_count === 1 ? "" : "s"} · {formatDate(v.created_at)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>

          {/* Table on larger screens */}
          <div className="hidden overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm md:block">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Uploaded</th>
                  <th className="px-4 py-3 font-medium">Duration</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Events</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {data.results.map((v) => (
                  <tr key={v.id} className="hover:bg-zinc-50">
                    <td className="max-w-xs truncate px-4 py-3 font-medium">
                      <Link href={`/videos/${v.id}`} className="hover:underline">
                        {v.original_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-zinc-600">{formatDate(v.created_at)}</td>
                    <td className="px-4 py-3 text-zinc-600">{formatSeconds(v.duration_s)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={v.status} />
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{v.event_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(data.next || data.previous) && (
            <div className="flex items-center justify-between text-sm">
              <button
                type="button"
                disabled={!data.previous}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-zinc-500">Page {page}</span>
              <button
                type="button"
                disabled={!data.next}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
