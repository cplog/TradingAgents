"""One-off diagnostic for the Topics extraction pipeline.

Picks one topic from the live state store, replays its latest run's articles
through the LLM extractor, and prints WHAT THE LLM ACTUALLY RETURNED at every
fallback stage. No mutation of state; safe to re-run.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env so TAVILY_API_KEY / LLM provider / Cloudflare creds are picked up.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

from api.config import build_service_config  # noqa: E402
from api.state_store import get_state_store  # noqa: E402
from api.topics_models import ExtractionResult, TopicArticle  # noqa: E402
from api.topics_store import get_topics_store  # noqa: E402
from api.topics_extract import _SYSTEM, _articles_to_prompt, _build_llm  # noqa: E402


def banner(text: str) -> None:
    print(f"\n{'=' * 8} {text} {'=' * 8}")


def main() -> int:
    cfg = build_service_config()
    print(f"provider={cfg.get('llm_provider')!r}  quick_think_llm={cfg.get('quick_think_llm')!r}")
    print(f"backend_url={cfg.get('backend_url')!r}")

    store = get_topics_store(get_state_store())
    topics = store.list_topics()
    if not topics:
        print("No topics in store. Run the API server once to seed.")
        return 1

    # Pick first topic that has a latest completed run with articles
    chosen = None
    for t in topics:
        latest = store.latest_run(t.id)
        if latest and latest.articles:
            chosen = (t, latest)
            break
    if chosen is None:
        print("No topic has cached articles yet. Run /refresh on one first.")
        return 1

    topic, latest_run = chosen
    print(f"\nTopic: {topic.id} — {topic.label}")
    print(f"Articles in latest run: {len(latest_run.articles)}")
    print(f"Existing candidates in latest run: {len(latest_run.candidates)}")
    print(f"Existing theme_summary: {(latest_run.theme_summary or '')[:160]!r}")

    articles = latest_run.articles[:8]  # cap to keep prompt small for diagnosis
    user_prompt = _articles_to_prompt(articles, topic.query)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    print(f"\nPrompt user-section length: {len(user_prompt)} chars")

    llm = _build_llm(cfg)
    print(f"\nLLM object type: {type(llm).__name__}")
    inner_model = getattr(llm, "_llm", llm)
    print(f"Inner model attrs: model_name={getattr(inner_model, 'model_name', None)!r}  "
          f"base_url={getattr(inner_model, 'openai_api_base', None)!r}")

    banner("STAGE 1: with_structured_output")
    try:
        structured = llm.with_structured_output(ExtractionResult)
        print(f"bind ok: structured type={type(structured).__name__}")
        result = structured.invoke(messages)
        print(f"invoke returned type: {type(result).__name__}")
        try:
            dumped = result.model_dump() if hasattr(result, "model_dump") else result
            print(json.dumps(dumped, indent=2, default=str)[:2000])
        except Exception as exc:
            print(f"dump error: {exc}; repr={result!r}")
    except Exception as exc:
        print(f"with_structured_output FAILED: {type(exc).__name__}: {exc}")

    banner("STAGE 2: raw llm.invoke (plain text)")
    try:
        raw = llm.invoke(messages)
        text = getattr(raw, "content", raw)
        if not isinstance(text, str):
            text = str(text)
        print(f"raw type: {type(raw).__name__}, content length: {len(text)}")
        print("--- BEGIN RAW CONTENT ---")
        print(text[:3000])
        print("--- END RAW CONTENT ---")
    except Exception as exc:
        print(f"plain invoke FAILED: {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
