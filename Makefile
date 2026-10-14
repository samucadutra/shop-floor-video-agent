.PHONY: up down logs test lint lint-backend lint-frontend samples kind-up kind-down

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

# Downloads the 4 demo clips (PRD Appendix A) into samples/ and checks their SHA-256.
samples:
	./scripts/download_samples.sh

# Local Kubernetes (docs/spec.md S12). Needs Docker, kind and kubectl; ports 3000 and 8000 free.
KIND_CLUSTER := shop-floor
KUBECTL := kubectl --context kind-$(KIND_CLUSTER) -n shop-floor

kind-up:
	@test -f .env || { echo "No .env: run 'cp -n .env.example .env' first"; exit 1; }
	kind get clusters | grep -qx $(KIND_CLUSTER) || kind create cluster --config k8s/kind-config.yaml
	docker compose build backend frontend
	kind load docker-image shop-floor-backend:dev shop-floor-frontend:dev --name $(KIND_CLUSTER)
	$(KUBECTL) apply -f k8s/00-namespace.yaml
	$(KUBECTL) create secret generic app-secrets --from-env-file=.env --dry-run=client -o yaml \
		| $(KUBECTL) apply -f -
	$(KUBECTL) apply $(addprefix -f ,$(sort $(wildcard k8s/0*.yaml)))
	$(KUBECTL) rollout status statefulset/postgres --timeout=180s
	$(KUBECTL) rollout status deploy/redis --timeout=180s
	$(KUBECTL) rollout status deploy/backend --timeout=180s
	$(KUBECTL) rollout status deploy/worker --timeout=180s
	$(KUBECTL) rollout status deploy/frontend --timeout=180s

kind-down:
	kind delete cluster --name $(KIND_CLUSTER)
