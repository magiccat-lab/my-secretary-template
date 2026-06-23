"""notion_env.py — Notion API key and DB ID resolver.

Reads NOTION_API_KEY (with NOTION_TOKEN fallback) and resolves DB IDs
from either environment variables or a bootstrap cache populated from
the 環境設定 DB.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_SECRETARY_HOME = Path(os.environ.get(
    "SECRETARY_HOME", str(Path(__file__).resolve().parents[2])
))
_CACHE_PATH = _SECRETARY_HOME / "data" / "notion_env_cache.json"

_ENV_KEY_MAP = {
    "tasks": "NOTION_DB_TASKS",
    "wishlist": "NOTION_DB_WISHLIST",
    "log_library": "NOTION_DB_LOG_LIBRARY",
}


def get_api_key() -> str:
    return os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN") or ""


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def get_db_id(name: str) -> str:
    """Resolve a DB ID by name (tasks / wishlist / log_library).

    Priority: env var > bootstrap cache > empty string.
    """
    env_key = _ENV_KEY_MAP.get(name, "")
    if env_key:
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    cache = _load_cache()
    cache_values = cache.get("values", {})
    for k, v in cache_values.items():
        if name.replace("_", "").lower() in k.replace("_", "").lower():
            if v:
                return str(v).strip()
    return ""


def get_env_db_id() -> str:
    return os.environ.get("SECRETARY_ENV_DB_ID", "").strip()
