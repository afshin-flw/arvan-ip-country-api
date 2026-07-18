# IP Country API

A production-oriented FastAPI service that resolves a public IPv4 or IPv6 address to a country and caches successful lookups in PostgreSQL. It includes a small responsive web UI, typed API responses, Alembic migrations, Prometheus metrics, structured logs, health probes, tests, and a non-root container image.

## Architecture

```text
Client
  → FastAPI
  → PostgreSQL cache lookup
      → hit: return cached country
      → miss: query GeoIP provider
              → store result
              → return country
```

The service validates and normalizes the address before querying PostgreSQL. An unexpired row is returned immediately. A missing or expired row is resolved through the configured GeoIP provider and atomically upserted. PostgreSQL uses an `INET` primary key, so concurrent writes converge on one cached row.

Source code lives in `src/ip_country_api`, tests in `tests`, and schema migrations in `migrations`.

## Routes

| Route | Purpose |
|---|---|
| `GET /` | Responsive lookup UI |
| `POST /api/v1/lookups` | Resolve `{"ip":"8.8.8.8"}` |
| `GET /docs` | OpenAPI UI |
| `GET /redoc` | ReDoc UI |
| `GET /openapi.json` | OpenAPI document |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | PostgreSQL and schema readiness |
| `GET /metrics` | Prometheus metrics |

Readiness performs a bounded database query and never calls the external provider. Errors use a stable `{"error": ...}` envelope and do not expose SQL, credentials, upstream bodies, or stack traces.

## Local Python setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required. Dependencies are locked in `uv.lock`.

```bash
uv sync --frozen --all-groups
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m "unit or api" --cov
```

The application reads configuration only from process environment variables; it does not automatically load dotenv files.

## Local PostgreSQL with Compose

The included Compose stack uses isolated, explicitly non-production credentials and fake provider mode:

```bash
docker compose up --build
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready
```

The `migrate` service applies `alembic upgrade head` before the application starts. PostgreSQL is not exposed on a host port. To remove the local database volume:

```bash
docker compose down -v
```

Do not reuse the Compose credentials outside local development.

## Alembic migrations and integration tests

With an isolated PostgreSQL database:

```bash
export DATABASE_URL='postgresql+psycopg://test_user:test_password@127.0.0.1:5432/ip_country_test'
export TEST_DATABASE_URL="$DATABASE_URL"
export APP_ENV=test
export GEOIP_PROVIDER=fake

uv run alembic upgrade head
uv run alembic check
uv run pytest -m integration
```

Integration tests deliberately downgrade and upgrade only `TEST_DATABASE_URL`. Never point them at a shared or production database.

## Docker

Build from the repository root:

```bash
docker build -t arvan-ip-country-api:local .
```

Run with runtime configuration:

```bash
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges \
  -p 127.0.0.1:8080:8080 \
  -e APP_ENV=development \
  -e GEOIP_PROVIDER=fake \
  -e DATABASE_URL='postgresql+psycopg://user:password@database:5432/ip_country' \
  arvan-ip-country-api:local
```

The multi-stage image uses Python 3.12, installs frozen runtime dependencies, runs as UID/GID `10001:10001`, exposes port 8080, uses an exec-form command, and supports a read-only root filesystem.

## Environment variables

| Variable | Description |
|---|---|
| `APP_NAME`, `APP_ENV`, `APP_VERSION` | Service identity and environment |
| `APP_HOST`, `APP_PORT` | Bind address and port |
| `LOG_LEVEL`, `LOG_FORMAT` | Logging level and `json`/`console` format |
| `DATABASE_URL` | Required PostgreSQL URL; secret |
| `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | Connection-pool limits |
| `DATABASE_POOL_TIMEOUT_SECONDS` | Pool wait timeout |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | Connection timeout |
| `GEOIP_PROVIDER` | `fake` or `ipinfo` |
| `GEOIP_PROVIDER_BASE_URL` | HTTPS provider endpoint |
| `IPINFO_TOKEN` | Required only for the IPinfo provider; secret |
| `GEOIP_PROVIDER_TIMEOUT_SECONDS` | Provider timeout |
| `GEOIP_PROVIDER_MAX_RETRIES` | Bounded provider retries |
| `GEOIP_CACHE_TTL_SECONDS` | Cache lifetime |
| `METRICS_ENABLED` | Enable application metrics |
| `CORS_ALLOWED_ORIGINS` | JSON list of allowed origins |
| `TRUSTED_HOSTS` | JSON list of accepted hostnames |

Copy `.env.example` only as a reference. Keep real values in a secret manager or an ignored local file.

### Fake provider mode

Use `APP_ENV=development` or `APP_ENV=test` with `GEOIP_PROVIDER=fake`. This deterministic mode makes no external GeoIP request and is used by CI.

### IPinfo provider mode

Set `GEOIP_PROVIDER=ipinfo`, keep the default HTTPS base URL, and inject `IPINFO_TOKEN` at runtime. Production rejects fake provider mode and IPinfo mode rejects an empty token.

## Metrics and logs

Prometheus metrics cover HTTP requests, lookup source, provider calls, database operations, errors, duration, and build information. Labels use a bounded vocabulary and never contain queried IP addresses, credentials, raw URLs, or exception messages.

Structured logs propagate a bounded `X-Request-ID`, omit the queried address, redact known credential fields, and emit only non-secret configuration summaries at startup.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`, and manual dispatch. It:

- validates `uv.lock` and installs frozen dependencies;
- checks Ruff formatting and lint;
- runs strict mypy;
- runs unit/API tests with coverage without external provider calls;
- runs Alembic and integration tests against an isolated PostgreSQL service;
- builds the `linux/amd64` production image without pushing it;
- verifies the image is non-root, contains no dotenv file, starts in fake mode, and passes liveness.

CI has only `contents: read` permission and requires no repository secret.

## Releases and GHCR

`.github/workflows/release.yml` accepts immutable semantic-version tags such as:

```text
v0.1.0
```

After all quality, migration, integration, and build gates pass, it publishes:

```text
ghcr.io/afshin-flw/arvan-ip-country-api:v0.1.0
ghcr.io/afshin-flw/arvan-ip-country-api:sha-<short-commit>
```

It never publishes `latest`. The workflow uses the short-lived GitHub Actions `GITHUB_TOKEN` with only `contents: read` and `packages: write`, and attaches OCI source, revision, version, title, and description metadata.

Future releases update this application, create a new application commit, push a fast-forward update to `main`, wait for CI, and create a new immutable semantic-version tag. Existing version tags must never move.

## Secret policy

Never commit `.env`, database credentials, IPinfo tokens, GitHub tokens, SSH keys, kubeconfig, TLS private keys, database dumps, runtime volumes, or generated artifacts. `.env.example` contains variable names and empty/safe values only. Tests use explicit isolated placeholders.

## Helm deployment

The reusable chart at `deploy/helm/ip-country-api` deploys the existing immutable GHCR image. It creates a runtime Secret, runs Alembic in a pre-install/pre-upgrade hook Job, starts two non-root replicas on different nodes, exposes port 8080 through a NodePort Service, and provisions ServiceMonitor, PrometheusRule, recording-rule, SLO alert, and Grafana dashboard resources.

The application SRE observability pack adds reusable recording rules, rolling seven-day availability and latency SLOs, multi-window burn-rate alerts, and two linked dashboards for service and application analysis. The infrastructure repository owns the linked CloudNativePG and K3s dashboards. See [SRE observability](docs/sre-observability.md), the [verified metric inventory](docs/observability-metric-inventory.md), and [controlled performance validation](docs/performance-validation.md).

For the challenge environment, copy or recreate:

```text
deploy/environments/challenge/values.challenge.local.yaml
```

This file is intentionally local and ignored. It contains challenge runtime variables and must be recreated on another controller. Never commit it. The committed `values.challenge.example.yaml` contains placeholders and is used by CI for Helm lint and template validation.

For the Arvan controller, use `deploy/environments/arvan/values.arvan.local.yaml`
from the committed `values.arvan.example.yaml`, then follow
[the Arvan deployment guide](docs/arvan-deployment.md).

Manual deployment from the application repository root:

```bash
./deploy/scripts/deploy-challenge.sh
./deploy/scripts/verify-challenge.sh
python3 ./deploy/scripts/generate-observability-traffic.py --help
python3 ./deploy/scripts/verify-sre-dashboards.py --help
```

The current challenge Service uses NodePort `30080`. The application connects only to the CloudNativePG read/write Service through a `postgresql+psycopg://` URL. The Alembic hook must succeed before Helm creates or updates the application workload. Runtime values flow from the ignored local file into a Helm-managed Kubernetes Secret and then into explicit `secretKeyRef` entries.

The current release flow is:

```text
GitHub Actions
→ GHCR immutable image
→ local Helm deployment
→ K3s
```

The possible future CD flow is:

```text
GitHub release
→ GitHub-hosted deploy job
→ public K3s API
→ helm upgrade --install
```

Future CD is intentionally not implemented in this repository. It requires a public API boundary and a restricted deployment ServiceAccount.

## Troubleshooting

- If migration fails, inspect the Helm hook Job and verify the CloudNativePG read/write Service and database URL.
- If readiness fails, confirm that the migration reached `head` and the database Service is reachable.
- If real lookups fail, verify provider egress and the runtime IPinfo token without logging it.
- If monitoring targets are missing, inspect the ServiceMonitor selector and the `http` Service port.
- If the dashboard is absent, verify that Grafana's sidecar watches all namespaces for `grafana_dashboard=1`.

## Non-goals

This repository does not contain Ansible, Terraform, cluster credentials, infrastructure topology, automatic CD, or production credentials. The chart deploys only the application runtime; infrastructure lifecycle remains outside this repository.
