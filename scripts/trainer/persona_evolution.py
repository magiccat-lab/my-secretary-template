#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("DISCORD_CORPUS_DB", ROOT / "data" / "discord_corpus.sqlite3"))
OUT = Path(os.environ.get("TRAINER_PERSONA_OUTPUT", ROOT / "data" / "notes" / "persona_suggestions.md"))
AGENT_FILES = [ROOT / "AGENT" / name for name in ("AGENTS.md", "USER.md", "IDENTITY.md", "JOBS.md")]


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def recent_lines() -> list[str]:
    path = DB_PATH if DB_PATH.is_absolute() else ROOT / DB_PATH
    if not path.exists():
        return []
    days = int(os.environ.get("TRAINER_LOOKBACK_DAYS", "14"))
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    con = sqlite3.connect(path)
    try:
        rows = con.execute("select content from messages where created_at >= ?", (since,)).fetchall()
    finally:
        con.close()
    lines = []
    for (content,) in rows:
        lines.extend(part.strip() for part in re.split(r"[\n。.!?]+", content or "") if len(part.strip()) >= 12)
    return lines


def existing_text() -> str:
    chunks = []
    for path in AGENT_FILES:
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks).lower()


def build_suggestions() -> str:
    now = dt.datetime.now().isoformat(timespec="seconds")
    existing = existing_text()
    lines = recent_lines()
    patterns = [
        ("Preference candidates", re.compile(r"\b(i prefer|i like|please use|avoid|don't use)\b", re.I)),
        ("Workflow candidates", re.compile(r"\b(always|never|before you|after you|when asked)\b", re.I)),
        ("Decision candidates", re.compile(r"\b(decided|decision|we will|let's use|ship it)\b", re.I)),
    ]
    out = ["# Persona Suggestions", "", f"GeneratedAt: {now}", "", "Review these suggestions manually before editing persona files.", ""]
    for title, pattern in patterns:
        counts = Counter(line for line in lines if pattern.search(line))
        out.extend([f"## {title}", ""])
        added = 0
        for line, count in counts.most_common(20):
            if line.lower() in existing:
                continue
            out.append(f"- count={count}: {line[:240]}")
            added += 1
        if added == 0:
            out.append("(no new candidates)")
        out.append("")
    return "\n".join(out)


def main() -> int:
    if not env_bool("FEATURE_TRAINER"):
        print("FEATURE_TRAINER is not true; skipping")
        return 0
    path = OUT if OUT.is_absolute() else ROOT / OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_suggestions(), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
