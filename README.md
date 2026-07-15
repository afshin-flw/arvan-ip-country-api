# IP Country API

## Architecture

FastAPI owns HTTP transport only. Typed domain models and `IPLookupService` implement validation, cache-aside ordering, TTL, and response source. `LookupRepository` abstracts persistence; its PostgreSQL implementation uses SQLAlchemy async sessions and an atomic `ON CONFLICT` upsert. `GeoIPProvider` abstracts resolution. `FakeGeoIPProvider` provides deterministic, network-free development fixtures, while `IPinfoLiteProvider` reuses one lifespan-owned `httpx.AsyncClient`. The engine, optional HTTP client, service graph, and redacted startup logging are created and closed in application lifespan.

## API and errors

`POST /api/v1/lookups` accepts `{"ip":"8.8.8.8"}` and returns normalized IP, ISO-like country code, country name, `database` or `provider` source, and UTC fetched/expiry timestamps. `/docs`, `/redoc`, and `/openapi.json` expose the typed contract.

Errors use `{"error":{"code":"...","message":"...","request_id":"..."}}`. Stable codes are `INVALID_IP`, `NON_PUBLIC_IP`, `DATABASE_UNAVAILABLE`, `DATABASE_SCHEMA_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `PROVIDER_AUTHENTICATION_FAILED`, `PROVIDER_RATE_LIMITED`, `PROVIDER_INVALID_RESPONSE`, `PROVIDER_UNAVAILABLE`, and `INTERNAL_ERROR`. Responses never contain SQL, connection details, raw upstream bodies, stack traces, or internal exception messages.

## Cache-aside behavior and schema

The service normalizes a global address with `ipaddress`, reads PostgreSQL, and returns an unexpired row without changing it. Missing or expired rows call the provider, calculate expiry from `GEOIP_CACHE_TTL_SECONDS`, atomically upsert, and return provider source. The `ip_lookup_cache` migration uses PostgreSQL `INET` as its primary key, `VARCHAR` country/provider fields, timezone-aware timestamps, and an expiry index.

The primary key prevents duplicates across replicas. Multiple simultaneous cache misses can still make multiple external calls; they safely converge on one row. There is intentionally no distributed lock, background refresh, stale-if-error, or preloaded global dataset.

## Environment reference

| Variable | Purpose |
|---|---|
| `APP_NAME`, `APP_ENV`, `APP_VERSION` | Identity and safe build metadata |
| `APP_HOST`, `APP_PORT` | Listen address and port |
| `LOG_LEVEL`, `LOG_FORMAT` | Logging threshold and `json`/`console` renderer |
| `DATABASE_URL` | Secret PostgreSQL/psycopg URL; required |
| `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | Bounded per-process pool |
| `DATABASE_POOL_TIMEOUT_SECONDS`, `DATABASE_CONNECT_TIMEOUT_SECONDS` | Database bounds |
| `GEOIP_PROVIDER`, `GEOIP_PROVIDER_BASE_URL` | `fake` for non-production local testing or `ipinfo`; HTTPS provider base |
| `IPINFO_TOKEN` | Secret provider credential; required only for `ipinfo` |
| `GEOIP_PROVIDER_TIMEOUT_SECONDS`, `GEOIP_PROVIDER_MAX_RETRIES` | External-call bounds |
| `GEOIP_CACHE_TTL_SECONDS` | Cache lifetime |
| `METRICS_ENABLED` | Custom metric recording |
| `CORS_ALLOWED_ORIGINS` | JSON list; empty by default |
| `TRUSTED_HOSTS` | Explicit JSON hostname list |

`.env.example` contains names and safe placeholders only. The application receives configuration from process environment variables. Local scripts explicitly source the ignored `.env.local`; the application never loads it implicitly. `ipinfo` fails validation without its token, and the fake provider fails validation in production mode.

## Local environment and PostgreSQL

Use the project-local environment; do not install packages globally:

```bash
cd /home/arvan/app
uv sync --all-groups
cd ..
./scripts/setup-local-postgres.sh
```

The setup script creates or safely reuses only `arvan_ip_country_app` and `arvan_ip_country_dev`, verifies the role is non-superuser, and writes the generated local credential to mode-0600 `.env.local` without printing it. Both `.venv` and `.env.local` must remain untracked.

Formal local runtime commands are:

```bash
cd /home/arvan/app
uv sync --all-groups
set -a; source .env.local; set +a
uv run alembic upgrade head
uv run uvicorn ip_country_api.main:app --host 0.0.0.0 --port 8080
```

From the repository root, `scripts/smoke-no-db.sh` proves graceful disconnected behavior and `scripts/smoke-db.sh` proves readiness, provider-to-database cache transition, row count, and metric samples.

## Migrations

Migrations are an explicit operational action:

```bash
uv run alembic upgrade head
uv run alembic check
```

Application replicas never migrate. A future Kubernetes release will use a dedicated migration Job or release hook.

## Health and metrics

`GET /health/live` is process-only. `GET /health/ready` executes a timeout-bounded query against `ip_lookup_cache`, distinguishing database from schema unavailability and never calling IPinfo.

`GET /metrics` exposes:

- `ip_country_http_requests_total` (`method`, `route`, `status_code`)
- `ip_country_http_request_duration_seconds` (`method`, `route`)
- `ip_country_lookup_total` (`source`, `result`)
- `ip_country_provider_requests_total` (`provider`, `result`)
- `ip_country_provider_request_duration_seconds` (`provider`)
- `ip_country_provider_errors_total` (`provider`, `error_type`)
- `ip_country_database_operations_total` (`operation`)
- `ip_country_database_operation_duration_seconds` (`operation`)
- `ip_country_database_errors_total` (`operation`, `error_type`)
- `ip_country_build_info` (`version`)

IP addresses, countries, request IDs, exception messages, raw URLs, and environment values are forbidden labels. Health and metrics traffic is excluded from application request metrics.

## Logging and correlation

JSON is the runtime default. A syntactically bounded inbound `X-Request-ID` is propagated; otherwise a UUID is generated. Logs include bounded route, method, status, duration, `lookup_source` (`provider` or `database`), and provider/result/error fields where applicable. The queried IP is not logged. Known credential keys are redacted, and startup logs only the explicit non-secret summary.

## Testing

```bash
uv sync --frozen --all-groups
uv run pytest -m "unit or api" --cov
TEST_DATABASE_URL='postgresql+psycopg://…' uv run pytest -m integration
```

The first command set requires no services. Integration tests downgrade/upgrade only the explicitly supplied isolated test database. All provider tests use fakes or `httpx.MockTransport`; never provide a real token.

## Dependency groups

Runtime dependencies are FastAPI/Uvicorn for HTTP, Pydantic Settings for configuration, SQLAlchemy/psycopg/Alembic for PostgreSQL and migrations, HTTPX/tenacity for bounded provider calls, prometheus-client for metrics, structlog for JSON logs, and Jinja2 for the local UI. The development group contains pytest, pytest-asyncio, pytest-cov, Ruff, and mypy. `pyproject.toml` and `uv.lock` are canonical; no global or handwritten requirements installation is supported.

## Docker

```bash
cd /home/arvan
docker build -f app/Dockerfile -t ip-country-api:phase-1.5 .
docker run --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges --user 10001:10001 \
  -e DATABASE_URL -e IPINFO_TOKEN -p 8080:8080 ip-country-api:phase-1.5
```

The multi-stage image installs runtime dependencies from `uv.lock`, contains no package manager or development group, uses exec-form Python startup, handles SIGTERM through Uvicorn, and stores no local persistent state.

The container contract is port 8080, liveness `/health/live`, readiness `/health/ready`, and Prometheus scrape path `/metrics`. Alembic remains an explicit command and will later run in a dedicated Kubernetes Job. Runtime configuration will later be split between ConfigMap and Secret.

## Persistent Docker demo

The repository-level demo uses the already validated `ip-country-api:phase-1.5` image, `postgres:17.6-bookworm`, the private `arvan_ip_country_network`, and the persistent `arvan_ip_country_postgres_data` volume. PostgreSQL is not published on a host port. Its initializer creates `arvan_ip_country_app` as a login role without superuser, database-creation, role-creation, or replication privileges and makes it owner of the dedicated `arvan_ip_country` database.

From `/home/arvan`:

```bash
make demo-up
make demo-test
make demo-status
make demo-logs
make demo-restart
make demo-down       # preserves PostgreSQL data
make demo-start      # starts again from the same volume
```

`demo-up` creates the ignored mode-0600 `app/.env.docker.local` when absent, starts PostgreSQL, runs `python -m alembic upgrade head` in a one-off application container, starts the API, and waits for readiness. It uses `GEOIP_PROVIDER=fake`, so no IPinfo token or external provider request is involved. `demo-test` verifies the UI, Swagger, ReDoc, probes, metrics, a provider-to-database cache transition, one normalized row, and bounded metric labels.

Access URLs are `http://127.0.0.1:8080/`, `/docs`, `/redoc`, `/health/live`, `/health/ready`, and `/metrics`. For an SSH tunnel, run `ssh -L 18080:127.0.0.1:8080 <user>@<server>` and browse to `http://127.0.0.1:18080/`.

Normal demo operations never delete the named volume. The explicit destructive reset is `docker compose --project-name arvan-ip-country --env-file app/.env.docker.local -f app/compose.yaml down -v`; do not use it when cached demo data must survive.

## Helm deployment contract

The application-only Helm chart is maintained at `deploy/helm/ip-country-api`. It injects safe settings through a ConfigMap, references `DATABASE_URL` and `IPINFO_TOKEN` from an existing Secret, runs Alembic in an explicit Helm hook Job, and deploys the web process without migration privileges or local persistence. See `docs/operations/helm-chart.md` for local rendering and installation guidance.

## Troubleshooting

- Startup validation errors: supply `DATABASE_URL`; supply `IPINFO_TOKEN` only for IPinfo, and never select the fake provider in production.
- Readiness says schema unavailable: run the explicit Alembic migration.
- Readiness says database unavailable: check network/DNS, credentials, failover endpoint, and pool timeout.
- Provider errors: verify the injected token, outbound connectivity, configured HTTPS base URL, and rate limits without logging the credential.
- Trusted-host rejection: add only the required hostname to `TRUSTED_HOSTS`; do not use a wildcard in production.
