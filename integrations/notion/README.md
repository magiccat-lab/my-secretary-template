# integrations/notion/

Notion 連携の設定ファイル置き場。

## ファイル

| ファイル | 中身 | 必須? |
|---|---|---|
| `(なし)` | Notion は OAuth 不要、Internal Integration の token 1 個だけで動く | — |

## 使い方

1. https://www.notion.so/my-integrations で Integration を作成
2. Internal Integration Secret をコピー（`secret_xxxx` 形式）
3. `~/secretary/.env` の `NOTION_TOKEN=` に貼り付け
4. 同期したい Notion DB のページ右上「…」→「Add connections」で作った Integration を許可
5. DB ページの URL から DB ID を取得（`https://www.notion.so/xxx?v=yyy` の `xxx` 部分）
6. `.env` の `NOTION_DB_TASKS=` `NOTION_DB_WISHLIST=` に貼り付け

## 同期スクリプト

| スクリプト | 動作 |
|---|---|
| `scripts/integrations/notion/sync_pending_to_notion.py` | `data/pending_tasks.json` → Notion DB（片方向）|
| `scripts/integrations/notion/wishlist_add.py` | CLI 引数で Wishlist DB に 1 行追加 |

詳細は `docs/notion.md` 参照。
