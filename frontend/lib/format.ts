/** 75.4 -> "1:15" */
export function formatSeconds(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** 0.876 -> "88%" */
export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

/** "0.0123" -> "$0.0123" */
export function formatCost(usd: string | number): string {
  const value = typeof usd === "string" ? Number.parseFloat(usd) : usd;
  return `$${(Number.isFinite(value) ? value : 0).toFixed(4)}`;
}

/** 74210 ms -> "1m 14s"; 950 -> "0.9s" */
export function formatDuration(ms: number | null): string {
  if (ms === null) return "–";
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}m ${total % 60}s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
