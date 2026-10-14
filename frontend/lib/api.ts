import type {
  AnalyzeResponse,
  Event,
  Paginated,
  RunTrace,
  Stats,
  Video,
  VideoListItem,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The DRF message: {"detail": "..."} or the first field error ({"file": ["..."]}). */
function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const data = body as Record<string, unknown>;
    if (typeof data.detail === "string") return data.detail;
    for (const value of Object.values(data)) {
      if (Array.isArray(value) && typeof value[0] === "string") return value[0];
      if (typeof value === "string") return value;
    }
  }
  return `Request failed (HTTP ${status}).`;
}

function parse(text: string): unknown {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError("Cannot reach the API. Is the backend running?", 0);
  }
  const body = parse(await response.text());
  if (!response.ok) throw new ApiError(errorMessage(body, response.status), response.status);
  return body as T;
}

export function getVideos(page = 1): Promise<Paginated<VideoListItem>> {
  return request(`/api/videos/?page=${page}`);
}

export function getVideo(id: string): Promise<Video> {
  return request(`/api/videos/${id}/`);
}

export function getEvents(id: string): Promise<Event[]> {
  return request(`/api/videos/${id}/events/`);
}

export function getTrace(runId: string): Promise<RunTrace> {
  return request(`/api/runs/${runId}/trace/`);
}

export function getStats(): Promise<Stats> {
  return request("/api/stats/");
}

export function analyzeVideo(id: string): Promise<AnalyzeResponse> {
  return request(`/api/videos/${id}/analyze/`, { method: "POST" });
}

/** Upload with XMLHttpRequest, because fetch has no upload progress. `onProgress` gets 0–1. */
export function uploadVideo(file: File, onProgress: (fraction: number) => void): Promise<Video> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/videos/`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      const body = parse(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Video);
      else reject(new ApiError(errorMessage(body, xhr.status), xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Upload failed: cannot reach the API.", 0));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
