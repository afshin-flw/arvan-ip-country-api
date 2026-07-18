#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export VALUES="${VALUES:-${APP_ROOT}/deploy/environments/arvan/values.arvan.local.yaml}"
exec "${SCRIPT_DIR}/deploy-challenge.sh"
