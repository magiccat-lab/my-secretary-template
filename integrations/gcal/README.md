# Google Calendar インテグレーション

カレンダーを読み、予定 30 分前に Discord へ投稿します。
`gcal_today.py` は今日の予定取得 CLI。

## ファイル
- `gcal_remind.py` — cron スクリプト（毎分）
- `gcal_today.py` — CLI

OAuth トークンは Google 共通の `integrations/google/token.json`（Calendar / Gmail /
Sheets / Drive / Docs / Forms 全スコープ）を `GOOGLE_TOKEN_PATH` 経由で共有します。認証フロー
（`reauth.py`）と `credentials.json` / `token.json` は `integrations/google/` 側にあります。

セットアップ・OAuth フロー・再認証はリポジトリ直下の `../../SETUP.md` セクション C3 を参照。
