// Display labels for the event types in backend/agent/event_types.yaml. Unknown keys fall back
// to a readable form of the key, so a new type in the YAML still shows up.
const LABELS: Record<string, string> = {
  missing_ppe: "Missing PPE",
  unsafe_proximity: "Unsafe proximity",
  fallen_object_or_spill: "Fallen object or spill",
};

export function eventLabel(key: string): string {
  return LABELS[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
