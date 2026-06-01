#!/usr/bin/env python3
"""session_watchdog.py — 固まった Claude Code セッションを自動復帰させる。

health_check.sh は「セッションが落ちた」は拾えるが「生きてるけど固まった」
（使用量上限プロンプト待ち / 選択肢プロンプト待ち / MCP 認証待ち / キュー詰まり）は
拾えない。このスクリプトは screen のバッファを覗いて既知のスタックパターンを検出し、
`screen -X stuff` で適切なキーを送って復帰させる。

cron の例（2 分おき）:
    */2 * * * * /usr/bin/python3 ~/secretary/scripts/session_watchdog.py >> /tmp/session_watchdog.log 2>&1

dry-run（送信せず検出だけ）:
    WATCHDOG_DRY_RUN=1 python3 ~/secretary/scripts/session_watchdog.py

環境変数:
    WATCHDOG_DRY_RUN       1 なら stuff せず検出ログのみ
    DISCORD_CHANNEL_RANDOM  通知先（任意。未設定なら通知しない）
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[1])))
load_dotenv(SECRETARY_HOME / ".env")

JST = timezone(timedelta(hours=9))
SESSION_NAME = "secretary"  # start_server.sh が立てる screen 名
SESSION_FILE = Path("/tmp/secretary_session.txt")  # 実 screen 名（あれば優先）
STATE_FILE = SECRETARY_HOME / "data" / "watchdog_state.json"
DRY_RUN = os.environ.get("WATCHDOG_DRY_RUN", "0") == "1"

DEDUP_SECONDS = 60
LOOP_WINDOW_HOURS = 24
LOOP_MAX_FIRES = 8

# (name, 正規表現リスト, 送信キー, 通知するか)
PATTERNS = [
    ("usage_limit",
     [r"5[-\s]hour limit reached", r"usage\s+limit\s+(exceeded|reached)", r"rate\s+limit\s+reached"],
     "1\n", True),
    ("choice_prompt", [r"^\s*1\)\s+.*\n\s*2\)\s+"], "1\n", True),
    ("mcp_auth", [r"\d+\s+MCP\s+servers?\s+needs?\s+auth"], "\x1b", True),  # Esc で dismiss
    ("queued_messages", [r"Press\s+up\s+to\s+edit\s+queued\s+messages"], "\n", False),
    ("session_start_hook_error", [r"SessionStart:\s*startup\s+hook\s+error"], "\n", False),
]


def log(msg: str) -> None:
    print(f"[{datetime.now(JST):%Y-%m-%d %H:%M:%S}] {msg}")


def session_name() -> str:
    if SESSION_FILE.exists():
        name = SESSION_FILE.read_text(encoding="utf-8").strip()
        if name:
            return name
    return SESSION_NAME


def capture_buffer(session: str) -> str:
    """screen のスクロールバックを hardcopy で吸い出す。"""
    with tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False) as tf:
        path = tf.name
    try:
        subprocess.run(
            ["screen", "-S", session, "-X", "hardcopy", "-h", path],
            timeout=10, check=False,
        )
        time.sleep(0.5)
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def detect(buffer_text: str) -> tuple[str, str, bool] | None:
    for name, pats, send, notify in PATTERNS:
        for pat in pats:
            if re.search(pat, buffer_text, re.IGNORECASE | re.MULTILINE):
                return name, send, notify
    return None


def load_state() -> dict:
    try:
        import json
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    import json
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def should_fire(state: dict, pattern: str, now: datetime) -> tuple[bool, str]:
    pat_state = state.setdefault("watchdog", {}).setdefault(pattern, {})
    last = pat_state.get("last_sent_at")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() < DEDUP_SECONDS:
                return False, "dedup（60秒以内に発火済み）"
        except ValueError:
            pass
    # loop guard: 24h で LOOP_MAX_FIRES を超えたら止める
    fires = [
        f for f in pat_state.get("fires", [])
        if _within(f, now, LOOP_WINDOW_HOURS)
    ]
    if len(fires) >= LOOP_MAX_FIRES:
        return False, f"loop 検知（24h で {LOOP_MAX_FIRES} 回超）— 自動復帰を停止"
    return True, ""


def _within(iso: str, now: datetime, hours: int) -> bool:
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() < hours * 3600
    except ValueError:
        return False


def record_fire(state: dict, pattern: str, now: datetime) -> None:
    pat_state = state["watchdog"][pattern]
    pat_state["last_sent_at"] = now.isoformat()
    fires = [f for f in pat_state.get("fires", []) if _within(f, now, LOOP_WINDOW_HOURS)]
    fires.append(now.isoformat())
    pat_state["fires"] = fires


def notify_discord(text: str) -> None:
    ch = os.environ.get("DISCORD_CHANNEL_RANDOM", "").strip()
    token_file = Path.home() / ".claude" / "channels" / "discord" / ".env"
    if not ch or not token_file.exists():
        return
    token = ""
    for line in token_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip()
    if not token:
        return
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{ch}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"content": text},
            timeout=10,
        )
    except requests.RequestException:
        pass


def main() -> int:
    session = session_name()
    # screen が無ければ health_check.sh の領分。何もしない。
    r = subprocess.run(["screen", "-list"], capture_output=True, text=True)
    if session not in r.stdout:
        log(f"screen '{session}' 不在、skip（落ちた検知は health_check.sh の担当）")
        return 0

    buffer_text = capture_buffer(session)
    if not buffer_text:
        log("バッファ取得できず、skip")
        return 0

    hit = detect(buffer_text)
    if not hit:
        return 0

    pattern, send, notify = hit
    now = datetime.now(JST)
    state = load_state()
    fire, reason = should_fire(state, pattern, now)
    if not fire:
        log(f"検出 '{pattern}' だが fire せず: {reason}")
        if "loop" in reason:
            notify_discord(f"⚠ session_watchdog: '{pattern}' が {reason}。手動確認を。")
        return 0

    if DRY_RUN:
        log(f"[DRY_RUN] '{pattern}' 検出 → '{send!r}' を送る（実送信なし）")
        return 0

    subprocess.run(["screen", "-S", session, "-X", "stuff", send], check=False)
    record_fire(state, pattern, now)
    save_state(state)
    log(f"'{pattern}' 検出 → stuff 送信で自動復帰")
    if notify:
        notify_discord(f"🔧 session_watchdog: '{pattern}' を検出、自動復帰させました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
