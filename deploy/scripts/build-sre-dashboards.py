#!/usr/bin/env python3
"""Build the version-controlled Grafana SRE dashboard pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "helm" / "ip-country-api" / "dashboards"
DATASOURCE = {"type": "prometheus", "uid": "prometheus"}
APP_NS = "__APP_NAMESPACE__"

DASHBOARD_LINKS = [
    ("SRE Service Overview", "arvan-challenge-sre-overview"),
    ("API Performance", "ip-country-api-performance"),
    ("CloudNativePG", "cloudnativepg-sre-performance"),
    ("K3s Reliability", "k3s-reliability-capacity"),
]


def query(expr: str, legend: str = "", *, allow_empty: bool = False) -> dict[str, Any]:
    target: dict[str, Any] = {
        "datasource": DATASOURCE,
        "expr": expr,
        "legendFormat": legend,
        "refId": "A",
    }
    if allow_empty:
        target["validationAllowEmpty"] = True
    return target


def queries(*items: tuple[str, str]) -> list[dict[str, Any]]:
    result = []
    for index, (expr, legend) in enumerate(items):
        target = query(expr, legend)
        target["refId"] = chr(ord("A") + index)
        result.append(target)
    return result


def panel(
    title: str,
    expr: str | None = None,
    *,
    kind: str = "timeseries",
    unit: str = "short",
    width: int = 8,
    height: int = 7,
    legend: str = "",
    description: str,
    targets: list[dict[str, Any]] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    thresholds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {"unit": unit}
    if min_value is not None:
        defaults["min"] = min_value
    if max_value is not None:
        defaults["max"] = max_value
    if thresholds:
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}
    options: dict[str, Any] = {}
    if kind == "timeseries":
        options = {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        }
    elif kind in {"stat", "gauge"}:
        options = {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "value",
            "graphMode": "area",
        }
    item: dict[str, Any] = {
        "type": kind,
        "title": title,
        "description": description,
        "datasource": DATASOURCE,
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": options,
        "gridPos": {"x": 0, "y": 0, "w": width, "h": height},
        "targets": targets if targets is not None else [query(expr or "vector(0)", legend)],
    }
    return item


def variable(name: str, expression: str, current: str, label: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "label": label or name.title(),
        "type": "query",
        "datasource": DATASOURCE,
        "query": {"query": expression, "refId": "StandardVariableQuery"},
        "definition": expression,
        "current": {"selected": False, "text": current, "value": current},
        "includeAll": True,
        "allValue": ".*",
        "multi": True,
        "refresh": 1,
        "sort": 1,
    }


class Layout:
    def __init__(self) -> None:
        self.panels: list[dict[str, Any]] = []
        self.y = 0
        self.panel_id = 1

    def row(self, title: str, description: str, items: list[dict[str, Any]]) -> None:
        self.panels.append(
            {
                "id": self.panel_id,
                "type": "row",
                "title": title,
                "description": description,
                "collapsed": False,
                "panels": [],
                "gridPos": {"x": 0, "y": self.y, "w": 24, "h": 1},
            }
        )
        self.panel_id += 1
        self.y += 1
        x = 0
        row_height = 0
        for item in items:
            width = item["gridPos"]["w"]
            height = item["gridPos"]["h"]
            if x + width > 24:
                self.y += row_height
                x = 0
                row_height = 0
            item["id"] = self.panel_id
            self.panel_id += 1
            item["gridPos"].update({"x": x, "y": self.y})
            self.panels.append(item)
            x += width
            row_height = max(row_height, height)
        self.y += row_height


def dashboard(
    uid: str, title: str, description: str, layout: Layout, variables: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "annotations": {"list": []},
        "description": description,
        "editable": False,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [
            {
                "asDropdown": False,
                "includeVars": False,
                "keepTime": False,
                "tags": [],
                "targetBlank": False,
                "title": "Active alerts",
                "type": "link",
                "url": "/alerting/list?view=state",
            },
        ]
        + [
            {
                "asDropdown": False,
                "includeVars": True,
                "keepTime": True,
                "tags": [],
                "targetBlank": False,
                "title": label,
                "type": "link",
                "url": f"/d/{target}",
            }
            for label, target in DASHBOARD_LINKS
            if target != uid
        ],
        "panels": layout.panels,
        "refresh": "30s",
        "schemaVersion": 41,
        "tags": ["arvan-challenge", "sre", "provisioned"],
        "templating": {"list": variables},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "title": title,
        "uid": uid,
        "version": 1,
        "weekStart": "",
    }


def sre_overview() -> dict[str, Any]:
    l = Layout()
    l.row(
        "Executive service status",
        "A fast health check across the application, database, Kubernetes, and monitoring layers.",
        [
            panel(
                "Overall service health",
                f'vector(scalar(kube_deployment_status_replicas_available{{namespace="{APP_NS}",deployment="ip-country-api"}} >= bool 2) * scalar(min(cnpg_collector_up{{namespace="database"}}) >= bool 1) * scalar(sum(kube_node_status_condition{{condition="Ready",status="true"}}) >= bool 3))',
                kind="stat",
                unit="bool",
                width=6,
                description="One means the application, PostgreSQL exporters, and all three nodes are healthy.",
                min_value=0,
                max_value=1,
            ),
            panel(
                "Application ready replicas",
                f'kube_deployment_status_replicas_available{{namespace="{APP_NS}",deployment="ip-country-api"}}',
                kind="stat",
                width=6,
                description="Ready application replicas.",
            ),
            panel(
                "PostgreSQL healthy instances",
                'sum(cnpg_collector_up{namespace="database"})',
                kind="stat",
                width=6,
                description="CloudNativePG instances reporting a healthy collector.",
            ),
            panel(
                "Current PostgreSQL Primary",
                'sum(cnpg_pg_replication_in_recovery{namespace="database"} == 0)',
                kind="stat",
                width=6,
                description="Expected current Primary count is one.",
            ),
            panel(
                "Synchronous standbys",
                'max(cnpg_synchronous_standby_count{namespace="database"})',
                kind="stat",
                width=6,
                description="Synchronous standby count reported by the Primary.",
            ),
            panel(
                "Kubernetes ready nodes",
                'sum(kube_node_status_condition{condition="Ready",status="true"})',
                kind="stat",
                width=6,
                description="Nodes whose Ready condition is true.",
            ),
            panel(
                "Application scrape targets",
                f'sum(up{{namespace="{APP_NS}",service="ip-country-api"}})',
                kind="stat",
                width=6,
                description="Application targets currently UP in Prometheus.",
            ),
            panel(
                "Critical alerts",
                'sum(ALERTS{alertstate="firing",severity="critical"}) or vector(0)',
                kind="stat",
                width=3,
                description="Currently firing critical alerts.",
            ),
            panel(
                "Warning alerts",
                'sum(ALERTS{alertstate="firing",severity="warning"}) or vector(0)',
                kind="stat",
                width=3,
                description="Currently firing warning alerts.",
            ),
        ],
    )
    l.row(
        "Golden signals",
        "Traffic, errors, latency, and saturation for the service and its persistence layer.",
        [
            panel(
                "Lookup request rate",
                "ip_country_api:http_requests:rate5m",
                unit="reqps",
                description="Five-minute lookup API request rate.",
            ),
            panel(
                "5xx error ratio",
                "ip_country_api:http_5xx_ratio:5m",
                unit="percentunit",
                description="Server-error ratio for eligible lookup requests.",
            ),
            panel(
                "API latency percentiles",
                targets=queries(
                    ("ip_country_api:http_latency_p50_seconds:5m", "p50"),
                    ("ip_country_api:http_latency_p95_seconds:5m", "p95"),
                    ("ip_country_api:http_latency_p99_seconds:5m", "p99"),
                ),
                unit="s",
                description="Lookup API latency percentiles over five minutes.",
            ),
            panel(
                "Application CPU",
                f'sum by (pod) (rate(container_cpu_usage_seconds_total{{namespace="{APP_NS}",container="api"}}[5m]))',
                unit="cores",
                legend="{{pod}}",
                description="CPU consumed by each API Pod.",
            ),
            panel(
                "Application memory",
                f'sum by (pod) (container_memory_working_set_bytes{{namespace="{APP_NS}",container="api"}})',
                unit="bytes",
                legend="{{pod}}",
                description="Working-set memory by API Pod.",
            ),
            panel(
                "Database connection utilization",
                'sum(cnpg_backends_total{namespace="database",datname="ip_country"}) / max(cnpg_pg_settings_setting{namespace="database",name="max_connections"})',
                unit="percentunit",
                description="Application database backends divided by configured maximum connections.",
            ),
            panel(
                "PostgreSQL PVC utilization",
                '100 * sum(kubelet_volume_stats_used_bytes{exported_namespace="database"}) by (persistentvolumeclaim) / sum(kubelet_volume_stats_capacity_bytes{exported_namespace="database"}) by (persistentvolumeclaim)',
                unit="percent",
                legend="{{persistentvolumeclaim}}",
                description="Used capacity for CloudNativePG PVCs.",
            ),
        ],
    )
    l.row(
        "Seven-day SLO",
        "Rolling SLO status. Only the currently retained history contributes while the service is younger than seven days.",
        [
            panel(
                "Availability SLI (7d)",
                "ip_country_api:availability_sli:7d",
                kind="gauge",
                unit="percentunit",
                width=6,
                description="Seven-day availability SLI from lookup API 5xx events.",
                min_value=0.98,
                max_value=1,
            ),
            panel(
                "Availability target",
                "vector(0.995)",
                kind="stat",
                unit="percentunit",
                width=6,
                description="Availability objective: 99.5 percent.",
            ),
            panel(
                "Availability budget consumed",
                "ip_country_api:availability_budget_consumed_ratio:7d",
                kind="gauge",
                unit="percentunit",
                width=6,
                description="Consumed availability error budget.",
            ),
            panel(
                "Availability budget remaining",
                "ip_country_api:availability_budget_remaining_ratio:7d",
                kind="gauge",
                unit="percentunit",
                width=6,
                description="Remaining availability error budget.",
            ),
            panel(
                "Availability burn rates",
                targets=queries(
                    ("ip_country_api:availability_burn_rate:5m", "5m"),
                    ("ip_country_api:availability_burn_rate:1h", "1h"),
                    ("ip_country_api:availability_burn_rate:6h", "6h"),
                    ("ip_country_api:availability_burn_rate:24h", "24h"),
                ),
                description="Availability error-budget burn across alert windows.",
            ),
            panel(
                "Latency SLI (7d)",
                "ip_country_api:latency_sli:7d",
                kind="gauge",
                unit="percentunit",
                width=6,
                description="Share of eligible requests completed within 500 ms.",
                min_value=0.8,
                max_value=1,
            ),
            panel(
                "Latency target",
                "vector(0.95)",
                kind="stat",
                unit="percentunit",
                width=6,
                description="Latency objective: 95 percent below 500 ms.",
            ),
            panel(
                "Latency budget consumed",
                "ip_country_api:latency_budget_consumed_ratio:7d",
                kind="gauge",
                unit="percentunit",
                width=6,
                description="Consumed latency error budget.",
            ),
            panel(
                "Latency budget remaining",
                "ip_country_api:latency_budget_remaining_ratio:7d",
                kind="gauge",
                unit="percentunit",
                width=6,
                description="Remaining latency error budget.",
            ),
            panel(
                "Latency burn rates",
                targets=queries(
                    ("ip_country_api:latency_burn_rate:5m", "5m"),
                    ("ip_country_api:latency_burn_rate:1h", "1h"),
                    ("ip_country_api:latency_burn_rate:6h", "6h"),
                    ("ip_country_api:latency_burn_rate:24h", "24h"),
                ),
                description="Latency error-budget burn across alert windows.",
            ),
        ],
    )
    l.row(
        "Dependency health",
        "Provider, PostgreSQL, cache, replication, and etcd indicators used to localize service risk.",
        [
            panel(
                "Provider error ratio",
                "ip_country_api:provider_error_ratio:5m",
                unit="percentunit",
                description="Provider error ratio when provider traffic exists.",
            ),
            panel(
                "Provider p95 latency",
                f'histogram_quantile(0.95, sum by (le) (ip_country_provider_request_duration_seconds_bucket{{namespace="{APP_NS}"}}))',
                unit="s",
                description="Cumulative IPinfo p95 latency for the current application Pods.",
            ),
            panel(
                "Database error ratio",
                "ip_country_api:database_error_ratio:5m",
                unit="percentunit",
                description="Application database-operation error ratio.",
            ),
            panel(
                "Database p95 latency",
                "ip_country_api:database_latency_p95_seconds:5m",
                unit="s",
                description="Application-observed PostgreSQL p95 operation latency.",
            ),
            panel(
                "Cache hit ratio",
                "ip_country_api:cache_hit_ratio:5m",
                unit="percentunit",
                description="Database cache hits among successful lookups.",
            ),
            panel(
                "Replication lag",
                'cnpg_pg_replication_lag{namespace="database"}',
                unit="s",
                legend="{{pod}}",
                description="CloudNativePG replay lag by instance.",
            ),
            panel(
                "etcd leader status",
                'etcd_server_is_leader{job="k3s-etcd"}',
                unit="bool",
                legend="{{instance}}",
                description="One series should identify the current etcd leader.",
            ),
        ],
    )
    l.row(
        "Service topology",
        "Placement and readiness relationships across application Pods, PostgreSQL instances, and K3s nodes.",
        [
            panel(
                "Application Pod placement",
                f'kube_pod_info{{namespace="{APP_NS}",pod=~"ip-country-api-.*"}}',
                kind="table",
                width=12,
                description="Application Pod-to-node placement.",
                legend="{{pod}} → {{node}}",
            ),
            panel(
                "PostgreSQL roles",
                'cnpg_pg_replication_in_recovery{namespace="database"}',
                kind="table",
                width=12,
                description="Zero is Primary and one is Replica for each PostgreSQL Pod.",
                legend="{{pod}}",
            ),
            panel(
                "Node readiness",
                'kube_node_status_condition{condition="Ready",status="true"}',
                kind="state-timeline",
                width=12,
                description="Ready state for each K3s node.",
                legend="{{node}}",
            ),
            panel(
                "Deployment desired vs available",
                targets=queries(
                    (
                        f'kube_deployment_spec_replicas{{namespace="{APP_NS}",deployment="ip-country-api"}}',
                        "desired",
                    ),
                    (
                        f'kube_deployment_status_replicas_available{{namespace="{APP_NS}",deployment="ip-country-api"}}',
                        "available",
                    ),
                ),
                width=12,
                description="Desired and available application replicas.",
            ),
        ],
    )
    return dashboard(
        "arvan-challenge-sre-overview",
        "Arvan Challenge — SRE Service Overview",
        "Primary cross-layer operational view for the challenge service.",
        l,
        [],
    )


def api_performance() -> dict[str, Any]:
    l = Layout()
    ns = "${namespace:regex}"
    pod = "${pod:regex}"
    route = "${route:regex}"
    status = "${status_code:regex}"
    l.row(
        "Traffic",
        "Request distribution and lookup throughput.",
        [
            panel(
                "Total RPS",
                f'sum(rate(ip_country_http_requests_total{{namespace=~"{ns}"}}[5m]))',
                unit="reqps",
                description="All instrumented application request traffic.",
            ),
            panel(
                "RPS by route",
                f'sum by (route) (rate(ip_country_http_requests_total{{namespace=~"{ns}",route=~"{route}"}}[5m]))',
                unit="reqps",
                legend="{{route}}",
                description="Request rate grouped by actual route label.",
            ),
            panel(
                "Requests by status",
                f'sum by (status_code) (increase(ip_country_http_requests_total{{namespace=~"{ns}",status_code=~"{status}"}}[5m]))',
                unit="short",
                legend="HTTP {{status_code}}",
                description="Five-minute request counts by HTTP status.",
            ),
            panel(
                "Request rate by Pod",
                f'sum by (pod) (rate(ip_country_http_requests_total{{namespace=~"{ns}",pod=~"{pod}"}}[5m]))',
                unit="reqps",
                legend="{{pod}}",
                description="Traffic distribution across API Pods.",
            ),
            panel(
                "Lookup throughput",
                f'sum by (source) (rate(ip_country_lookup_total{{namespace=~"{ns}",pod=~"{pod}"}}[5m]))',
                unit="reqps",
                legend="{{source}}",
                description="Successful lookup rate split by cache or provider source.",
            ),
        ],
    )
    l.row(
        "Latency",
        "Server-side request latency and the 500 ms objective boundary.",
        [
            panel(
                "Overall latency percentiles",
                targets=queries(
                    (
                        f'histogram_quantile(0.50, sum by (le) (rate(ip_country_http_request_duration_seconds_bucket{{namespace=~"{ns}",route=~"{route}"}}[5m]))) and on() (sum(increase(ip_country_http_request_duration_seconds_count{{namespace=~"{ns}",route=~"{route}"}}[5m])) > 0)',
                        "p50",
                    ),
                    (
                        f'histogram_quantile(0.95, sum by (le) (rate(ip_country_http_request_duration_seconds_bucket{{namespace=~"{ns}",route=~"{route}"}}[5m]))) and on() (sum(increase(ip_country_http_request_duration_seconds_count{{namespace=~"{ns}",route=~"{route}"}}[5m])) > 0)',
                        "p95",
                    ),
                    (
                        f'histogram_quantile(0.99, sum by (le) (rate(ip_country_http_request_duration_seconds_bucket{{namespace=~"{ns}",route=~"{route}"}}[5m]))) and on() (sum(increase(ip_country_http_request_duration_seconds_count{{namespace=~"{ns}",route=~"{route}"}}[5m])) > 0)',
                        "p99",
                    ),
                ),
                unit="s",
                description="Overall latency percentiles.",
            ),
            panel(
                "p95 by route",
                f'histogram_quantile(0.95, sum by (le,route) (rate(ip_country_http_request_duration_seconds_bucket{{namespace=~"{ns}",route=~"{route}",route!="unmatched"}}[1h]))) and on(route) (sum by (route) (increase(ip_country_http_request_duration_seconds_count{{namespace=~"{ns}",route=~"{route}",route!="unmatched"}}[1h])) > 0)',
                unit="s",
                legend="{{route}}",
                description="One-hour p95 latency grouped by known application route.",
            ),
            panel(
                "Request latency heatmap",
                f'sum by (le) (rate(ip_country_http_request_duration_seconds_bucket{{namespace=~"{ns}",route=~"{route}"}}[5m]))',
                kind="heatmap",
                unit="s",
                description="Histogram bucket distribution for request latency.",
            ),
            panel(
                "Slow-request ratio (>500 ms)",
                "ip_country_api:http_latency_bad_ratio:5m",
                unit="percentunit",
                description="Eligible lookup requests slower than 500 ms.",
            ),
            panel(
                "p95 latency by Pod",
                f'histogram_quantile(0.95, sum by (le,pod) (rate(ip_country_http_request_duration_seconds_bucket{{namespace=~"{ns}",pod=~"{pod}",route=~"{route}"}}[5m]))) and on(pod) (sum by (pod) (increase(ip_country_http_request_duration_seconds_count{{namespace=~"{ns}",pod=~"{pod}",route=~"{route}"}}[5m])) > 0)',
                unit="s",
                legend="{{pod}}",
                description="Per-Pod p95 application latency.",
            ),
        ],
    )
    l.row(
        "Cache behavior",
        "Cache effectiveness and lookup-source distribution.",
        [
            panel(
                "Database cache hits",
                f'sum(rate(ip_country_lookup_total{{namespace=~"{ns}",source="database",result="success"}}[5m]))',
                unit="reqps",
                description="Successful database cache-hit rate.",
            ),
            panel(
                "Provider lookups",
                f'sum(rate(ip_country_lookup_total{{namespace=~"{ns}",source="provider",result="success"}}[5m])) or vector(0)',
                unit="reqps",
                description="Provider lookup rate; zero is expected for cached traffic.",
            ),
            panel(
                "Cache hit ratio",
                "ip_country_api:cache_hit_ratio:5m",
                unit="percentunit",
                description="Successful lookups served by PostgreSQL.",
            ),
            panel(
                "Cache miss ratio",
                "1 - ip_country_api:cache_hit_ratio:5m",
                unit="percentunit",
                description="Successful lookups requiring provider data.",
            ),
            panel(
                "Lookup source distribution",
                f'sum by (source) (increase(ip_country_lookup_total{{namespace=~"{ns}",result="success"}}[5m]))',
                unit="short",
                legend="{{source}}",
                description="Five-minute lookup count by source.",
            ),
            panel(
                "Cache-hit trend",
                f'sum(rate(ip_country_lookup_total{{namespace=~"{ns}",source="database",result="success"}}[5m]))',
                unit="reqps",
                description="Cache-hit rate over time.",
            ),
        ],
    )
    l.row(
        "Dependency performance",
        "Provider and database rates, errors, and histogram latency.",
        [
            panel(
                "Provider request rate",
                f'sum by (result) (rate(ip_country_provider_requests_total{{namespace=~"{ns}"}}[5m])) or vector(0)',
                unit="reqps",
                legend="{{result}}",
                description="External provider request rate by result.",
            ),
            panel(
                "Provider error ratio",
                "ip_country_api:provider_error_ratio:5m",
                unit="percentunit",
                description="Provider failure ratio when provider traffic exists.",
            ),
            panel(
                "Provider latency percentiles",
                targets=queries(
                    (
                        f'histogram_quantile(0.50, sum by (le) (ip_country_provider_request_duration_seconds_bucket{{namespace=~"{ns}"}}))',
                        "p50",
                    ),
                    (
                        f'histogram_quantile(0.95, sum by (le) (ip_country_provider_request_duration_seconds_bucket{{namespace=~"{ns}"}}))',
                        "p95",
                    ),
                    (
                        f'histogram_quantile(0.99, sum by (le) (ip_country_provider_request_duration_seconds_bucket{{namespace=~"{ns}"}}))',
                        "p99",
                    ),
                ),
                unit="s",
                description="Cumulative IPinfo latency percentiles for current Pods.",
            ),
            panel(
                "Database operation rate",
                f'sum by (operation) (rate(ip_country_database_operations_total{{namespace=~"{ns}"}}[5m]))',
                unit="ops",
                legend="{{operation}}",
                description="Application database operations by type.",
            ),
            panel(
                "Database error ratio",
                "ip_country_api:database_error_ratio:5m",
                unit="percentunit",
                description="Application database-operation error ratio.",
            ),
            panel(
                "Database latency percentiles",
                targets=queries(
                    (
                        f'histogram_quantile(0.50, sum by (le) (rate(ip_country_database_operation_duration_seconds_bucket{{namespace=~"{ns}"}}[5m]))) and on() (sum(increase(ip_country_database_operation_duration_seconds_count{{namespace=~"{ns}"}}[5m])) > 0)',
                        "p50",
                    ),
                    (
                        f'histogram_quantile(0.95, sum by (le) (rate(ip_country_database_operation_duration_seconds_bucket{{namespace=~"{ns}"}}[5m]))) and on() (sum(increase(ip_country_database_operation_duration_seconds_count{{namespace=~"{ns}"}}[5m])) > 0)',
                        "p95",
                    ),
                    (
                        f'histogram_quantile(0.99, sum by (le) (rate(ip_country_database_operation_duration_seconds_bucket{{namespace=~"{ns}"}}[5m]))) and on() (sum(increase(ip_country_database_operation_duration_seconds_count{{namespace=~"{ns}"}}[5m])) > 0)',
                        "p99",
                    ),
                ),
                unit="s",
                description="Database operation latency percentiles.",
            ),
        ],
    )
    l.row(
        "Runtime and Kubernetes",
        "Per-Pod resource, readiness, restart, placement, and network detail.",
        [
            panel(
                "CPU by Pod",
                f'sum by (pod) (rate(container_cpu_usage_seconds_total{{namespace=~"{ns}",container="api",pod=~"{pod}"}}[5m]))',
                unit="cores",
                legend="{{pod}}",
                description="CPU usage by API Pod.",
            ),
            panel(
                "CPU throttling ratio",
                f'sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{{namespace=~"{ns}",container="api",pod=~"{pod}"}}[5m])) / clamp_min(sum by (pod) (rate(container_cpu_cfs_periods_total{{namespace=~"{ns}",container="api",pod=~"{pod}"}}[5m])), 0.000001)',
                unit="percentunit",
                legend="{{pod}}",
                description="CFS throttled-period ratio by Pod.",
            ),
            panel(
                "Memory working set",
                f'sum by (pod) (container_memory_working_set_bytes{{namespace=~"{ns}",container="api",pod=~"{pod}"}})',
                unit="bytes",
                legend="{{pod}}",
                description="Working-set memory by API Pod.",
            ),
            panel(
                "Memory limit utilization",
                f'sum by (pod) (container_memory_working_set_bytes{{namespace=~"{ns}",container="api",pod=~"{pod}"}}) / sum by (pod) (kube_pod_container_resource_limits{{namespace=~"{ns}",container="api",resource="memory",pod=~"{pod}"}})',
                unit="percentunit",
                legend="{{pod}}",
                description="Working set divided by declared memory limit.",
            ),
            panel(
                "Restarts",
                f'sum by (pod) (kube_pod_container_status_restarts_total{{namespace=~"{ns}",container="api",pod=~"{pod}"}})',
                unit="short",
                legend="{{pod}}",
                description="Container restart count.",
            ),
            panel(
                "Pod readiness",
                f'kube_pod_container_status_ready{{namespace=~"{ns}",container="api",pod=~"{pod}"}}',
                kind="state-timeline",
                unit="bool",
                legend="{{pod}}",
                description="Readiness state by API Pod.",
            ),
            panel(
                "Pod distribution",
                f'kube_pod_info{{namespace=~"{ns}",pod=~"{pod}"}}',
                kind="table",
                legend="{{pod}} → {{node}}",
                description="API Pod-to-node placement.",
            ),
            panel(
                "Network receive",
                f'sum by (pod) (rate(container_network_receive_bytes_total{{namespace=~"{ns}",pod=~"{pod}"}}[5m]))',
                unit="Bps",
                legend="{{pod}}",
                description="Pod receive throughput.",
            ),
            panel(
                "Network transmit",
                f'sum by (pod) (rate(container_network_transmit_bytes_total{{namespace=~"{ns}",pod=~"{pod}"}}[5m]))',
                unit="Bps",
                legend="{{pod}}",
                description="Pod transmit throughput.",
            ),
        ],
    )
    l.row(
        "Release identity",
        "Runtime version and Kubernetes rollout identity available from metrics.",
        [
            panel(
                "Application version",
                f'max by (version) (ip_country_build_info{{namespace=~"{ns}"}})',
                kind="table",
                width=6,
                legend="{{version}}",
                description="Version label exported by the application.",
            ),
            panel(
                "Pod creation timestamps",
                f'kube_pod_created{{namespace=~"{ns}",pod=~"{pod}"}}',
                unit="dateTimeAsIso",
                width=6,
                legend="{{pod}}",
                description="Creation time of each API Pod.",
            ),
            panel(
                "Current replicas",
                f'kube_deployment_status_replicas{{namespace=~"{ns}",deployment="ip-country-api"}}',
                kind="stat",
                width=6,
                description="Current application replica count.",
            ),
            panel(
                "Available replicas",
                f'kube_deployment_status_replicas_available{{namespace=~"{ns}",deployment="ip-country-api"}}',
                kind="stat",
                width=6,
                description="Available application replicas.",
            ),
        ],
    )
    vars_ = [
        variable("namespace", "label_values(ip_country_build_info, namespace)", APP_NS),
        variable("pod", 'label_values(ip_country_build_info{namespace=~"$namespace"}, pod)', ".*"),
        variable(
            "route",
            'label_values(ip_country_http_requests_total{namespace=~"$namespace"}, route)',
            ".*",
            "Route",
        ),
        variable(
            "status_code",
            'label_values(ip_country_http_requests_total{namespace=~"$namespace"}, status_code)',
            ".*",
            "Status code",
        ),
    ]
    return dashboard(
        "ip-country-api-performance",
        "IP Country API — Performance Deep Dive",
        "Application traffic, latency, cache, dependency, and runtime performance.",
        l,
        vars_,
    )


def postgres_performance() -> dict[str, Any]:
    l = Layout()
    ns = "${namespace:regex}"
    cluster = "${cluster:regex}"
    instance = "${instance:regex}"
    db = "${database:regex}"
    l.row(
        "Cluster topology",
        "CloudNativePG health, roles, placement, and synchronization.",
        [
            panel(
                "Healthy instances",
                f'sum(cnpg_collector_up{{namespace=~"{ns}",cluster=~"{cluster}"}})',
                kind="stat",
                description="Healthy CNPG collectors.",
            ),
            panel(
                "Current Primary",
                f'sum(cnpg_pg_replication_in_recovery{{namespace=~"{ns}",pod=~"{instance}"}} == 0)',
                kind="stat",
                description="Expected Primary count is one.",
            ),
            panel(
                "Replica count",
                f'sum(cnpg_pg_replication_in_recovery{{namespace=~"{ns}",pod=~"{instance}"}} == 1)',
                kind="stat",
                description="Replica instances in recovery.",
            ),
            panel(
                "Role by instance",
                f'cnpg_pg_replication_in_recovery{{namespace=~"{ns}",pod=~"{instance}"}}',
                kind="state-timeline",
                legend="{{pod}} (0 Primary, 1 Replica)",
                description="PostgreSQL recovery state identifies Primary and Replicas.",
            ),
            panel(
                "Instance-to-node placement",
                f'kube_pod_info{{namespace=~"{ns}",pod=~"{instance}"}}',
                kind="table",
                legend="{{pod}} → {{node}}",
                description="PostgreSQL Pod placement.",
            ),
            panel(
                "Synchronous standbys",
                f'max(cnpg_synchronous_standby_count{{namespace=~"{ns}"}})',
                kind="stat",
                description="Synchronous standby count reported by CNPG.",
            ),
            panel(
                "Postmaster start time",
                f'cnpg_pg_postmaster_start_time{{namespace=~"{ns}",pod=~"{instance}"}}',
                unit="dateTimeAsIso",
                legend="{{pod}}",
                description="Instance start times reveal restart or role-change events.",
            ),
        ],
    )
    l.row(
        "Replication",
        "Replay lag, WAL distance, slots, and synchronous state.",
        [
            panel(
                "Replication lag",
                f'cnpg_pg_replication_lag{{namespace=~"{ns}",pod=~"{instance}"}}',
                unit="s",
                legend="{{pod}}",
                description="Replay lag by instance.",
            ),
            panel(
                "WAL sent difference",
                f'cnpg_pg_stat_replication_sent_diff_bytes{{namespace=~"{ns}",pod=~"{instance}"}}',
                unit="bytes",
                legend="{{pod}}",
                description="WAL byte distance at the sender.",
            ),
            panel(
                "WAL replay difference",
                f'cnpg_pg_stat_replication_replay_diff_bytes{{namespace=~"{ns}",pod=~"{instance}"}}',
                unit="bytes",
                legend="{{pod}}",
                description="Replay byte distance on replication connections.",
            ),
            panel(
                "Replay delay",
                f'cnpg_pg_stat_replication_replay_lag_seconds{{namespace=~"{ns}",pod=~"{instance}"}}',
                unit="s",
                legend="{{pod}}",
                description="Replay lag from pg_stat_replication.",
            ),
            panel(
                "Replication slots active",
                f'cnpg_pg_replication_slots_active{{namespace=~"{ns}",pod=~"{instance}"}}',
                unit="bool",
                legend="{{pod}} / {{slot_name}}",
                description="Replication slot active state.",
            ),
            panel(
                "Slot retained WAL",
                f'cnpg_pg_replication_slots_pg_wal_lsn_diff{{namespace=~"{ns}",pod=~"{instance}"}}',
                unit="bytes",
                legend="{{pod}} / {{slot_name}}",
                description="WAL retained by replication slots.",
            ),
        ],
    )
    l.row(
        "Connections",
        "Backend state and configured connection capacity.",
        [
            panel(
                "Total connections",
                f'sum by (pod) (cnpg_backends_total{{namespace=~"{ns}",pod=~"{instance}",datname=~"{db}"}})',
                legend="{{pod}}",
                description="Database backends by instance.",
            ),
            panel(
                "Active connections",
                f'sum by (pod) (cnpg_backends_total{{namespace=~"{ns}",pod=~"{instance}",datname=~"{db}",state="active"}})',
                legend="{{pod}}",
                description="Active backends.",
            ),
            panel(
                "Idle connections",
                f'sum by (pod) (cnpg_backends_total{{namespace=~"{ns}",pod=~"{instance}",datname=~"{db}",state="idle"}})',
                legend="{{pod}}",
                description="Idle backends.",
            ),
            panel(
                "Connection utilization",
                f'sum(cnpg_backends_total{{namespace=~"{ns}",datname=~"{db}"}}) / max(cnpg_pg_settings_setting{{namespace=~"{ns}",name="max_connections"}})',
                unit="percentunit",
                description="Backends divided by max_connections.",
            ),
            panel(
                "Maximum connections",
                f'max by (pod) (cnpg_pg_settings_setting{{namespace=~"{ns}",pod=~"{instance}",name="max_connections"}})',
                legend="{{pod}}",
                description="Configured max_connections by instance.",
            ),
        ],
    )
    l.row(
        "Transactions",
        "Transaction throughput and failure indicators.",
        [
            panel(
                "TPS",
                f'sum(rate(cnpg_pg_stat_database_xact_commit{{namespace=~"{ns}",datname=~"{db}"}}[5m]) + rate(cnpg_pg_stat_database_xact_rollback{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                unit="ops",
                description="Commit plus rollback rate.",
            ),
            panel(
                "Commits",
                f'sum by (pod) (rate(cnpg_pg_stat_database_xact_commit{{namespace=~"{ns}",pod=~"{instance}",datname=~"{db}"}}[5m]))',
                unit="ops",
                legend="{{pod}}",
                description="Commit rate by instance.",
            ),
            panel(
                "Rollbacks",
                f'sum by (pod) (rate(cnpg_pg_stat_database_xact_rollback{{namespace=~"{ns}",pod=~"{instance}",datname=~"{db}"}}[5m]))',
                unit="ops",
                legend="{{pod}}",
                description="Rollback rate by instance.",
            ),
            panel(
                "Rollback ratio",
                f'sum(rate(cnpg_pg_stat_database_xact_rollback{{namespace=~"{ns}",datname=~"{db}"}}[5m])) / clamp_min(sum(rate(cnpg_pg_stat_database_xact_commit{{namespace=~"{ns}",datname=~"{db}"}}[5m]) + rate(cnpg_pg_stat_database_xact_rollback{{namespace=~"{ns}",datname=~"{db}"}}[5m])), 0.000001)',
                unit="percentunit",
                description="Rollbacks as a share of transactions.",
            ),
            panel(
                "Deadlocks",
                f'sum(increase(cnpg_pg_stat_database_deadlocks{{namespace=~"{ns}",datname=~"{db}"}}[5m])) or vector(0)',
                description="Deadlocks observed during five minutes.",
            ),
            panel(
                "Conflicts",
                f'sum(increase(cnpg_pg_stat_database_conflicts{{namespace=~"{ns}",datname=~"{db}"}}[5m])) or vector(0)',
                description="Recovery conflicts during five minutes.",
            ),
        ],
    )
    l.row(
        "Buffer and tuple behavior",
        "Buffer cache effectiveness, tuple activity, and temporary I/O.",
        [
            panel(
                "Database cache hit ratio",
                f'sum(rate(cnpg_pg_stat_database_blks_hit{{namespace=~"{ns}",datname=~"{db}"}}[5m])) / clamp_min(sum(rate(cnpg_pg_stat_database_blks_hit{{namespace=~"{ns}",datname=~"{db}"}}[5m]) + rate(cnpg_pg_stat_database_blks_read{{namespace=~"{ns}",datname=~"{db}"}}[5m])), 0.000001)',
                unit="percentunit",
                description="PostgreSQL shared-buffer hit ratio.",
            ),
            panel(
                "Blocks read and hit",
                targets=queries(
                    (
                        f'sum(rate(cnpg_pg_stat_database_blks_read{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                        "read",
                    ),
                    (
                        f'sum(rate(cnpg_pg_stat_database_blks_hit{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                        "hit",
                    ),
                ),
                unit="ops",
                description="Block read and cache-hit rates.",
            ),
            panel(
                "Tuple activity",
                targets=queries(
                    (
                        f'sum(rate(cnpg_pg_stat_database_tup_returned{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                        "returned",
                    ),
                    (
                        f'sum(rate(cnpg_pg_stat_database_tup_fetched{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                        "fetched",
                    ),
                    (
                        f'sum(rate(cnpg_pg_stat_database_tup_inserted{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                        "inserted",
                    ),
                    (
                        f'sum(rate(cnpg_pg_stat_database_tup_updated{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                        "updated",
                    ),
                    (
                        f'sum(rate(cnpg_pg_stat_database_tup_deleted{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                        "deleted",
                    ),
                ),
                unit="ops",
                description="Tuple activity by operation.",
            ),
            panel(
                "Temporary bytes",
                f'sum(rate(cnpg_pg_stat_database_temp_bytes{{namespace=~"{ns}",datname=~"{db}"}}[5m]))',
                unit="Bps",
                description="Temporary-file byte generation.",
            ),
            panel(
                "Temporary files",
                f'sum(increase(cnpg_pg_stat_database_temp_files{{namespace=~"{ns}",datname=~"{db}"}}[5m])) or vector(0)',
                description="Temporary files created over five minutes.",
            ),
        ],
    )
    l.row(
        "WAL and checkpoints",
        "WAL generation and checkpoint pressure.",
        [
            panel(
                "WAL generation",
                f'sum by (pod) (rate(cnpg_collector_wal_bytes{{namespace=~"{ns}",pod=~"{instance}"}}[5m]))',
                unit="Bps",
                legend="{{pod}}",
                description="WAL generation rate.",
            ),
            panel(
                "Requested checkpoints",
                f'sum(rate(cnpg_pg_stat_checkpointer_checkpoints_req{{namespace=~"{ns}"}}[5m]))',
                unit="ops",
                description="Requested checkpoint rate.",
            ),
            panel(
                "Timed checkpoints",
                f'sum(rate(cnpg_pg_stat_checkpointer_checkpoints_timed{{namespace=~"{ns}"}}[5m]))',
                unit="ops",
                description="Timed checkpoint rate.",
            ),
            panel(
                "Checkpoint write time",
                f'sum(rate(cnpg_pg_stat_checkpointer_write_time{{namespace=~"{ns}"}}[5m])) / 1000',
                unit="s",
                description="Checkpoint write seconds per second.",
            ),
            panel(
                "Checkpoint sync time",
                f'sum(rate(cnpg_pg_stat_checkpointer_sync_time{{namespace=~"{ns}"}}[5m])) / 1000',
                unit="s",
                description="Checkpoint sync seconds per second.",
            ),
        ],
    )
    l.row(
        "Capacity",
        "Database, PVC, compute, and restart capacity indicators.",
        [
            panel(
                "Database size",
                f'max by (datname) (cnpg_pg_database_size_bytes{{namespace=~"{ns}",datname=~"{db}"}})',
                unit="bytes",
                legend="{{datname}}",
                description="Current database size.",
            ),
            panel(
                "Database growth rate",
                f'max by (datname) (deriv(cnpg_pg_database_size_bytes{{namespace=~"{ns}",datname=~"{db}"}}[1h]))',
                unit="Bps",
                legend="{{datname}}",
                description="One-hour linear database size trend.",
            ),
            panel(
                "PVC utilization",
                f'100 * kubelet_volume_stats_used_bytes{{exported_namespace=~"{ns}"}} / kubelet_volume_stats_capacity_bytes{{exported_namespace=~"{ns}"}}',
                unit="percent",
                legend="{{persistentvolumeclaim}}",
                description="CloudNativePG PVC utilization.",
            ),
            panel(
                "CPU by instance",
                f'sum by (pod) (rate(container_cpu_usage_seconds_total{{namespace=~"{ns}",container="postgres",pod=~"{instance}"}}[5m]))',
                unit="cores",
                legend="{{pod}}",
                description="PostgreSQL CPU by Pod.",
            ),
            panel(
                "Memory by instance",
                f'sum by (pod) (container_memory_working_set_bytes{{namespace=~"{ns}",container="postgres",pod=~"{instance}"}})',
                unit="bytes",
                legend="{{pod}}",
                description="PostgreSQL working-set memory.",
            ),
            panel(
                "Pod restarts",
                f'sum by (pod) (kube_pod_container_status_restarts_total{{namespace=~"{ns}",container="postgres",pod=~"{instance}"}})',
                legend="{{pod}}",
                description="PostgreSQL container restart count.",
            ),
        ],
    )
    l.row(
        "Application dependency view",
        "Application-observed database health alongside PostgreSQL readiness.",
        [
            panel(
                "Application DB operation rate",
                "sum by (operation) (rate(ip_country_database_operations_total[5m]))",
                unit="ops",
                legend="{{operation}}",
                description="Database operations initiated by the application.",
            ),
            panel(
                "Application DB p95 latency",
                "ip_country_api:database_latency_p95_seconds:5m",
                unit="s",
                description="Application-observed database p95 latency.",
            ),
            panel(
                "Application DB error ratio",
                "ip_country_api:database_error_ratio:5m",
                unit="percentunit",
                description="Application database error ratio.",
            ),
            panel(
                "Application ready replicas",
                f'kube_deployment_status_replicas_available{{namespace="{APP_NS}",deployment="ip-country-api"}}',
                kind="stat",
                description="Application readiness next to PostgreSQL health.",
            ),
        ],
    )
    vars_ = [
        variable("namespace", "label_values(cnpg_collector_up, namespace)", "database"),
        variable(
            "cluster",
            'label_values(cnpg_collector_up{namespace=~"$namespace"}, cluster)',
            "ip-country-postgres",
        ),
        variable("instance", 'label_values(cnpg_collector_up{namespace=~"$namespace"}, pod)', ".*"),
        variable(
            "database",
            'label_values(cnpg_pg_stat_database_xact_commit{namespace=~"$namespace"}, datname)',
            "ip_country",
        ),
    ]
    return dashboard(
        "cloudnativepg-sre-performance",
        "CloudNativePG — SRE and Performance",
        "CloudNativePG topology, replication, transactions, WAL, and capacity.",
        l,
        vars_,
    )


def k3s_reliability() -> dict[str, Any]:
    l = Layout()
    node = "${node:regex}"
    ns = "${namespace:regex}"
    workload = "${workload:regex}"
    l.row(
        "Cluster summary",
        "Immediate reliability risks across nodes and workloads.",
        [
            panel(
                "Ready nodes",
                f'sum(kube_node_status_condition{{node=~"{node}",condition="Ready",status="true"}})',
                kind="stat",
                description="Ready K3s nodes.",
            ),
            panel(
                "Unavailable Deployments",
                f'sum(kube_deployment_status_replicas_unavailable{{namespace=~"{ns}",deployment=~"{workload}"}}) or vector(0)',
                kind="stat",
                description="Unavailable Deployment replicas.",
            ),
            panel(
                "Unavailable StatefulSets",
                f'sum(kube_statefulset_replicas{{namespace=~"{ns}"}} - kube_statefulset_status_replicas_ready{{namespace=~"{ns}"}}) or vector(0)',
                kind="stat",
                description="Desired minus ready StatefulSet replicas.",
            ),
            panel(
                "Pending Pods",
                f'sum(kube_pod_status_phase{{namespace=~"{ns}",phase="Pending"}} == 1) or vector(0)',
                kind="stat",
                description="Pods currently Pending.",
            ),
            panel(
                "CrashLooping containers",
                f'sum(kube_pod_container_status_waiting_reason{{namespace=~"{ns}",reason="CrashLoopBackOff"}} == 1) or vector(0)',
                kind="stat",
                description="Containers in CrashLoopBackOff.",
            ),
            panel(
                "Restart rate",
                f'sum(rate(kube_pod_container_status_restarts_total{{namespace=~"{ns}"}}[15m]))',
                unit="ops",
                description="Container restart rate.",
            ),
            panel(
                "Current firing alerts",
                'sum(ALERTS{alertstate="firing"}) or vector(0)',
                kind="stat",
                description="All firing Prometheus alerts.",
            ),
        ],
    )
    l.row(
        "Node capacity",
        "CPU, memory, filesystem, network, load, and Pod saturation by node.",
        [
            panel(
                "CPU utilization",
                f'1 - avg by (instance) (rate(node_cpu_seconds_total{{mode="idle",instance=~"{node}(:.*)?"}}[5m]))',
                unit="percentunit",
                legend="{{instance}}",
                description="Non-idle CPU share by node-exporter instance.",
            ),
            panel(
                "Memory utilization",
                f'1 - node_memory_MemAvailable_bytes{{instance=~"{node}(:.*)?"}} / node_memory_MemTotal_bytes{{instance=~"{node}(:.*)?"}}',
                unit="percentunit",
                legend="{{instance}}",
                description="Used memory share.",
            ),
            panel(
                "Filesystem utilization",
                f'1 - node_filesystem_avail_bytes{{instance=~"{node}(:.*)?",fstype!~"tmpfs|overlay|squashfs"}} / node_filesystem_size_bytes{{instance=~"{node}(:.*)?",fstype!~"tmpfs|overlay|squashfs"}}',
                unit="percentunit",
                legend="{{instance}} {{mountpoint}}",
                description="Filesystem utilization on persistent filesystems.",
            ),
            panel(
                "Filesystem available",
                f'node_filesystem_avail_bytes{{instance=~"{node}(:.*)?",fstype!~"tmpfs|overlay|squashfs"}}',
                unit="bytes",
                legend="{{instance}} {{mountpoint}}",
                description="Available filesystem bytes.",
            ),
            panel(
                "Node network throughput",
                targets=queries(
                    (
                        f'sum by (instance) (rate(node_network_receive_bytes_total{{instance=~"{node}(:.*)?",device!~"lo|veth.*|flannel.*|cni.*"}}[5m]))',
                        "RX {{instance}}",
                    ),
                    (
                        f'sum by (instance) (rate(node_network_transmit_bytes_total{{instance=~"{node}(:.*)?",device!~"lo|veth.*|flannel.*|cni.*"}}[5m]))',
                        "TX {{instance}}",
                    ),
                ),
                unit="Bps",
                description="Physical node receive and transmit throughput.",
            ),
            panel(
                "Node load average",
                targets=queries(
                    (f'node_load1{{instance=~"{node}(:.*)?"}}', "1m {{instance}}"),
                    (f'node_load5{{instance=~"{node}(:.*)?"}}', "5m {{instance}}"),
                    (f'node_load15{{instance=~"{node}(:.*)?"}}', "15m {{instance}}"),
                ),
                description="Linux load average by node.",
            ),
            panel(
                "Pod count by node",
                f'count by (node) (kube_pod_info{{node=~"{node}"}})',
                legend="{{node}}",
                description="Scheduled Pod count by node.",
            ),
        ],
    )
    l.row(
        "Workload reliability",
        "Readiness, restarts, OOM events, and scheduling pressure.",
        [
            panel(
                "Application desired vs ready",
                targets=queries(
                    (
                        f'kube_deployment_spec_replicas{{namespace="{APP_NS}",deployment="ip-country-api"}}',
                        "desired",
                    ),
                    (
                        f'kube_deployment_status_replicas_ready{{namespace="{APP_NS}",deployment="ip-country-api"}}',
                        "ready",
                    ),
                ),
                description="Application desired and ready replicas.",
            ),
            panel(
                "Monitoring unavailable replicas",
                'sum(kube_deployment_status_replicas_unavailable{namespace="monitoring"}) or vector(0)',
                description="Unavailable monitoring Deployment replicas.",
            ),
            panel(
                "PostgreSQL readiness",
                'sum(cnpg_collector_up{namespace="database"})',
                kind="stat",
                description="Healthy CloudNativePG instances.",
            ),
            panel(
                "Pod restart timeline",
                f'sum by (namespace,pod) (increase(kube_pod_container_status_restarts_total{{namespace=~"{ns}"}}[15m]))',
                legend="{{namespace}}/{{pod}}",
                description="Container restarts over fifteen minutes.",
            ),
            panel(
                "OOMKilled events",
                f'sum(increase(kube_pod_container_status_last_terminated_reason{{namespace=~"{ns}",reason="OOMKilled"}}[1h])) or vector(0)',
                description="Recent OOMKilled terminations.",
            ),
            panel(
                "Unschedulable Pods",
                f'sum(kube_pod_status_scheduled{{namespace=~"{ns}",condition="false"}} == 1) or vector(0)',
                description="Pods whose Scheduled condition is false.",
            ),
        ],
    )
    l.row(
        "Kubernetes API",
        "API request volume, errors, latency, and saturation.",
        [
            panel(
                "API request rate",
                "sum by (verb) (rate(apiserver_request_total[5m]))",
                unit="reqps",
                legend="{{verb}}",
                description="Kubernetes API request rate by verb.",
            ),
            panel(
                "API 5xx ratio",
                'sum(rate(apiserver_request_total{code=~"5.."}[5m])) / clamp_min(sum(rate(apiserver_request_total[5m])), 0.000001)',
                unit="percentunit",
                description="Kubernetes API server-error ratio.",
            ),
            panel(
                "API latency percentiles",
                targets=queries(
                    (
                        'histogram_quantile(0.50, sum by (le) (rate(apiserver_request_duration_seconds_bucket{verb!~"WATCH|CONNECT"}[5m])))',
                        "p50",
                    ),
                    (
                        'histogram_quantile(0.95, sum by (le) (rate(apiserver_request_duration_seconds_bucket{verb!~"WATCH|CONNECT"}[5m])))',
                        "p95",
                    ),
                    (
                        'histogram_quantile(0.99, sum by (le) (rate(apiserver_request_duration_seconds_bucket{verb!~"WATCH|CONNECT"}[5m])))',
                        "p99",
                    ),
                ),
                unit="s",
                description="Non-streaming API request latency.",
            ),
            panel(
                "Inflight requests",
                "sum by (request_kind) (apiserver_current_inflight_requests)",
                legend="{{request_kind}}",
                description="Current API inflight request count.",
            ),
            panel(
                "API availability",
                '1 - (sum(rate(apiserver_request_total{code=~"5.."}[5m])) / clamp_min(sum(rate(apiserver_request_total[5m])), 0.000001))',
                unit="percentunit",
                description="API availability derived from 5xx responses.",
            ),
        ],
    )
    l.row(
        "etcd",
        "Consensus leadership, storage, disk latency, and proposal failures.",
        [
            panel(
                "Members with leader",
                'sum(etcd_server_has_leader{job="k3s-etcd"})',
                kind="stat",
                description="etcd members currently observing a leader.",
            ),
            panel(
                "Current leader",
                'etcd_server_is_leader{job="k3s-etcd"}',
                kind="state-timeline",
                unit="bool",
                legend="{{instance}}",
                description="Leader identity across etcd members.",
            ),
            panel(
                "Leader changes",
                'sum(increase(etcd_server_leader_changes_seen_total{job="k3s-etcd"}[1h])) or vector(0)',
                description="Leader changes seen in one hour.",
            ),
            panel(
                "Database size",
                'etcd_mvcc_db_total_size_in_bytes{job="k3s-etcd"}',
                unit="bytes",
                legend="{{instance}}",
                description="etcd MVCC database size.",
            ),
            panel(
                "WAL fsync p95/p99",
                targets=queries(
                    (
                        'histogram_quantile(0.95, sum by (le) (rate(etcd_disk_wal_fsync_duration_seconds_bucket{job="k3s-etcd"}[5m])))',
                        "p95",
                    ),
                    (
                        'histogram_quantile(0.99, sum by (le) (rate(etcd_disk_wal_fsync_duration_seconds_bucket{job="k3s-etcd"}[5m])))',
                        "p99",
                    ),
                ),
                unit="s",
                description="etcd WAL fsync latency.",
            ),
            panel(
                "Backend commit p95",
                'histogram_quantile(0.95, sum by (le) (rate(etcd_disk_backend_commit_duration_seconds_bucket{job="k3s-etcd"}[5m])))',
                unit="s",
                description="etcd backend commit p95 latency.",
            ),
            panel(
                "Proposal failures",
                'sum(increase(etcd_server_proposals_failed_total{job="k3s-etcd"}[5m])) or vector(0)',
                description="Failed etcd proposals in five minutes.",
            ),
        ],
    )
    l.row(
        "DNS and networking",
        "CoreDNS request quality and Pod network flow/errors.",
        [
            panel(
                "CoreDNS request rate",
                "sum by (type) (rate(coredns_dns_requests_total[5m]))",
                unit="reqps",
                legend="{{type}}",
                description="DNS request rate by query type.",
            ),
            panel(
                "CoreDNS error rate",
                'sum by (rcode) (rate(coredns_dns_responses_total{rcode!="NOERROR"}[5m])) or vector(0)',
                unit="reqps",
                legend="{{rcode}}",
                description="Non-NOERROR DNS responses.",
            ),
            panel(
                "CoreDNS p95 latency",
                "histogram_quantile(0.95, sum by (le) (rate(coredns_dns_request_duration_seconds_bucket[5m])))",
                unit="s",
                description="CoreDNS p95 request latency.",
            ),
            panel(
                "Pod network throughput",
                targets=queries(
                    (
                        f'sum by (namespace) (rate(container_network_receive_bytes_total{{namespace=~"{ns}"}}[5m]))',
                        "RX {{namespace}}",
                    ),
                    (
                        f'sum by (namespace) (rate(container_network_transmit_bytes_total{{namespace=~"{ns}"}}[5m]))',
                        "TX {{namespace}}",
                    ),
                ),
                unit="Bps",
                description="Pod network throughput by namespace.",
            ),
            panel(
                "Pod network errors",
                targets=queries(
                    (
                        f'sum(rate(container_network_receive_errors_total{{namespace=~"{ns}"}}[5m])) or vector(0)',
                        "receive",
                    ),
                    (
                        f'sum(rate(container_network_transmit_errors_total{{namespace=~"{ns}"}}[5m])) or vector(0)',
                        "transmit",
                    ),
                ),
                unit="ops",
                description="Pod network error rate.",
            ),
            panel(
                "Pod packet drops",
                targets=queries(
                    (
                        f'sum(rate(container_network_receive_packets_dropped_total{{namespace=~"{ns}"}}[5m])) or vector(0)',
                        "receive",
                    ),
                    (
                        f'sum(rate(container_network_transmit_packets_dropped_total{{namespace=~"{ns}"}}[5m])) or vector(0)',
                        "transmit",
                    ),
                ),
                unit="ops",
                description="Pod network packet-drop rate.",
            ),
        ],
    )
    l.row(
        "Storage",
        "Persistent volume usage across monitoring and PostgreSQL.",
        [
            panel(
                "PersistentVolume utilization",
                f'100 * kubelet_volume_stats_used_bytes{{exported_namespace=~"{ns}"}} / kubelet_volume_stats_capacity_bytes{{exported_namespace=~"{ns}"}}',
                unit="percent",
                legend="{{exported_namespace}}/{{persistentvolumeclaim}}",
                description="PVC utilization by claim.",
            ),
            panel(
                "PVC available bytes",
                f'kubelet_volume_stats_available_bytes{{exported_namespace=~"{ns}"}}',
                unit="bytes",
                legend="{{exported_namespace}}/{{persistentvolumeclaim}}",
                description="Available PVC capacity.",
            ),
            panel(
                "Prometheus PVC utilization",
                '100 * kubelet_volume_stats_used_bytes{exported_namespace="monitoring",persistentvolumeclaim=~"prometheus-.*"} / kubelet_volume_stats_capacity_bytes{exported_namespace="monitoring",persistentvolumeclaim=~"prometheus-.*"}',
                unit="percent",
                description="Prometheus storage utilization.",
            ),
            panel(
                "Grafana PVC utilization",
                '100 * kubelet_volume_stats_used_bytes{exported_namespace="monitoring",persistentvolumeclaim=~".*grafana.*"} / kubelet_volume_stats_capacity_bytes{exported_namespace="monitoring",persistentvolumeclaim=~".*grafana.*"}',
                unit="percent",
                description="Grafana storage utilization.",
            ),
            panel(
                "Alertmanager PVC utilization",
                '100 * kubelet_volume_stats_used_bytes{exported_namespace="monitoring",persistentvolumeclaim=~"alertmanager-.*"} / kubelet_volume_stats_capacity_bytes{exported_namespace="monitoring",persistentvolumeclaim=~"alertmanager-.*"}',
                unit="percent",
                description="Alertmanager storage utilization.",
            ),
            panel(
                "PostgreSQL PVC utilization",
                '100 * kubelet_volume_stats_used_bytes{exported_namespace="database"} / kubelet_volume_stats_capacity_bytes{exported_namespace="database"}',
                unit="percent",
                legend="{{persistentvolumeclaim}}",
                description="CloudNativePG storage utilization.",
            ),
        ],
    )
    vars_ = [
        variable("node", "label_values(kube_node_info, node)", ".*"),
        variable("namespace", "label_values(kube_pod_info, namespace)", ".*"),
        variable("workload", "label_values(kube_deployment_status_replicas, deployment)", ".*"),
    ]
    return dashboard(
        "k3s-reliability-capacity",
        "K3s — Reliability and Capacity",
        "Reliability risks and capacity saturation across the K3s platform.",
        l,
        vars_,
    )


def expected() -> dict[str, dict[str, Any]]:
    return {
        "arvan-challenge-sre-overview.json": sre_overview(),
        "ip-country-api-performance.json": api_performance(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail when committed JSON differs")
    args = parser.parse_args()
    generated = expected()
    mismatches: list[str] = []
    if not args.check:
        OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, payload in generated.items():
        content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        path = OUTPUT / filename
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                mismatches.append(filename)
        else:
            path.write_text(content, encoding="utf-8")
    if mismatches:
        print("Dashboard JSON is stale: " + ", ".join(mismatches))
        return 1
    print(
        f"Validated {len(generated)} reproducible dashboard JSON files."
        if args.check
        else f"Generated {len(generated)} dashboard JSON files in {OUTPUT}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
