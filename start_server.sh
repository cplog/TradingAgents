#!/bin/bash
# TradingAgents backend-only startup script
# Uses the project-local .venv-linux virtual environment

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv-linux/bin/python"

if [[ ! -f "${VENV_PYTHON}" ]]; then
  echo "Error: ${VENV_PYTHON} not found. Run: ./scripts/setup_venv.sh" >&2
  exit 1
fi

echo "Using Python: ${VENV_PYTHON}"
"${VENV_PYTHON}" --version
echo ""
echo "Starting uvicorn server..."
echo ""

exec "${VENV_PYTHON}" -m uvicorn api.main:app --host 0.0.0.0 --port 8808 --reload
