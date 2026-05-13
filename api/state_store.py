"""Optional durable key-value store for API runtime state (local JSON or Cloudflare KV)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import requests
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Env vars that may be persisted via admin UI (values are sensitive).
ALLOWED_PERSISTED_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_CN_API_KEY",
        "ZHIPU_API_KEY",
        "ZHIPU_CN_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "OPENROUTER_API_KEY",
        "MOONSHOT_API_KEY",
        "KIMI_CODE_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
    }
)


class StateStore:
    """Abstract KV facade."""

    def get_str(self, key: str) -> Optional[str]:
        raise NotImplementedError

    def put_str(self, key: str, value: str) -> None:
        raise NotImplementedError

    def get_json(self, key: str) -> Any:
        raw = self.get_str(key)
        if raw is None or raw == "":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON for state key %s", key)
            return None

    def put_json(self, key: str, value: Any) -> None:
        self.put_str(key, json.dumps(value, ensure_ascii=False))


class LocalFileStateStore(StateStore):
    """JSON object stored at ~/.tradingagents/api_state.json — keys map to JSON values."""

    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            home = Path(os.path.expanduser("~")) / ".tradingagents"
            home.mkdir(parents=True, exist_ok=True)
            path = Path(
                os.getenv("TRADINGAGENTS_API_STATE_FILE", str(home / "api_state.json"))
            )
        self._path = path
        self._root: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            text = self._path.read_text(encoding="utf-8")
            obj = json.loads(text)
            if isinstance(obj, dict):
                self._root = obj
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load state file %s: %s", self._path, exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._root, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_str(self, key: str) -> Optional[str]:
        if key not in self._root:
            return None
        val = self._root[key]
        if isinstance(val, str):
            return val
        return json.dumps(val, ensure_ascii=False)

    def put_str(self, key: str, value: str) -> None:
        try:
            self._root[key] = json.loads(value)
        except json.JSONDecodeError:
            self._root[key] = value
        self._save()


class CloudflareKVStore(StateStore):
    """Cloudflare Workers KV REST binding (account namespace)."""

    def __init__(
        self,
        account_id: str,
        namespace_id: str,
        api_token: str,
    ) -> None:
        self._base = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/storage/kv/namespaces/{namespace_id}/values"
        )
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "text/plain",
        }

    def get_str(self, key: str) -> Optional[str]:
        url = f"{self._base}/{quote(key, safe='')}"
        try:
            r = requests.get(url, headers=self._headers, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            logger.warning("KV get failed for %s: %s", key, exc)
            return None

    def put_str(self, key: str, value: str) -> None:
        url = f"{self._base}/{quote(key, safe='')}"
        r = requests.put(url, headers=self._headers, data=value.encode("utf-8"), timeout=60)
        r.raise_for_status()


_store: Optional[StateStore] = None


def get_state_store() -> StateStore:
    """Singleton state store: Cloudflare KV if configured, else local file."""
    global _store
    if _store is not None:
        return _store
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    ns = os.getenv("CLOUDFLARE_KV_NAMESPACE_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if account and ns and token:
        _store = CloudflareKVStore(account, ns, token)
        logger.info("State store: Cloudflare KV namespace_id=%s", ns)
    else:
        _store = LocalFileStateStore()
        logger.info("State store: local file")
    return _store


def reset_state_store_for_tests() -> None:
    global _store
    _store = None
