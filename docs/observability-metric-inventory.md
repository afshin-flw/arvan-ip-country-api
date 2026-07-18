# Observability metric inventory

This inventory is verified against the live Prometheus API during each environment rollout. It intentionally lists only metric families used by the application rules, the two application-owned dashboards, and the two linked infrastructure-owned SRE dashboards. Histogram `_bucket` series are counters even when the Prometheus metadata endpoint reports the suffixed series as `unknown`.

## Application

| Metric | Type | Important labels | Unit | Source | Use |
| --- | --- | --- | --- | --- | --- |
| `ip_country_http_requests_total` | Counter | `namespace`, `pod`, `method`, `route`, `status_code` | requests | API | Traffic, errors, availability SLO and burn rates |
| `ip_country_http_request_duration_seconds_bucket` | Histogram bucket | `namespace`, `pod`, `method`, `route`, `le` | seconds | API | p50/p95/p99, heatmap and latency SLO |
| `ip_country_http_request_duration_seconds_count` | Histogram count | `namespace`, `pod`, `method`, `route` | requests | API | Latency bad-event denominator |
| `ip_country_lookup_total` | Counter | `namespace`, `pod`, `source`, `result` | lookups | API | Lookup throughput and cache-hit ratio |
| `ip_country_provider_requests_total` | Counter | `namespace`, `pod`, `provider`, `result` | requests | API | Provider traffic and error ratio |
| `ip_country_provider_request_duration_seconds_bucket` | Histogram bucket | `namespace`, `pod`, `provider`, `le` | seconds | API | Provider latency percentiles |
| `ip_country_database_operations_total` | Counter | `namespace`, `pod`, `operation` | operations | API | Database operation rate and error-ratio denominator |
| `ip_country_database_operation_duration_seconds_bucket` | Histogram bucket | `namespace`, `pod`, `operation`, `le` | seconds | API | Database operation latency percentiles |
| `ip_country_database_errors_total` | Counter | `namespace`, `pod`, `operation`, `error_type` | errors | API | Database error ratio; series is created lazily on the first failure |
| `ip_country_build_info` | Gauge | `namespace`, `pod`, `version` | identity | API | Release identity |

The verified `route` values are `/`, `/api/v1/lookups`, and `unmatched`. SLO rules select only `/api/v1/lookups`; health and metrics endpoints are not included by the middleware instrumentation.

## CloudNativePG and PostgreSQL

| Metric | Type | Important labels | Unit | Source | Use |
| --- | --- | --- | --- | --- | --- |
| `cnpg_collector_up` | Gauge | `namespace`, `cluster`, `pod` | boolean | CNPG | Cluster and exporter health |
| `cnpg_pg_replication_in_recovery` | Gauge | `namespace`, `pod` | boolean | PostgreSQL | Primary/Replica role |
| `cnpg_synchronous_standby_count` | Gauge | `namespace`, `pod` | instances | PostgreSQL | Synchronous standby health |
| `cnpg_pg_replication_lag` | Gauge | `namespace`, `pod` | seconds | PostgreSQL | Replica replay lag |
| `cnpg_pg_stat_replication_sent_diff_bytes` / `replay_diff_bytes` / `replay_lag_seconds` | Gauges | `namespace`, `pod` | bytes / seconds | PostgreSQL | Replication distance and delay |
| `cnpg_pg_replication_slots_active` / `slots_pg_wal_lsn_diff` | Gauges | `namespace`, `pod`, `slot_name`, `slot_type` | boolean / bytes | PostgreSQL | Replication-slot state and retained WAL |
| `cnpg_backends_total` | Gauge | `namespace`, `pod`, `datname`, `state`, `usename` | connections | PostgreSQL | Active, idle, and total connections |
| `cnpg_pg_settings_setting` | Gauge | `namespace`, `pod`, `name` | setting-dependent | PostgreSQL | `max_connections` capacity |
| `cnpg_pg_stat_database_xact_commit` / `xact_rollback` | Counters | `namespace`, `pod`, `datname` | transactions | PostgreSQL | TPS and rollback ratio |
| `cnpg_pg_stat_database_deadlocks` / `conflicts` | Counters | `namespace`, `pod`, `datname` | events | PostgreSQL | Transaction failure signals |
| `cnpg_pg_stat_database_blks_hit` / `blks_read` | Counters | `namespace`, `pod`, `datname` | blocks | PostgreSQL | Buffer-cache hit ratio |
| `cnpg_pg_stat_database_tup_*` | Counters | `namespace`, `pod`, `datname` | tuples | PostgreSQL | Tuple activity |
| `cnpg_pg_stat_database_temp_bytes` / `temp_files` | Counters | `namespace`, `pod`, `datname` | bytes / files | PostgreSQL | Temporary I/O |
| `cnpg_collector_wal_bytes` | Gauge | `namespace`, `pod`, `stats_reset` | bytes | CNPG | WAL generation trend |
| `cnpg_pg_stat_checkpointer_*` | Counters | `namespace`, `pod` | checkpoints / milliseconds | PostgreSQL | Checkpoint rate and duration |
| `cnpg_pg_database_size_bytes` | Gauge | `namespace`, `pod`, `datname` | bytes | PostgreSQL | Database size and growth trend |
| `cnpg_pg_postmaster_start_time` | Gauge | `namespace`, `pod` | Unix seconds | PostgreSQL | Instance restart/role timeline |

## Kubernetes, containers, nodes, DNS, and API server

| Metric family | Type | Important labels | Unit | Source | Use |
| --- | --- | --- | --- | --- | --- |
| `kube_node_status_condition` | Gauge | `node`, `condition`, `status` | boolean | kube-state-metrics | Node readiness |
| `kube_deployment_*` / `kube_statefulset_*` | Gauges | `namespace`, workload name | replicas | kube-state-metrics | Desired, ready, and unavailable replicas |
| `kube_pod_status_*` / `kube_pod_container_status_*` | Gauges/Counters | `namespace`, `pod`, `container`, state/reason | state / restarts | kube-state-metrics | Pending, readiness, CrashLoop, OOM and restarts |
| `kube_pod_info` / `kube_pod_created` | Gauges | `namespace`, `pod`, `node` | identity / Unix seconds | kube-state-metrics | Placement and creation time |
| `kube_pod_container_resource_limits` | Gauge | `namespace`, `pod`, `container`, `resource` | bytes/cores | kube-state-metrics | Memory limit utilization |
| `container_cpu_usage_seconds_total` / `container_cpu_cfs_*` | Counters | `namespace`, `pod`, `container`, `node` | CPU seconds / periods | cAdvisor | CPU and throttling |
| `container_memory_working_set_bytes` | Gauge | `namespace`, `pod`, `container`, `node` | bytes | cAdvisor | Pod memory |
| `container_network_*` | Counters | `namespace`, `pod`, `interface`, `node` | bytes/packets/errors | cAdvisor | Pod network traffic and errors |
| `node_cpu_seconds_total` | Counter | `instance`, `cpu`, `mode` | CPU seconds | node-exporter | Node CPU utilization |
| `node_memory_*` | Gauges | `instance` | bytes | node-exporter | Node memory utilization |
| `node_filesystem_*` | Gauges | `instance`, `device`, `mountpoint`, `fstype` | bytes | node-exporter | Filesystem capacity |
| `node_network_*` | Counters | `instance`, `device` | bytes/errors | node-exporter | Node network traffic |
| `node_load1` / `node_load5` / `node_load15` | Gauges | `instance` | load | node-exporter | Node scheduler pressure |
| `kubelet_volume_stats_*` | Gauges | `exported_namespace`, `persistentvolumeclaim`, `node` | bytes | kubelet | PVC usage and capacity |
| `apiserver_request_total` | Counter | `code`, `verb`, `resource`, `node` | requests | kube-apiserver | API traffic and availability |
| `apiserver_request_duration_seconds_bucket` | Histogram bucket | `verb`, `resource`, `le`, `node` | seconds | kube-apiserver | API latency |
| `apiserver_current_inflight_requests` | Gauge | `request_kind`, `node` | requests | kube-apiserver | API saturation |
| `coredns_dns_requests_total` / `responses_total` | Counters | `server`, `type`, `rcode` | requests | CoreDNS | DNS traffic and errors |
| `coredns_dns_request_duration_seconds_bucket` | Histogram bucket | `server`, `zone`, `le` | seconds | CoreDNS | DNS latency |

## etcd

| Metric | Type | Important labels | Unit | Source | Use |
| --- | --- | --- | --- | --- | --- |
| `etcd_server_has_leader` / `etcd_server_is_leader` | Gauges | `instance`, `job` | boolean | etcd | Member and leader health |
| `etcd_server_leader_changes_seen_total` | Counter | `instance`, `job` | changes | etcd | Leadership stability |
| `etcd_mvcc_db_total_size_in_bytes` | Gauge | `instance`, `job` | bytes | etcd | Backend size |
| `etcd_disk_wal_fsync_duration_seconds_bucket` | Histogram bucket | `instance`, `le` | seconds | etcd | WAL fsync p95/p99 |
| `etcd_disk_backend_commit_duration_seconds_bucket` | Histogram bucket | `instance`, `le` | seconds | etcd | Backend commit latency |
| `etcd_server_proposals_failed_total` | Counter | `instance`, `job` | proposals | etcd | Consensus failures |

## Intentionally omitted instrumentation

- PostgreSQL lock counts by lock mode and long-running transaction duration are not exported by the current CNPG collector.
- A reliable failover/switchover event counter is not present; role and postmaster-start timelines are shown instead.
- The application exports its semantic version but not the immutable container digest as a metric; Kubernetes still verifies the digest operationally.
- `container_spec_memory_limit_bytes` is absent, so memory utilization uses kube-state-metrics resource limits.
- No distributed tracing, request exemplars, log correlation, or production user-journey metrics are available.
