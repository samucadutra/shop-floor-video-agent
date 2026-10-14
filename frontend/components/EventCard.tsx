import { eventLabel } from "@/lib/eventTypes";
import { formatPercent, formatSeconds } from "@/lib/format";
import type { Event } from "@/lib/types";
import SeverityBadge from "./SeverityBadge";

export default function EventCard({
  event,
  onSeek,
}: {
  event: Event;
  onSeek: (seconds: number) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSeek(event.timestamp_s)}
      className="w-full rounded-lg border border-zinc-200 bg-white p-4 text-left shadow-sm hover:border-zinc-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-zinc-500">{formatSeconds(event.timestamp_s)}</span>
        <span className="font-medium">{eventLabel(event.event_type)}</span>
        <SeverityBadge severity={event.severity} />
        <span className="ml-auto text-xs text-zinc-500">
          {formatPercent(event.confidence)} confidence
        </span>
      </div>
      <p className="mt-2 text-sm text-zinc-700">{event.explanation}</p>
    </button>
  );
}
