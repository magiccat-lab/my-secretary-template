#!/usr/bin/env python3
"""shop_list_add.py — Notion の お店リスト DB に新規ページを追加する CLI

エージェントが「〇〇って店記録して」「〇〇行きたい」等と言われたら
このスクリプトを呼んで Notion DB に追加する。

使い方:
    python3 scripts/integrations/notion/shop_list_add.py \
        --name "ラーメン二郎 三田本店" \
        --genre "その他" \
        --area "三田" \
        --budget "~3000円" \
        --memo "次の出張のついでに行く"

必要な Notion DB プロパティ（テンプレート複製で設定済み）:
- 店名      (title)
- ジャンル  (select)   ※和食 / イタリアン / フレンチ / 中華 / 焼肉 / 寿司 / カフェ / バー / その他
- エリア    (rich_text)
- 予算帯    (select)   ※~3000円 / 3000~5000円 / 5000~10000円 / 10000円~
- 個室      (checkbox)
- URL       (url)
- メモ      (rich_text)
- ステータス(select)   ※行きたい / 行った / お気に入り
- 追加日    (date)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[3])))
load_dotenv(SECRETARY_HOME / ".env")

sys.path.insert(0, str(SECRETARY_HOME / "scripts"))
from lib.notion_env import get_api_key, get_db_id

NOTION_TOKEN = get_api_key()
DB_ID = get_db_id("shop_list")

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def add_shop(
    name: str,
    genre: str = "",
    area: str = "",
    budget: str = "",
    private_room: bool = False,
    url: str = "",
    memo: str = "",
    status: str = "行きたい",
) -> tuple[bool, str]:
    """お店リスト DB に 1 ページ追加。成功フラグと message を返す"""
    if not NOTION_TOKEN or not DB_ID:
        return False, "NOTION_API_KEY または NOTION_DB_SHOP_LIST が未設定"

    props: dict = {
        "店名": {"title": [{"text": {"content": name[:200]}}]},
        "追加日": {"date": {"start": dt.date.today().isoformat()}},
        "ステータス": {"select": {"name": status}},
        "個室": {"checkbox": private_room},
    }
    if genre:
        props["ジャンル"] = {"select": {"name": genre[:40]}}
    if area:
        props["エリア"] = {"rich_text": [{"text": {"content": area}}]}
    if budget:
        props["予算帯"] = {"select": {"name": budget}}
    if url:
        props["URL"] = {"url": url}
    if memo:
        props["メモ"] = {"rich_text": [{"text": {"content": memo[:2000]}}]}

    body = {"parent": {"database_id": DB_ID}, "properties": props}
    try:
        r = requests.post(f"{NOTION_API}/pages", headers=_headers(), json=body, timeout=30)
        if r.status_code in (200, 201):
            return True, f"追加成功: {name}"
        return False, f"Notion API エラー {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, f"通信失敗: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="店名（必須）")
    parser.add_argument("--genre", default="", help="ジャンル（和食 / イタリアン / フレンチ / 中華 / 焼肉 / 寿司 / カフェ / バー / その他）")
    parser.add_argument("--area", default="", help="エリア（三田 / 渋谷 等）")
    parser.add_argument("--budget", default="", help="予算帯（~3000円 / 3000~5000円 / 5000~10000円 / 10000円~）")
    parser.add_argument("--private-room", action="store_true", help="個室あり")
    parser.add_argument("--url", default="", help="URL")
    parser.add_argument("--memo", default="", help="メモ")
    parser.add_argument("--status", default="行きたい", help="ステータス（行きたい / 行った / お気に入り）")
    args = parser.parse_args()

    ok, msg = add_shop(
        name=args.name,
        genre=args.genre,
        area=args.area,
        budget=args.budget,
        private_room=args.private_room,
        url=args.url,
        memo=args.memo,
        status=args.status,
    )
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
