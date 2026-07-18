#!/usr/bin/env python3
"""Validate every dashboard PromQL expression through the live Prometheus API."""

from __future__ import annotations

import argparse
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_DASHBOARD_DIR = (
    Path(__file__).resolve().parents[1] / "helm" / "ip-country-api" / "dashboards"
)

SUBSTITUTIONS = {
    "arvan-challenge-sre-overview": {},
    "ip-country-api-performance": {
        "${namespace:regex}": "ip-country-api",
        "${pod:regex}": ".*",
        "${route:regex}": ".*",
        "${status_code:regex}": ".*",
    },
    "cloudnativepg-sre-performance": {
        "${namespace:regex}": "database",
        "${cluster:regex}": "ip-country-postgres",
        "${instance:regex}": ".*",
        "${database:regex}": "ip_country",
    },
    "k3s-reliability-capacity": {
        "${node:regex}": ".*",
        "${namespace:regex}": ".*",
        "${workload:regex}": ".*",
    },
}

GENERIC_VARIABLES = {
    "cluster": ".*",
    "instance": ".*",
    "integration": ".*",
    "job": ".*",
    "namespace": ".*",
    "node": ".*",
    "pod": ".*",
    "route": ".*",
    "service": ".*",
    "status_code": ".*",
    "type": ".*",
    "volume": ".*",
    "workload": ".*",
}

@dataclass(frozen=True, slots=True)
class Check:
    dashboard: str
    panel: str
    expression: str
    valid: bool
    useful: bool
    legitimate_zero: bool
    empty_allowed: bool
    finite: bool
    error: str | None = None


def iter_panels(payload: Any) -> Iterator[dict[str, Any]]:
    if isinstance(payload, dict):
        if "targets" in payload and "title" in payload:
            yield payload
        for value in payload.values():
            yield from iter_panels(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from iter_panels(value)


def values_from_result(data: dict[str, Any]) -> list[float]:
    result_type = data.get("resultType")
    result = data.get("result")
    raw_values: list[str] = []
    if result_type in {"scalar", "string"} and isinstance(result, list) and len(result) == 2:
        raw_values.append(str(result[1]))
    elif isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            if "value" in item:
                raw_values.append(str(item["value"][1]))
            for value in item.get("values", []):
                raw_values.append(str(value[1]))
    parsed = []
    for value in raw_values:
        try:
            parsed.append(float(value))
        except ValueError:
            continue
    return parsed


def prometheus_query(base_url: str, expression: str, timeout: float) -> dict[str, Any]:
    body = urllib.parse.urlencode({"query": expression}).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/query",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "arvan-dashboard-validator/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def render_expression(uid: str, expression: str, namespace: str) -> str:
    rendered = expression.replace("__APP_NAMESPACE__", namespace).replace("$__rate_interval", "5m")
    for before, after in SUBSTITUTIONS.get(uid, {}).items():
        rendered = rendered.replace(before, after)
    for name, value in GENERIC_VARIABLES.items():
        # Validate the data behind a Grafana selection across every available
        # value. Exact-match template variables must change operator as well as
        # value; rendering `instance=".*"` would search for a literal instance
        # named `.*` and report a false empty result.
        for token in (f"${{{name}}}", f"${name}"):
            rendered = rendered.replace(f'=~"{token}"', f'=~"{value}"')
            rendered = rendered.replace(f'="{token}"', f'=~"{value}"')
        for token in (f"${{{name}:regex}}", f"${{{name}}}", f"${name}"):
            rendered = rendered.replace(token, value)
    return rendered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:19090")
    parser.add_argument("--namespace", default="ip-country-api")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--dashboard-dir",
        action="append",
        type=Path,
        help="dashboard directory to validate; repeat for application and infrastructure sources",
    )
    args = parser.parse_args()
    if urllib.parse.urlparse(args.prometheus_url).scheme not in {"http", "https"}:
        parser.error("--prometheus-url supports only http and https URLs")
    return args


def main() -> int:
    args = parse_args()
    checks: list[Check] = []
    dashboard_counts: dict[str, int] = {}
    dashboard_dirs = args.dashboard_dir or [DEFAULT_DASHBOARD_DIR]
    paths = sorted({path for directory in dashboard_dirs for path in directory.rglob("*.json")})
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        uid = payload["uid"]
        count = 0
        for panel_payload in iter_panels(payload):
            panel_title = str(panel_payload["title"])
            for target in panel_payload.get("targets", []):
                expression = target.get("expr")
                if not expression:
                    continue
                count += 1
                rendered = render_expression(uid, expression, args.namespace)
                allow_empty = bool(target.get("validationAllowEmpty", False))
                try:
                    response = prometheus_query(args.prometheus_url, rendered, args.timeout)
                    if response.get("status") != "success":
                        checks.append(
                            Check(
                                uid,
                                panel_title,
                                rendered,
                                False,
                                False,
                                False,
                                allow_empty,
                                False,
                                response.get("error", "Prometheus API error"),
                            )
                        )
                        continue
                    values = values_from_result(response["data"])
                    finite = all(math.isfinite(value) for value in values)
                    has_data = bool(values) and finite
                    zero = has_data and all(value == 0 for value in values)
                    checks.append(
                        Check(
                            uid,
                            panel_title,
                            rendered,
                            True,
                            has_data,
                            zero,
                            allow_empty,
                            finite,
                            None if has_data or allow_empty else "empty result",
                        )
                    )
                except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                    checks.append(
                        Check(
                            uid,
                            panel_title,
                            rendered,
                            False,
                            False,
                            False,
                            allow_empty,
                            False,
                            type(exc).__name__,
                        )
                    )
        dashboard_counts[uid] = count

    invalid = [item for item in checks if not item.valid]
    empty = [item for item in checks if item.valid and not item.useful]
    unexplained_empty = [item for item in empty if not item.empty_allowed]
    non_finite = [item for item in checks if not item.finite]
    summary = {
        "dashboards": dashboard_counts,
        "total_expressions": len(checks),
        "valid_expressions": sum(item.valid for item in checks),
        "useful_data_expressions": sum(item.useful for item in checks),
        "legitimate_zero_results": sum(item.legitimate_zero for item in checks),
        "empty_expressions": len(empty),
        "allowed_empty_expressions": sum(item.empty_allowed for item in empty),
        "unexplained_empty_expressions": len(unexplained_empty),
        "parse_or_api_errors": len(invalid),
        "non_finite_expressions": len(non_finite),
    }
    summary["dashboard_results"] = {
        uid: {
            "total": len(items),
            "useful": sum(item.useful for item in items),
            "legitimate_zero": sum(item.legitimate_zero for item in items),
            "unexplained_empty": sum(
                item.valid and not item.useful and not item.empty_allowed for item in items
            ),
            "api_errors": sum(not item.valid for item in items),
            "non_finite": sum(not item.finite for item in items),
        }
        for uid in sorted(dashboard_counts)
        for items in [[item for item in checks if item.dashboard == uid]]
    }
    if invalid or unexplained_empty or non_finite:
        summary["failures"] = [
            asdict(item) for item in (invalid + unexplained_empty + non_finite)
        ]
    rendered_summary = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered_summary)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered_summary + "\n", encoding="utf-8")
    return 1 if invalid or unexplained_empty or non_finite else 0


if __name__ == "__main__":
    raise SystemExit(main())
