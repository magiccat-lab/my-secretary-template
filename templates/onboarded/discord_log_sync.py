#!/usr/bin/env python3
from __future__ import annotations
"""Sample task: invoke Discord log sync to Notion."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "discord_corpus.sqlite3"

def main() -> int:
    if not DB.exists():
        print(f"{DB} does not exist. Run corpus_writer.py first.", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB)
    rows = con.execute(
        "select created_at, channel_id, author_name, content from messages order by id desc limit 10"
    ).fetchall()
    con.close()

    for created_at, channel_id, author, content in rows:
        print(f"{created_at} #{channel_id} {author}: {content[:120]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
