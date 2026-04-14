# Google Calendar インテグレーション

カレンダーを読み、予定 30 分前に Discord へ投稿します。
`gcal_today.py` は今日の予定取得 CLI。

## ファイル
- `gcal_remind.py` — cron スクリプト（毎分）
- `gcal_today.py` — CLI
- `reauth.py` — OAuth フロー（Calendar / Gmail / Sheets 全スコープ）
- `token.json` / `credentials.json` — gitignore 対象

セットアップ・OAuth フロー・再認証は `docs/SETUP.md` セクション 10 を参照。
