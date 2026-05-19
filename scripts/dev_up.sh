#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_CMD="${BACKEND_CMD:-uvicorn api.main:app --host ${BACKEND_HOST} --port ${BACKEND_PORT}}"
FRONTEND_CMD="${FRONTEND_CMD:-npm run dev -- --host ${FRONTEND_HOST} --port ${FRONTEND_PORT}}"
# Default 0: an old uvicorn on :8000 causes POST /analyze 422 on hot_money/policy/lockup/kronos.
# Opt in to reuse: REUSE_BACKEND_IF_BUSY=1 ./scripts/dev_up.sh
REUSE_BACKEND_IF_BUSY="${REUSE_BACKEND_IF_BUSY:-0}"

backend_pid=""
frontend_pid=""

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "${frontend_pid}" ]] && kill -0 "${frontend_pid}" >/dev/null 2>&1; then
    echo
    echo "Stopping frontend (pid ${frontend_pid})..."
    kill "${frontend_pid}" >/dev/null 2>&1 || true
  fi

  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" >/dev/null 2>&1; then
    echo "Stopping backend (pid ${backend_pid})..."
    kill "${backend_pid}" >/dev/null 2>&1 || true
  fi

  wait >/dev/null 2>&1 || true
  exit "${exit_code}"
}

is_port_busy() {
  local port="$1"
  lsof -iTCP:"${port}" -sTCP:LISTEN -n -P >/dev/null 2>&1
}

if ! command -v uvicorn >/dev/null 2>&1; then
  if [[ "${REUSE_BACKEND_IF_BUSY}" != "1" ]]; then
    echo "Error: 'uvicorn' is not in PATH. Activate your Python environment first." >&2
    exit 1
  fi
fi

if [[ ! -d "${FRONTEND_DIR}" ]]; then
  echo "Error: frontend directory not found at ${FRONTEND_DIR}" >&2
  exit 1
fi

if [[ ! -f "${FRONTEND_DIR}/package.json" ]]; then
  echo "Error: frontend/package.json not found. Did frontend setup complete?" >&2
  exit 1
fi

# ----- Kronos forecasting model (real upstream clone) -----------------------
# Spec: docs/superpowers/specs/2026-05-19-real-kronos-integration-design.md (D2)
# Skip with SKIP_KRONOS_INSTALL=1 once the vendor is set up.
KRONOS_UPSTREAM_SHA="${KRONOS_UPSTREAM_SHA:-67b630e67f6a18c9e9be918d9b4337c960db1e9a}"
KRONOS_VENDOR_DIR="${ROOT_DIR}/vendor/kronos"

if [[ "${SKIP_KRONOS_INSTALL:-0}" != "1" ]]; then
  if [[ ! -d "${KRONOS_VENDOR_DIR}/.git" ]]; then
    echo "[dev_up] cloning Kronos into ${KRONOS_VENDOR_DIR}"
    mkdir -p "${ROOT_DIR}/vendor"
    git clone https://github.com/shiyu-coder/Kronos.git "${KRONOS_VENDOR_DIR}"

    echo "[dev_up] pinning Kronos to ${KRONOS_UPSTREAM_SHA}"
    git -C "${KRONOS_VENDOR_DIR}" fetch --quiet origin
    git -C "${KRONOS_VENDOR_DIR}" checkout --quiet "${KRONOS_UPSTREAM_SHA}"

    echo "[dev_up] installing Kronos requirements"
    pip install -r "${KRONOS_VENDOR_DIR}/requirements.txt"
  else
    echo "[dev_up] Kronos vendor present at ${KRONOS_VENDOR_DIR} (skip clone; SKIP_KRONOS_INSTALL=1 to also skip pin check)"
  fi
fi
# ---------------------------------------------------------------------------

if is_port_busy "${FRONTEND_PORT}"; then
  echo "Error: frontend port ${FRONTEND_PORT} is already in use." >&2
  echo "Tip: stop the existing frontend or run with FRONTEND_PORT=<port>." >&2
  exit 1
fi

trap cleanup EXIT INT TERM

if is_port_busy "${BACKEND_PORT}"; then
  if [[ "${REUSE_BACKEND_IF_BUSY}" == "1" ]]; then
    echo "Backend port ${BACKEND_PORT} already in use; reusing existing backend."
    echo "Tip: if new API routes 404 (e.g. Sectors / GET /api/catalog/industry-constituents), restart that process and re-run this script."
    echo
    echo "WARNING: An old uvicorn on :${BACKEND_PORT} often causes POST /analyze 422 on hot_money, policy, lockup, kronos"
    echo "         (literal_error for analysts). Stop that process, then from repo root:"
    echo "           pip install -e '.[api]' && PYTHONPATH=\$(pwd) uvicorn api.main:app --host ${BACKEND_HOST} --port ${BACKEND_PORT}"
    echo "         Verify GET /config includes analyze_analyst_body_schema=registered_string_list on the running API."
  else
    echo "Error: backend port ${BACKEND_PORT} is already in use." >&2
    echo "Tip: stop the existing backend or run with BACKEND_PORT=<port>." >&2
    exit 1
  fi
else
  if ! command -v uvicorn >/dev/null 2>&1; then
    echo "Error: 'uvicorn' is not in PATH. Activate your Python environment first." >&2
    exit 1
  fi
  echo "Starting backend: ${BACKEND_CMD}"
  echo "(PYTHONPATH prepends repo root so ./api beats any stale tradingagents wheel.)"
  (cd "${ROOT_DIR}" && PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" eval "${BACKEND_CMD}") &
  backend_pid=$!

  sleep 1
  if ! kill -0 "${backend_pid}" >/dev/null 2>&1; then
    echo "Error: backend failed to start." >&2
    exit 1
  fi
fi

echo "Starting frontend: ${FRONTEND_CMD}"
(cd "${FRONTEND_DIR}" && eval "${FRONTEND_CMD}") &
frontend_pid=$!

sleep 1
if ! kill -0 "${frontend_pid}" >/dev/null 2>&1; then
  echo "Error: frontend failed to start." >&2
  exit 1
fi

echo
echo "Dev stack is up:"
echo "- API:   http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "- UI:    http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo
echo "Press Ctrl+C to stop both services."

if [[ -n "${backend_pid}" ]]; then
  wait "${backend_pid}" "${frontend_pid}"
else
  wait "${frontend_pid}"
fi
