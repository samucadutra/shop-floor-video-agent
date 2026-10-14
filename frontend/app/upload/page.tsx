"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Dropzone from "@/components/Dropzone";
import ErrorState from "@/components/ErrorState";
import UploadNotice from "@/components/UploadNotice";
import { analyzeVideo, ApiError, uploadVideo } from "@/lib/api";
import { formatBytes, formatSeconds } from "@/lib/format";
import type { Video } from "@/lib/types";

const message = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [video, setVideo] = useState<Video | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const upload = async (picked: File) => {
    setFile(picked);
    setVideo(null);
    setError(null);
    setProgress(0);
    try {
      setVideo(await uploadVideo(picked, setProgress));
    } catch (e) {
      setError(message(e));
    } finally {
      setProgress(null);
    }
  };

  const analyze = async () => {
    if (!video) return;
    setStarting(true);
    setError(null);
    try {
      await analyzeVideo(video.id);
      router.push(`/videos/${video.id}`);
    } catch (e) {
      setError(message(e));
      setStarting(false);
    }
  };

  const uploading = progress !== null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Upload a video</h1>
      <UploadNotice />
      <Dropzone
        onFile={upload}
        onError={(msg) => {
          setFile(null);
          setVideo(null);
          setError(msg);
        }}
        disabled={uploading || starting}
      />

      {uploading && file && (
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="flex justify-between gap-4 text-sm">
            <span className="truncate">{file.name}</span>
            <span className="shrink-0 text-zinc-500">{Math.round(progress * 100)}%</span>
          </div>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-200"
            role="progressbar"
            aria-valuenow={Math.round(progress * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="h-full bg-zinc-900 transition-[width]"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          {progress >= 1 && (
            <p className="mt-2 text-xs text-zinc-500">Checking the video on the server…</p>
          )}
        </div>
      )}

      {error && <ErrorState message={error} />}

      {video && (
        <div className="flex flex-col gap-4 rounded-lg border border-green-200 bg-green-50 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium text-green-900">{video.original_name} uploaded</p>
            <p className="text-green-800">
              {formatSeconds(video.duration_s)} · {video.width}×{video.height} ·{" "}
              {formatBytes(video.size_bytes)}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Link
              href={`/videos/${video.id}`}
              className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium hover:bg-zinc-100"
            >
              View video
            </Link>
            <button
              type="button"
              onClick={analyze}
              disabled={starting}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-60"
            >
              {starting ? "Starting…" : "Analyze"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
