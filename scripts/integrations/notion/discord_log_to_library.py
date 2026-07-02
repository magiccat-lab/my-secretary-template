#!/usr/bin/env python3
"""discord_log_to_library.py — Discord ログを日次で Notion Log Library DB に送る。

直近 24 時間の Discord メッセージを集めて、Notion の Log Library DB に 1 ページとして投下する。
まとめ資料・ログは md でなく Notion Log Library に集約する方針（AGENT/AGENTS.md 参照）。

チャンネル取得モード:
    1. DISCORD_GUILD_ID を設定 → サーバー内の全テキストチャンネルを自動取得（推奨）
       DISCORD_LOG_EXCLUDE_CHANNELS でカンマ区切りのチャンネルIDを除外可能
    2. DISCORD_GUILD_ID が未設定 → 従来どおり RANDOM/MAIL/EXTRA の明示指定のみ

環境変数:
    NOTION_API_KEY                Notion Internal Integration Secret
    NOTION_TOKEN                  旧変数名（NOTION_API_KEY が無い場合のみ fallback）
    NOTION_DB_LOG_LIBRARY         Log Library DB の ID
    DISCORD_GUILD_ID              サーバーID（設定すると全チャンネル自動取得）
    DISCORD_LOG_EXCLUDE_CHANNELS  除外チャンネルID（カンマ区切り、任意）
    DISCORD_CHANNEL_RANDOM        主チャンネル（GUILD_ID 未設定時は必須）
    DISCORD_CHANNEL_MAIL          メールチャンネル（任意）
    DISCORD_CHANNEL_EXTRA         追加チャンネル（カンマ区切り、任意）
    DISCORD_BOT_TOKEN             ~/.claude/channels/discord/.env から読む

cron の例（毎日 23:50 にその日の分を送る）:
    50 23 * * * /usr/bin/python3 ~/secretary/scripts/integrations/notion/discord_log_to_library.py >> /tmp/discord_log_to_library.log 2>&1
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[3])))
load_dotenv(SECRETARY_HOME / ".env")
if str(SECRETARY_HOME) not in sys.path:
    sys.path.insert(0, str(SECRETARY_HOME))

from scripts.lib.notion_config import get_notion_setting, notion_token  # noqa: E402

JST = timezone(timedelta(hours=9))
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DISCORD_API = "https://discord.com/api/v10"
TIMEOUT_SEC = 30
LOOKBACK_HOURS = 24
MAX_BLOCK_CHARS = 1900  # Notion rich_text の 2000 文字上限に余裕

NOTION_TOKEN = notion_token()
DB_ID = get_notion_setting("NOTION_DB_LOG_LIBRARY", "")


def _discord_token() -> str:
    p = Path.home() / ".claude" / "channels" / "discord" / ".env"
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


def _guild_channels(token: str, guild_id: str) -> list[tuple[str, str]]:
    """ギルド内の全テキストチャンネルを (name, channel_id) で返す。"""
    headers = {"Authorization": f"Bot {token}"}
    r = requests.get(
        f"{DISCORD_API}/guilds/{guild_id}/channels",
        headers=headers, timeout=TIMEOUT_SEC,
    )
    if r.status_code != 200:
        print(f"⚠ ギルドチャンネル取得失敗: HTTP {r.status_code}", file=sys.stderr)
        return []
    exclude = {
        x.strip()
        for x in os.environ.get("DISCORD_LOG_EXCLUDE_CHANNELS", "").split(",")
        if x.strip()
    }
    # type 0=text, 5=announcement — voice/category/forum は除外
    text_types = {0, 5}
    out: list[tuple[str, str]] = []
    for ch in sorted(r.json(), key=lambda c: c.get("position", 0)):
        if ch.get("type") not in text_types:
            continue
        ch_id = ch["id"]
        if ch_id in exclude:
            continue
        out.append((ch.get("name", ch_id), ch_id))
    return out


def _channels(token: str = "") -> list[tuple[str, str]]:
    """(label, channel_id) のリスト。空 ID は除外。"""
    guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if guild_id and token:
        chs = _guild_channels(token, guild_id)
        if chs:
            return chs
        print("⚠ ギルドチャンネル取得失敗、明示指定にフォールバック", file=sys.stderr)
    out: list[tuple[str, str]] = []
    main = os.environ.get("DISCORD_CHANNEL_RANDOM", "").strip()
    mail = os.environ.get("DISCORD_CHANNEL_MAIL", "").strip()
    if main:
        out.append(("random", main))
    if mail and mail != main:
        out.append(("mail", mail))
    extra = os.environ.get("DISCORD_CHANNEL_EXTRA", "").strip()
    for c in (x.strip() for x in extra.split(",")):
        if c and c not in {cid for _, cid in out}:
            out.append((c, c))
    return out


def fetch_messages(token: str, channel_id: str, cutoff: datetime) -> list[dict]:
    """直近 cutoff 以降のメッセージを古い順で全件返す。"""
    headers = {"Authorization": f"Bot {token}"}
    all_msgs = []
    before = None
    while True:
        url = f"{DISCORD_API}/channels/{channel_id}/messages?limit=100"
        if before:
            url += f"&before={before}"
        r = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
        if r.status_code != 200:
            print(f"⚠ ch {channel_id} 取得失敗: HTTP {r.status_code}", file=sys.stderr)
            break
        batch = r.json()
        if not batch:
            break
        reached_cutoff = False
        for m in batch:
            ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
            if ts >= cutoff:
                all_msgs.append(m)
            else:
                reached_cutoff = True
        if reached_cutoff or len(batch) < 100:
            break
        before = batch[-1]["id"]
        time.sleep(0.5)
    all_msgs.reverse()
    return all_msgs


def _chunk(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _blocks_from_text(text: str) -> list[dict]:
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        }
        for chunk in _chunk(text, MAX_BLOCK_CHARS)
    ]


def create_log_page(title: str, date_str: str, source: str, summary: str,
                    children: list[dict]) -> bool:
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": title[:200]}}]},
            "Date": {"date": {"start": date_str}},
            "Category": {"select": {"name": "discord-log"}},
            "Source": {"rich_text": [{"text": {"content": source[:200]}}]},
            "Summary": {"rich_text": [{"text": {"content": summary[:1900]}}]},
        },
        "children": children[:90],
    }
    r = requests.post(
        f"{NOTION_API}/pages", headers=headers, json=payload, timeout=TIMEOUT_SEC
    )
    if r.status_code not in (200, 201):
        print(f"❌ Notion ページ作成失敗: HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    # Notion 未設定なら何もせず正常終了（Notion 連携をしていない構成では cron が
    # 毎日エラーにならないよう skip 扱い）。
    if not NOTION_TOKEN or not DB_ID:
        print("Notion 未設定（NOTION_API_KEY / NOTION_DB_LOG_LIBRARY）、skip")
        return 0
    token = _discord_token()
    if not token:
        print("DISCORD_BOT_TOKEN が無い、skip")
        return 0

    now = datetime.now(JST)
    cutoff = (now - timedelta(hours=LOOKBACK_HOURS)).astimezone(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    lines: list[str] = []
    total = 0
    labels: list[str] = []
    channels = _channels(token)
    print(f"対象チャンネル: {len(channels)} 件")
    for label, ch_id in channels:
        msgs = fetch_messages(token, ch_id, cutoff)
        if not msgs:
            continue
        labels.append(label)
        lines.append(f"=== #{label} ({len(msgs)} 件) ===")
        for m in msgs:
            ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")).astimezone(JST)
            author = m.get("author", {}).get("username", "?")
            content = m.get("content") or ""
            extras: list[str] = []
            for att in m.get("attachments", []):
                extras.append(f"[添付: {att.get('filename', '?')}]")
            for emb in m.get("embeds", []):
                emb_title = emb.get("title") or emb.get("description", "")[:60]
                if emb_title:
                    extras.append(f"[埋込: {emb_title}]")
            if not content and not extras:
                content = "[空メッセージ]"
            line = f"[{ts:%H:%M}] {author}: {content}"
            if extras:
                line += " " + " ".join(extras)
            lines.append(line)
        lines.append("")
        total += len(msgs)
        time.sleep(0.4)  # Discord レート制限に余裕

    if total == 0:
        print("メッセージなし（24h）、ページ作成スキップ")
        return 0

    body = "\n".join(lines)
    summary = f"{date_str} の Discord ログ {total} 件 / ch: {', '.join(labels)}"
    blocks = _blocks_from_text(body)
    max_blocks = 90
    page_num = 0
    all_ok = True
    while blocks:
        page_num += 1
        batch, blocks = blocks[:max_blocks], blocks[max_blocks:]
        suffix = f" (part {page_num})" if page_num > 1 or blocks else ""
        ok = create_log_page(
            title=f"Discord log {date_str}{suffix}",
            date_str=date_str,
            source=", ".join(labels),
            summary=summary if page_num == 1 else f"{summary} (続き part {page_num})",
            children=batch,
        )
        if not ok:
            all_ok = False
            break
    print(f"✅ Log Library に投下: {total} 件 ({page_num} ページ)" if all_ok else "❌ 投下失敗")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
