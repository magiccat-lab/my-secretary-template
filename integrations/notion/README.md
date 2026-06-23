# integrations/notion/

Notion 連携の設定ファイル置き場。

## ファイル

| ファイル | 中身 | 必須? |
|---|---|---|
| `(なし)` | Notion は OAuth 不要、Internal Integration の token 1 個だけで動く | — |

## 使い方

1. https://www.notion.so/my-integrations で Integration を作成
2. Internal Integration Secret をコピー（`secret_xxxx` or `ntn_xxxx` 形式）
3. `~/secretary/.env` の `NOTION_API_KEY=` に貼り付け
4. 同期したい Notion DB のページ右上「…」→「Add connections」で作った Integration を許可
5. `環境設定` DB の ID を `SECRETARY_ENV_DB_ID=` に設定（他の DB ID は環境設定 DB から自動取得）
6. 詳細は `SETUP.md` G2 を参照

## 同期スクリプト

| スクリプト | 動作 |
|---|---|
| `scripts/integrations/notion/sync_pending_to_notion.py` | `data/pending_tasks.json` → Notion DB（片方向）|
| `scripts/integrations/notion/wishlist_add.py` | CLI 引数で Wishlist DB に 1 行追加 |

詳細は `docs/notion.md` 参照。
