# Google 共通 OAuth

Calendar / Gmail / Sheets / Drive で使う **1 個の OAuth トークン**をここで管理します。
各機能（`integrations/gcal/`・`integrations/gmail/`・Sheets 同期）はこのトークンを
`GOOGLE_TOKEN_PATH` 経由で共有します。サービスごとに別トークンは作りません。

## ファイル
- `reauth.py` — OAuth フロー（Calendar / Gmail / Sheets / Drive 全スコープを一括で取得）
- `credentials.json` — Google Cloud で発行した OAuth クライアント（gitignore 対象、手動で置く）
- `token.json` — `reauth.py` 実行後に生成される認可済みトークン（gitignore 対象）

## 使い方
1. Google Cloud で OAuth クライアントを発行し `credentials.json` をここに置く
2. `python3 integrations/google/reauth.py` を 1 回実行して `token.json` を生成
3. `.env` の `GOOGLE_TOKEN_PATH=integrations/google/token.json`（デフォルト）を確認

詳細はリポジトリ直下の `../../SETUP.md` セクション C3、および `../../docs/google.md` を参照。
