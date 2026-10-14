# Shop Floor Video Agent

Portfolio PoC: an agentic AI system that analyzes short factory and warehouse videos and reports safety events.

## Source of truth

- `docs/prd.md`: what to build and why.
- `docs/spec.md`: how to build it.
- `docs/tasks.md`: the task list and its status.

Read all three before any work. If they disagree, or something is not covered, ask before deciding.

## How to work

- Work only on the task or phase I ask for. Do not start the next phase on your own.
- After finishing a task, mark it as done in `docs/tasks.md`.
- Every phase must end with its verification commands passing. Show me the output.
- Keep code simple and readable. No features outside the PRD.

## Secrets and configuration

- Never hardcode secrets or model names. Use environment variables.
- Keep `.env.example` updated whenever a variable is added, renamed or removed.
- `.env` is never committed.

## LLM usage in tests

- Tests and CI use the mock LLM provider (`LLM_PROVIDER=mock`).
- Never call a real LLM in tests.

## Git

- Never run `git push` or create remote repositories.
- Make local commits only when I ask.

## Code style

- **Python:** type hints everywhere, ruff for lint, pytest + pytest-django for tests.
- **Frontend:** TypeScript in strict mode, Tailwind CSS only (no other styling), ESLint.

## Commands

Add each command here when it is created, with one line saying what it does. Run them from the repository root.

| Task | Command | What it does |
| ---- | ------- | ------------ |
| First setup | `cp -n .env.example .env` | Local env file (git-ignored) |
| Run | `make up` (`docker compose up -d --build`) | Builds and starts postgres, redis, backend, worker, frontend |
| Stop | `make down` | Stops the stack (data volumes kept) |
| Logs | `make logs` | Follows backend and worker logs |
| Health | `curl -fsS http://localhost:8000/api/health/` | Checks the DB and Redis through the API |
| Test | `make test` (`docker compose exec -T backend pytest -q`) | Backend tests; needs the stack up |
| Lint | `make lint` | `lint-backend` + `lint-frontend` |
| Lint backend | `make lint-backend` | `ruff check .` and `ruff format --check .` in the backend container |
| Lint frontend | `make lint-frontend` | ESLint + `tsc --noEmit` in a throwaway `node:22-alpine` container |
| Sample videos | `make samples` | Downloads the 4 demo clips to `samples/` (git-ignored) and checks their SHA-256 |
| Migrations | `docker compose run --rm -v "$PWD/backend:/app" backend python manage.py makemigrations` | Writes new migration files into `backend/` (the image has no source mount) |
| Kind up | `make kind-up` | Creates the kind cluster, builds and loads images, creates `app-secrets` from `.env`, applies `k8s/` |
| Kind down | `make kind-down` | Deletes the kind cluster and its data |
| CI lint | `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest -color` | Lints `.github/workflows/ci.yml` |
| K8s validate | `docker run --rm -v "$PWD/k8s":/k8s ghcr.io/yannh/kubeconform:latest -strict -summary -ignore-filename-pattern kind-config /k8s` | Validates the manifests (same as the CI `k8s` job) |

URLs: frontend http://localhost:3000, API http://localhost:8000/api/.
