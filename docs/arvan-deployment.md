# Arvan K3s deployment

The Arvan challenge deployment uses the released Linux AMD64 image
`ghcr.io/afshin-flw/arvan-ip-country-api@sha256:081ba4b3aac7779934329f33ebf98546743a1c27f044f195039209fa46026e85`.
It does not build or retag the image.

Create `deploy/environments/arvan/values.arvan.local.yaml` from the committed
example. Keep mode `0600`; the file is ignored by Git. Set the real IPinfo token
and a URL-encoded `postgresql+psycopg://` URL for
`ip-country-postgres-rw.database.svc.cluster.local:5432/ip_country`. Never print
or commit either value.

The Arvan values use `trustedHosts: ["*"]` because Prometheus Operator scrapes
the two application endpoints through dynamic Pod IPs. This is a challenge-only
runtime override; the reusable chart default stays restricted. The service does
not use the Host header for routing, redirects, or authorization.

From the controller, use the pinned project-local Helm v3.21.3 binary and the
explicit kubeconfig under
`/home/arvan/ansible-k3s-preparation/.generated/arvan/kubeconfig`:

```bash
HELM=/home/arvan/.tools/helm/v3.21.3/helm ./deploy/scripts/deploy-arvan.sh
HELM=/home/arvan/.tools/helm/v3.21.3/helm ./deploy/scripts/verify-challenge.sh
```

The release is `ip-country-api` in namespace `ip-country-api`. Its migration
hook must reach Alembic head before two hardened replicas roll out on distinct
nodes. The Service owns NodePort 30080; Terraform separately owns the cloud
firewall rule. PostgreSQL, Prometheus, and Alertmanager remain private.

This phase intentionally uses manual Helm from the controller. It does not add
automatic CD, Ingress, or TLS.
