#!/usr/bin/env python3
"""Discord チャンネルにメッセージを送信するヘルパー。

マルチ秘書対応:
- secretaries.yaml の sender 設定に基づいて Bot token / Webhook を切り替え
- 未設定（secretaries.yaml なし）なら従来通り Bot トークンで送信
"""

import os
import sys
from pathlib import Path

import requests

_LIB = str(Path(__file__).resolve().parent / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)


def _load_discord_token() -> str:
    env_path = Path.home() / ".claude" / "channels" / "discord" / ".env"
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1]
    raise RuntimeError("DISCORD_BOT_TOKEN not found")


def send_via_bot(channel_id: str, message: str) -> bool:
    token = _load_discord_token()
    r = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        },
        json={"content": message},
        timeout=10,
    )
    if r.status_code == 200:
        return True
    print(f"Discord送信エラー: {r.status_code} {r.text}", file=sys.stderr)
    return False


def send_via_webhook(
    webhook_url: str,
    message: str,
    *,
    username: str = "",
    avatar_url: str = "",
) -> bool:
    payload: dict = {"content": message}
    if username:
        payload["username"] = username
    if avatar_url:
        payload["avatar_url"] = avatar_url

    r = requests.post(webhook_url, json=payload, timeout=10)
    if r.status_code in (200, 204):
        return True
    print(f"Webhook送信エラー: {r.status_code} {r.text}", file=sys.stderr)
    return False


def send(channel_id: str, message: str, *, secretary_id: str = "") -> bool:
    """config resolver 経由で適切な秘書として送信する。"""
    try:
        from config import get_sender_config, resolve_secretary

        sender = get_sender_config(secretary_id=secretary_id or None)
        if sender["kind"] == "webhook" and sender.get("webhook_url"):
            return send_via_webhook(
                sender["webhook_url"],
                message,
                username=sender.get("display_name", ""),
            )
    except Exception:
        pass

    return send_via_bot(channel_id, message)


def send_for_job(channel_id: str, message: str, *, job_name: str) -> bool:
    """ジョブの担当秘書として送信する。"""
    try:
        from config import get_secretary_for_job, get_sender_config

        sec = get_secretary_for_job(job_name)
        sender = get_sender_config(secretary_id=sec["id"])
        if sender["kind"] == "webhook" and sender.get("webhook_url"):
            return send_via_webhook(
                sender["webhook_url"],
                message,
                username=sender.get("display_name", ""),
            )
    except Exception:
        pass

    return send_via_bot(channel_id, message)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: discord_send.py <channel_id> <message> [--secretary <id>] [--job <name>]")
        sys.exit(1)

    channel_id = sys.argv[1]
    message = sys.argv[2]
    secretary_id = ""
    job_name = ""

    for flag, var_name in [("--secretary", "secretary_id"), ("--job", "job_name")]:
        if flag in sys.argv:
            idx = sys.argv.index(flag)
            if idx + 1 < len(sys.argv):
                locals()[var_name] = sys.argv[idx + 1]

    if job_name:
        ok = send_for_job(channel_id, message, job_name=job_name)
    else:
        ok = send(channel_id, message, secretary_id=secretary_id)
    sys.exit(0 if ok else 1)
