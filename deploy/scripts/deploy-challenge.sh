#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CHART="${APP_ROOT}/deploy/helm/ip-country-api"
VALUES="${VALUES:-${APP_ROOT}/deploy/environments/challenge/values.challenge.local.yaml}"
KUBECONFIG_PATH="${KUBECONFIG_PATH:-/home/arvan/ansible-k3s-preparation/.generated/arvan/kubeconfig}"
KNOWN_HOSTS="${KNOWN_HOSTS:-/home/arvan/ansible-k3s-preparation/.generated/arvan/known_hosts}"
SSH_KEY="${SSH_KEY:-/home/ubuntu/.ssh/id_rsa}"

if command -v helm >/dev/null 2>&1; then
  HELM="${HELM:-$(command -v helm)}"
else
  HELM="${HELM:-/home/arvan/.tools/helm/v3.21.3/helm}"
fi

test -x "${HELM}" || { echo "Helm binary not found: ${HELM}" >&2; exit 1; }
test -f "${VALUES}" || { echo "Local values file not found: ${VALUES}" >&2; exit 1; }
test -f "${KUBECONFIG_PATH}" || { echo "Kubeconfig not found: ${KUBECONFIG_PATH}" >&2; exit 1; }
test -f "${KNOWN_HOSTS}" || { echo "SSH known-hosts file not found: ${KNOWN_HOSTS}" >&2; exit 1; }

server_url="$(awk '$1 == "server:" {print $2; exit}' "${KUBECONFIG_PATH}")"
server_host="${server_url#https://}"
server_host="${server_host%%:*}"
test -n "${server_host}" || { echo "Unable to resolve K3s server from kubeconfig" >&2; exit 1; }

export NO_PROXY="${server_host},${NO_PROXY:-}"
export no_proxy="${server_host},${no_proxy:-}"

ssh_options=(
  -i "${SSH_KEY}"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=${KNOWN_HOSTS}"
  -o GlobalKnownHostsFile=/dev/null
)

existing_nodeport="$(
  ssh "${ssh_options[@]}" "root@${server_host}" k3s kubectl get services -A -o json |
    jq -r '.items[] | select(any(.spec.ports[]?; .nodePort == 30080)) | (.metadata.namespace + "/" + .metadata.name)'
)"
if test -n "${existing_nodeport}" && test "${existing_nodeport}" != "ip-country-api/ip-country-api"; then
  echo "NodePort 30080 is already owned by ${existing_nodeport}" >&2
  exit 1
fi

cd "${APP_ROOT}"
"${HELM}" upgrade --install ip-country-api \
  "${CHART}" \
  --namespace ip-country-api \
  --create-namespace \
  --values "${VALUES}" \
  --kubeconfig "${KUBECONFIG_PATH}" \
  --atomic \
  --wait \
  --timeout 10m
