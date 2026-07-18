# Controlled performance validation

This procedure generates **controlled dashboard-population and functional performance traffic**. It is not a maximum-capacity benchmark.

## Profile

The default bounded profile sends 1,500 requests with concurrency 20 across all three NodePort addresses:

- approximately 85% valid lookups for the already cached IP;
- approximately 10% root-page requests;
- approximately 3% liveness/readiness requests;
- approximately 2% invalid lookup requests that should return 4xx;
- no intentional 5xx traffic.

```bash
python3 deploy/scripts/generate-observability-traffic.py \
  --base-url http://188.121.120.245:30080 \
  --base-url http://37.152.186.253:30080 \
  --base-url http://95.38.235.15:30080 \
  --requests 1500 \
  --concurrency 20 \
  --cached-ip 208.67.222.222 \
  --timeout 5 \
  --output-json deploy/results/observability-traffic.json
```

The script reports total and successful requests, expected 4xx responses, unexpected failures, duration, throughput, and client-side p50/p95/p99 latency. It exits non-zero for any unexpected status or transport failure.

## Evidence gates

Before and after traffic, compare per-Pod HTTP counters, cache-hit counters, provider counters, CPU, memory, restarts, target health, CNPG health, and SLO alerts. The provider count must not increase during cached traffic. At most one separately selected fresh-IP request may be used to populate the provider path.

The application was deployed recently. Seven-day recording rules use seven-day rolling ranges, but only currently available Prometheus history contributes; results are not a complete seven-day production observation period.

## Interpretation limits

- Synthetic traffic does not represent production users or internet distributions.
- The result does not establish maximum throughput, saturation, or safe production capacity.
- Cache-heavy traffic intentionally emphasizes the normal PostgreSQL-hit path and avoids IPinfo abuse.
- No tracing or log correlation is available for per-request breakdowns.

## Latest challenge evidence

Record the Arvan execution evidence here only after the three public NodePort addresses, cache flow, Prometheus counters, and SLO series have been verified. Historical laboratory-cluster measurements are intentionally not reused as Arvan evidence.
