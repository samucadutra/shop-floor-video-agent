# Shop Floor Video Agent: Demo

A 3-minute walkthrough, followed by the recorded results on the 4 sample clips and the check against the [PRD §14](prd.md#14-success-criteria-for-the-poc) success criteria.

## Before the demo

```bash
make samples                         # 4 x OK
docker compose up -d --build         # mock provider unless .env says otherwise
curl -fsS http://localhost:8000/api/health/
```

For an offline demo, keep `LLM_PROVIDER=mock`. It gives the same result every time and makes no network call. For a live Gemini demo, set `LLM_PROVIDER=gemini` and run sample 1 once beforehand to check that the daily quota is not used up. A Gemini run takes a few minutes, so start it before you begin talking.

## Script (about 3 minutes)

**0:00 – 0:20 The problem.** Plants record hours of footage that nobody watches. Sending every frame to a vision model is slow and expensive. This agent decides where to look.

**0:20 – 0:50 Upload sample 1.** Open http://localhost:3000/upload. Point at the notice "Upload only public stock videos". Drop `samples/16106604.mp4`; the progress bar fills and the page opens the video detail. Click **Analyze**. The status badge turns `processing`, and trace steps appear while the run is in progress.

**0:50 – 1:50 Follow the trace.** Once it is `done`, walk down the agent trace:

- **Survey** looked at a frame every 2 s plus scene changes and found 3 candidates: `missing_ppe` ~2 s, `unsafe_proximity` ~7 s, `missing_ppe` ~15 s.
- **Plan** made no LLM call. It chose 3 windows and ranked the high-severity proximity window first.
- **Inspect** asked one focused question per window at 2 fps. The third window shows "c3 not seen: the worker wears a white hard hat and an orange hi-vis jacket".
- **Verify** confirmed two events and **dropped the decoy**. Open the step to show the `save_event` tool calls.
- **Report** wrote the summary.

Point at **Run metrics**: 37 frames, 7 LLM calls, tokens, and cost (0 on the free tier). Then click the red marker on the timeline: the player jumps to 0:07, where the worker stands next to the moving forklift. Click the `Missing PPE` card: it jumps to 0:02.

**1:50 – 2:20 The control clip.** Upload and analyze `samples/31751344.mp4` (a forklift in an empty aisle). The trace drops both `unsafe_proximity` decoys ("there is no person on foot in the aisle, only the driver"). Only two low-severity `missing_ppe` events for the driver remain. The agent does not cry wolf when nobody is on foot.

**2:20 – 2:50 Dashboard.** Open http://localhost:3000/dashboard. Show the events by type, by severity and per video, plus average processing time, total tokens, estimated cost, and runs succeeded / failed.

**2:50 – 3:00 Close.** Switching to Gemini is one env var (`LLM_PROVIDER=gemini`). The same stack runs on kind (`make kind-up`), and CI runs lint, tests, builds and manifest validation with the mock.

## Results on the sample clips

### Mock provider (2026-10-14)

All 4 clips analyzed one after another on a fresh stack (`LLM_PROVIDER=mock`, default limits). "Frames" compares frames analyzed with what a full 2 fps pass would need.

| # | Clip | Status | Events found | Decoys dropped | Frames / 2 fps pass | LLM calls | Matches Appendix A |
| - | ---- | ------ | ------------ | -------------- | ------------------- | --------- | ------------------ |
| 1 | `16106604.mp4` (25 s) | done, completed | `missing_ppe` 2.0 s medium 0.88; `unsafe_proximity` 7.0 s high 0.82 | `missing_ppe` ~15 s (hard hat and orange jacket) | 37 / 51 (73%) | 7 | yes |
| 2 | `4294438.mp4` (15 s) | done, completed | `missing_ppe` 8.5 s medium 0.90 (window 0–14.5 s) | `unsafe_proximity` ~5 s (only the driver) | 22 / 30 (73%) | 4 | yes |
| 3 | Gemini free tier analyzes all 4 samples one after another without a rate limit error or paid usage | ❌ not met on 2026-10-14 | No paid usage (free tier key, prices 0). All 4 clips were analyzed only by moving to another Flash model each time one ran out of its daily quota (`gemini-3-flash-preview` for clip 1, `gemini-3.5-flash-lite` for clips 2–4). There were HTTP 503 overload errors too. The throttle prevents per-minute errors, but not the daily cap. Retry on a fresh quota with one model. |
| 4 | Gemini finds the Appendix A events, no high severity event on the control clip, and every event has a timestamp, severity, confidence and an explanation | ⚠️ partly met | 3 of 6 expected events found, and 1 more found by the survey but lost to a 503. There were 2 false positives. The spill in clip 3 and the first PPE moment in clip 4 were missed. ✅ No high severity event on the control clip. ✅ Every event has a timestamp, severity, confidence and an explanation that matches the frames. Details in the Gemini table. |

### Gemini free tier (2026-10-14)

The configured model, `gemini-3.8-flash`, used up its free tier daily quota during the first attempt. The quota is counted per model, so the clips were run on other Flash models instead, one after another. These were the models that still responded that day:

- `gemini-3.7-flash`: busy (HTTP 503 "high demand") on every retry, then out of quota. No clip finished.
- `gemini-3-flash-preview`: clip 1 finished. Its quota ran out at the start of clip 2.
- `gemini-3.5-flash-lite`: clips 2, 3 and 4 finished.

Default limits were used, prices were 0, and no paid usage was involved.

| # | Clip | Model | Events found | Dropped | Frames / 2 fps pass | Calls | Time | Compared with Appendix A |
| - | ---- | ----- | ------------ | ------- | ------------------- | ----- | ---- | ------------------------ |
| 1 | `16106604.mp4` | `gemini-3-flash-preview` | `unsafe_proximity` 4.0 s medium 0.90, 12.0 s high 0.90, 24.0 s high 0.95; `fallen_object_or_spill` 24.0 s medium 0.95 ("pile of wooden planks, tripping hazard") | `missing_ppe` ~0 s and `fallen_object_or_spill` ~0 s: the 0–2 s window failed with HTTP 503 after 3 retries | 40 / 51 (78%) | 7 | 132 s | **Partly.** `unsafe_proximity` was found inside the expected 6–21 s range (12 s) and next to it (4 s, 24 s). The **missing hard hat was found by the survey but lost to the 503** before verify. The planks event is a false positive: stacked lumber, not a fallen object. |
| 2 | `4294438.mp4` | `gemini-3.5-flash-lite` | `missing_ppe` at 0, 4, 8 and 12 s, medium 0.95 ("beanie, no hi-vis vest") | – (the `unsafe_proximity` decoy never became a candidate) | 35 / 30 (117%) | 7 | 24 s | **Yes**, but as 4 separate events for one long event. With candidates every 4 s, the windows covered the whole clip, so the agent used more frames than a full pass. |
| 3 | Gemini free tier analyzes all 4 samples one after another without a rate limit error or paid usage | ❌ not met on 2026-10-14 | No paid usage (free tier key, prices 0). All 4 clips were analyzed only by moving to another Flash model each time one ran out of its daily quota (`gemini-3-flash-preview` for clip 1, `gemini-3.5-flash-lite` for clips 2–4). There were HTTP 503 overload errors too. The throttle prevents per-minute errors, but not the daily cap. Retry on a fresh quota with one model. |
| 4 | Gemini finds the Appendix A events, no high severity event on the control clip, and every event has a timestamp, severity, confidence and an explanation | ⚠️ partly met | 3 of 6 expected events found, and 1 more found by the survey but lost to a 503. There were 2 false positives. The spill in clip 3 and the first PPE moment in clip 4 were missed. ✅ No high severity event on the control clip. ✅ Every event has a timestamp, severity, confidence and an explanation that matches the frames. Details in the Gemini table. |

What this run shows:

- **The resilience paths worked on a real provider.** HTTP 503 errors were retried with backoff. A window that still failed was dropped, and the run continued (clip 1). The daily quota failed runs at once with the clear message, without retrying. One invalid JSON reply was fixed by the validation retry (clip 3).
- **Detection quality is mixed**, as the PRD risk table expects from a free tier model. The larger Flash model did better than Flash-Lite. Of the 6 expected events, 3 were found (proximity in 1, PPE in 2, PPE in 4 at 30 s), and 1 more was found by the survey but lost to the outage (PPE in 1). There were 2 false positives (the planks in clip 1, the scrubber in clip 3) and no high severity event on the control clip.
- **Free tier capacity is the real limit.** The daily quota per model was a few dozen requests at most. Analyzing all 4 clips needs about 25 calls. Run them on a day with a fresh quota, on one model, ideally a full Flash model.

## PRD §14 success criteria

| # | Criterion | Status | Evidence / note |
| - | --------- | ------ | --------------- |
| 1 | `docker compose up` on a clean machine; full flow with the mock and no API key; realistic events and at least one dropped decoy on the 4 samples | ✅ | Fresh clone check (Phase 11 Verify, no `.env`); the mock table above; every clip drops at least one decoy |
| 2 | The same flow on kind by following the README | ✅ | Phase 9 Verify on a fresh cluster (`make kind-up`, upload, analyze, `done`, JSON logs) |
| 3 | Gemini free tier analyzes all 4 samples one after another without a rate limit error or paid usage | ❌ not met on 2026-10-14 | No paid usage (free tier key, prices 0). All 4 clips were analyzed only by moving to another Flash model each time one ran out of its daily quota (`gemini-3-flash-preview` for clip 1, `gemini-3.5-flash-lite` for clips 2–4). There were HTTP 503 overload errors too. The throttle prevents per-minute errors, but not the daily cap. Retry on a fresh quota with one model. |
| 4 | Gemini finds the Appendix A events, no high severity event on the control clip, and every event has a timestamp, severity, confidence and an explanation | ⚠️ partly met | 3 of 6 expected events found, and 1 more found by the survey but lost to a 503. There were 2 false positives. The spill in clip 3 and the first PPE moment in clip 4 were missed. ✅ No high severity event on the control clip. ✅ Every event has a timestamp, severity, confidence and an explanation that matches the frames. Details in the Gemini table. |
| 5 | Frames analyzed < 50% of a full 2 fps pass, and the trace shows why each window was chosen | ⚠️ partly met | Only the 38 s control clip is under 50% (49% with the mock, 36% with Gemini). The 15–25 s clips use 66–78%, and 117% on Gemini clip 2, where candidates every 4 s made windows that covered the whole clip. On a clip this short, the survey (1 frame every 2 s plus scene changes) and ±2 s windows at 2 fps cost about as much as a full pass. The savings grow with length (the 130 s limit gives 260 frames at 2 fps, but the budget is capped at 120). The plan step always records chosen and skipped windows and why. The limits were not tuned to pass this check. |
| 6 | Switching between `gemini` and `mock` needs only an env var change | ✅ | The Gemini runs above were started by changing only `LLM_PROVIDER` and `GEMINI_MODEL` for the backend and worker, with no code change |
| 7 | `make test` and `make lint` pass locally; the GitHub Actions workflow is green | ✅ local / ⏳ GitHub | 159 tests passed and lint was clean (Phase 10). The workflow status is on the README badge; the user checks it after pushing. |
| 8 | No secrets in the repository or in logs | ✅ | `.env` is git-ignored and never committed. The repo contains no real key (only fake keys in the redaction tests). The Compose logs, including the real Gemini runs, do not contain the key. |
