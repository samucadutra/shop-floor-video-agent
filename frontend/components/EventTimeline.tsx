import { eventLabel } from "@/lib/eventTypes";
import { formatSeconds } from "@/lib/format";
import type { Event } from "@/lib/types";
import { SEVERITY_COLORS } from "./SeverityBadge";

export default function EventTimeline({
  events,
  durationS,
  onSeek,
}: {
  events: Event[];
  durationS: number;
  onSeek: (seconds: number) => void;
}) {
  return (
    <div>
      <div className="relative h-8 rounded-md bg-zinc-200" aria-label="Event timeline">
        {events.map((e) => {
          const left = durationS > 0 ? Math.min(100, (e.timestamp_s / durationS) * 100) : 0;
          return (
            <button
              key={e.id}
              type="button"
              onClick={() => onSeek(e.timestamp_s)}
              title={`${eventLabel(e.event_type)} at ${formatSeconds(e.timestamp_s)} (${e.severity})`}
              aria-label={`Jump to ${eventLabel(e.event_type)} at ${formatSeconds(e.timestamp_s)}`}
              style={{ left: `${left}%` }}
              className={`absolute top-0 h-8 w-2 -translate-x-1/2 rounded-sm ring-2 ring-white hover:scale-x-150 focus:outline-none focus-visible:ring-zinc-900 ${SEVERITY_COLORS[e.severity].marker}`}
            />
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-xs text-zinc-500">
        <span>0:00</span>
        <span>{formatSeconds(durationS)}</span>
      </div>
    </div>
  );
}
