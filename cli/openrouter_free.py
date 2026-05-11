"""OpenRouter free-model helpers.

This is a standalone extension module so upstream pulls rarely conflict.
Enable by setting the environment variable TRADINGAGENTS_OPENROUTER_FREE_ONLY=1
or by setting config["openrouter_free_only"] = True.
"""
import os
from typing import List, Tuple

from rich.console import Console

console = Console()


def fetch_free_models(top_n: int = 10) -> List[Tuple[str, str]]:
    """Fetch free models from OpenRouter (prompt + completion price == 0)."""
    import requests

    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        resp.raise_for_status()
        models = resp.json().get("data", [])
    except Exception as e:
        console.print(f"\n[yellow]Could not fetch OpenRouter models: {e}[/yellow]")
        return []

    choices: List[Tuple[str, str]] = []
    for m in models:
        model_id = m.get("id", "")
        name = m.get("name") or model_id
        pricing = m.get("pricing", {})
        try:
            prompt_price = float(pricing.get("prompt", "0") or 0)
            completion_price = float(pricing.get("completion", "0") or 0)
        except ValueError:
            continue

        if prompt_price > 0 or completion_price > 0:
            continue

        # Prefer models that support tools (needed for structured agents)
        supports_tools = "tools" in m.get("supported_parameters", [])
        sort_key = (not supports_tools, name)
        choices.append((sort_key, name, model_id))

    choices.sort(key=lambda x: x[0])
    return [(name, mid) for _, name, mid in choices[:top_n]]


def select_openrouter_free_model() -> str:
    """Interactive picker limited to free models, with openrouter/free fallback."""
    import questionary

    models = fetch_free_models(top_n=10)

    if not models:
        console.print("[yellow]No free models discovered; falling back to openrouter/free.[/yellow]")
        return "openrouter/free"

    choices = [questionary.Choice(name, value=mid) for name, mid in models]
    choices.append(questionary.Choice("Auto (openrouter/free)", value="openrouter/free"))
    choices.append(questionary.Choice("Custom model ID", value="custom"))

    choice = questionary.select(
        "Select OpenRouter Model (free tier):",
        choices=choices,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style([
            ("selected", "fg:magenta noinherit"),
            ("highlighted", "fg:magenta noinherit"),
            ("pointer", "fg:magenta noinherit"),
        ]),
    ).ask()

    if choice is None or choice == "custom":
        return questionary.text(
            "Enter OpenRouter model ID:",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
        ).ask().strip()

    return choice
