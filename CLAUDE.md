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

Add each command here when it is created, with one line saying what it does.

| Task | Command |
| ---- | ------- |
| Run  | _not created yet_ |
| Test | _not created yet_ |
| Lint | _not created yet_ |
