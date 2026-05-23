#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "discord_corpus.sqlite3"


def _db_path(db_path: str | None = None) -> Path:
    raw = db_path or os.environ.get("DISCORD_CORPUS_DB") or str(DEFAULT_DB)
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _tokens(query: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[\w\-@.]+", query) if len(t) >= 2]


def _score(text: str, tokens: list[str]) -> int:
    low = text.lower()
    return sum(low.count(token) for token in tokens)


def search_corpus(query: str, limit: int = 10, db_path: str | None = None) -> list[dict]:
    path = _db_path(db_path)
    if not query.strip() or not path.exists():
        return []
    max_rows = int(os.environ.get("CHAT_SEARCH_MAX_ROWS", "5000"))
    tokens = _tokens(query)
    if not tokens:
        return []
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            select message_id, channel_id, channel_name, author_name, content, created_at
            from messages
            order by created_at desc
            limit ?
            """,
            (max_rows,),
        ).fetchall()
    finally:
        con.close()
    hits = []
    for row in rows:
        content = row["content"] or ""
        score = _score(content, tokens)
        if score <= 0:
            continue
        item = dict(row)
        item["score"] = score
        item["snippet"] = content.replace("\n", " ")[:300]
        hits.append(item)
    hits.sort(key=lambda item: (item["score"], item["created_at"]), reverse=True)
    return hits[:limit]


def reason_with_claude(query: str, hits: list[dict]) -> str:
    command = os.environ.get("CHAT_SEARCH_CLAUDE_CMD", "claude")
    if not shutil.which(command):
        return ""
    context = "\n".join(f"- {h['created_at']} #{h.get('channel_name') or ''}: {h['snippet']}" for h in hits)
    prompt = (
        "Summarize these local chat search hits. Do not invent facts. "
        f"Query: {query}\n\nHits:\n{context}"
    )
    proc = subprocess.run(
        [command, "-p", prompt],
        text=True,
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--db")
    parser.add_argument("--reason", action="store_true")
    args = parser.parse_args()

    hits = search_corpus(args.query, args.limit, args.db)
    for hit in hits:
        channel = hit.get("channel_name") or hit.get("channel_id") or "unknown"
        print(f"{hit['created_at']} score={hit['score']} #{channel} {hit.get('author_name') or ''}")
        print(hit["snippet"])
        print()
    if args.reason and hits:
        summary = reason_with_claude(args.query, hits)
        if summary:
            print("## Reasoned Summary")
            print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
