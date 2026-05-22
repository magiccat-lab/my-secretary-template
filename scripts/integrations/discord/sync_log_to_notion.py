#!/usr/bin/env python3
from __future__ import annotations
"""Daily batch: backfill un-synced rows from local SQLite to Notion."""

import os
import sqlite3
import sys
from pathlib import Path

from corpus_writer import DB, init_db, notion_push

def main() -> int:
    if not os.environ.get("NOTION_TOKEN") or not os.environ.get("NOTION_DB_CONVERSATION_LOG"):
        print("NOTION_TOKEN and NOTION_DB_CONVERSATION_LOG are required.", file=sys.stderr)
        return 1

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    init_db(con)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select * from messages where notion_page_id is null order by id asc limit 100"
    ).fetchall()

    count = 0
    for row in rows:
        page_id = notion_push(dict(row))
        con.execute(
            "update messages set notion_page_id=?, synced_at=datetime('now') where id=?",
            (page_id, row["id"]),
        )
        con.commit()
        count += 1

    con.close()
    print(f"synced {count} messages")
    return 0

if __name__ == "__main__":
    sys.exit(main())
