#!/usr/bin/env bash
# Smoke-test: local pydantic accepts extended analysts + POST /analyze returns 200 (not 422).
# Usage: from repo root, API already on API_URL (default http://127.0.0.1:8000).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
API="${API_URL:-http://127.0.0.1:8000}"
DATE="$(date +%Y-%m-%d)"

echo "=== 1) Pydantic: AnalyzeRequest with hot_money (must succeed) ==="
python - <<'PY'
from api.models import AnalyzeRequest

AnalyzeRequest.model_validate(
    {
        "ticker": "AAPL",
        "analysts": ["market", "social", "news", "fundamentals", "hot_money", "policy", "lockup", "kronos"],
    }
)
print("OK — this checkout accepts extended analysts.")
PY

echo
echo "=== 2) GET ${API}/config (schema hints) ==="
# Note: do not use `curl ... | python - <<'PY'` — the heredoc steals stdin from the pipe.
curl -sS "${API}/config" | python -c 'import json, sys
try:
    j = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print("ERROR: /config not JSON — wrong URL or API down?", e, file=sys.stderr)
    sys.exit(2)
sig = j.get("analyze_analyst_body_schema")
ids = j.get("supported_analyst_ids") or []
print(f"analyze_analyst_body_schema: {sig!r}")
print(f"supported_analyst_ids ({len(ids)}): {ids}")
if sig != "registered_string_list":
    print(
        "WARNING: stale API — POST may still use four-way Literal and return 422.",
        file=sys.stderr,
    )
'

echo
echo "=== 3) POST ${API}/analyze (enqueue job; analysts include hot_money) ==="
export DATE
BODY="$(python -c "import json, os; print(json.dumps({'ticker':'AAPL','date':os.environ['DATE'],'analysts':['market','social','news','fundamentals','hot_money','policy','lockup','kronos'],'config_overrides':{'max_debate_rounds':1,'max_risk_discuss_rounds':1}}))")"

resp="$(curl -sS -o /tmp/ta_analyze_resp.json -w "%{http_code}" -X POST "${API}/analyze" \
  -H "Content-Type: application/json" \
  -d "${BODY}")"
echo "HTTP ${resp}"
cat /tmp/ta_analyze_resp.json | python -m json.tool 2>/dev/null || cat /tmp/ta_analyze_resp.json
echo

if [[ "${resp}" != "200" ]]; then
  echo "FAILED — fix stale uvicorn (kill :8000) then:" >&2
  echo "  cd \"${ROOT}\" && pip install -e '.[api]' && PYTHONPATH=\"${ROOT}\" uvicorn api.main:app --port 8000" >&2
  echo "Or restart dev stack without reusing a busy port:" >&2
  echo "  REUSE_BACKEND_IF_BUSY=0 ./scripts/dev_up.sh" >&2
  echo >&2
  echo "If you only need a quick POST smoke against an OLD API (four analysts):" >&2
  echo "  curl -sS -X POST \"${API}/analyze\" -H \"Content-Type: application/json\" \\" >&2
  echo "    -d '{\"ticker\":\"AAPL\",\"date\":\"'\"${DATE}\"'\",\"analysts\":[\"market\",\"social\",\"news\",\"fundamentals\"],\"config_overrides\":{\"max_debate_rounds\":1,\"max_risk_discuss_rounds\":1}}'" >&2
  exit 1
fi

echo "SUCCESS — poll GET ${API}/jobs/<job_id> for status."
