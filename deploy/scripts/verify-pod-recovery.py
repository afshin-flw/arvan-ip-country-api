#!/usr/bin/env python3
"""Delete one application Pod while continuously checking cached lookups."""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--ssh-user", default="ubuntu")
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--namespace", default="ip-country-api")
    parser.add_argument("--selector", default="app.kubernetes.io/instance=ip-country-api")
    parser.add_argument("--base-url", action="append", required=True)
    parser.add_argument("--cached-ip", default="45.33.32.156")
    parser.add_argument("--request-interval", type=float, default=0.05)
    parser.add_argument("--request-timeout", type=float, default=3.0)
    parser.add_argument("--recovery-timeout", type=float, default=180.0)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Cluster:
    def __init__(self, args: argparse.Namespace) -> None:
        self.prefix = [
            "ssh",
            "-i",
            str(args.ssh_key),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={args.known_hosts}",
            f"{args.ssh_user}@{args.ssh_host}",
            "sudo",
            "k3s",
            "kubectl",
        ]

    def run(self, *arguments: str) -> str:
        completed = subprocess.run(
            [*self.prefix, *arguments],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout


def pod_inventory(cluster: Cluster, namespace: str, selector: str) -> list[dict[str, Any]]:
    payload = json.loads(
        cluster.run("-n", namespace, "get", "pods", "-l", selector, "-o", "json")
    )
    pods = []
    for item in payload["items"]:
        statuses = item.get("status", {}).get("containerStatuses", [])
        pods.append(
            {
                "name": item["metadata"]["name"],
                "node": item.get("spec", {}).get("nodeName"),
                "phase": item.get("status", {}).get("phase"),
                "ready": bool(statuses)
                and all(status.get("ready", False) for status in statuses)
                and not item["metadata"].get("deletionTimestamp"),
            }
        )
    return sorted(pods, key=lambda pod: pod["name"])


def main() -> int:
    args = parse_args()
    cluster = Cluster(args)
    before = pod_inventory(cluster, args.namespace, args.selector)
    ready_before = [pod for pod in before if pod["ready"]]
    if len(ready_before) != 2 or len({pod["node"] for pod in ready_before}) != 2:
        raise RuntimeError(f"expected two Ready Pods on distinct nodes, got {ready_before}")

    deleted = ready_before[0]
    stop = threading.Event()
    lock = threading.Lock()
    status_codes: collections.Counter[str] = collections.Counter()
    failures: collections.Counter[str] = collections.Counter()

    def send_requests() -> None:
        request_number = 0
        while not stop.is_set():
            base_url = args.base_url[request_number % len(args.base_url)].rstrip("/")
            request_number += 1
            url = f"{base_url}/api/v1/lookups"
            request = urllib.request.Request(
                url,
                data=json.dumps({"ip": args.cached_ip}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=args.request_timeout) as response:
                    code = response.status
                    response.read()
                with lock:
                    status_codes[str(code)] += 1
                    if code != 200:
                        failures[f"HTTP {code}"] += 1
            except urllib.error.HTTPError as exc:
                with lock:
                    status_codes[str(exc.code)] += 1
                    failures[f"HTTP {exc.code}"] += 1
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                with lock:
                    failures[type(exc).__name__] += 1
            stop.wait(args.request_interval)

    traffic = threading.Thread(target=send_requests, daemon=True)
    traffic.start()
    started_at = utc_now()
    started = time.monotonic()
    cluster.run(
        "-n",
        args.namespace,
        "delete",
        "pod",
        deleted["name"],
        "--wait=false",
    )

    recovered = False
    after: list[dict[str, Any]] = []
    while time.monotonic() - started < args.recovery_timeout:
        after = pod_inventory(cluster, args.namespace, args.selector)
        ready_after = [pod for pod in after if pod["ready"]]
        names = {pod["name"] for pod in after}
        if (
            len(ready_after) == 2
            and deleted["name"] not in names
            and any(pod["name"] not in {item["name"] for item in before} for pod in ready_after)
        ):
            recovered = True
            break
        time.sleep(0.5)

    recovery_seconds = time.monotonic() - started
    time.sleep(2.0)
    stop.set()
    traffic.join(timeout=args.request_timeout + 2.0)
    ready_after = [pod for pod in after if pod["ready"]]
    replacement = next(
        (pod for pod in ready_after if pod["name"] not in {item["name"] for item in before}),
        None,
    )
    unexpected_failures = sum(failures.values())
    result = {
        "started_at": started_at,
        "completed_at": utc_now(),
        "deleted_pod": deleted,
        "replacement_pod": replacement,
        "recovery_seconds": recovery_seconds,
        "before": before,
        "after": after,
        "ready_replicas_after": len(ready_after),
        "distinct_nodes_after": len({pod["node"] for pod in ready_after}),
        "requests": sum(status_codes.values()) + unexpected_failures,
        "status_codes": dict(sorted(status_codes.items())),
        "failure_types": dict(sorted(failures.items())),
        "unexpected_failures": unexpected_failures,
        "recovered": recovered,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if recovered and unexpected_failures == 0 and len(ready_after) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
