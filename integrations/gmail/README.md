# Gmail インテグレーション

Gmail 受信箱を毎分ポーリングし、新着メールを webhook 経由で Discord に
転送します。OAuth トークンは gcal と共有（`integrations/gcal/token.json`）。

## ファイル
- `gmail_monitor.py` — cron スクリプト（毎分）

セットアップは `docs/SETUP.md` セクション 10 を参照。
