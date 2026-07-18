# SRE observability pack

## Architecture

```text
Application metrics
→ ServiceMonitor
→ Prometheus
→ recording rules
→ seven-day SLO and burn rates
→ Grafana dashboards
→ Alertmanager
```

Helm and Git are authoritative for the application monitoring resources. The Grafana sidecar watches all namespaces for ConfigMaps labeled `grafana_dashboard=1`; the dashboards use the existing `prometheus` datasource UID. The service overview ConfigMap targets `00 — SRE Overview`; the application overview and performance ConfigMaps target `08 — Application`. The infrastructure monitoring foundation enables `foldersFromFilesStructure`, so these target directories become real Grafana folders.

## Dashboards

- **Arvan Challenge — SRE Service Overview** is the incident and presentation entry point. It answers service health, user errors, latency, error-budget, dependency, and topology questions.
- **IP Country API — Performance Deep Dive** is for application engineers. It drills into routes, status codes, Pods, cache behavior, provider/database latency, and runtime resources.
- **CloudNativePG — SRE and Performance** is linked from the application dashboards but provisioned and owned by the infrastructure repository.
- **K3s — Reliability and Capacity** is linked from the application dashboards but provisioned and owned by the infrastructure repository.

Each dashboard links to the other three and complements rather than replaces the existing K3s, PostgreSQL, and application overview dashboards.

## SLO model

- Availability objective: **99.5%**.
- Latency objective: **95% below 500 ms**.
- Window: rolling **7 days**.
- Availability bad events: HTTP 5xx responses for `route="/api/v1/lookups"`.
- Latency bad events: eligible lookup requests above the histogram bucket `le="0.5"`.

Health and metrics endpoints are outside the request instrumentation. Root-page and unmatched-route traffic are explicitly excluded by the lookup route selector. Expected 4xx validation responses are not availability errors. Rules require observed eligible traffic before producing an SLI, preventing an idle service from being reported as perfectly healthy.

Availability burn rate divides the observed 5xx ratio by `1 - 0.995 = 0.005`. Latency burn rate divides the over-500-ms ratio by `1 - 0.95 = 0.05`. Budget-consumed series may exceed one; budget-remaining series are clamped at zero.

## Availability burn alerts

- `IPCountryAPIAvailabilityFastBurn`: 5m and 1h burn rates above 14.4 for 2 minutes; critical.
- `IPCountryAPIAvailabilitySlowBurn`: 1h and 6h burn rates above 3 for 15 minutes; warning.

Check current API 5xx responses, recent releases, Pod readiness, database readiness, and dependency failures. Preserve evidence before restarting anything. A 4xx validation response is not an availability failure.

## Latency burn alerts

- `IPCountryAPILatencyFastBurn`: 5m and 1h burn rates above 14.4 for 2 minutes; critical.
- `IPCountryAPILatencySlowBurn`: 1h and 6h burn rates above 3 for 15 minutes; warning.

Compare application p95/p99 with provider and database p95, then inspect CPU throttling, memory, PostgreSQL connections/replication, and node saturation. Do not infer a capacity limit from the controlled challenge traffic.

## Validation

Generate bounded traffic with `deploy/scripts/generate-observability-traffic.py`, then expose the Prometheus service through a temporary local SSH port-forward and run:

```bash
python3 deploy/scripts/verify-sre-dashboards.py \
  --prometheus-url http://127.0.0.1:19090 \
  --output-json deploy/results/sre-dashboard-validation.json
```

The validator parses the application dashboard directory and any repeated infrastructure `--dashboard-dir` arguments, renders known Helm/Grafana variables with live challenge values, checks every PromQL expression, rejects API/parse errors, rejects NaN/Inf, and rejects unexplained empty results.

## Limitations

- Prometheus retention is seven days, and the application has not existed for a complete seven-day observation period.
- Current traffic is synthetic challenge traffic, not production traffic or a capacity benchmark.
- There is no distributed tracing or log aggregation/correlation.
- IPinfo cache misses are intentionally limited.
- Some desired PostgreSQL lock and long-transaction instrumentation is absent and therefore omitted.
