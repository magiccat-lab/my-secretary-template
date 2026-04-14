# tasks.md — タスクストレージ（pending_tasks.json + Sheets 同期）

秘書のタスク管理ストレージと、オプションの Google Sheets 双方向同期。

---

## 1. ローカル JSON の構造

- **ファイル**: `~/secretary/data/pending_tasks.json`
- **形式**:
  ```json
  {
    "primary": [
      {"title": "...", "done": false, "created_at": "YYYY-MM-DD"}
    ]
  }
  ```
- セクション分けは任意。デフォルトは `primary` のみ。
- タスク追加・表示のルール（未完了のみ表示、番号で指定、等）は
  `AGENT/AGENTS.md` の「タスク管理」参照。

---

## 2. 編集の作法（排他ロック）

`task_store.py` は `fcntl.flock` で `pending_tasks.json` をロックする。
cron中に手で編集するとロスト発火することがあるので、手動編集は非推奨。
代わりにコンテキストマネージャを使う:

```python
from scripts.lib.task_store import update_tasks
with update_tasks() as data:
    data['primary'].append({
        'title': 'X',
        'done': False,
        'created_at': '2026-04-14'
    })
```

または会話でエージェント（自分）に追加させる。

---

## 3. Google Sheets タスクミラー（オプション）

`data/pending_tasks.json` をGoogle Sheetと双方向同期。モバイル編集や
パートナーとの共有に便利。

### 3.1 トリガーフレーズ
「タスクをスマホからも見たい」「タスクを共有したい」「Sheetsと同期して」

### 3.2 前提
Google OAuthが既に通っていること（`integrations/gcal/token.json` 作成済み）。
まだなら `docs/google.md` で先にSheets APIを有効化して認証を通す。

### 3.3 セットアップ
1. ユーザーにGoogle Driveで空のシートを作ってもらう
2. URLからIDを取る: `https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit`
3. `.env` に `TASK_SHEET_ID=...` をEditで追加
4. （Sheetsスコープが取れていなければ）`python3 integrations/gcal/reauth.py` を再実行
5. 初回プッシュ:
   ```bash
   cd ~/secretary && python3 scripts/task_sheet_sync.py push
   ```
6. cron登録:
   ```cron
   */15 * * * * cd /home/YOUR_USER/secretary && /usr/bin/python3 scripts/task_sheet_sync.py push >> /tmp/task_sheet.log 2>&1
   ```

### 3.4 競合時の挙動
**ローカルJSONが正**。`push` は破壊的でシートをクリアして書き直す。
シート側で編集したいときは:

1. シートで編集
2. `python3 scripts/task_sheet_sync.py pull`（シート → JSON取り込み）
3. 次のcron `push` で確定

### 3.5 シートのレイアウト

| section | title | done | created_at | completed_at | remind_at |
|---|---|---|---|---|---|

- `section`: 通常 `primary`
- `done`: `TRUE` / `FALSE`
- 日付列: `YYYY-MM-DD`

手動で追加した列はpushで破棄される。残したいなら2タブ目に置く（最初の
シートしか触らない）。

### 3.6 機能オフ
`TASK_SHEET_ID` を空にする。スクリプトは自動で no-op になる。
