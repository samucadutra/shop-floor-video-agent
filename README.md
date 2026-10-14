# Shop Floor Video Agent

<!-- Replace OWNER with the GitHub user or org once the remote exists. -->
[![CI](https://github.com/samucadutra/shop-floor-video-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/samucadutra/shop-floor-video-agent/actions/workflows/ci.yml)

An agentic AI system that analyzes short factory floor videos and reports safety events. Work in progress: see [docs/prd.md](docs/prd.md) and [docs/tasks.md](docs/tasks.md).

## Run on kind

The same stack runs on a local single-node [kind](https://kind.sigs.k8s.io/) cluster. The manifests are in [k8s/](k8s/).

Prerequisites: Docker, `kind` and `kubectl`.

```bash
cp -n .env.example .env     # the cluster Secret is created from this file
docker compose down         # frees ports 3000 and 8000
make kind-up                # creates the cluster, builds and loads the images, applies k8s/, waits for rollouts
kubectl -n shop-floor get pods
```

Then open the UI at http://localhost:3000 and the API at http://localhost:8000/api/ (the same URLs as Compose; kind maps NodePorts 30030 and 30080 to them).

- The `app-secrets` Secret is created from `.env` (`kubectl create secret generic app-secrets --from-env-file=.env`) and is never committed. Its values override the `app-config` ConfigMap, except `DJANGO_DEBUG`, which is always `false` on the cluster.
- The ConfigMap sets `LLM_PROVIDER=mock`, so no API key is needed. To use Gemini, set `LLM_PROVIDER`, `GEMINI_API_KEY` and `GEMINI_MODEL` in `.env`, then run `make kind-up` again and `kubectl -n shop-floor rollout restart deploy/backend deploy/worker`.
- Logs: `kubectl -n shop-floor logs deploy/worker -f`.
- Media (uploads and frames) live on a `ReadWriteOnce` volume shared by the backend and the worker. That works because kind has one node; production would use object storage.
- `make kind-down` deletes the cluster and all its data.
