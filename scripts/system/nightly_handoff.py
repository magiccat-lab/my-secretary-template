#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "claude" / "handoff.md"


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def run_git_log() -> str:
    since = os.environ.get("HANDOFF_GIT_SINCE", "00:00")
    cmd = ["git", "log", f"--since={since}", "--oneline", "--decorate", "--stat"]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=20)
    if proc.returncode != 0:
        return f"(git log unavailable: {proc.stderr.strip()[:300]})"
    return proc.stdout.strip() or "(no commits today)"


def load_pending_tasks() -> list[dict]:
    path = Path(os.environ.get("PENDING_TASKS_PATH", ROOT / "data" / "pending_tasks.json"))
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [{"title": "pending task file exists but is not valid JSON", "status": "error"}]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        tasks = data.get("tasks", [])
        return [item for item in tasks if isinstance(item, dict)]
    return []


def recent_discord_rows() -> list[dict]:
    db_path = Path(os.environ.get("DISCORD_CORPUS_DB", ROOT / "data" / "discord_corpus.sqlite3"))
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    if not db_path.exists():
        return []
    limit = int(os.environ.get("HANDOFF_DISCORD_LIMIT", "40"))
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            select created_at, channel_name, author_name, content
            from messages
            order by created_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows][::-1]


def summarize_task(item: dict) -> str:
    title = str(item.get("title") or item.get("Title") or item.get("task") or item)[:160]
    status = str(item.get("status") or item.get("Status") or "open")
    due = str(item.get("due") or item.get("DueAt") or item.get("due_at") or "")
    suffix = f" due={due}" if due else ""
    return f"- [{status}] {title}{suffix}"


def render() -> str:
    now = dt.datetime.now().isoformat(timespec="seconds")
    tasks = load_pending_tasks()
    rows = recent_discord_rows()
    lines = [
        "# Nightly Handoff",
        "",
        f"- GeneratedAt: {now}",
        f"- Repository: {ROOT.name}",
        "",
        "## Git Activity",
        "",
        "```text",
        run_git_log(),
        "```",
        "",
        "## Pending Tasks",
        "",
    ]
    if tasks:
        lines.extend(summarize_task(item) for item in tasks[:50])
    else:
        lines.append("(no pending tasks found)")
    lines.extend(["", "## Recent Discord Messages", ""])
    if rows:
        for row in rows:
            created = row.get("created_at", "")
            channel = row.get("channel_name") or "unknown-channel"
            author = row.get("author_name") or "unknown-author"
            content = str(row.get("content") or "").replace("\n", " ")[:240]
            lines.append(f"- {created} #{channel} {author}: {content}")
    else:
        lines.append("(no recent corpus rows found)")
    lines.extend(["", "## Next Session Checklist", "", "- Review pending tasks.", "- Check failed cron jobs.", "- Continue from the most recent user request.", ""])
    return "\n".join(lines)


def maybe_restart() -> None:
    command = os.environ.get("HANDOFF_RESTART_COMMAND", "").strip()
    if not command:
        return
    subprocess.run(command, shell=True, cwd=ROOT, check=False, timeout=60)


def main() -> int:
    if not env_bool("FEATURE_HANDOFF"):
        print("FEATURE_HANDOFF is not true; skipping")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT}")
    maybe_restart()
    return 0


if __name__ == "__main__":
    sys.exit(main())
