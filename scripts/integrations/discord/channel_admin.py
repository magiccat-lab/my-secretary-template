#!/usr/bin/env python3
from __future__ import annotations
"""Discord `+ch <id> <name>` admin command to register a channel into Channel DB."""

import argparse
import datetime as dt
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "data" / "discord_channels.sqlite3"
CMD_RE = re.compile(r"^\+ch\s+(\S+)\s+(.+)$")

def init_db(con: sqlite3.Connection) -> None:
    con.execute("""
    create table if not exists channels (
      channel_id text primary key,
      channel_name text not null,
      created_at text not null
    )
    """)
    con.commit()

def add_channel(channel_id: str, name: str) -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    init_db(con)
    con.execute(
        "insert or replace into channels(channel_id, channel_name, created_at) values(?,?,?)",
        (channel_id, name, dt.datetime.now(dt.timezone.utc).isoformat()),
    )
    con.commit()
    con.close()

def parse_command(text: str) -> tuple[str, str] | None:
    m = CMD_RE.match(text.strip())
    if not m:
        return None
    return m.group(1), m.group(2).strip()

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("message", nargs="*")
    p.add_argument("--channel-id")
    p.add_argument("--name")
    args = p.parse_args()

    if args.channel_id and args.name:
        add_channel(args.channel_id, args.name)
        print(f"added {args.channel_id} {args.name}")
        return 0

    parsed = parse_command(" ".join(args.message))
    if not parsed:
        print("usage: +ch <id> <name>", file=sys.stderr)
        return 2
    add_channel(*parsed)
    print(f"added {parsed[0]} {parsed[1]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
