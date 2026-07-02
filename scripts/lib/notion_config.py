"""Notion 連携の設定ローダー。

`.env` に直接書かれた `NOTION_DB_*` を優先し、無ければ `SECRETARY_ENV_DB_ID`
で指定された Notion の環境設定 DB から値を取得する。
"""

from __future__ import annotations

import os
from typing import Any

import requests

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TIMEOUT_SEC = 30

_ENV_DB_CACHE: dict[str, str] | None = None


def notion_token() -> str:
    """現行名を優先し、旧名 `NOTION_TOKEN` にも fallback する。"""
    return os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN", "")


def notion_headers(token: str | None = None) -> dict[str, str]:
    token = token if token is not None else notion_token()
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def get_notion_setting(key: str, default: str = "") -> str:
    """環境変数または環境設定 DB から `key` の値を取得する。"""
    direct = os.environ.get(key)
    if direct:
        return direct
    return _load_env_db_settings().get(key, default)


def _load_env_db_settings() -> dict[str, str]:
    global _ENV_DB_CACHE
    if _ENV_DB_CACHE is not None:
        return _ENV_DB_CACHE

    token = notion_token()
    env_db_id = os.environ.get("SECRETARY_ENV_DB_ID", "")
    if not token or not env_db_id:
        _ENV_DB_CACHE = {}
        return _ENV_DB_CACHE

    url = f"{NOTION_API}/databases/{env_db_id}/query"
    payload: dict[str, Any] = {"page_size": 100}
    settings: dict[str, str] = {}

    while True:
        r = requests.post(
            url,
            headers=notion_headers(token),
            json=payload,
            timeout=TIMEOUT_SEC,
        )
        r.raise_for_status()
        body = r.json()
        for page in body.get("results", []):
            key, value = _setting_from_page(page.get("properties", {}))
            if key and value:
                settings[key] = value

        if not body.get("has_more"):
            break
        payload["start_cursor"] = body.get("next_cursor")

    _ENV_DB_CACHE = settings
    return settings


def _setting_from_page(props: dict[str, Any]) -> tuple[str, str]:
    key = _first_prop_text(props, ("設定名", "key", "Key", "Name", "名前"), prefer_title=True)
    value = _first_prop_text(props, ("値", "value", "Value", "設定値"))
    return key.strip(), value.strip()


def _first_prop_text(
    props: dict[str, Any],
    names: tuple[str, ...],
    *,
    prefer_title: bool = False,
) -> str:
    for name in names:
        if name in props:
            text = _prop_text(props[name])
            if text:
                return text

    if prefer_title:
        for prop in props.values():
            if prop.get("type") == "title":
                text = _prop_text(prop)
                if text:
                    return text

    for prop in props.values():
        if prop.get("type") == "rich_text":
            text = _prop_text(prop)
            if text:
                return text
    return ""


def _prop_text(prop: dict[str, Any]) -> str:
    prop_type = prop.get("type")
    value = prop.get(prop_type)
    if prop_type in {"title", "rich_text"}:
        return "".join(part.get("plain_text", "") for part in value or [])
    if prop_type == "select" and value:
        return value.get("name", "")
    if prop_type in {"url", "email", "phone_number"}:
        return value or ""
    if prop_type == "number" and value is not None:
        return str(value)
    if prop_type == "checkbox":
        return "true" if value else "false"
    if prop_type == "formula":
        return _prop_text(value or {})
    return ""
