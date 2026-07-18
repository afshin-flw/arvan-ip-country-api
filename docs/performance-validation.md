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

The 2026-07-18 Arvan run used all three public NodePort addresses, 1,500
requests, concurrency 20, and cached IP `45.33.32.156`. It completed in
12.421 seconds at 120.762 requests/second. Client-side latency was 0.122
seconds p50, 0.407 seconds p95, and 0.665 seconds p99.

- 1,470 requests returned HTTP 200.
- 30 intentionally invalid requests returned the expected HTTP 422.
- 1,275 requests exercised the cached lookup path, with 150 root, 45 health,
  and 30 validation requests completing the bounded mix.
- There were zero unexpected HTTP or transport failures.

The cache-flow gate used a separate fresh IP: the first request returned
`source=provider`, the second returned `source=database`, and exactly one row
was present afterward. Prometheus observed one provider success and one
database hit for that gate. This is challenge evidence, not a production load
test or a capacity claim.

The availability recovery gate continuously sent 163 cached lookup requests
while one application Pod was deleted. All 163 returned HTTP 200; the
replacement became Ready in 8.575 seconds, and the two Ready replicas again
occupied distinct nodes.
