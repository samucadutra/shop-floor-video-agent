// Types that mirror the API JSON (PRD §8, backend/videos/serializers.py).

export type VideoStatus = "uploaded" | "processing" | "done" | "failed";
export type RunStatus = "queued" | "running" | "succeeded" | "failed";
export type Severity = "low" | "medium" | "high";
export type StepStatus = "ok" | "retried" | "error";

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface VideoListItem {
  id: string;
  original_name: string;
  status: VideoStatus;
  duration_s: number;
  event_count: number;
  created_at: string;
}

export interface Run {
  id: string;
  status: RunStatus;
  provider: string;
  model: string;
  summary: string;
  is_partial: boolean;
  stop_reason: string;
  error_message: string;
  iterations: number;
  frames_analyzed: number;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string; // decimal as a string
  duration_ms: number | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Video {
  id: string;
  original_name: string;
  status: VideoStatus;
  duration_s: number;
  width: number;
  height: number;
  fps: number;
  size_bytes: number;
  file_url: string;
  current_run: Run | null;
  active_run_id: string | null;
  error_message: string | null;
  created_at: string;
}

export interface Event {
  id: string;
  event_type: string;
  timestamp_s: number;
  start_s: number;
  end_s: number;
  severity: Severity;
  confidence: number;
  explanation: string;
  frame_ref: string;
}

export interface AnalyzeResponse {
  run_id: string;
  status: RunStatus;
}

export interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
  output_summary: string;
}

export interface AgentStep {
  id: number;
  index: number;
  node: "survey" | "plan" | "inspect" | "verify" | "report";
  iteration: number;
  input_summary: string;
  decision: string;
  tool_calls: ToolCall[];
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
  latency_ms: number;
  status: StepStatus;
  error_message: string;
  created_at: string;
}

export interface RunTrace {
  run_id: string;
  status: RunStatus;
  is_partial: boolean;
  stop_reason: string;
  steps: AgentStep[];
}

export interface Stats {
  events_by_type: { event_type: string; count: number }[];
  events_by_severity: { severity: Severity; count: number }[];
  events_per_video: { video_id: string; name: string; count: number }[];
  avg_processing_ms: number | null;
  total_tokens: number;
  total_estimated_cost_usd: string;
  runs_succeeded: number;
  runs_failed: number;
}
