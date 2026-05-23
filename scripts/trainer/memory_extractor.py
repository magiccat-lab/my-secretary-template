#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("DISCORD_CORPUS_DB", ROOT / "data" / "discord_corpus.sqlite3"))
NOTION_API = "https://api.notion.com/v1"
PATTERNS = [
    ("preference", re.compile(r"\b(i prefer|i like|please use|avoid|don't use)\b", re.I), 0.70),
    ("decision", re.compile(r"\b(decided|decision|we will|let's use|ship it)\b", re.I), 0.75),
    ("fact", re.compile(r"\b(my|our|the)\s+[\w -]{2,40}\s+(is|are|means)\b", re.I), 0.60),
]


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def recent_messages() -> list[dict]:
    path = DB_PATH if DB_PATH.is_absolute() else ROOT / DB_PATH
    if not path.exists():
        return []
    days = int(os.environ.get("TRAINER_LOOKBACK_DAYS", "14"))
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            select message_id, content, created_at
            from messages
            where created_at >= ?
            order by created_at asc
            """,
            (since,),
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def candidates() -> list[dict]:
    minimum = float(os.environ.get("TRAINER_MIN_CONFIDENCE", "0.60"))
    out = []
    seen = set()
    for row in recent_messages():
        for line in re.split(r"[\n。.!?]+", row["content"]):
            text = line.strip()
            if len(text) < 12:
                continue
            for kind, pattern, confidence in PATTERNS:
                if confidence < minimum or not pattern.search(text):
                    continue
                key = hashlib.sha256(f"{kind}:{text}".encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"kind": kind, "summary": text[:500], "evidence": row["message_id"], "confidence": confidence, "key": key})
    return out


def headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def push_memory(item: dict) -> str | None:
    notion_secret_present = bool(os.environ.get("NOTION_TOKEN"))
    dbid = os.environ.get("NOTION_DB_MEMORY")
    if not notion_secret_present or not dbid:
        return None
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body = {
        "parent": {"database_id": dbid},
        "properties": {
            "Title": {"title": [{"text": {"content": item["summary"][:80] or "memory"}}]},
            "SourceKey": {"rich_text": [{"text": {"content": item["key"]}}]},
            "Status": {"select": {"name": "new"}},
            "CreatedAt": {"date": {"start": now}},
            "UpdatedAt": {"date": {"start": now}},
            "Source": {"select": {"name": "discord"}},
            "ExternalId": {"rich_text": [{"text": {"content": item["evidence"]}}]},
            "Kind": {"select": {"name": item["kind"]}},
            "Confidence": {"number": item["confidence"]},
            "Summary": {"rich_text": [{"text": {"content": item["summary"]}}]},
            "Evidence": {"rich_text": [{"text": {"content": item["evidence"]}}]},
        },
    }
    for _ in range(4):
        response = requests.post(f"{NOTION_API}/pages", headers=headers(), json=body, timeout=30)
        if response.status_code == 429:
            time.sleep(float(response.headers.get("Retry-After", "1")))
            continue
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Notion HTTP {response.status_code}: {response.text[:300]}")
        return response.json()["id"]
    raise RuntimeError("Notion rate limit retry exceeded")


def main() -> int:
    if not env_bool("FEATURE_TRAINER"):
        print("FEATURE_TRAINER is not true; skipping")
        return 0
    items = candidates()
    pushed = 0
    for item in items:
        if push_memory(item):
            pushed += 1
    print(f"candidates={len(items)} pushed={pushed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
