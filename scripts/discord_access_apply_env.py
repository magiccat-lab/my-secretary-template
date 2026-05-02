#!/usr/bin/env python3
"""discord_access_apply_env.py — `.env` 値から Discord プラグインの allowlist 自動設定

`/discord:access` の対話設定を、 `.env` の DISCORD_CHANNEL_RANDOM /
DISCORD_USER_ID を使って 1 発で書き込む。 mention 不要モードで通すので
ユーザーは ch にメッセージ送るだけで秘書が応答する。

書き込み先 [Claude Code Discord プラグインの allowlist]:
    ~/.claude/channels/discord/access.json

スキーマ:
    {
      "dmPolicy": "allowlist",
      "allowFrom": [<user_id>],        // DM 許可ユーザー
      "groups": {
        "<channel_id>": {
          "requireMention": false,     // false = mention 不要
          "allowFrom": [<user_id>]
        }
      }
    }

使い方 [Claude Code セッション外、 通常のシェルで実行]:
    python3 ~/secretary/scripts/discord_access_apply_env.py

複数 ch 通したい場合は env に追加してこの script に渡す:
    DISCORD_CHANNEL_EXTRA="123456,789012" python3 ... apply_env.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("python-dotenv 未 install: pip install --break-system-packages python-dotenv", file=sys.stderr)
    sys.exit(1)

SECRETARY_ROOT = Path(os.environ.get("SECRETARY_HOME", str(Path.home() / "secretary")))
ENV_PATH = SECRETARY_ROOT / ".env"
ACCESS_PATH = Path.home() / ".claude" / "channels" / "discord" / "access.json"


def main() -> int:
    if not ENV_PATH.exists():
        print(f"❌ .env 無し: {ENV_PATH}", file=sys.stderr)
        return 1

    load_dotenv(ENV_PATH)
    user_id = os.environ.get("DISCORD_USER_ID", "").strip()
    main_ch = os.environ.get("DISCORD_CHANNEL_RANDOM", "").strip()
    extra = os.environ.get("DISCORD_CHANNEL_EXTRA", "").strip()
    extra_chs = [c.strip() for c in extra.split(",") if c.strip()]

    if not user_id:
        print("❌ DISCORD_USER_ID 未設定 [.env]", file=sys.stderr)
        return 1

    channels: list[str] = []
    if main_ch:
        channels.append(main_ch)
    channels.extend(extra_chs)

    if not channels:
        print("⚠ DISCORD_CHANNEL_RANDOM も DISCORD_CHANNEL_EXTRA も空、 DM 許可のみ書き込む")

    # 既存 access.json をロード [無ければ初期化]
    ACCESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if ACCESS_PATH.exists():
        try:
            data = json.loads(ACCESS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    data.setdefault("dmPolicy", "allowlist")
    data.setdefault("allowFrom", [])
    data.setdefault("groups", {})

    # DM allowlist に user_id 追加
    if user_id not in data["allowFrom"]:
        data["allowFrom"].append(user_id)
        print(f"  + DM allowlist に {user_id} 追加")

    # 各 ch の allow + mention 不要モード
    for ch_id in channels:
        existing = data["groups"].get(ch_id, {})
        existing["requireMention"] = False  # mention 不要強制
        allow_from = existing.get("allowFrom", [])
        if user_id not in allow_from:
            allow_from.append(user_id)
        existing["allowFrom"] = allow_from
        data["groups"][ch_id] = existing
        print(f"  + ch {ch_id} を allow [requireMention=false]")

    ACCESS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 書き込み完了: {ACCESS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
