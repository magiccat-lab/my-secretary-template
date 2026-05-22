#!/usr/bin/env python3
from __future__ import annotations
"""Sample task: digest of open tasks via Discord post."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS_JSON = ROOT / "data" / "tasks.json"

def load_tasks() -> list[dict]:
    if not TASKS_JSON.exists():
        return []
    return json.loads(TASKS_JSON.read_text(encoding="utf-8"))

def main() -> int:
    tasks = load_tasks()
    open_tasks = [t for t in tasks if t.get("status", "open") not in {"done", "archived"}]
    urgent = [t for t in open_tasks if t.get("priority") in {"high", "urgent"}]

    print("Task digest")
    print(f"- open: {len(open_tasks)}")
    print(f"- urgent: {len(urgent)}")
    for task in open_tasks[:10]:
        title = task.get("title", "Untitled")
        due = task.get("due", "no due")
        priority = task.get("priority", "normal")
        print(f"- [{priority}] {title} ({due})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
