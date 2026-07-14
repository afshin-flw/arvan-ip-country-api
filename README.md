# IP Country API

## Architecture

FastAPI owns HTTP transport only. Typed domain models and `IPLookupService` implement validation, cache-aside ordering, TTL, and response source. `LookupRepository` abstracts persistence; its PostgreSQL implementation uses SQLAlchemy async sessions and an atomic `ON CONFLICT` upsert. `GeoIPProvider` abstracts external resolution; `IPinfoLiteProvider` reuses one lifespan-owned `httpx.AsyncClient`. The engine, HTTP client, service graph, and redacted startup logging are created and closed in application lifespan.

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
| `GEOIP_PROVIDER`, `GEOIP_PROVIDER_BASE_URL` | Provider selection and HTTPS base |
| `IPINFO_TOKEN` | Secret provider credential; required |
| `GEOIP_PROVIDER_TIMEOUT_SECONDS`, `GEOIP_PROVIDER_MAX_RETRIES` | External-call bounds |
| `GEOIP_CACHE_TTL_SECONDS` | Cache lifetime |
| `METRICS_ENABLED` | Custom metric recording |
| `CORS_ALLOWED_ORIGINS` | JSON list; empty by default |
| `TRUSTED_HOSTS` | Explicit JSON hostname list |

`.env.example` contains names and safe placeholders only. The application does not load `.env`; inject variables into the process. Required secrets fail validation when missing.

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

JSON is the runtime default. A syntactically bounded inbound `X-Request-ID` is propagated; otherwise a UUID is generated. Logs include bounded route, method, status, duration, provider/result/error fields where applicable. The queried IP is not logged. Known credential keys are redacted, and startup logs only the explicit non-secret summary.

## Testing

```bash
uv sync --frozen --all-groups
uv run pytest -m "unit or api" --cov
TEST_DATABASE_URL='postgresql+psycopg://…' uv run pytest -m integration
```

The first command set requires no services. Integration tests downgrade/upgrade only the explicitly supplied isolated test database. All provider tests use fakes or `httpx.MockTransport`; never provide a real token.

## Docker

```bash
docker build -t ip-country-api:phase-1 .
docker run --read-only --tmpfs /tmp --user 10001:10001 \
  -e DATABASE_URL -e IPINFO_TOKEN -p 8000:8000 ip-country-api:phase-1
```

The multi-stage image installs runtime dependencies from `uv.lock`, contains no package manager or development group, uses exec-form Python startup, handles SIGTERM through Uvicorn, and stores no local persistent state.

## Troubleshooting

- Startup validation errors: supply both secrets and ensure the database URL is PostgreSQL.
- Readiness says schema unavailable: run the explicit Alembic migration.
- Readiness says database unavailable: check network/DNS, credentials, failover endpoint, and pool timeout.
- Provider errors: verify the injected token, outbound connectivity, configured HTTPS base URL, and rate limits without logging the credential.
- Trusted-host rejection: add only the required hostname to `TRUSTED_HOSTS`; do not use a wildcard in production.
