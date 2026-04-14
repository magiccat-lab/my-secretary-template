#!/usr/bin/env python3
"""次の Claude Code セッション用の handoff.md を生成する。

まとめる内容:
  - 指定チャンネルの Discord 直近メッセージ（12時間以内にアクティブなもの）
  - pending_tasks.json の未完了タスク
  - 今日の git ログ

出力先: ~/secretary/data/handoff.md

次のセッションは、コールドスタートするのではなく、起動時にこれを読んで
文脈を回復すること。
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from scripts.lib.jst import JST  # noqa: E402
from scripts.lib.task_store import load_tasks  # noqa: E402

HANDOFF_PATH = os.path.expanduser("~/secretary/data/handoff.md")

# スキャン対象のチャンネル。必要に応じて追加・削除（環境変数 -> チャンネルID）
CHANNELS = {name: os.getenv(env_key, "") for name, env_key in [
    ("random", "DISCORD_CHANNEL_RANDOM"),
]}


def _discord_token() -> str | None:
    """Discord bot トークンを返す。取得できなければ None"""
    tok = os.environ.get("DISCORD_BOT_TOKEN")
    if tok:
        return tok
    path = os.path.expanduser("~/.claude/channels/discord/.env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.startswith("DISCORD_BOT_TOKEN="):
                    return line.strip().split("=", 1)[1]
    return None


def fetch_messages(channel_id: str, limit: int = 15) -> list:
    """チャンネルの最新メッセージを取得。エラー時は []"""
    token = _discord_token()
    if not token or not channel_id:
        return []
    try:
        import requests

        r = requests.get(
            f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}",
            headers={"Authorization": f"Bot {token}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def format_message(msg: dict) -> str:
    author = msg.get("author", {}).get("username", "?")
    content = msg.get("content", "").replace("\n", " ")[:120]
    ts = msg.get("timestamp", "")[:16]
    return f"  - [{author} {ts}] {content}"


def get_pending_tasks() -> dict:
    try:
        data = load_tasks()
        out = {}
        for section, tasks in data.items():
            if not isinstance(tasks, list):
                continue
            out[section] = [t["title"] for t in tasks if not t.get("done")]
        return out
    except Exception:
        return {}


def get_git_log() -> str:
    now = datetime.now(JST)
    since = now.strftime("%Y-%m-%d 00:00")
    try:
        r = subprocess.run(
            ["git", "-C", _REPO_ROOT, "log", "--format=- %s", f"--since={since}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip() or "(なし)"
    except Exception:
        return "(取得できませんでした)"


def main() -> None:
    now = datetime.now(JST)
    lines = [f"# 引継ぎ: {now.strftime('%Y-%m-%d %H:%M')} (自動生成)", ""]

    # --- チャンネル文脈 ---
    lines.append("## 直近のチャンネル動向")
    lines.append("(最新15件、新しい順 — 直近12時間にアクティブなチャンネルのみ)")
    lines.append("")

    for name, ch_id in CHANNELS.items():
        if not ch_id:
            continue
        msgs = fetch_messages(ch_id, limit=30)
        if not msgs:
            continue

        recent = False
        for m in msgs:
            ts = m.get("timestamp", "")
            if not ts:
                continue
            try:
                mt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if (now - mt.astimezone(JST)).total_seconds() < 12 * 3600:
                    recent = True
                    break
            except Exception:
                pass
        if not recent:
            continue

        lines.append(f"### #{name} ({ch_id})")
        for m in reversed(msgs):
            lines.append(format_message(m))
        lines.append("")

    # --- 未完了タスク ---
    lines.append("## 未完了タスク")
    tasks = get_pending_tasks()
    any_task = False
    for section, items in tasks.items():
        if items:
            any_task = True
            lines.append(f"**{section}**")
            for t in items:
                lines.append(f"- {t}")
    if not any_task:
        lines.append("(なし)")
    lines.append("")

    # --- Git ログ ---
    lines.append("## 直近のコミット")
    lines.append(get_git_log())
    lines.append("")

    os.makedirs(os.path.dirname(HANDOFF_PATH), exist_ok=True)
    with open(HANDOFF_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"handoff written: {HANDOFF_PATH}")


if __name__ == "__main__":
    main()
