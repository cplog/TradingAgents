#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8808}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-53173}"

BACKEND_CMD="${BACKEND_CMD:-uvicorn api.main:app --host ${BACKEND_HOST} --port ${BACKEND_PORT}}"
FRONTEND_CMD="${FRONTEND_CMD:-npm run dev -- --host ${FRONTEND_HOST} --port ${FRONTEND_PORT}}"
# Default 0: an old uvicorn on :8808 causes POST /analyze 422 on hot_money/policy/lockup/kronos.
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

pids_on_port() {
  local port="$1"
  lsof -tiTCP:"${port}" -sTCP:LISTEN -n -P 2>/dev/null || true
}

# Stop whatever is listening on `port` (SIGTERM, then SIGKILL). Exits on failure.
free_port() {
  local port="$1"
  local label="${2:-port ${port}}"
  local pids pid i

  pids="$(pids_on_port "${port}")"
  if [[ -z "${pids}" ]]; then
    return 0
  fi

  echo "[dev_up] ${label} port ${port} in use — stopping listener(s): ${pids//$'\n'/ }"
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    kill -TERM "${pid}" 2>/dev/null || true
  done <<< "${pids}"

  for (( i = 0; i < 20; i++ )); do
    is_port_busy "${port}" || return 0
    sleep 0.25
  done

  pids="$(pids_on_port "${port}")"
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    kill -KILL "${pid}" 2>/dev/null || true
  done <<< "${pids}"
  sleep 0.5

  if is_port_busy "${port}"; then
    echo "Error: could not free ${label} port ${port}." >&2
    lsof -iTCP:"${port}" -sTCP:LISTEN -n -P >&2 || true
    exit 1
  fi
}

# Prefer `python` from an activated venv/conda env. On macOS, bare `python3` is often
# Homebrew's PEP-668 "externally managed" interpreter even when conda is active.
resolve_kronos_python() {
  if [[ -n "${KRONOS_PYTHON:-}" ]]; then
    echo "${KRONOS_PYTHON}"
    return 0
  fi
  local candidate
  for candidate in python python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      if "${candidate}" -m pip --version >/dev/null 2>&1; then
        "${candidate}" -c "import sys; print(sys.executable)"
        return 0
      fi
    fi
  done
  echo "python3"
}

# Uvicorn can take 10–30s to import api.main before binding; Vite proxies fail until then.
wait_for_backend_ready() {
  local port="$1"
  local max_wait="${2:-90}"
  local url="http://127.0.0.1:${port}/api/health"
  local i=0

  echo "Waiting for backend at ${url} (up to ${max_wait}s)..."
  while (( i < max_wait )); do
    if curl -sf "${url}" >/dev/null 2>&1; then
      echo "Backend ready (${i}s)."
      return 0
    fi
    if [[ -n "${backend_pid:-}" ]] && ! kill -0 "${backend_pid}" >/dev/null 2>&1; then
      echo "Error: backend exited before ${url} responded." >&2
      return 1
    fi
    sleep 1
    (( i++ )) || true
  done

  echo "Error: backend did not respond on ${url} within ${max_wait}s." >&2
  echo "Check the uvicorn output above for import errors or port conflicts." >&2
  return 1
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

# Use the same interpreter that will run uvicorn (activate your venv/conda first).
KRONOS_PYTHON="$(resolve_kronos_python)"

if [[ "${SKIP_KRONOS_INSTALL:-0}" != "1" ]]; then
  if [[ ! -d "${KRONOS_VENDOR_DIR}/.git" ]]; then
    echo "[dev_up] cloning Kronos into ${KRONOS_VENDOR_DIR}"
    mkdir -p "${ROOT_DIR}/vendor"
    git clone https://github.com/shiyu-coder/Kronos.git "${KRONOS_VENDOR_DIR}"

    echo "[dev_up] pinning Kronos to ${KRONOS_UPSTREAM_SHA}"
    git -C "${KRONOS_VENDOR_DIR}" fetch --quiet origin
    git -C "${KRONOS_VENDOR_DIR}" checkout --quiet "${KRONOS_UPSTREAM_SHA}"
  else
    echo "[dev_up] Kronos vendor present at ${KRONOS_VENDOR_DIR}"
  fi

  if [[ ! -f "${KRONOS_VENDOR_DIR}/requirements.txt" ]]; then
    echo "Error: ${KRONOS_VENDOR_DIR}/requirements.txt missing. Remove vendor/kronos and re-run." >&2
    exit 1
  fi

  # Install inference deps only — vendor requirements.txt pins pandas 2.2.2 which
  # conflicts with tradingagents (pandas>=2.3.0). matplotlib is not needed at runtime.
  echo "[dev_up] installing Kronos inference deps via ${KRONOS_PYTHON} -m pip"
  if ! "${KRONOS_PYTHON}" -m pip install \
    "torch>=2.0.0" \
    "einops==0.8.1" \
    "huggingface_hub==0.33.1" \
    "safetensors==0.6.2"; then
    echo "Error: Kronos dependency install failed for ${KRONOS_PYTHON}." >&2
    echo "Activate your project venv/conda env first, or set KRONOS_PYTHON to that interpreter." >&2
    echo "Example: conda activate llm_base && ./scripts/dev_up.sh" >&2
    echo "Or skip: SKIP_KRONOS_INSTALL=1 ./scripts/dev_up.sh" >&2
    exit 1
  fi
else
  echo "[dev_up] SKIP_KRONOS_INSTALL=1 — not cloning or installing Kronos deps"
fi
# ---------------------------------------------------------------------------

free_port "${FRONTEND_PORT}" "frontend"

trap cleanup EXIT INT TERM

start_backend=1
if is_port_busy "${BACKEND_PORT}"; then
  if [[ "${REUSE_BACKEND_IF_BUSY}" == "1" ]]; then
    start_backend=0
    echo "Backend port ${BACKEND_PORT} already in use; reusing existing backend."
    echo "Tip: if new API routes 404 (e.g. Monitor /api/monitor/status, Sectors /api/catalog/industry-constituents), restart that process and re-run this script."
    echo "      POST to missing routes returns 405 from the SPA static handler — same fix."
    echo
    echo "WARNING: An old uvicorn on :${BACKEND_PORT} often causes POST /analyze 422 on hot_money, policy, lockup, kronos"
    echo "         (literal_error for analysts). Stop that process, then from repo root:"
    echo "           pip install -e '.[api]' && PYTHONPATH=\$(pwd) uvicorn api.main:app --host ${BACKEND_HOST} --port ${BACKEND_PORT}"
    echo "         Verify GET /config includes analyze_analyst_body_schema=registered_string_list on the running API."
    if ! wait_for_backend_ready "${BACKEND_PORT}"; then
      exit 1
    fi
  else
    free_port "${BACKEND_PORT}" "backend"
  fi
fi

if [[ "${start_backend}" == "1" ]]; then
  if ! command -v uvicorn >/dev/null 2>&1; then
    echo "Error: 'uvicorn' is not in PATH. Activate your Python environment first." >&2
    exit 1
  fi
  echo "Starting backend: ${BACKEND_CMD}"
  echo "(PYTHONPATH prepends repo root so ./api beats any stale tradingagents wheel.)"
  (cd "${ROOT_DIR}" && PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" eval "${BACKEND_CMD}") &
  backend_pid=$!

  if ! kill -0 "${backend_pid}" >/dev/null 2>&1; then
    echo "Error: backend failed to start." >&2
    exit 1
  fi
  if ! wait_for_backend_ready "${BACKEND_PORT}"; then
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
