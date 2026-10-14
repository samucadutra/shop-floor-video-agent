"use client";

import { useRef, useState, type DragEvent } from "react";

const EXTENSIONS = [".mp4", ".mov", ".webm"];
export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? "200") || 200;

/** The same type and size rules as the server (which checks again). */
export function checkFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Unsupported file type. Allowed: mp4, mov, webm.";
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `The file is too large. The limit is ${MAX_UPLOAD_MB} MB.`;
  }
  return null;
}

export default function Dropzone({
  onFile,
  onError,
  disabled = false,
}: {
  onFile: (file: File) => void;
  onError: (message: string) => void;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const pick = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    const error = checkFile(file);
    if (error) onError(error);
    else onFile(file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    if (!disabled) pick(e.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 text-center transition-colors sm:p-12 ${
        dragging ? "border-zinc-900 bg-zinc-100" : "border-zinc-300 bg-white"
      } ${disabled ? "opacity-60" : ""}`}
    >
      <p className="font-medium text-zinc-800">Drop a video here</p>
      <p className="text-sm text-zinc-500">
        MP4, MOV or WebM, up to {MAX_UPLOAD_MB} MB and about 2 minutes
      </p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed"
      >
        Choose a file
      </button>
      <input
        ref={input}
        type="file"
        accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm"
        className="hidden"
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = ""; // allow picking the same file again
        }}
      />
    </div>
  );
}
