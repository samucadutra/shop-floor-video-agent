# Shop Floor Video Agent: Technical Specification

| Field   | Value                          |
| ------- | ------------------------------ |
| Status  | Draft v1                       |
| Date    | 2026-10-14                     |
| Inputs  | [prd.md](prd.md)               |
| Tasks   | [tasks.md](tasks.md)           |

The PRD says **what** to build. This spec says **how**. If they disagree, the PRD wins and this file is fixed. Section numbers here (S1, S2, …) are referenced from `tasks.md`.

---

## S1. Repository layout

```
shop-floor-video-agent/
├── backend/
│   ├── config/                  # Django project
│   │   ├── settings.py          # all settings read from env (django-environ)
│   │   ├── urls.py
│   │   ├── celery.py            # Celery app
│   │   ├── logging.py           # JSON formatter, context filter, redaction filter
│   │   └── wsgi.py
│   ├── core/                    # Django app: health, stats, media serving
│   │   ├── views.py             # HealthView, StatsView, serve_media (Range aware)
│   │   └── urls.py
│   ├── videos/                  # Django app: domain models and REST API
│   │   ├── models.py            # Video, AnalysisRun, Event, AgentStep
│   │   ├── serializers.py
│   │   ├── validators.py        # upload validation
│   │   ├── views.py
│   │   ├── services.py          # start_analysis, finish_run, fail_run, mark_stale_runs
│   │   ├── tasks.py             # Celery task analyze_video
│   │   ├── urls.py
│   │   └── migrations/
│   ├── agent/                   # plain Python package (no Django imports except repository.py)
│   │   ├── graph.py             # build_graph(deps) -> compiled LangGraph
│   │   ├── state.py             # AgentState, Budget
│   │   ├── nodes.py             # survey, plan, inspect, verify, report
│   │   ├── tools.py             # get_frames, analyze_frames, save_event
│   │   ├── guardrails.py        # AgentLimits, budget_exceeded()
│   │   ├── schemas.py           # Pydantic schemas for LLM output
│   │   ├── prompts.py           # prompt builders
│   │   ├── event_types.py       # loads event_types.yaml
│   │   ├── event_types.yaml
│   │   ├── repository.py        # the only DB access of the agent (save_event, record_step)
│   │   ├── runner.py            # run_agent(run_id): builds deps, invokes graph
│   │   └── providers/
│   │       ├── base.py          # Frame, LLMRequest, RawResponse, LLMResult, BaseProvider
│   │       ├── client.py        # LLMClient: throttle, retry, validation, cost
│   │       ├── factory.py       # build_provider(settings, video_info)
│   │       ├── gemini.py
│   │       ├── mock.py
│   │       ├── anthropic.py     # optional (Phase 5)
│   │       ├── openai.py        # optional (Phase 5)
│   │       └── mock_fixtures/   # one YAML per sample video + generic.yaml
│   ├── media_tools/
│   │   └── ffmpeg.py            # probe, extract_survey, extract_scenes, extract_window
│   ├── tests/                   # pytest + pytest-django
│   ├── conftest.py
│   ├── manage.py
│   ├── pyproject.toml           # deps, ruff and pytest config
│   └── Dockerfile
├── frontend/                    # Next.js App Router (S10)
├── k8s/                         # kind config + manifests (S12)
├── scripts/download_samples.sh
├── .github/workflows/ci.yml     # (S13)
├── docs/                        # prd.md, spec.md, tasks.md
├── docker-compose.yml           # (S11)
├── Makefile                     # (S15)
├── .env.example                 # (S14)
├── .gitignore                   # .env, media/, samples/, node_modules/, .next/, __pycache__/
├── CLAUDE.md
└── README.md
```

**Design rule:** the agent receives its dependencies (LLM client, frame extractor, repository, limits) through one `AgentDeps` dataclass. Tests build the graph with fakes and need no Celery.

## S2. Backend stack and settings

| Item               | Choice                                                                 |
| ------------------ | ---------------------------------------------------------------------- |
| Python             | 3.12 (`python:3.12-slim` image + `apt-get install ffmpeg`)             |
| Django             | 5.2 LTS                                                                |
| Main libraries     | `djangorestframework`, `django-environ`, `django-cors-headers`, `psycopg[binary]`, `celery[redis]`, `langgraph`, `pydantic>=2`, `pyyaml`, `tenacity`, `google-genai`, `python-json-logger`, `gunicorn` |
| Optional extras    | `anthropic`, `openai` (`pip install .[anthropic,openai]`)              |
| Dev                | `pytest`, `pytest-django`, `ruff`                                      |
| Lint config        | ruff: `line-length = 100`, rules `E,F,I,B,UP,SIM`; `ruff format`       |

Settings (`config/settings.py`) read every value from env (S14). Notable settings:

- `INSTALLED_APPS`: `corsheaders`, `rest_framework`, `core`, `videos`.
- `REST_FRAMEWORK`: `DEFAULT_PAGINATION_CLASS = PageNumberPagination`, `PAGE_SIZE = 20`; JSON renderer only, plus the browsable API when `DJANGO_DEBUG=true`.
- `MEDIA_ROOT = env("MEDIA_ROOT")`, `MEDIA_URL = "/media/"`.
- `CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")`.
- `CELERY_BROKER_URL = env("REDIS_URL")`, `CELERY_TASK_IGNORE_RESULT = True` (state lives in Postgres), `CELERY_TASK_ACKS_LATE = True`, `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`.
- `AGENT = AgentLimits(...)` built once from env and passed to the agent.

## S3. Data model

All primary keys are UUID (`default=uuid.uuid4`) except `AgentStep` (`BigAutoField`). Timestamps use `auto_now_add` / `auto_now`.

### Video (`videos.Video`)

| Field          | Django field                                          | Notes                                  |
| -------------- | ----------------------------------------------------- | -------------------------------------- |
| id             | `UUIDField(primary_key=True)`                          |                                        |
| original_name  | `CharField(max_length=255)`                            | Shown in the UI only                   |
| file           | `FileField(upload_to="videos/")`                       | Saved as `videos/<uuid>.<ext>`         |
| size_bytes     | `BigIntegerField`                                      |                                        |
| sha256         | `CharField(max_length=64, db_index=True)`              | Mock fixture matching                  |
| duration_s     | `FloatField`                                           | From ffprobe                           |
| width, height  | `PositiveIntegerField`                                 |                                        |
| fps            | `FloatField`                                           |                                        |
| status         | `CharField(choices=VideoStatus)`                       | `uploaded`, `processing`, `done`, `failed` |
| current_run    | `OneToOneField(AnalysisRun, null=True, on_delete=SET_NULL, related_name="+")` | Latest successful run |
| created_at, updated_at | `DateTimeField`                                |                                        |

Ordering: `-created_at`.

### AnalysisRun (`videos.AnalysisRun`)

| Field                       | Django field                                   | Notes                                     |
| --------------------------- | ---------------------------------------------- | ----------------------------------------- |
| id                          | `UUIDField(primary_key=True)`                   |                                           |
| video                       | `ForeignKey(Video, on_delete=CASCADE, related_name="runs")` |                              |
| status                      | `CharField(choices=RunStatus)`                  | `queued`, `running`, `succeeded`, `failed` |
| provider, model             | `CharField(max_length=50)`, `CharField(max_length=100)` | Copied from settings at start    |
| summary                     | `TextField(blank=True)`                         |                                           |
| is_partial                  | `BooleanField(default=False)`                   |                                           |
| stop_reason                 | `CharField(choices=StopReason, blank=True)`     | `completed`, `max_iterations`, `max_frames`, `max_tokens`, `max_cost`, `max_llm_calls`, `timeout`, `error` |
| error_message               | `TextField(blank=True)`                         | Safe, user facing                         |
| iterations                  | `PositiveIntegerField(default=0)`               |                                           |
| frames_analyzed             | `PositiveIntegerField(default=0)`               |                                           |
| llm_calls                   | `PositiveIntegerField(default=0)`               |                                           |
| input_tokens, output_tokens | `PositiveIntegerField(default=0)`               |                                           |
| estimated_cost_usd          | `DecimalField(max_digits=10, decimal_places=4, default=0)` |                                |
| started_at, finished_at     | `DateTimeField(null=True)`                      |                                           |
| duration_ms                 | `PositiveIntegerField(null=True)`               |                                           |
| celery_task_id              | `CharField(max_length=255, blank=True)`         |                                           |
| created_at                  | `DateTimeField(auto_now_add=True)`              |                                           |

Constraint: `UniqueConstraint(fields=["video"], condition=Q(status__in=["queued","running"]), name="one_active_run_per_video")`. This is the database-level guard behind the `409` response.

### Event (`videos.Event`)

| Field          | Django field                                                   | Notes                     |
| -------------- | -------------------------------------------------------------- | ------------------------- |
| id             | `UUIDField(primary_key=True)`                                   |                           |
| run            | `ForeignKey(AnalysisRun, on_delete=CASCADE, related_name="events")` |                       |
| video          | `ForeignKey(Video, on_delete=CASCADE, related_name="events")`  | Denormalized              |
| event_type     | `CharField(max_length=50, db_index=True)`                       | A key from `event_types.yaml` |
| timestamp_s    | `FloatField`                                                    | Used for seeking          |
| start_s, end_s | `FloatField`                                                    |                           |
| severity       | `CharField(choices=Severity)`                                   | `low`, `medium`, `high`   |
| confidence     | `FloatField`                                                    | 0.0–1.0 (`CheckConstraint`) |
| explanation    | `TextField`                                                     |                           |
| frame_ref      | `CharField(max_length=255)`                                     | Relative frame path       |
| created_at     | `DateTimeField(auto_now_add=True)`                              |                           |

Ordering: `timestamp_s`.

### AgentStep (`videos.AgentStep`)

| Field                       | Django field                                                     | Notes                         |
| --------------------------- | ---------------------------------------------------------------- | ----------------------------- |
| id                          | `BigAutoField`                                                    |                               |
| run                         | `ForeignKey(AnalysisRun, on_delete=CASCADE, related_name="steps")` |                             |
| index                       | `PositiveIntegerField`                                            | `UniqueConstraint(run, index)` |
| node                        | `CharField(choices=Node)`                                         | `survey`, `plan`, `inspect`, `verify`, `report` |
| iteration                   | `PositiveIntegerField`                                            |                               |
| input_summary               | `TextField`                                                       |                               |
| decision                    | `TextField`                                                       |                               |
| tool_calls                  | `JSONField(default=list)`                                         | `[{tool, args, output_summary}]` |
| input_tokens, output_tokens | `PositiveIntegerField(default=0)`                                 |                               |
| estimated_cost_usd          | `DecimalField(max_digits=10, decimal_places=4, default=0)`        |                               |
| latency_ms                  | `PositiveIntegerField(default=0)`                                 |                               |
| status                      | `CharField(choices=StepStatus)`                                   | `ok`, `retried`, `error`      |
| error_message               | `TextField(blank=True)`                                           |                               |
| created_at                  | `DateTimeField(auto_now_add=True)`                                |                               |

Ordering: `index`.

## S4. REST API

All routes are under `/api/`. Errors use DRF's default format.

| Method | Path                         | View                    | Serializer (response)          | Codes            |
| ------ | ---------------------------- | ----------------------- | ------------------------------ | ---------------- |
| POST   | `/api/videos/`               | `VideoViewSet.create`   | in: `VideoUploadSerializer`, out: `VideoDetailSerializer` | 201, 400 |
| GET    | `/api/videos/`               | `VideoViewSet.list`     | `VideoListSerializer` (paginated) | 200           |
| GET    | `/api/videos/{id}/`          | `VideoViewSet.retrieve` | `VideoDetailSerializer`        | 200, 404         |
| POST   | `/api/videos/{id}/analyze/`  | `VideoViewSet.analyze` (`@action`) | `{"run_id", "status"}`  | 202, 404, 409    |
| GET    | `/api/videos/{id}/events/`   | `VideoViewSet.events` (`@action`)  | `EventSerializer(many=True)` | 200, 404   |
| GET    | `/api/runs/{id}/trace/`      | `RunTraceView`          | `RunTraceSerializer`           | 200, 404         |
| GET    | `/api/stats/`                | `StatsView`             | plain dict (S4.3)              | 200              |
| GET    | `/api/health/`               | `HealthView`            | plain dict                     | 200, 503         |
| GET    | `/media/<path>`              | `core.views.serve_media` | file bytes                    | 200, 206, 404, 416 |

`VideoViewSet` is a `GenericViewSet` with the create, list and retrieve mixins only (no update or delete). The request and response shapes are the ones in PRD §8.

### S4.1 Serializers

| Serializer              | Fields                                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------------------ |
| `VideoUploadSerializer` | `file` (write only); `validate_file` runs `validators.validate_upload` (S4.2)                    |
| `VideoListSerializer`   | `id, original_name, status, duration_s, event_count, created_at` (`event_count` from `annotate(Count("current_run__events"))`) |
| `RunSummarySerializer`  | `id, status, provider, model, summary, is_partial, stop_reason, error_message, iterations, frames_analyzed, llm_calls, input_tokens, output_tokens, estimated_cost_usd, duration_ms, started_at, finished_at` |
| `VideoDetailSerializer` | `id, original_name, status, duration_s, width, height, fps, size_bytes, file_url, current_run (RunSummarySerializer), active_run_id, error_message, created_at` |
| `EventSerializer`       | `id, event_type, timestamp_s, start_s, end_s, severity, confidence, explanation, frame_ref`     |
| `AgentStepSerializer`   | all `AgentStep` fields except `run`                                                              |
| `RunTraceSerializer`    | `run_id, status, is_partial, stop_reason, steps (AgentStepSerializer(many=True))`               |

- `file_url` is `request.build_absolute_uri(video.file.url)`.
- `active_run_id` is the id of the `queued`/`running` run, or `null`.
- `error_message` is from the latest run if it `failed`, else `null`.
- `/events/` returns events of `current_run` only (an empty list if there is none).

### S4.2 Upload validation (`videos/validators.py`)

Checks run in this order and stop at the first failure (`400` with a field error on `file`):

1. Extension in `{.mp4, .mov, .webm}` (case insensitive).
2. Declared content type in `{video/mp4, video/quicktime, video/webm}`, or `application/octet-stream`. curl and some clients send that generic type when they don't know the format; step 4 (ffprobe) is the real format check. Any other type, such as `text/plain`, is rejected.
3. Size ≤ `MAX_UPLOAD_MB` MiB.
4. The file is written to a temp path and probed with `ffprobe` (S9). It must have at least one video stream, and `duration ≤ MAX_VIDEO_SECONDS`.
5. SHA-256 is computed while streaming to disk.

On success the file is saved as `videos/<uuid>.<ext>` (never the user's name). The probe metadata fills the model.

### S4.3 Stats (`GET /api/stats/`)

Computed with ORM aggregates:

- `events_by_type`, `events_by_severity`, `events_per_video`: over events of each video's `current_run`.
- `avg_processing_ms`: mean `duration_ms` of `succeeded` runs.
- `total_tokens`, `total_estimated_cost_usd`, `runs_succeeded`, `runs_failed`: over all stored runs. Older succeeded runs are deleted on re-analysis, so totals cover the runs that are kept.

### S4.4 Health (`GET /api/health/`)

The view runs `SELECT 1` through `django.db.connection`, and `PING` on Redis with `redis.Redis.from_url(REDIS_URL, socket_timeout=2)`. Any failure gives `503` with that component set to `"error"`.

### S4.5 Media serving with Range

`serve_media(request, path)` resolves the path safely inside `MEDIA_ROOT` (rejects `..`), then:

- With no `Range` header, it returns `FileResponse` (200) with `Accept-Ranges: bytes`.
- With `Range: bytes=start-end`, it returns 206 with `Content-Range` and only those bytes.
- An invalid range gives 416.

It is used in Compose and in k8s. Video seeking in the browser depends on it.

## S5. Analysis flow (Celery)

### S5.1 Start (`videos/services.py: start_analysis(video)`)

Everything happens in `transaction.atomic()`:

1. `select_for_update` the video. Mark stale runs as failed (S5.3).
2. If an active run exists, raise `RunAlreadyActive`, which the view returns as `409`.
3. Create `AnalysisRun(status=queued, provider, model)`. Set `video.status = processing`.
4. `transaction.on_commit(lambda: analyze_video.delay(str(run.id)))`.

### S5.2 Task (`videos/tasks.py`)

```python
@shared_task(bind=True, acks_late=True,
             soft_time_limit=settings.AGENT_RUN_TIMEOUT_SECONDS,
             time_limit=settings.AGENT_RUN_TIMEOUT_SECONDS + 30)
def analyze_video(self, run_id: str) -> None: ...
```

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Django API
    participant DB as PostgreSQL
    participant Q as Redis
    participant W as Celery worker
    participant AG as LangGraph agent
    FE->>API: POST /api/videos/{id}/analyze/
    API->>DB: create run (queued), video=processing
    API->>Q: analyze_video(run_id) (on commit)
    API-->>FE: 202 {run_id}
    W->>Q: take task
    W->>DB: run=running, started_at
    W->>AG: run_agent(run_id)
    AG->>DB: AgentStep rows, Event rows (per step)
    alt success
        W->>DB: one transaction: run=succeeded + metrics, video.current_run=run, delete older runs, video=done
    else error or timeout
        W->>DB: run=failed (+stop_reason, error_message), video=failed
    end
    loop every 3 s
        FE->>API: GET /api/videos/{id}/
    end
```

- `finish_run(run, result)` runs in one transaction. It saves the metrics, `summary`, `is_partial` and `stop_reason`, sets `video.current_run = run` and `video.status = done`, then deletes the video's other runs (`CASCADE` removes their events and steps). This makes re-analysis idempotent, and a failed re-run never removes the last good result.
- `fail_run(run, reason, message)` sets the run to `failed` and the video to `failed`. `current_run` is not touched, so the previous events stay visible.
- `SoftTimeLimitExceeded` calls `fail_run(stop_reason="timeout")`. Any other exception calls `fail_run(stop_reason="error", message=<safe text>)` and is logged with the traceback.
- The worker runs with concurrency 1 (`-c 1`). That keeps the in-process LLM throttle correct, and it is enough for a demo.

### S5.3 Stale runs

`mark_stale_runs(video)`: a `queued` or `running` run with `created_at` older than `AGENT_RUN_TIMEOUT_SECONDS + 60` s is set to `failed` with `stop_reason=timeout` and the message "Worker stopped before finishing". It is called from `start_analysis` and from `VideoViewSet.retrieve`.

## S6. Agent (LangGraph)

### S6.1 Event types

`agent/event_types.yaml`:

```yaml
- key: missing_ppe
  label: Missing PPE
  description: A person without a hard hat or without a high-visibility safety vest.
  default_severity: medium
- key: unsafe_proximity
  label: Unsafe proximity
  description: >-
    A person on foot within about 2 meters of machinery or a forklift that is moving at that
    moment. The machine's own operator and parked or stationary machines do not count.
  default_severity: high
- key: fallen_object_or_spill
  label: Fallen object or spill
  description: >-
    An object dropped on the floor, or a liquid spill or wet floor in a work area. Neatly
    stacked or stored materials do not count.
  default_severity: medium
```

`event_types.py` loads it into `list[EventType]` (a Pydantic model) and checks that keys are unique and severities valid. The file path can be overridden with `EVENT_TYPES_FILE`.

### S6.2 State

```python
class Budget(TypedDict):
    frames: int; llm_calls: int; input_tokens: int; output_tokens: int; cost_usd: float

class CandidateState(TypedDict):
    id: str                      # "c1", "c2", ...
    event_type: str
    time_s: float
    reason: str
    status: Literal["open", "confirmed", "dropped"]
    looks: int                   # how many times it was inspected

class Window(TypedDict):
    id: str; start_s: float; end_s: float; candidate_ids: list[str]; question: str

class AgentState(TypedDict):
    run_id: str
    video_path: str
    duration_s: float
    event_types: list[dict]
    survey_frames: list[dict]          # Frame as dict (timestamp_s, path, source)
    scene_notes: list[str]
    candidates: list[CandidateState]
    windows: list[Window]              # windows chosen in the current iteration
    observations: list[dict]           # Observation dicts from the current iteration
    confirmed_event_ids: list[str]
    iteration: int
    budget: Budget
    is_partial: bool
    stop_reason: str | None
    summary: str
```

### S6.3 Graph

```mermaid
stateDiagram-v2
    [*] --> survey
    survey --> plan
    plan --> inspect: windows selected
    plan --> report: no windows (nothing open, or no budget)
    inspect --> verify
    verify --> plan: open candidates, iteration < max, budget left
    verify --> report: otherwise
    report --> [*]
```

```python
g = StateGraph(AgentState)
g.add_node("survey", survey); g.add_node("plan", plan); g.add_node("inspect", inspect)
g.add_node("verify", verify); g.add_node("report", report)
g.add_edge(START, "survey"); g.add_edge("survey", "plan")
g.add_conditional_edges("plan", after_plan, {"inspect": "inspect", "report": "report"})
g.add_edge("inspect", "verify")
g.add_conditional_edges("verify", after_verify, {"plan": "plan", "report": "report"})
g.add_edge("report", END)
graph = g.compile()   # invoked with config={"recursion_limit": 50}
```

### S6.4 Nodes

Each node writes exactly one `AgentStep` through `repository.record_step(...)`. Exception: `inspect` writes one step per window. Each LLM call goes through `tools.analyze_frames`, which updates `budget`.

| Node      | LLM call | Behavior |
| --------- | -------- | -------- |
| `survey`  | yes, once per batch of `FRAMES_PER_CALL` frames, with images | `get_frames` in survey mode (S9: interval frames + scene frames, merged, frames closer than 1 s dropped). Survey may use at most 50% of `AGENT_MAX_FRAMES`; if it needs more, the interval is widened. Each batch returns a `SurveyResult`. Candidates are sorted by time and get ids `c1…cN`. A sighting of the same type within `WINDOW_PADDING_S` of the latest sighting already merged into a candidate joins that candidate, so a continuous event stays one candidate. Unknown `event_type` values are dropped and noted in the step. A failure after the retry **fails the run**. |
| `plan`    | **no** (deterministic) | Takes `open` candidates. Builds windows `[t − pad, t + pad]` with `pad = WINDOW_PADDING_S × (1 + looks)`, clamped to `[0, duration]`, and merges overlapping windows. Ranks them by the highest `default_severity` of their candidates, then by the number of candidates. Selects windows while `frames_used + (end − start) × INSPECT_FPS ≤ AGENT_MAX_FRAMES`. Builds a focused question per window from the event type descriptions and candidate reasons. Increments `iteration`. The decision text lists chosen and skipped windows with reasons. |
| `inspect` | yes, one per window, with images | `get_frames(start, end, INSPECT_FPS)`, then `analyze_frames(frames, question)` returns an `InspectResult`. A failure after the retry drops the window's candidates (`status=dropped`, reason "analysis failed"), records the step as `error`, and the run continues. Increments `looks` on each candidate. |
| `verify`  | yes, once per iteration, **text only** (observations, no images) | Returns a `VerifyResult`. `confirm` with `confidence ≥ CONFIDENCE_THRESHOLD` calls `save_event` and sets the candidate `confirmed`. `confirm` below the threshold, or `drop`, sets it `dropped` with a reason. `uncertain` keeps it `open`. A failure after the retry drops this iteration's candidates and the run continues. |
| `report`  | yes, once, text only | Gets the confirmed events, scene notes and dropped candidates. Returns a `ReportResult`. Sets `stop_reason` (`completed` if it is not already set). A failure after the retry **fails the run**. |

### S6.5 Edges and stop conditions (`agent/guardrails.py`)

```python
@dataclass(frozen=True)
class AgentLimits:
    max_iterations: int; max_frames: int; max_tokens: int; max_cost_usd: float
    max_llm_calls: int; report_reserve_tokens: int

def budget_exceeded(state: AgentState, limits: AgentLimits) -> str | None:
    """Return the stop reason, or None. The report reserve is excluded."""
    b = state["budget"]
    if b["frames"] >= limits.max_frames: return "max_frames"
    if b["input_tokens"] + b["output_tokens"] >= limits.max_tokens - limits.report_reserve_tokens: return "max_tokens"
    if limits.max_cost_usd > 0 and b["cost_usd"] >= limits.max_cost_usd: return "max_cost"
    if b["llm_calls"] >= limits.max_llm_calls - 1: return "max_llm_calls"   # keep 1 call for report
    return None
```

- `after_plan`: return `"inspect"` if windows were selected. Otherwise return `"report"`; if open candidates remain, set `is_partial=True` and `stop_reason="max_frames"` (they could not fit in the budget).
- `after_verify`: if `budget_exceeded(...)` returns a reason, set `is_partial=True` and that `stop_reason`, and return `"report"`. If open candidates remain and `iteration < max_iterations`, return `"plan"`. If open candidates remain at the max, set `is_partial=True` and `stop_reason="max_iterations"`, mark the remaining ones `dropped` (reason "unresolved"), and return `"report"`. Otherwise return `"report"`.
- `analyze_frames` also checks the budget **before** each call. If the call would break a limit, it raises `BudgetExhausted` instead of calling. Only the `report` stage may use the reserved tokens and the last LLM call. The node catches this, records it, and the next edge sends the run to `report`.
- Frame limit: `get_frames` raises `BudgetExhausted` if extracting the frames would pass `max_frames`.
- Run timeout: Celery `soft_time_limit` (S5.2).

### S6.6 Tools (`agent/tools.py`)

| Tool | Signature | Behavior |
| ---- | --------- | -------- |
| `get_frames` | `(start: float, end: float, fps: float, *, mode: Literal["survey","window"]="window") -> list[Frame]` | Calls `media_tools.ffmpeg` (S9) and writes to `MEDIA_ROOT/frames/<run_id>/`. Results are cached by `(mode, start, end, fps)`. Counts frames against the budget. |
| `analyze_frames` | `(frames: list[Frame], question: str, *, stage: Stage, schema: type[T], payload: dict) -> T` | Builds an `LLMRequest`, calls `LLMClient.analyze` (S7), adds tokens, cost and the call to the budget, and returns the parsed model. |
| `save_event` | `(event_type, timestamp_s, start_s, end_s, severity, confidence, explanation, frame_ref) -> str` | Checks that `event_type` is configured, `0 ≤ confidence ≤ 1` and `0 ≤ timestamp_s ≤ duration`. Creates an `Event` through the repository and returns its id. |

The tools are plain functions bound to `AgentDeps` (no LangChain tool-calling: the graph decides which tool runs, which is easier to test and to trace). Each call is added to the current step's `tool_calls` as `{tool, args, output_summary}`. Image bytes are never stored; only frame paths are.

### S6.7 Trace recording

`repository.record_step(run_id, node, iteration, input_summary, decision, tool_calls, usage, latency_ms, status, error_message)` assigns the next `index` and saves the step at once, so the trace grows while the run is in progress. The API reads it at `/api/runs/{id}/trace/`.

### S6.8 Prompts (`agent/prompts.py`)

One builder per stage. Each prompt contains:

1. The role: "You are a safety inspector reviewing factory floor video frames".
2. The event type list (key + description).
3. The frame list with timestamps (images are attached in the same order).
4. The task for the stage.
5. "Reply with a single JSON object (not a list), matching this JSON Schema:" followed by `Schema.model_json_schema()`. Some models answer with a bare list when there is only one item.

The verify and report prompts include candidates and observations as compact JSON. Prompts never include file system paths or settings.

## S7. LLM providers

### S7.1 Interface (`agent/providers/base.py`)

```python
Stage = Literal["survey", "inspect", "verify", "report"]

@dataclass(frozen=True)
class Frame:
    timestamp_s: float
    path: Path
    source: Literal["survey", "scene", "window"]

@dataclass(frozen=True)
class LLMRequest:
    stage: Stage
    prompt: str
    schema: type[BaseModel]
    frames: tuple[Frame, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)   # structured data the prompt was built from

@dataclass(frozen=True)
class RawResponse:
    text: str
    input_tokens: int
    output_tokens: int

@dataclass(frozen=True)
class LLMResult:
    parsed: BaseModel
    raw_text: str
    input_tokens: int       # summed over attempts
    output_tokens: int
    latency_ms: int
    attempts: int           # 1 or 2 (validation retry)
    cost_usd: float

class RetryableLLMError(Exception): ...      # 429, 5xx, timeouts
class QuotaExhaustedError(Exception): ...    # daily free tier quota: not retried
class LLMOutputError(Exception): ...         # invalid output after the retry

class BaseProvider(ABC):
    name: str
    model: str
    @abstractmethod
    def complete(self, request: LLMRequest, extra_instruction: str | None = None) -> RawResponse: ...
```

Each provider only maps a request to its SDK call and maps SDK errors to `RetryableLLMError` and `QuotaExhaustedError`. Everything else lives in `LLMClient`.

### S7.2 `LLMClient` (`agent/providers/client.py`)

`LLMClient(provider, settings).analyze(request) -> LLMResult`:

1. **Throttle:** a sliding window of call times allows at most `LLM_MAX_REQUESTS_PER_MINUTE` calls in 60 s, and sleeps until a slot is free.
2. **Call with backoff:** `tenacity` retries on `RetryableLLMError`, up to `LLM_MAX_RETRIES` times (default 3). The wait is exponential with jitter, `initial=2, max=30`. Each call has a timeout of `LLM_TIMEOUT_SECONDS`, passed to the SDK.
3. **Parse:** take the first JSON object in `text` (strip code fences), then `request.schema.model_validate_json(...)`.
4. **On a parse or validation error:** call `complete` once more, with `extra_instruction` set to the validation error (truncated to 1,000 characters) plus "Return valid JSON only". If that also fails, raise `LLMOutputError`.
5. **Cost:** `(in × LLM_INPUT_PRICE_PER_MTOK + out × LLM_OUTPUT_PRICE_PER_MTOK) / 1e6`.

Logs record stage, provider, model, attempts, tokens and latency. They never record the prompt text, image data or API keys.

### S7.3 Factory (`agent/providers/factory.py`)

`build_provider(settings, video_info: VideoInfo) -> BaseProvider`. `VideoInfo` has `sha256`, `filename` and `duration_s`; only the mock uses it.

| `LLM_PROVIDER` | Class | Required env | SDK call |
| -------------- | ----- | ------------ | -------- |
| `gemini` (default) | `GeminiProvider` | `GEMINI_API_KEY`, `GEMINI_MODEL` | `google.genai.Client(api_key=...).models.generate_content(model=GEMINI_MODEL, contents=[prompt, *image_parts], config=GenerateContentConfig(response_mime_type="application/json", temperature=0.2))`. Images use `types.Part.from_bytes(data, mime_type="image/jpeg")`. Usage comes from `response.usage_metadata.prompt_token_count` / `candidates_token_count`. HTTP 429 with a per-day quota message raises `QuotaExhaustedError`; other 429 and 5xx errors raise `RetryableLLMError`. |
| `mock` | `MockProvider` | none | S7.4 |
| `anthropic` (optional) | `AnthropicProvider` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | `anthropic.Anthropic().messages.create(model=..., max_tokens=2000, messages=[{"role":"user","content":[*image_blocks(base64 jpeg), {"type":"text","text":prompt}]}])`. Usage from `usage.input_tokens` / `output_tokens`. |
| `openai` (optional) | `OpenAIProvider` | `OPENAI_API_KEY`, `OPENAI_MODEL` | `openai.OpenAI().chat.completions.create(model=..., response_format={"type":"json_object"}, messages=[{"role":"user","content":[{"type":"text","text":prompt}, *image_url_parts(data URL)]}])`. Usage from `usage.prompt_tokens` / `completion_tokens`. |

Missing required env for the selected provider raises `ImproperlyConfigured` at worker start (fail fast), with a message that names the variable, not its value. Model names come only from env.

### S7.4 Mock provider (`agent/providers/mock.py`)

- **Fixture lookup:** match `video_info.sha256` against `mock_fixtures/*.yaml`, then `video_info.filename`. If neither matches, use `generic.yaml`, whose times are fractions of the duration (0.2, 0.5, 0.8).
- **Responses by `request.stage`**, always as JSON text that goes through the same validation path as real providers:
  - `survey`: fixture events and decoys whose time falls in `[min(frame ts) − 1, max(frame ts) + 1]`, as `Candidate`s.
  - `inspect`: an `Observation` for each candidate id in `payload["candidates"]`. `seen=true` and details from the fixture for real events; for decoys, `seen=false` with the decoy's `drop_reason`.
  - `verify`: `confirm` with the fixture's severity, confidence and explanation for real events; `drop` with `drop_reason` for decoys.
  - `report`: a summary built from the confirmed events and the fixture's `scene_notes`.
- **Tokens:** `input_tokens = 300 + 260 × len(frames) + len(prompt) // 4`, `output_tokens = len(text) // 4`.
- **Delay:** `time.sleep(MOCK_LATENCY_MS / 1000)` per call.
- **Test hooks** (fixture keys, used only in tests): `invalid_json_once: [stage]` returns broken JSON on the first call of that stage; `error_on: [stage]` always returns broken JSON.

Fixture schema (validated with Pydantic `MockFixture`):

```yaml
sha256: e20b2a53363817e70a236b7139b48a6c85bd14ba822f8f741ab64500e2e55a75
filename: 16106604.mp4
scene_notes: Outdoor lumber yard with stacked pallets, a yard forklift and two workers.
events:
  - event_type: missing_ppe
    time_s: 1.5
    start_s: 0.0
    end_s: 4.0
    severity: medium
    confidence: 0.88
    explanation: A worker in a hi-vis vest stands in the yard without a hard hat.
  - event_type: unsafe_proximity
    time_s: 9.0
    start_s: 6.0
    end_s: 21.0
    severity: high
    confidence: 0.82
    explanation: A worker stands about one meter from the forklift while it moves.
decoys:
  - event_type: missing_ppe
    time_s: 15.0
    reason: Worker near the loader, head partly hidden.
    drop_reason: The worker wears a white hard hat and an orange hi-vis jacket.
```

Fixtures for the 4 Appendix A clips are written in Phase 4. Their times are checked frame by frame.

## S8. Pydantic schemas (`agent/schemas.py`)

```python
Severity = Literal["low", "medium", "high"]

class Candidate(BaseModel):
    event_type: str
    time_s: float = Field(ge=0)
    reason: str = Field(min_length=1, max_length=300)

class SurveyResult(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list, max_length=20)
    scene_notes: str = Field(default="", max_length=500)

class Observation(BaseModel):
    candidate_id: str
    seen: bool
    time_s: float = Field(ge=0)
    details: str = Field(max_length=500)

class InspectResult(BaseModel):
    observations: list[Observation]

class VerifyDecision(BaseModel):
    candidate_id: str
    decision: Literal["confirm", "drop", "uncertain"]
    event_type: str
    timestamp_s: float = Field(ge=0)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(max_length=500)
    drop_reason: str | None = None

    @model_validator(mode="after")
    def check_window(self) -> Self:  # start_s <= timestamp_s <= end_s
        ...

class VerifyResult(BaseModel):
    decisions: list[VerifyDecision]

class ReportResult(BaseModel):
    summary: str = Field(min_length=1, max_length=1500)
```

Checks that need run context (known event type, known candidate id, time ≤ duration) are done in the node after parsing. Items that fail them are dropped and noted in the step's decision; they never fail the run.

## S9. ffmpeg (`media_tools/ffmpeg.py`)

All calls use `subprocess.run([...], check=True, capture_output=True, timeout=120)` with an argument list and never `shell=True`. `SCALE` keeps the long side ≤ `FRAME_MAX_SIDE` (default 768) and never upscales:

```
SCALE = "scale='if(gt(iw,ih),min(iw,{M}),-2)':'if(gt(iw,ih),-2,min(ih,{M}))'"
```

| Function | Command | Output |
| -------- | ------- | ------ |
| `probe(path) -> VideoMeta` | `ffprobe -v error -print_format json -show_format -show_streams IN` | `duration_s` (format.duration), `width`, `height`, `fps` (from `avg_frame_rate`), `has_video`. Raises `InvalidVideo` on non-zero exit or no video stream. |
| `extract_survey(IN, OUT, interval_s)` | `ffmpeg -hide_banner -loglevel error -i IN -vf "fps=1/{interval_s},{SCALE}" -q:v 4 OUT/survey_%04d.jpg` | Frame *n* (1-based) has `timestamp_s = (n − 1) × interval_s`. |
| `extract_scenes(IN, OUT, threshold)` | `ffmpeg -hide_banner -i IN -vf "select='gt(scene,{threshold})',showinfo,{SCALE}" -fps_mode vfr -q:v 4 OUT/scene_%04d.jpg` | Timestamps are parsed from stderr lines matching `pts_time:([0-9.]+)` from `showinfo`, in order. |
| `extract_window(IN, OUT, start, end, fps)` | `ffmpeg -hide_banner -loglevel error -ss {start} -to {end} -i IN -vf "fps={fps},{SCALE}" -q:v 4 OUT/win_{start:07.2f}_%04d.jpg` | Frame *n* has `timestamp_s = start + (n − 1) / fps`. |

Survey mode in `get_frames` = `extract_survey(SURVEY_INTERVAL_S)` + `extract_scenes(SCENE_THRESHOLD)`, merged by time. A scene frame closer than 1 s to a survey frame is dropped.

Tests generate a clip at test time:
`ffmpeg -f lavfi -i testsrc=duration=10:size=640x360:rate=25 -pix_fmt yuv420p tmp/test.mp4`
To get a known scene change, two `testsrc`/`color` segments are joined with `concat`.

## S10. Frontend

| Item     | Choice                                                                                            |
| -------- | ------------------------------------------------------------------------------------------------- |
| Runtime  | Node 22 LTS                                                                                       |
| Stack    | Next.js (App Router, current stable, pinned in `package.json`), React, TypeScript `strict: true`, Tailwind CSS, Recharts, ESLint (`next/core-web-vitals`, `next/typescript`) |
| Build    | `output: "standalone"`; `NEXT_PUBLIC_API_URL` is a build arg (the browser calls the API directly) |
| Scripts  | `dev`, `build`, `start`, `lint`, `typecheck` (`tsc --noEmit`)                                     |

### S10.1 Routes (`frontend/app/`)

| Route           | File                         | Content |
| --------------- | ---------------------------- | ------- |
| `/`             | `page.tsx`                   | `redirect("/videos")` |
| `/upload`       | `upload/page.tsx`            | `UploadNotice`, `Dropzone`, progress bar, "Analyze" button, redirect to `/videos/[id]` |
| `/videos`       | `videos/page.tsx`            | Table on desktop, cards on mobile, `StatusBadge`, event count; polls while any video is `processing` |
| `/videos/[id]`  | `videos/[id]/page.tsx`       | `VideoPlayer`, `EventTimeline`, `EventCard` list, `SummaryCard`, `RunMetrics`, `TracePanel`, Analyze/Re-analyze button, error banner; polls while `processing` |
| `/dashboard`    | `dashboard/page.tsx`         | 3 × `BarChartCard` + `StatTile` row |
| layout          | `layout.tsx`                 | `Nav` (Videos, Upload, Dashboard), page container |

The pages are client components (`"use client"`) that use `fetch`, with no extra state library.

### S10.2 Components (`frontend/components/`)

| Component      | Responsibility |
| -------------- | -------------- |
| `Nav`          | Top bar with links; collapses on small screens |
| `UploadNotice` | "Upload only public stock videos" notice (PRD §9 Data) |
| `Dropzone`     | Drag and drop and file picker; checks type (`.mp4/.mov/.webm`) and size (`NEXT_PUBLIC_MAX_UPLOAD_MB`) before upload |
| `StatusBadge`  | Colored pill for `uploaded/processing/done/failed` |
| `VideoPlayer`  | `<video controls>` with `forwardRef` exposing `seekTo(seconds)` (sets `currentTime`, then `play()`) |
| `EventTimeline`| A bar as wide as the video; a marker per event at `timestamp_s / duration_s`, colored by severity; click calls `seekTo` |
| `EventCard`    | Type label, `mm:ss` timestamp, `SeverityBadge`, confidence %, explanation; click calls `seekTo` |
| `SeverityBadge`| `low/medium/high` colors |
| `SummaryCard`  | Run summary; "Partial result: <stop reason>" banner when `is_partial` |
| `RunMetrics`   | Duration, frames, LLM calls, tokens, cost, provider/model |
| `TracePanel`   | Fetches `/api/runs/{id}/trace/`; a list of `TraceStep` |
| `TraceStep`    | Collapsible: node, iteration, decision (always visible), input summary, tool calls, tokens, latency, cost, status/error |
| `BarChartCard` | Recharts `BarChart` in a card with a title and an empty state |
| `StatTile`     | Label + big number |
| `EmptyState`, `ErrorState`, `Spinner` | Shared states |

### S10.3 Library code

- `lib/types.ts`: TypeScript types that mirror PRD §8 JSON (`Video`, `VideoListItem`, `Run`, `Event`, `AgentStep`, `RunTrace`, `Stats`, `Paginated<T>`).
- `lib/api.ts`: `getVideos()`, `getVideo(id)`, `uploadVideo(file, onProgress)` (uses `XMLHttpRequest` for upload progress), `analyzeVideo(id)`, `getEvents(id)`, `getTrace(runId)`, `getStats()`. A non-2xx response throws an `ApiError` with the DRF message.
- `lib/format.ts`: `formatSeconds`, `formatPercent`, `formatCost`, `formatDuration`.
- `hooks/usePolling.ts`: `usePolling(fn, { intervalMs: 3000, enabled })`; it stops when `enabled` is false and on unmount.

Styling uses Tailwind utility classes only, with no CSS modules and no component library. The layout is mobile first; the detail page uses two columns on `lg` (player and timeline on the left, events and trace on the right).

## S11. Docker Compose (`docker-compose.yml`)

| Service    | Image / build                     | Command | Ports | Depends on | Volumes |
| ---------- | --------------------------------- | ------- | ----- | ---------- | ------- |
| `postgres` | `postgres:16-alpine`              | default | none (internal) | – | `pgdata:/var/lib/postgresql/data` |
| `redis`    | `redis:7-alpine`                  | default | none (internal) | – | – |
| `backend`  | `build: ./backend` → `shop-floor-backend:dev` | `sh -c "python manage.py migrate --noinput && gunicorn config.wsgi -b 0.0.0.0:8000 -w 2 --timeout 120"` | `8000:8000` | postgres, redis (healthy) | `media:/app/media` |
| `worker`   | same image as backend             | `celery -A config worker -l info -c 1` | – | postgres, redis (healthy), backend (started) | `media:/app/media` |
| `frontend` | `build: ./frontend` (arg `NEXT_PUBLIC_API_URL=http://localhost:8000`) → `shop-floor-frontend:dev` | `node server.js` | `3000:3000` | backend | – |

- Healthchecks: postgres `pg_isready`, redis `redis-cli ping`, backend `python -c` urlopen on `/api/health/`.
- `env_file: { path: .env, required: false }`. If there is no `.env`, the compose `environment` defaults make `docker compose up` work alone: `LLM_PROVIDER=${LLM_PROVIDER:-mock}` and local DB credentials. The code default stays `gemini` (PRD); Compose falls back to `mock` only when nothing is set.
- The backend image installs the dev dependencies too, so `docker compose exec backend pytest` works. This is simple and fine for a demo.
- Backend Dockerfile: `python:3.12-slim`, `apt-get install -y --no-install-recommends ffmpeg`, non-root user `app`, `WORKDIR /app`, `pip install .[dev]`.
- Frontend Dockerfile: multi-stage `node:22-alpine` (deps → build → runner with `.next/standalone`), non-root.

## S12. Kubernetes on kind (`k8s/`)

| File | Content |
| ---- | ------- |
| `kind-config.yaml` | Cluster `shop-floor`, 1 node, `extraPortMappings`: containerPort 30080 → host 8000, 30030 → host 3000 |
| `00-namespace.yaml` | Namespace `shop-floor` |
| `01-configmap.yaml` | `app-config`: non-secret env (S14 defaults; `DJANGO_DEBUG=false`, `CORS_ALLOWED_ORIGINS=http://localhost:3000`) |
| `02-postgres.yaml` | `Service postgres` (5432) + `StatefulSet postgres` (1 replica, `volumeClaimTemplates` 1 Gi) |
| `03-redis.yaml` | `Service redis` + `Deployment redis` |
| `04-media-pvc.yaml` | `PersistentVolumeClaim media` (RWO, 2 Gi, default `standard` class of kind) |
| `05-backend.yaml` | `Deployment backend` (1 replica, `initContainers: migrate` running `python manage.py migrate --noinput`, gunicorn container, readiness/liveness on `/api/health/`, media PVC at `/app/media`) + `Service backend` NodePort 30080 |
| `06-worker.yaml` | `Deployment worker` (1 replica, same image, celery command, media PVC) |
| `07-frontend.yaml` | `Deployment frontend` + `Service frontend` NodePort 30030 |

- All containers use `envFrom: [configMapRef: app-config, secretRef: app-secrets]`. With envFrom, the later source wins, so `.env` values override the ConfigMap.
- The secret is never committed: `kubectl -n shop-floor create secret generic app-secrets --from-env-file=.env`.
- Images are `shop-floor-backend:dev` and `shop-floor-frontend:dev`, `imagePullPolicy: IfNotPresent`, loaded with `kind load docker-image ... --name shop-floor`.
- Resource requests and limits are small (backend and worker 250m/512Mi request, 1 CPU/1Gi limit).
- Migrations run in an init container instead of a separate Job, so they always run before the API starts.
- The RWO media volume works because kind has a single node, so backend and worker share it. The PRD notes that production would use object storage.

## S13. CI (`.github/workflows/ci.yml`)

Triggers: `push` to `main` and `pull_request`. Jobs run in parallel:

| Job | Steps |
| --- | ----- |
| `backend` | `services`: `postgres:16-alpine`, `redis:7-alpine` (with health options). `actions/setup-python` 3.12 with pip cache. `sudo apt-get install -y ffmpeg`. `pip install ./backend[dev]`. `ruff check backend`, `ruff format --check backend`, `pytest -q` with env `LLM_PROVIDER=mock`, `MOCK_LATENCY_MS=0`, `DATABASE_URL=postgres://...@localhost:5432/...`, `REDIS_URL=redis://localhost:6379/0`, `DJANGO_SECRET_KEY=ci-only`. |
| `frontend` | `actions/setup-node` 22 with npm cache. In `frontend/`: `npm ci`, `npm run lint`, `npm run typecheck`, `npm run build` (env `NEXT_PUBLIC_API_URL=http://localhost:8000`). |
| `docker` | `docker build -t shop-floor-backend:ci backend` and `docker build -t shop-floor-frontend:ci frontend` (no push, no registry login). |
| `k8s` | Validate manifests with `kubeconform` (`docker run --rm -v $PWD/k8s:/k8s ghcr.io/yannh/kubeconform:latest -strict -summary -ignore-filename-pattern kind-config /k8s`). |

No secrets are needed. CI never calls a real LLM.

## S14. Environment variables

The code default applies when the variable is unset. `.env.example` lists every variable with this default (secrets empty) and a one-line comment.

| Variable | Default | Used by | Description |
| -------- | ------- | ------- | ----------- |
| `DJANGO_SECRET_KEY` | none (required) | backend, worker | Django secret |
| `DJANGO_DEBUG` | `false` | backend | Debug mode (`.env.example`: `true`) |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,backend` | backend | Comma list |
| `DATABASE_URL` | none (required) | backend, worker | e.g. `postgres://app:app@postgres:5432/shopfloor` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `shopfloor`, `app`, `app` | postgres container | Must match `DATABASE_URL` |
| `REDIS_URL` | `redis://redis:6379/0` | backend, worker | Celery broker and health check |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | backend | Comma list |
| `MEDIA_ROOT` | `/app/media` | backend, worker | Uploads and frames |
| `LOG_LEVEL` | `INFO` | backend, worker | |
| `MAX_UPLOAD_MB` | `200` | backend | Upload size limit |
| `MAX_VIDEO_SECONDS` | `130` | backend | Duration limit |
| `EVENT_TYPES_FILE` | `agent/event_types.yaml` | worker | Event type config |
| `LLM_PROVIDER` | `gemini` | worker | `gemini`, `mock`, `anthropic`, `openai` |
| `GEMINI_API_KEY` | empty | worker | Secret, from Google AI Studio |
| `GEMINI_MODEL` | empty (`.env.example`: `gemini-flash-latest`) | worker | A free tier Flash or Flash-Lite model |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | empty | worker | Optional provider |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | empty | worker | Optional provider |
| `LLM_INPUT_PRICE_PER_MTOK` | `0` | worker | USD per 1M input tokens |
| `LLM_OUTPUT_PRICE_PER_MTOK` | `0` | worker | USD per 1M output tokens |
| `LLM_TIMEOUT_SECONDS` | `60` | worker | Per call |
| `LLM_MAX_RETRIES` | `3` | worker | Backoff retries on 429/5xx |
| `LLM_MAX_REQUESTS_PER_MINUTE` | `8` | worker | Throttle |
| `AGENT_MAX_ITERATIONS` | `3` | worker | Guardrail |
| `AGENT_MAX_FRAMES` | `120` | worker | Guardrail |
| `AGENT_MAX_TOKENS` | `200000` | worker | Guardrail |
| `AGENT_MAX_COST_USD` | `0.50` | worker | Guardrail (no effect when prices are 0) |
| `AGENT_MAX_LLM_CALLS` | `20` | worker | Guardrail |
| `AGENT_REPORT_RESERVE_TOKENS` | `4000` | worker | Tokens kept for the report |
| `AGENT_RUN_TIMEOUT_SECONDS` | `600` | worker | Celery soft time limit |
| `SURVEY_INTERVAL_S` | `2` | worker | Survey frame interval |
| `SCENE_THRESHOLD` | `0.4` | worker | ffmpeg scene score |
| `INSPECT_FPS` | `2` | worker | Frame rate inside windows |
| `WINDOW_PADDING_S` | `2` | worker | Seconds around a candidate |
| `FRAMES_PER_CALL` | `12` | worker | Max images per LLM call |
| `FRAME_MAX_SIDE` | `768` | worker | Resize long side (px) |
| `CONFIDENCE_THRESHOLD` | `0.6` | worker | Min confidence to keep an event |
| `MOCK_LATENCY_MS` | `300` | worker | Mock delay (`0` in tests) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | frontend (build) | API base URL for the browser |
| `NEXT_PUBLIC_MAX_UPLOAD_MB` | `200` | frontend (build) | Client side size check |

`GEMINI_MODEL` has no code default because model names are never hardcoded. The value in `.env.example` is a suggestion to check against the AI Studio model list.

## S15. Makefile

| Target | Command(s) |
| ------ | ---------- |
| `up` | `docker compose up -d --build` |
| `down` | `docker compose down` |
| `logs` | `docker compose logs -f backend worker` |
| `test` | `docker compose exec -T backend pytest -q` |
| `lint` | `docker compose exec -T backend ruff check . && docker compose exec -T backend ruff format --check .` then `lint-frontend` |
| `lint-frontend` | `docker run --rm -v $(PWD)/frontend:/app -w /app node:22-alpine sh -c "npm ci && npm run lint && npm run typecheck"` (no local Node needed) |
| `samples` | `scripts/download_samples.sh`: downloads the 4 Appendix A files to `samples/<id>.mp4`, checks SHA-256 and prints `OK`/`MISMATCH` per file |
| `kind-up` | create cluster from `k8s/kind-config.yaml`, build both images, `kind load docker-image`, apply `00-namespace.yaml`, create `app-secrets` from `.env`, `kubectl apply -f k8s/`, wait for rollouts |
| `kind-down` | `kind delete cluster --name shop-floor` |

## S16. Logging

- Formatter: `pythonjsonlogger.json.JsonFormatter`, one JSON object per line on stdout. Fields: `timestamp`, `level`, `logger`, `message`, plus `run_id`, `video_id`, `node` when set.
- Context: a `contextvars`-based filter adds `run_id`, `video_id` and `node`. They are set in `analyze_video` and in each node.
- Redaction filter: it replaces the values of every env var whose name ends in `_KEY`, `_SECRET` or `_PASSWORD`, and patterns `AIza[0-9A-Za-z_-]{20,}`, `sk-[A-Za-z0-9_-]{20,}` and `Bearer \S+`, with `[REDACTED]` in the message and arguments.
- Django's `django.request` and Celery's loggers use the same handler.
