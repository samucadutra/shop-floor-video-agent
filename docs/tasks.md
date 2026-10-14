# Shop Floor Video Agent: Tasks

Design: [spec.md](spec.md). Requirements: [prd.md](prd.md).

**Rules**

- Work on one phase at a time, and only the phase that was asked for.
- Mark a task done (`- [x]`) when it is finished.
- A phase is done when every command in its **Verify** block passes and the output has been shown.
- `S<n>` refers to a section of `spec.md`.

Unless a task says otherwise, the commands run from the repository root with the Compose stack up.

---

## Phase 1 Scaffold and Docker Compose

**Goal:** the empty stack starts with one command and the health endpoint answers.

- [x] **1.1** Create the repository layout from S1 (empty packages with `__init__.py`), `.gitignore`, and `README.md` with a title only.
- [x] **1.2** `backend/pyproject.toml` with the dependencies, ruff config and pytest config (S2). Create the Django project `config` and the apps `core` and `videos`.
- [x] **1.3** `config/settings.py` reading env with `django-environ` (S2, S14). Write `.env.example` with every S14 variable used so far.
- [x] **1.4** `config/celery.py` (Celery app, autodiscover) and `core` `HealthView` at `/api/health/` (S4.4).
- [x] **1.5** `backend/Dockerfile` (S11) with ffmpeg, a non-root user and dev dependencies.
- [x] **1.6** Create the Next.js app in `frontend/` (TypeScript strict, Tailwind, ESLint, `typecheck` script, `output: "standalone"`), with a placeholder home page. Write `frontend/Dockerfile` (S11).
- [x] **1.7** `docker-compose.yml` with the 5 services, healthchecks, volumes and env defaults (S11).
- [x] **1.8** `Makefile` with `up`, `down`, `logs`, `test`, `lint`, `lint-frontend` (S15).
- [x] **1.9** Test `tests/core/test_health.py`: 200 with DB and Redis up; 503 when Redis is unreachable (patched).
- [x] **1.10** Add the run, test and lint commands to `CLAUDE.md`.

### Verify

```bash
cp -n .env.example .env
docker compose up -d --build
docker compose ps                                   # 5 services up; postgres and redis "healthy"
curl -fsS http://localhost:8000/api/health/         # {"status":"ok","database":"ok","redis":"ok"}
curl -fsSL -o /dev/null -w "%{http_code}\n" http://localhost:3000/   # 200
docker compose exec -T backend pytest -q            # all passed
docker compose exec -T backend ruff check .         # All checks passed!
docker compose exec -T backend ruff format --check .
make lint-frontend                                  # ESLint and tsc report no errors
```

**Done when:** all commands pass on a fresh `docker compose up`.

---

## Phase 2 Django models, API and upload

**Goal:** videos can be uploaded, listed, read and played (with seeking). There is no analysis yet.

- [ ] **2.1** Models `Video`, `AnalysisRun`, `Event`, `AgentStep` with the choices and constraints from S3. Create migrations.
- [ ] **2.2** `media_tools/ffmpeg.py: probe()` (S9). It is needed by upload validation.
- [ ] **2.3** `videos/validators.py: validate_upload` (S4.2): extension, MIME type, size, ffprobe, duration, SHA-256.
- [ ] **2.4** Serializers from S4.1.
- [ ] **2.5** `VideoViewSet` (create, list, retrieve, `events` action) and `RunTraceView`. URLs from S4; `/events/` and `/trace/` return empty lists for now.
- [ ] **2.6** `core.views.serve_media` with Range support (S4.5), mounted at `/media/`.
- [ ] **2.7** `scripts/download_samples.sh` and the `make samples` target (S15).
- [ ] **2.8** Test helper `make_test_video(tmp_path, seconds)` in `conftest.py` (ffmpeg `testsrc`, S9).
- [ ] **2.9** Tests: valid upload (201, metadata saved), wrong extension, wrong MIME type, a fake `.mp4` (ffprobe fails), too large (setting overridden), too long, list pagination and `event_count`, detail 404, Range request (206 and `Content-Range`), path traversal (404).

### Verify

```bash
docker compose exec -T backend python manage.py makemigrations --check --dry-run   # No changes detected
docker compose exec -T backend pytest -q                                           # all passed
docker compose exec -T backend ruff check .
make samples                                                                       # 4 x OK
curl -fsS -F file=@samples/16106604.mp4 http://localhost:8000/api/videos/ | tee /tmp/up.json   # 201, status "uploaded", duration_s ~25.4
VID=$(python3 -c 'import json;print(json.load(open("/tmp/up.json"))["id"])')
curl -fsS http://localhost:8000/api/videos/ | python3 -m json.tool | head -20     # count >= 1
curl -fsS http://localhost:8000/api/videos/$VID/ | python3 -m json.tool          # detail with file_url, current_run null
URL=$(python3 -c 'import json;print(json.load(open("/tmp/up.json"))["file_url"])')
curl -s -o /dev/null -w "%{http_code}\n" -H "Range: bytes=0-99" "$URL"           # 206
printf 'not a video' > /tmp/fake.mp4
curl -s -o /dev/null -w "%{http_code}\n" -F file=@/tmp/fake.mp4 http://localhost:8000/api/videos/   # 400
```

**Done when:** the commands pass and the uploaded file plays and seeks when its `file_url` is opened in a browser.

---

## Phase 3 Video processing with ffmpeg and Celery

**Goal:** "Analyze" runs a real background job that extracts frames and moves the statuses correctly. There is no LLM yet.

- [ ] **3.1** `media_tools/ffmpeg.py`: `extract_survey`, `extract_scenes`, `extract_window` with the scale expression (S9).
- [ ] **3.2** Tests for the extractors: frame counts and timestamps for a 10 s clip; a scene change found in a clip built with concat; frames are never larger than `FRAME_MAX_SIDE`.
- [ ] **3.3** `videos/services.py`: `start_analysis`, `finish_run`, `fail_run`, `mark_stale_runs` (S5.1–S5.3).
- [ ] **3.4** `analyze` action: returns 202 with `run_id`, or 409 if a run is active (S4, S5.1).
- [ ] **3.5** `videos/tasks.py: analyze_video` skeleton. It sets `running`, extracts the survey frames to `MEDIA_ROOT/frames/<run_id>/`, records `frames_analyzed`, then calls `finish_run` with an empty result. Handles the soft time limit and errors (S5.2).
- [ ] **3.6** Tests (with `CELERY_TASK_ALWAYS_EAGER` and `django_capture_on_commit_callbacks`): status flow `uploaded → processing → done`; 409 on a second start; a failure path sets `failed` and keeps `current_run`; re-analysis deletes the older run; a stale run is marked failed.

### Verify

```bash
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check .
VID=$(curl -fsS -F file=@samples/16106604.mp4 http://localhost:8000/api/videos/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -fsS -X POST http://localhost:8000/api/videos/$VID/analyze/ | tee /tmp/run.json             # 202 {"run_id": ..., "status": "queued"}
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/videos/$VID/analyze/  # 409 (run immediately after the first call)
for i in $(seq 1 20); do S=$(curl -fsS http://localhost:8000/api/videos/$VID/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])'); echo $S; [ "$S" = done ] && break; sleep 2; done   # ends with "done"
RUN=$(python3 -c 'import json;print(json.load(open("/tmp/run.json"))["run_id"])')
docker compose exec -T worker sh -c "ls /app/media/frames/$RUN | wc -l"                          # > 10 frames
docker compose logs worker --tail 20                                                             # task received and succeeded
```

**Done when:** the commands pass, and a re-analysis leaves only one run for the video in the database.

---

## Phase 4 Agent with LangGraph using the mock provider

**Goal:** the full survey → plan → inspect → verify → report loop runs offline with the mock, and saves events, a summary and a trace.

- [ ] **4.1** `agent/event_types.yaml` and its loader (S6.1).
- [ ] **4.2** `agent/schemas.py` (S8) with unit tests for valid and invalid payloads.
- [ ] **4.3** `agent/providers/base.py`, `client.py` (parse, validate, one retry, cost; throttle and backoff can be no-ops until Phase 5) and `factory.py` (S7.1–S7.3).
- [ ] **4.4** `agent/providers/mock.py` and the `MockFixture` schema (S7.4). Write `generic.yaml`.
- [ ] **4.5** Write the 4 sample fixtures from PRD Appendix A, with times checked frame by frame (extract frames at 2 fps and read them).
- [ ] **4.6** `agent/state.py`, `guardrails.py` (`AgentLimits`, `budget_exceeded`) and `tools.py` (`get_frames`, `analyze_frames`, `save_event`) (S6.2, S6.5, S6.6).
- [ ] **4.7** `agent/prompts.py` (S6.8) and `agent/nodes.py` (S6.4).
- [ ] **4.8** `agent/graph.py` (S6.3), `repository.py` (`record_step`, `save_event`) and `runner.py`. Connect `analyze_video` to `run_agent`.
- [ ] **4.9** Tests with the mock (no network): a full run on a test clip creates events, a summary and ≥ 5 steps; each guardrail (iterations, frames, tokens, LLM calls) stops the run with `is_partial=true` and the right `stop_reason`; `invalid_json_once` gives a `retried` step and the run succeeds; `error_on: [survey]` fails the run; `error_on: [inspect]` drops candidates and the run continues; a decoy is dropped; re-analysis does not duplicate events.

### Verify

```bash
docker compose exec -T backend pytest -q                       # all passed
docker compose exec -T backend ruff check .
grep -n "LLM_PROVIDER" .env                                    # LLM_PROVIDER=mock for this phase
docker compose up -d --force-recreate backend worker
VID=$(curl -fsS -F file=@samples/16106604.mp4 http://localhost:8000/api/videos/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
RUN=$(curl -fsS -X POST http://localhost:8000/api/videos/$VID/analyze/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
for i in $(seq 1 30); do S=$(curl -fsS http://localhost:8000/api/videos/$VID/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])'); [ "$S" = done ] && break; sleep 2; done; echo $S   # done
curl -fsS http://localhost:8000/api/videos/$VID/events/ | python3 -c 'import sys,json;[print(e["event_type"], e["timestamp_s"], e["severity"], e["confidence"]) for e in json.load(sys.stdin)]'   # missing_ppe and unsafe_proximity
curl -fsS http://localhost:8000/api/runs/$RUN/trace/ | python3 -c 'import sys,json;[print(s["index"], s["node"], s["status"], "|", s["decision"][:80]) for s in json.load(sys.stdin)["steps"]]'   # survey, plan, inspect…, verify, report; one decoy dropped
curl -fsS -X POST http://localhost:8000/api/videos/$VID/analyze/ > /dev/null; sleep 15
curl -fsS http://localhost:8000/api/videos/$VID/events/ | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))'   # same count as before (no duplicates)
```

**Done when:** the commands pass, and the 4 sample clips each give the events listed in PRD Appendix A.

---

## Phase 5 Real LLM providers (Gemini; Anthropic and OpenAI optional)

**Goal:** the same agent works with Gemini on the free tier, with throttling and retries. The other providers are optional.

- [ ] **5.1** In `LLMClient`: the sliding window throttle (`LLM_MAX_REQUESTS_PER_MINUTE`), `tenacity` backoff on `RetryableLLMError`, timeouts, and no retry on `QuotaExhaustedError` (S7.2).
- [ ] **5.2** `agent/providers/gemini.py` (S7.3): images as JPEG parts, JSON response type, usage, and error mapping.
- [ ] **5.3** Fail fast in the factory when the selected provider's env is missing (the message names the variable only).
- [ ] **5.4** Tests with a fake provider (no network): backoff on 429 and 503 (the wait patched to 0), no retry on 400, a quota error fails the run with a clear message, the throttle waits once over the limit (fake clock), cost math, and Gemini error mapping using fake SDK exceptions.
- [ ] **5.5** Update `.env.example` (`GEMINI_API_KEY`, `GEMINI_MODEL`, prices).
- [ ] **5.6** Manual run with Gemini on sample 1, then compare the events with PRD Appendix A.
- [ ] **5.7** (optional) `agent/providers/anthropic.py` + tests with fake SDK errors.
- [ ] **5.8** (optional) `agent/providers/openai.py` + tests with fake SDK errors.

### Verify

```bash
docker compose exec -T backend pytest -q                                    # all passed, no network used
docker compose exec -T backend ruff check .
grep -rnE "gemini-|claude-|gpt-" backend --include=*.py                     # no output (no hardcoded model names)
# Manual check with the free tier: set LLM_PROVIDER=gemini, GEMINI_API_KEY and GEMINI_MODEL in .env
docker compose up -d --force-recreate backend worker
VID=$(curl -fsS -F file=@samples/16106604.mp4 http://localhost:8000/api/videos/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -fsS -X POST http://localhost:8000/api/videos/$VID/analyze/
for i in $(seq 1 100); do S=$(curl -fsS http://localhost:8000/api/videos/$VID/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])'); [ "$S" != processing ] && break; sleep 3; done; echo $S   # done
curl -fsS http://localhost:8000/api/videos/$VID/ | python3 -c 'import sys,json;r=json.load(sys.stdin)["current_run"];print(r["provider"], r["model"], r["llm_calls"], r["input_tokens"], r["stop_reason"])'   # gemini <model> <=20 ... completed
curl -fsS http://localhost:8000/api/videos/$VID/events/ | python3 -m json.tool
```

**Done when:** the tests pass, and a Gemini run on sample 1 finishes without a rate limit error and finds at least the missing hard hat.

---

## Phase 6 Frontend: upload, list and video detail

**Goal:** a user can do the whole flow in the browser.

- [ ] **6.1** `lib/types.ts`, `lib/api.ts` (with upload progress through XHR) and `lib/format.ts` (S10.3).
- [ ] **6.2** `hooks/usePolling.ts`.
- [ ] **6.3** `layout.tsx` + `Nav`, and `/` redirecting to `/videos`.
- [ ] **6.4** `/upload`: `UploadNotice`, `Dropzone` with client side type and size checks, progress bar, Analyze button, redirect to the detail page.
- [ ] **6.5** `/videos`: responsive table/cards, `StatusBadge`, event count, polling while processing, empty and error states.
- [ ] **6.6** `/videos/[id]`: `VideoPlayer` (`seekTo`), `EventTimeline`, `EventCard`, `SeverityBadge`, `SummaryCard`, Analyze/Re-analyze button, polling, failed-run banner.
- [ ] **6.7** Check the layout at 375 px and 1280 px wide.

### Verify

```bash
make lint-frontend                                                    # no ESLint or tsc errors
docker compose build frontend && docker compose up -d frontend        # build succeeds
curl -fsSL -o /dev/null -w "%{http_code}\n" http://localhost:3000/upload   # 200
curl -fsSL -o /dev/null -w "%{http_code}\n" http://localhost:3000/videos   # 200
```

Manual check in the browser (with `LLM_PROVIDER=mock`):

1. Drop `samples/16106604.mp4` on `/upload`; the progress bar moves and the page redirects to the detail page.
2. Click Analyze; the badge shows `processing`, then `done` with no page reload.
3. Click each timeline marker and event card; the player jumps to that second.
4. Drop a `.txt` file; a clear error appears and nothing is uploaded.
5. In a narrow window (375 px) there is no horizontal scroll.

**Done when:** all automated commands pass and the 5 manual checks pass.

---

## Phase 7 Frontend: agent trace panel and dashboard

**Goal:** users can see how the agent decided, and the totals across videos.

- [ ] **7.1** `StatsView` at `/api/stats/` (S4.3), with tests: empty database, two videos with events, failed runs counted.
- [ ] **7.2** `TracePanel` and `TraceStep` on the detail page (S10.2), refreshed while the run is in progress.
- [ ] **7.3** `RunMetrics` on the detail page.
- [ ] **7.4** `/dashboard`: 3 × `BarChartCard` (by type, by severity, per video) and `StatTile`s (average processing time, total tokens, total cost, runs succeeded/failed).
- [ ] **7.5** Empty states for the dashboard and the trace.

### Verify

```bash
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check .
curl -fsS http://localhost:8000/api/stats/ | python3 -m json.tool        # all keys from PRD §8 present
make lint-frontend
docker compose build frontend && docker compose up -d frontend
curl -fsSL -o /dev/null -w "%{http_code}\n" http://localhost:3000/dashboard   # 200
```

Manual check in the browser:

1. The detail page of an analyzed video shows every step with node, decision, tokens, latency and status, and at least one dropped decoy.
2. With the mock, the dashboard counts match `curl /api/stats/`.
3. After `docker compose down -v && docker compose up -d`, the dashboard shows the empty state and no error.

**Done when:** the commands and the 3 manual checks pass.

---

## Phase 8 Hardening: errors, limits, logging, security

**Goal:** the PoC behaves well when things go wrong, and leaks nothing.

- [ ] **8.1** JSON logging with the context filter and the redaction filter (S16), for Django, Celery and the agent.
- [ ] **8.2** Tests for the redaction filter (env-based values, `AIza…`, `sk-…`, `Bearer …`).
- [ ] **8.3** Clear user-facing `error_message` for each failure type: quota exhausted, timeout, invalid LLM output, ffmpeg failure, worker lost (stale run).
- [ ] **8.4** UI: a partial-result banner with the stop reason, the failed-run message and the Retry button (check them against each failure type).
- [ ] **8.5** CORS: allowed only for `CORS_ALLOWED_ORIGINS`. Test with an allowed and a blocked origin.
- [ ] **8.6** Upload limits are enforced on the server even when the client check is skipped (tests already exist from Phase 2; add one test with a real 201 MB sparse file).
- [ ] **8.7** Check that `DJANGO_DEBUG=false` returns JSON 404 and 500 responses with no stack traces.
- [ ] **8.8** Check that `.env` is git-ignored and that `.env.example` matches S14 (a test compares the keys in `.env.example` with a list in settings).

### Verify

```bash
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check .
git check-ignore .env && echo "ignored"                                                     # ignored
docker compose logs worker --no-log-prefix --tail 50 | grep '^{' | python3 -c 'import sys,json;[json.loads(l) for l in sys.stdin];print("json ok")'   # json ok
[ -n "$(grep -E '^GEMINI_API_KEY=.+' .env)" ] && (docker compose logs 2>&1 | grep -c "$(grep -E '^GEMINI_API_KEY=' .env | cut -d= -f2-)" || true)   # 0 (or nothing if no key set)
curl -s -D - -o /dev/null -H "Origin: http://localhost:3000" http://localhost:8000/api/videos/ | grep -i access-control-allow-origin   # header present
curl -s -D - -o /dev/null -H "Origin: http://evil.example" http://localhost:8000/api/videos/ | grep -ci access-control-allow-origin    # 0
truncate -s 201M /tmp/big.mp4 && curl -s -o /dev/null -w "%{http_code}\n" -F file=@/tmp/big.mp4 http://localhost:8000/api/videos/   # 400
curl -s http://localhost:8000/api/nope/ | head -c 200                                         # short JSON or plain 404, no stack trace (with DJANGO_DEBUG=false)
```

**Done when:** all commands pass. Each failure type shows a clear message in the UI, checked with the mock `error_on` hook.

---

## Phase 9 Kubernetes on kind

**Goal:** the full stack runs on a local kind cluster.

- [ ] **9.1** `k8s/kind-config.yaml` with the port mappings (S12).
- [ ] **9.2** Manifests `00`–`07` (S12): namespace, configmap, postgres, redis, media PVC, backend (with the migrate init container), worker, frontend.
- [ ] **9.3** The `kind-up` and `kind-down` Makefile targets (S15).
- [ ] **9.4** README section "Run on kind".

### Verify

```bash
docker compose down                                         # free ports 3000 and 8000
make kind-up
kubectl -n shop-floor get pods                              # all Running/Ready (postgres-0, redis, backend, worker, frontend)
kubectl -n shop-floor rollout status deploy/backend --timeout=180s
curl -fsS http://localhost:8000/api/health/                 # {"status":"ok",...}
curl -fsSL -o /dev/null -w "%{http_code}\n" http://localhost:3000/   # 200
VID=$(curl -fsS -F file=@samples/16106604.mp4 http://localhost:8000/api/videos/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -fsS -X POST http://localhost:8000/api/videos/$VID/analyze/
sleep 30; curl -fsS http://localhost:8000/api/videos/$VID/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])'   # done
kubectl -n shop-floor logs deploy/worker --tail 5           # JSON log lines
make kind-down
```

**Done when:** the commands pass on a fresh cluster, following only the README.

---

## Phase 10 GitHub Actions CI

**Goal:** a workflow that lints, tests and builds everything with the mock provider.

- [ ] **10.1** `.github/workflows/ci.yml` with the jobs `backend`, `frontend`, `docker` and `k8s` (S13).
- [ ] **10.2** Make sure the tests read the DB and Redis from env so they run in CI service containers (no Compose).
- [ ] **10.3** A CI status badge in the README (the URL is filled in once the user creates the remote).
- [ ] **10.4** Run the same steps locally (below). The user pushes and checks the run on GitHub; Claude never pushes.

### Verify

```bash
docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest -color   # no errors
docker build -t shop-floor-backend:ci backend
docker build -t shop-floor-frontend:ci --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 frontend
docker run --rm -v "$PWD/k8s":/k8s ghcr.io/yannh/kubeconform:latest -strict -summary -ignore-filename-pattern kind-config /k8s   # Invalid: 0, Errors: 0
docker compose exec -T -e LLM_PROVIDER=mock -e MOCK_LATENCY_MS=0 backend pytest -q   # all passed
make lint
```

**Done when:** the local commands pass. After the user pushes, the workflow is green on GitHub (the user checks it).

---

## Phase 11 README, architecture diagram and demo

**Goal:** a reviewer can understand, run and evaluate the project from the README alone.

- [ ] **11.1** README: what it is (2–3 lines), screenshots (upload, detail with trace, dashboard), quick start (`cp .env.example .env`, `make samples`, `docker compose up`), providers (mock/Gemini, free tier notes, privacy warning), sample videos with links and creator credits (PRD Appendix A), architecture Mermaid diagram (PRD §10), agent loop diagram (S6.3), commands, kind, CI, limitations, and what production would add (PRD §3).
- [ ] **11.2** `docs/demo.md`: a 3-minute demo script (upload sample 1, follow the trace, open the control clip, show the dashboard).
- [ ] **11.3** Run all 4 sample clips with the mock and with Gemini. Record the results against PRD Appendix A in `docs/demo.md`.
- [ ] **11.4** Final check against the PRD §14 success criteria. Every item is ticked or has a note.

### Verify

```bash
# needs a local commit of the current work (ask the user first)
docker compose down -v
rm -rf /tmp/sfva-fresh && git clone . /tmp/sfva-fresh && cd /tmp/sfva-fresh
docker compose up -d --build                                 # works with no .env (mock provider)
curl -fsS http://localhost:8000/api/health/
make samples                                                 # 4 x OK
for f in samples/*.mp4; do curl -fsS -F file=@$f http://localhost:8000/api/videos/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])'; done > /tmp/ids.txt
for id in $(cat /tmp/ids.txt); do curl -fsS -X POST http://localhost:8000/api/videos/$id/analyze/ > /dev/null; done; sleep 60
for id in $(cat /tmp/ids.txt); do curl -fsS http://localhost:8000/api/videos/$id/ | python3 -c 'import sys,json;v=json.load(sys.stdin);print(v["original_name"], v["status"])'; done   # 4 x done
curl -fsS http://localhost:8000/api/stats/ | python3 -m json.tool
docker compose down -v && cd - && rm -rf /tmp/sfva-fresh
```

**Done when:** a fresh clone works by following the README, and every PRD §14 criterion is met or explained.
