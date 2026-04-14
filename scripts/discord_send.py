#!/usr/bin/env python3
"""
Discordチャンネルに直接メッセージを送信するヘルパー
Claudeを介さず、ボットトークンで直接Discord APIを叩く
"""
import os
import sys
import requests

def load_token() -> str:
    env_path = os.path.expanduser("~/.claude/channels/discord/.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1]
    raise RuntimeError("DISCORD_BOT_TOKEN not found")

def send(channel_id: str, message: str) -> bool:
    token = load_token()
    r = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        },
        json={"content": message},
        timeout=10
    )
    if r.status_code == 200:
        return True
    else:
        print(f"Discord送信エラー: {r.status_code} {r.text}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: discord_send.py <channel_id> <message>")
        sys.exit(1)
    channel_id = sys.argv[1]
    message = sys.argv[2]
    ok = send(channel_id, message)
    sys.exit(0 if ok else 1)
