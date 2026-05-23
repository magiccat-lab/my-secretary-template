#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = Path(os.environ.get("DIARY_STATE_PATH", ROOT / "data" / "diary_prompt_state.json"))


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_state() -> dict:
    path = STATE_PATH if STATE_PATH.is_absolute() else ROOT / STATE_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict) -> None:
    path = STATE_PATH if STATE_PATH.is_absolute() else ROOT / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def post_prompt(text: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if webhook:
        import requests

        requests.post(webhook, json={"content": text}, timeout=10)
        return
    channel_id = os.environ.get("DISCORD_CHANNEL_RANDOM", "")
    if not channel_id:
        print("No Discord destination configured", file=sys.stderr)
        return
    sys.path.insert(0, str(ROOT))
    from scripts.lib.discord_post import post

    result = post(channel_id=channel_id, text=text)
    if not result.get("ok"):
        print(result.get("error"), file=sys.stderr)


def main() -> int:
    if not env_bool("FEATURE_DIARY"):
        print("FEATURE_DIARY is not true; skipping")
        return 0
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    state = load_state()
    if state.get("last_prompt_date") == today:
        print("diary prompt already sent today")
        return 0
    prompt = os.environ.get("DIARY_PROMPT_TEXT", "What did you do today?")
    post_prompt(prompt)
    state.update({"last_prompt_date": today, "last_prompt_at": now.isoformat(), "written_dates": state.get("written_dates", [])})
    save_state(state)
    print("diary prompt sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
