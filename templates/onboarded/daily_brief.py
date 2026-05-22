#!/usr/bin/env python3
from __future__ import annotations
"""Sample task: morning brief with weather + tasks."""

import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load_user() -> str:
    for path in [ROOT / "AGENT" / "USER.md", ROOT / "shared" / "USER.md"]:
        if path.exists():
            return path.read_text(encoding="utf-8")[:4000]
    return "No USER.md found."

def load_tasks() -> list[str]:
    path = ROOT / "data" / "tasks.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def post_discord(message: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print(message)
        return
    import requests
    r = requests.post(webhook, json={"content": message}, timeout=20)
    r.raise_for_status()

def main() -> int:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    user = load_user()
    tasks = load_tasks()[:8]
    task_block = "\n".join(f"- {t}" for t in tasks) if tasks else "- No local tasks found."

    message = (
        f"Daily brief {today}\n\n"
        f"Tasks:\n{task_block}\n\n"
        f"Context loaded from USER.md: {len(user)} chars"
    )
    post_discord(message[:1900])
    return 0

if __name__ == "__main__":
    sys.exit(main())
