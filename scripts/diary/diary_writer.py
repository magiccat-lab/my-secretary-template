#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = Path(os.environ.get("DIARY_STATE_PATH", ROOT / "data" / "diary_prompt_state.json"))
DB_PATH = Path(os.environ.get("DISCORD_CORPUS_DB", ROOT / "data" / "discord_corpus.sqlite3"))
NOTION_API = "https://api.notion.com/v1"


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_state() -> dict:
    path = STATE_PATH if STATE_PATH.is_absolute() else ROOT / STATE_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict) -> None:
    path = STATE_PATH if STATE_PATH.is_absolute() else ROOT / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def find_reply(prompt_at: str) -> dict | None:
    path = DB_PATH if DB_PATH.is_absolute() else ROOT / DB_PATH
    if not path.exists():
        return None
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """
            select message_id, content, created_at
            from messages
            where created_at > ?
            order by created_at asc
            limit 1
            """,
            (prompt_at,),
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


def notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def write_diary(date_value: str, reply: dict) -> str | None:
    notion_secret_present = bool(os.environ.get("NOTION_TOKEN"))
    dbid = os.environ.get("NOTION_DB_DIARY")
    if not notion_secret_present or not dbid:
        print("NOTION_TOKEN or NOTION_DB_DIARY is missing", file=sys.stderr)
        return None
    content = str(reply["content"])[:1900]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body = {
        "parent": {"database_id": dbid},
        "properties": {
            "Title": {"title": [{"text": {"content": f"Diary {date_value}"}}]},
            "SourceKey": {"rich_text": [{"text": {"content": f"diary:{date_value}"}}]},
            "Status": {"select": {"name": "done"}},
            "CreatedAt": {"date": {"start": now}},
            "UpdatedAt": {"date": {"start": now}},
            "Source": {"select": {"name": "discord"}},
            "ExternalId": {"rich_text": [{"text": {"content": str(reply["message_id"])}}]},
            "Date": {"date": {"start": date_value}},
            "Mood": {"select": {"name": "unknown"}},
            "Summary": {"rich_text": [{"text": {"content": content[:500]}}]},
            "Highlights": {"rich_text": [{"text": {"content": content}}]},
            "NextActions": {"rich_text": []},
        },
    }
    for _ in range(4):
        response = requests.post(f"{NOTION_API}/pages", headers=notion_headers(), json=body, timeout=30)
        if response.status_code == 429:
            time.sleep(float(response.headers.get("Retry-After", "1")))
            continue
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Notion HTTP {response.status_code}: {response.text[:300]}")
        return response.json()["id"]
    raise RuntimeError("Notion rate limit retry exceeded")


def main() -> int:
    if not env_bool("FEATURE_DIARY"):
        print("FEATURE_DIARY is not true; skipping")
        return 0
    state = load_state()
    prompt_at = state.get("last_prompt_at")
    date_value = state.get("last_prompt_date")
    if not prompt_at or not date_value:
        print("no diary prompt state")
        return 0
    written = set(state.get("written_dates", []))
    if date_value in written:
        print("diary already written")
        return 0
    reply = find_reply(prompt_at)
    if not reply:
        print("no reply found")
        return 0
    write_diary(date_value, reply)
    written.add(date_value)
    state["written_dates"] = sorted(written)[-60:]
    save_state(state)
    print("diary written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
