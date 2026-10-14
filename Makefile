.PHONY: up down logs test lint lint-backend lint-frontend

# Start the whole stack (builds images when needed).
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f backend worker

# Backend tests (mock LLM provider). Needs the stack up.
test:
	docker compose exec -T backend pytest -q

lint: lint-backend lint-frontend

lint-backend:
	docker compose exec -T backend ruff check .
	docker compose exec -T backend ruff format --check .

# Runs in a throwaway Node container on a copy of frontend/ (no local Node needed,
# host node_modules untouched).
lint-frontend:
	docker run --rm -v "$(CURDIR)/frontend:/src:ro" node:22-alpine sh -c '\
		mkdir /app && tar -C /src --exclude=node_modules --exclude=.next -cf - . | tar -C /app -xf - && \
		cd /app && npm ci --no-audit --no-fund --loglevel=error && npm run lint && npm run typecheck'
