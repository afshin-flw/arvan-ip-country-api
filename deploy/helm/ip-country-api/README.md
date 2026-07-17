# IP Country API Helm chart

This chart deploys the immutable IP Country API image with two replicas, a Helm-managed runtime Secret, a pre-install/pre-upgrade Alembic Job, NodePort access, Prometheus monitoring, alerts, and a Grafana dashboard.

## Install

Use an environment-specific values file containing an image digest and runtime credentials:

```bash
helm upgrade --install ip-country-api \
  deploy/helm/ip-country-api \
  --namespace ip-country-api \
  --create-namespace \
  --values deploy/environments/challenge/values.challenge.local.yaml \
  --atomic --wait --timeout 10m
```

The image renders as `repository@sha256:...`; a tag is not appended when `image.digest` is set. The application and migration containers run as UID/GID 10001 with a read-only root filesystem and no Linux capabilities. The application ServiceAccount has no RBAC permissions and no mounted API token.

## Migration and runtime configuration

The migration Job runs `python -m alembic upgrade head` before install and upgrade. Helm aborts the operation if migration fails. The Deployment consumes every application environment variable through explicit references to the `ip-country-api-runtime` Secret.

The challenge-local file is intentionally ignored and must never be committed. `values.challenge.example.yaml` is safe to use for lint and template validation.

## Monitoring

The ServiceMonitor discovers both Pod endpoints through the `http` Service port and scrapes `/metrics`. PrometheusRule covers availability, replica readiness, HTTP errors, latency, database errors, provider errors, and target health. A ConfigMap labeled `grafana_dashboard=1` provisions **IP Country API Overview** when the Grafana sidecar watches all namespaces.

## Upgrade behavior

An unchanged values file causes a safe Helm revision without changing the Pod template. Runtime Secret changes alter the checksum annotation and trigger a controlled rollout. Existing release tags and image digests must never be moved.
