# Gmail インテグレーション

Gmail 受信箱を毎分ポーリングし、新着メールを webhook 経由で Discord に
転送します。OAuth トークンは Google 共通の `integrations/google/token.json`
（Calendar / Gmail / Sheets / Drive 全スコープ）を `GOOGLE_TOKEN_PATH` 経由で共有します。

## ファイル
- `gmail_monitor.py` — cron スクリプト（毎分）

セットアップはリポジトリ直下の `../../SETUP.md` セクション C3 を参照。
