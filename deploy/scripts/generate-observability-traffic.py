#!/usr/bin/env python3
"""Generate bounded dashboard-population traffic with the Python standard library."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Result:
    base_url: str
    category: str
    status: int
    latency_seconds: float
    expected: bool
    error: str | None = None


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def request_for(
    index: int, base_url: str, cached_ip: str
) -> tuple[urllib.request.Request, str, set[int]]:
    bucket = index % 100
    headers = {"Accept": "application/json", "User-Agent": "arvan-observability-traffic/1.0"}
    if bucket < 85:
        body = json.dumps({"ip": cached_ip}).encode()
        headers["Content-Type"] = "application/json"
        return (
            urllib.request.Request(
                f"{base_url}/api/v1/lookups", data=body, headers=headers, method="POST"
            ),
            "cached_lookup",
            {200},
        )
    if bucket < 95:
        return urllib.request.Request(f"{base_url}/", headers=headers), "root", {200}
    if bucket < 98:
        path = "/health/live" if index % 2 else "/health/ready"
        return urllib.request.Request(f"{base_url}{path}", headers=headers), "health", {200}
    body = json.dumps({"ip": "not-an-ip"}).encode()
    headers["Content-Type"] = "application/json"
    return (
        urllib.request.Request(
            f"{base_url}/api/v1/lookups", data=body, headers=headers, method="POST"
        ),
        "expected_4xx",
        {400, 422},
    )


def execute(index: int, base_urls: list[str], cached_ip: str, timeout: float) -> Result:
    base_url = base_urls[index % len(base_urls)].rstrip("/")
    request, category, expected_statuses = request_for(index, base_url, cached_ip)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            status = response.status
            return Result(
                base_url,
                category,
                status,
                time.perf_counter() - started,
                status in expected_statuses,
            )
    except urllib.error.HTTPError as exc:
        exc.read()
        return Result(
            base_url,
            category,
            exc.code,
            time.perf_counter() - started,
            exc.code in expected_statuses,
        )
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        return Result(
            base_url, category, 0, time.perf_counter() - started, False, type(exc).__name__
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", action="append", required=True, help="repeat to distribute traffic"
    )
    parser.add_argument("--requests", type=int, default=1500)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--cached-ip", default="208.67.222.222")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    if args.requests < 1 or args.requests > 10_000:
        parser.error("--requests must be between 1 and 10000")
    if args.concurrency < 1 or args.concurrency > 100:
        parser.error("--concurrency must be between 1 and 100")
    if args.timeout <= 0 or args.timeout > 30:
        parser.error("--timeout must be greater than zero and at most 30 seconds")
    if any(urllib.parse.urlparse(url).scheme not in {"http", "https"} for url in args.base_url):
        parser.error("--base-url supports only http and https URLs")
    return args


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(
            executor.map(
                lambda index: execute(index, args.base_url, args.cached_ip, args.timeout),
                range(args.requests),
            )
        )
    duration = time.perf_counter() - started
    latencies = [item.latency_seconds for item in results]
    category_counts = Counter(item.category for item in results)
    status_counts = Counter(str(item.status) for item in results)
    base_url_counts = Counter(item.base_url for item in results)
    unexpected = [item for item in results if not item.expected]
    expected_4xx = sum(item.category == "expected_4xx" and item.expected for item in results)
    summary = {
        "profile": "controlled dashboard-population and functional performance traffic",
        "requests": len(results),
        "concurrency": args.concurrency,
        "duration_seconds": duration,
        "throughput_requests_per_second": len(results) / duration,
        "latency_seconds": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "successful_requests": sum(item.expected for item in results),
        "expected_4xx_responses": expected_4xx,
        "unexpected_failures": len(unexpected),
        "categories": dict(sorted(category_counts.items())),
        "status_codes": dict(sorted(status_counts.items())),
        "base_urls": dict(sorted(base_url_counts.items())),
    }
    if unexpected:
        summary["unexpected_failure_samples"] = [asdict(item) for item in unexpected[:10]]
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
