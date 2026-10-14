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
| 3 | `13422071.mp4` (15 s) | done, completed | `fallen_object_or_spill` 1.0 s low 0.78 | `missing_ppe` ~10.5 s (hi-vis vest) | 21 / 29 (72%) | 5 | yes |
| 4 | `31751344.mp4` (38 s) | done, completed | `missing_ppe` 6.5 s low 0.70; `missing_ppe` 31.5 s low 0.70 | `unsafe_proximity` ~7 s and ~32 s (no one on foot) | 37 / 75 (49%) | 6 | yes; no high severity event |

### Gemini free tier (2026-10-14, not complete)

The Gemini runs could not be finished on 2026-10-14. The project's free tier daily quota for the configured model ran out after the first survey call of clip 1.

| # | Clip | Result |
| - | ---- | ------ |
| 1 | `16106604.mp4` | The survey succeeded (15,134 input tokens) and found `missing_ppe` ~0 s and `unsafe_proximity` ~6 s, which are both expected events. It also found an extra `unsafe_proximity` candidate at ~24 s. The run then **failed in inspect** with "Gemini free tier daily quota reached, try again tomorrow or use the mock provider." Before that, there were some HTTP 503 errors, which were retried with backoff. |
| 2 | `4294438.mp4` | Failed at once with the same quota message (HTTP 429 `RESOURCE_EXHAUSTED`, daily quota). |
| 3, 4 | – | Not run (quota). |

The failure path behaved as designed: no retry on the daily quota, a clear message on the video, the run marked `failed`, and the Retry button available.

**To do:** rerun all 4 clips once the quota resets (`LLM_PROVIDER=gemini`, one after another) and replace this table with the events found and the comparison with Appendix A.

## PRD §14 success criteria

| # | Criterion | Status | Evidence / note |
| - | --------- | ------ | --------------- |
| 1 | `docker compose up` on a clean machine; full flow with the mock and no API key; realistic events and at least one dropped decoy on the 4 samples | ✅ | Fresh clone check (Phase 11 Verify, no `.env`); the mock table above; every clip drops at least one decoy |
| 2 | The same flow on kind by following the README | ✅ | Phase 9 Verify on a fresh cluster (`make kind-up`, upload, analyze, `done`, JSON logs) |
| 3 | Gemini free tier analyzes all 4 samples one after another without a rate limit error or paid usage | ⏳ not yet shown | Blocked by the daily quota on 2026-10-14 (see above). No paid usage: the key is a free tier AI Studio key and prices are 0. Rerun when the quota resets. |
| 4 | Gemini finds the Appendix A events, no high severity event on the control clip, and every event has a timestamp, severity, confidence and an explanation | ⏳ partly shown | On clip 1 the Gemini survey found both expected candidates before the quota ran out. A full check is needed after the rerun. The schema guarantees the event fields (Pydantic validation and `save_event` checks). |
| 5 | Frames analyzed < 50% of a full 2 fps pass, and the trace shows why each window was chosen | ⚠️ partly met | The control clip (38 s) uses 49%. The three short clips (15–25 s) use 72–73%: the survey (1 frame every 2 s plus scene changes) and ±2 s windows at 2 fps cost almost as much as a full pass on a clip this short. The savings grow with length (the 130 s limit gives 260 frames at 2 fps, but the budget is capped at 120). The plan step always records chosen and skipped windows and why. The limits were not tuned to pass this check. |
| 6 | Switching between `gemini` and `mock` needs only an env var change | ✅ | The Gemini runs above were started by changing only `LLM_PROVIDER` for the backend and worker |
| 7 | `make test` and `make lint` pass locally; the GitHub Actions workflow is green | ✅ local / ⏳ GitHub | 159 tests passed and lint was clean (Phase 10). The workflow status is on the README badge; the user checks it after pushing. |
| 8 | No secrets in the repository or in logs | ✅ | `.env` is git-ignored and never committed. The repo contains no real key (only fake keys in the redaction tests). The Compose logs, including the real Gemini runs, do not contain the key. |
