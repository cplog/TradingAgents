#!/usr/bin/env python3
"""Smoke-test the new parallel_analysts and semantic_debate_termination features."""

import os
import sys
import time
from pathlib import Path

# Repo root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

import datetime
TICKER = os.getenv("TEST_TICKER", "AAPL")
DATE = os.getenv("TEST_DATE", datetime.date.today().isoformat())

config = DEFAULT_CONFIG.copy()
# Use the same provider as the production API service (ollama-remote)
config["llm_provider"] = "ollama-remote"
# Available models on the remote Ollama instance: nemotron3:33b, qwen3.6:35b
config["deep_think_llm"] = "qwen3.6:35b"
config["quick_think_llm"] = "qwen3.6:35b"
config["parallel_analysts"] = True
config["semantic_debate_termination"] = True
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["dimensions_in_graph"] = True

SELECTED_ANALYSTS = [
    "market", "news",
]

# Clear any pending memory entries so reflection doesn't block the run
memory_path = Path(config["memory_log_path"])
if memory_path.exists():
    text = memory_path.read_text(encoding="utf-8")
    # Remove pending entries (simple heuristic: remove lines with | pending)
    cleaned = "\n".join(
        line for line in text.splitlines()
        if "| pending" not in line
    )
    if cleaned != text:
        memory_path.write_text(cleaned, encoding="utf-8")
        print("Cleared pending memory entries to skip reflection phase.")

print(f"=== TradingAgents New Features Smoke Test ===")
print(f"Ticker: {TICKER}")
print(f"Date:   {DATE}")
print(f"Analysts: {SELECTED_ANALYSTS}")
print(f"parallel_analysts: {config['parallel_analysts']}")
print(f"semantic_debate_termination: {config['semantic_debate_termination']}")
print(f"Provider: {config['llm_provider']}")
print(f"Deep think: {config['deep_think_llm']}")
print(f"Quick think: {config['quick_think_llm']}")
print()

t0 = time.time()

try:
    graph = TradingAgentsGraph(
        selected_analysts=SELECTED_ANALYSTS,
        config=config,
        debug=True,
    )
    final_state, decision = graph.propagate(TICKER, DATE)
    elapsed = time.time() - t0

    print(f"\n=== Completed in {elapsed:.1f}s ===")
    print(f"\nFinal Decision:\n{decision}\n")

    # Print which reports were generated
    for analyst in SELECTED_ANALYSTS:
        key = f"{analyst}_report" if analyst != "social" else "sentiment_report"
        report = final_state.get(key, "")
        status = f"{len(report)} chars" if report else "EMPTY"
        print(f"  {key}: {status}")

    # Check debate states
    inv = final_state.get("investment_debate_state", {})
    risk = final_state.get("risk_debate_state", {})
    print(f"\n  Bull/Bear turns: {inv.get('count', 0)}")
    print(f"  Risk turns:      {risk.get('count', 0)}")
    print(f"  Dimensions:      {'present' if final_state.get('dimensions_summary') else 'missing'}")

except Exception as e:
    elapsed = time.time() - t0
    print(f"\n=== FAILED after {elapsed:.1f}s ===")
    import traceback
    traceback.print_exc()
    sys.exit(1)
