#!/usr/bin/env python3
from __future__ import annotations
"""Sanitize and push Discord messages to local SQLite + Notion Conversation Log DB."""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
DB = Path(os.environ.get("DISCORD_CORPUS_DB", ROOT / "data" / "discord_corpus.sqlite3"))

SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|secret_[A-Za-z0-9]{12,}|[A-Za-z0-9+/]{80,})")

def sanitize(text: str) -> str:
    try:
        sys.path.insert(0, str(ROOT))
        from scripts.lib import sanitize_lint  # type: ignore
        for _, pattern in getattr(sanitize_lint, "PATTERNS", []):
            text = re.sub(pattern, "[REDACTED]", text)
        return text
    except Exception:
        return SECRET_RE.sub("[REDACTED]", text)

def init_db(con: sqlite3.Connection) -> None:
    con.execute("""
    create table if not exists messages (
      id integer primary key autoincrement,
      message_id text unique,
      channel_id text not null,
      channel_name text,
      author_id text,
      author_name text,
      content text not null,
      content_hash text not null,
      created_at text not null,
      notion_page_id text,
      synced_at text
    )
    """)
    con.commit()

def write_local(row: dict) -> bool:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    init_db(con)
    try:
        con.execute("""
        insert into messages(message_id, channel_id, channel_name, author_id, author_name, content, content_hash, created_at)
        values(?,?,?,?,?,?,?,?)
        """, (
            row["message_id"], row["channel_id"], row.get("channel_name", ""),
            row.get("author_id", ""), row.get("author_name", ""),
            row["content"], row["content_hash"], row["created_at"],
        ))
        con.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()

def notion_push(row: dict) -> str | None:
    token = os.environ.get("NOTION_TOKEN")
    dbid = os.environ.get("NOTION_DB_CONVERSATION_LOG")
    if not token or not dbid:
        return None
    body = {
        "parent": {"database_id": dbid},
        "properties": {
            "Title": {"title": [{"text": {"content": row["content"][:80] or "message"}}]},
            "Platform": {"select": {"name": "discord"}},
            "ChannelId": {"rich_text": [{"text": {"content": row["channel_id"]}}]},
            "MessageId": {"rich_text": [{"text": {"content": row["message_id"]}}]},
            "Role": {"select": {"name": "user"}},
            "Message": {"rich_text": [{"text": {"content": row["content"][:1900]}}]},
            "Sanitized": {"checkbox": True},
            "CreatedAt": {"date": {"start": row["created_at"]}},
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    for attempt in range(4):
        r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", "1")))
            continue
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Notion HTTP {r.status_code}: {r.text[:500]}")
        return r.json()["id"]
    raise RuntimeError("Notion rate limit retry exceeded")

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--message-id", required=True)
    p.add_argument("--channel-id", required=True)
    p.add_argument("--channel-name", default="")
    p.add_argument("--author-id", default="")
    p.add_argument("--author-name", default="")
    p.add_argument("--content", required=True)
    p.add_argument("--push-notion", action="store_true")
    args = p.parse_args()

    content = sanitize(args.content)
    row = {
        "message_id": args.message_id,
        "channel_id": args.channel_id,
        "channel_name": args.channel_name,
        "author_id": args.author_id,
        "author_name": args.author_name,
        "content": content,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    inserted = write_local(row)
    if inserted and args.push_notion:
        notion_push(row)
    print("inserted" if inserted else "duplicate")
    return 0

if __name__ == "__main__":
    sys.exit(main())
