#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG_PATH="${KUBECONFIG_PATH:-/home/arvan/ansible-k3s-preparation/.generated/arvan/kubeconfig}"
KNOWN_HOSTS="${KNOWN_HOSTS:-/home/arvan/ansible-k3s-preparation/.generated/arvan/known_hosts}"
SSH_KEY="${SSH_KEY:-}"
EXPECTED_IMAGE="ghcr.io/afshin-flw/arvan-ip-country-api@sha256:081ba4b3aac7779934329f33ebf98546743a1c27f044f195039209fa46026e85"

if command -v helm >/dev/null 2>&1; then
  HELM="${HELM:-$(command -v helm)}"
else
  HELM="${HELM:-/home/arvan/.tools/helm/v3.21.3/helm}"
fi

test -x "${HELM}"
test -f "${KUBECONFIG_PATH}"
if [[ -z "${SSH_KEY}" ]]; then
  for candidate in /root/.ssh/id_rsa /home/ubuntu/.ssh/id_rsa; do
    if [[ -r "${candidate}" ]]; then
      SSH_KEY="${candidate}"
      break
    fi
  done
fi
test -r "${SSH_KEY}"

server_url="$(awk '$1 == "server:" {print $2; exit}' "${KUBECONFIG_PATH}")"
server_host="${server_url#https://}"
server_host="${server_host%%:*}"
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
remote_kubectl() {
  ssh "${ssh_options[@]}" "ubuntu@${server_host}" sudo k3s kubectl "$@"
}

status_json="$("${HELM}" status ip-country-api --namespace ip-country-api --kubeconfig "${KUBECONFIG_PATH}" -o json)"
test "$(jq -r '.info.status' <<<"${status_json}")" = deployed
hooks="$("${HELM}" get hooks ip-country-api --namespace ip-country-api --kubeconfig "${KUBECONFIG_PATH}")"
grep -q 'name: ip-country-api-migrate' <<<"${hooks}"
grep -q 'alembic' <<<"${hooks}"
grep -q 'upgrade' <<<"${hooks}"
grep -q 'head' <<<"${hooks}"

deployment_json="$(remote_kubectl -n ip-country-api get deployment ip-country-api -o json)"
test "$(jq -r '.status.availableReplicas' <<<"${deployment_json}")" -eq 2
test "$(jq -r '.spec.replicas' <<<"${deployment_json}")" -eq 2
test "$(jq -r '.spec.template.spec.containers[0].image' <<<"${deployment_json}")" = "${EXPECTED_IMAGE}"
test "$(jq -r '.spec.template.spec.securityContext.runAsUser' <<<"${deployment_json}")" -eq 10001
test "$(jq -r '.spec.template.spec.containers[0].securityContext.readOnlyRootFilesystem' <<<"${deployment_json}")" = true

pods_json="$(remote_kubectl -n ip-country-api get pods -l app.kubernetes.io/component=api -o json)"
test "$(jq '[.items[] | select(.status.phase == "Running") | select(all(.status.containerStatuses[]; .ready == true))] | length' <<<"${pods_json}")" -eq 2
test "$(jq '[.items[].spec.nodeName] | unique | length' <<<"${pods_json}")" -eq 2

service_json="$(remote_kubectl -n ip-country-api get service ip-country-api -o json)"
test "$(jq -r '.spec.type' <<<"${service_json}")" = NodePort
test "$(jq -r '.spec.ports[0].nodePort' <<<"${service_json}")" -eq 30080
endpoints_json="$(remote_kubectl -n ip-country-api get endpoints ip-country-api -o json)"
test "$(jq '[.subsets[].addresses[]] | length' <<<"${endpoints_json}")" -eq 2

node_ips="$(remote_kubectl get nodes -o json | jq -r '.items[].status.addresses[] | select(.type == "InternalIP") | .address')"
while IFS= read -r node_ip; do
  test -n "${node_ip}" || continue
  curl --noproxy '*' --fail --silent --show-error --max-time 10 "http://${node_ip}:30080/health/live" >/dev/null
  curl --noproxy '*' --fail --silent --show-error --max-time 10 "http://${node_ip}:30080/health/ready" >/dev/null
  curl --noproxy '*' --fail --silent --show-error --max-time 10 "http://${node_ip}:30080/metrics" | grep -q '^ip_country_build_info'
done <<<"${node_ips}"

remote_kubectl -n ip-country-api get servicemonitor ip-country-api >/dev/null
remote_kubectl -n ip-country-api get prometheusrule ip-country-api >/dev/null
remote_kubectl -n ip-country-api get configmap ip-country-api-dashboard >/dev/null

ssh "${ssh_options[@]}" "ubuntu@${server_host}" sudo bash -s <<'REMOTE_VERIFY'
set -Eeuo pipefail
prom_log=/tmp/ip-country-api-prometheus-port-forward.log
grafana_log=/tmp/ip-country-api-grafana-port-forward.log
k3s kubectl -n monitoring port-forward service/kube-prometheus-stack-prometheus 19090:9090 >"${prom_log}" 2>&1 &
prom_pid=$!
k3s kubectl -n monitoring port-forward service/kube-prometheus-stack-grafana 13000:80 >"${grafana_log}" 2>&1 &
grafana_pid=$!
cleanup() {
  kill "${prom_pid}" "${grafana_pid}" >/dev/null 2>&1 || true
  wait "${prom_pid}" "${grafana_pid}" >/dev/null 2>&1 || true
}
trap cleanup EXIT
for attempt in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:19090/-/ready >/dev/null 2>&1 && curl --fail --silent http://127.0.0.1:13000/api/health >/dev/null 2>&1; then
    break
  fi
  test "${attempt}" -lt 30 || exit 1
  sleep 1
done
targets=$(curl --fail --silent http://127.0.0.1:19090/api/v1/targets)
test "$(jq '[.data.activeTargets[] | select(.labels.namespace == "ip-country-api" and .labels.service == "ip-country-api" and .health == "up")] | length' <<<"${targets}")" -eq 2
rules=$(curl --fail --silent http://127.0.0.1:19090/api/v1/rules)
test "$(jq '[.data.groups[].rules[] | select(.name == "IPCountryAPIUnavailable")] | length' <<<"${rules}")" -eq 1
user=$(k3s kubectl -n monitoring get secret grafana-admin -o jsonpath="{.data.admin-user}" | base64 -d)
password=$(k3s kubectl -n monitoring get secret grafana-admin -o jsonpath="{.data.admin-password}" | base64 -d)
test "$(curl --fail --silent --user "${user}:${password}" "http://127.0.0.1:13000/api/search?query=IP%20Country%20API%20Overview" | jq '[.[] | select(.uid == "ip-country-api-overview")] | length')" -eq 1
REMOTE_VERIFY

printf 'Verification passed: release deployed, 2 Ready Pods on distinct nodes, NodePort healthy, monitoring discovered, image digest exact.\n'
