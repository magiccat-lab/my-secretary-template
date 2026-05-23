# JOBS.md — 定期実行ジョブ

秘書に「いつ何をさせるか」を記述するファイル。1ジョブ1行にまとめて、
詳細はスクリプトやスキルファイルに寄せるのが推奨。

## タイムゾーンのルール

ここに書く時刻はすべて JST（Asia/Tokyo）。`cron` や `at` も JST で指定。
詳細は `docs/cron.md` 参照。

---

## コアジョブ（テンプレートに同梱）

### タスクリマインダー
- スクリプト: `scripts/task_remind.py`
- Cron: `30 6,22 * * *`（1日2回 — 好みで調整）
- `data/pending_tasks.json` をスキャンして未完了分を `DISCORD_CHANNEL_RANDOM` に投稿。

### 死活監視
- スクリプト: `scripts/health_check.sh`
- Cron: `*/5 * * * *`
- webhook / screen / claude のどれかが落ちていたら再起動。

### デイリー handoff [Phase 1]
- スクリプト: `scripts/daily_handoff.py`
- Cron: `0 3 * * *`（または停止前に手動実行）
- `data/handoff.md` を書いて、次のセッションが引き継げるようにする。
- > **Phase 2 以降は** `scripts/system/nightly_handoff.py` + `data/claude/handoff.md` を使います（`FEATURE_HANDOFF=true` で有効化）。

### 週次再起動（オプション）
- スクリプト: `scripts/weekly_restart.sh`
- Cron: `10 3 * * 0`（日曜 3:10）
- screen セッションをコールドスタートし直す。24/7 稼働を何日も続けるなら有効化推奨。

---

## オプションのインテグレーション

`.env` で有効化し、cron の行をコメントアウトから戻す。

### カレンダーリマインド（Google Calendar）
- スクリプト: `integrations/gcal/gcal_remind.py`
- Cron: `* * * * *`（毎分）
- Env: `GCAL_REMIND_ENABLED=true`, `GCAL_CALENDAR_ID=...`
- 予定の30分前に random チャンネルへ通知。

### Gmail モニター
- スクリプト: `integrations/gmail/gmail_monitor.py`
- Cron: `* * * * *`
- Env: `GMAIL_ENABLED=true`
- 自動返信のフィルタ、Google Docs のサイレントアーカイブ付き。

### Notion 同期（Tasks）
- スクリプト: `scripts/integrations/notion/sync_pending_to_notion.py`
- Cron: `*/5 * * * *`
- Env: `NOTION_TOKEN`, `NOTION_DB_TASKS`
- `data/pending_tasks.json` を Notion DB に片方向同期（5 分間隔）。
- セットアップは `SETUP.md` G2 / 詳細 `docs/notion.md` 参照。

### Wishlist 追加（オンデマンド）
- スクリプト: `scripts/integrations/notion/wishlist_add.py`
- Cron: なし（会話駆動。エージェントが「〇〇記録して」を受けたら CLI 実行）
- Env: `NOTION_TOKEN`, `NOTION_DB_WISHLIST`

---

## Phase 1 拡張ジョブ [docs/setup/* + scripts/system/ 参照]

### watchdog [死活監視 + 自動復帰]
- スクリプト: `scripts/system/watchdog.py`
- Cron: `*/5 * * * *` または systemd service [`scripts/system/my-secretary-watchdog.service.tpl`]
- 動作: webhook_server / discord_bot_daemon の port / pgrep を check、 落ちてたら restart + Discord alert
- 詳細: `docs/setup/systemd.md`

### Discord conversation log → Notion + SQLite
- スクリプト: `scripts/integrations/discord/corpus_writer.py` [realtime] + `sync_log_to_notion.py` [日次]
- Cron: `0 3 * * *` [日次補填]
- Env: `NOTION_TOKEN`, `NOTION_DB_CONVERSATION_LOG`
- 動作: 全 message を sanitize_lint で個人情報マスク後、 Conversation Log DB に 1 row push + local SQLite に保管 [RAG fallback]

### Channel 追加 [`+ch <id> <name>`]
- スクリプト: `scripts/integrations/discord/channel_admin.py`
- Cron: なし [Discord メッセ駆動]
- 動作: webhook で `+ch` コマンドを受けて Channel DB に row 追加 + `data/channels.json` 自動更新

### 重複なし scrape recommend
- スクリプト: `scripts/recommendations/sample_scrape_recommend.py`
- Cron: `0 8 * * *` [毎朝 8:00]
- 動作: YouTube / Web から 3 件抽出、 重複防止 [local JSON or Notion Recommendations DB]、 random ch に push

### Notion DB 自動作成 [初回 1 回のみ]
- スクリプト: `scripts/integrations/notion/create_databases.py`
- Cron: なし [手動 1 回]
- 動作: NOTION_PARENT_PAGE_ID 親 page 配下に 8 DB 自動作成、 ID を `.env.generated.notion` に出力

---

## サンプルジョブ（実装例・コピペして使う）

新しいジョブを追加するときのパターン例。下のスクリプトは**未実装**なので、
必要になったら以下の流れで組み立てる:

1. `scripts/` に実スクリプトを Write
2. 下の crontab 行を `crontab -e` に追加（または `docs/cron.md` の heredoc パターンで一括登録）
3. 手動で1回叩いて成功確認
4. このファイルの「コアジョブ」節に1行足す

### [SAMPLE] 朝のダイジェスト
- script: `scripts/morning_digest.py`（未実装・例として）
- crontab: `0 8 * * 1-5 /usr/bin/python3 /home/YOUR_USER/secretary/scripts/morning_digest.py >> /tmp/morning_digest.log 2>&1`
- 動作: 平日 08:00 に「天気 + 今日のタスク一覧」をまとめて `DISCORD_CHANNEL_RANDOM` に投稿
- 追加時に秘書がやること:
  (1) `scripts/morning_digest.py` を Write（weather API + `scripts/lib/task_store.py` から未完了タスク取得）
  (2) `crontab -l` に1行追加
  (3) 動作確認のため手動で1回実行

### [SAMPLE] 週次振り返りテンプレ
- script: `scripts/weekly_review.py`（未実装・例として）
- crontab: `0 10 * * MON /usr/bin/python3 /home/YOUR_USER/secretary/scripts/weekly_review.py >> /tmp/weekly_review.log 2>&1`
- 動作: 毎週月曜 10:00 に「先週やったこと/今週やること」テンプレを自分用チャンネルに投稿（空欄を返信で埋める運用）
- 追加時に秘書がやること:
  (1) `scripts/weekly_review.py` を Write（定型文を `discord_post.post` で送るだけ）
  (2) crontab 追加 (3) 初回手動実行でフォーマット確認

### [SAMPLE] 食事記録の自動追記
- script: `scripts/lib/meal_log.py`（未実装・例として）
- トリガー: cron ではなく**会話中のキーワード** — メッセージに「食事記録」が含まれたら `data/meals.md` に `YYYY-MM-DD HH:MM <本文>` を追記
- 実装: エージェントが会話ルールとして処理するパターン（cron不要）。`AGENT/AGENTS.md` に1行足すか、本スクリプトを webhook 経由で `/log_meal` エンドポイントから叩いてもよい
- 追加時に秘書がやること:
  (1) `scripts/lib/meal_log.py` を Write（`data/meals.md` に追記する関数）
  (2) 会話ルールを `AGENT/AGENTS.md` に追記、または `docs/webhook.md` を参照して `/log_meal` エンドポイントを追加

### [SAMPLE] タスク件数メトリクス記録
- script: `scripts/metrics_pending_tasks.py`（未実装・例として）
- crontab: `0 * * * * /usr/bin/python3 /home/YOUR_USER/secretary/scripts/metrics_pending_tasks.py >> /tmp/metrics_pending.log 2>&1`
- 動作: 毎時00分に `pending_tasks.json` の未完了件数を `scripts/lib/metrics_db.py` に記録（後で推移を可視化できる）
- 追加時に秘書がやること:
  (1) `scripts/metrics_pending_tasks.py` を Write（`track_metrics` デコレータ付き、`data/pending_tasks.json` の `done=False` を数える）
  (2) crontab 追加 (3) `python3 scripts/lib/metrics_db.py stats --hours 24` で翌日に蓄積を確認

---

## 自分のジョブを追加

以下のテーブル形式で追加してください:

| トリガー | スクリプト | 動作 |
|---------|--------|--------|
| `cron: 0 9 * * MON` | `scripts/weekly_news.py` | 週次ニュースを #random に投稿 |
| キーワード "log mood" | 会話 | `data/mood.md` に追記 |

追加方法:
1. **チャットで頼む**: 「X を Y の頻度でやるジョブを追加して」と言えば、
   秘書がスクリプトと crontab エントリを起こしてくれる。
2. **先にここに書く**: 秘書はこのファイルをジョブ仕様として読む。
3. **自分で書く**: `scripts/` にスクリプトを作って、`crontab -e` に
   エントリを追加し、上のテーブルに1行足す。

---

## Phase 2 拡張ジョブ [FEATURE_* フラグで有効化]

Phase 2 の各機能を有効化すると、以下のジョブが cron / オンデマンドで追加されます。
`python3 scripts/system/install_cron.py add` で自動登録されます。詳細は `docs/setup/` 参照。

### nightly_handoff [毎晩の引き継ぎ生成]
- スクリプト: `scripts/system/nightly_handoff.py`
- Cron: `30 3 * * *`（デフォルト。`HANDOFF_TIME` で変更可）
- Env: `FEATURE_HANDOFF=true`
- 動作: Discord 履歴 + pending_tasks / agent_backlog を集約して `data/claude/handoff.md` を上書き。次セッションが即座に文脈を把握できるようにする

### gmail_monitor [Gmail モニタリング]
- スクリプト: `integrations/gmail/gmail_monitor.py`
- Cron: `* * * * *`（毎分）
- Env: `FEATURE_GMAIL=true`（または後方互換 `GMAIL_ENABLED=true`）
- 動作: 未読メールをポーリングして `integrations/gmail/filter_rules.yaml` のルールに従い Discord 通知 + 任意自動返信

### daily_prompt + diary_writer [日記プロンプト]
- スクリプト: `scripts/system/diary_prompt.py`
- Cron: `30 21 * * *`（デフォルト。`DIARY_PROMPT_TIME` で変更可）
- Env: `FEATURE_DIARY=true`
- 動作: 毎晩 Discord にプロンプトを投下、返答を `data/notes/YYYY-MM-DD-diary.md` に保存

### memory_extractor [会話から記憶抽出]
- スクリプト: `scripts/system/memory_extractor.py`
- Cron: `0 2 * * *`（深夜 2:00）
- Env: `FEATURE_TRAINER=true`
- 動作: 直近の Discord ログから重要な事実・好み・パターンを抽出し `data/notes/knowledge.md` に追記

### persona_evolution [persona 自動更新提案]
- スクリプト: `scripts/system/persona_evolution.py`
- Cron: `0 4 * * 0`（日曜 4:00）
- Env: `FEATURE_TRAINER=true`
- 動作: `TRAINER_LOOKBACK_DAYS` 日分の会話を分析して `data/notes/persona_suggestions.md` に提案を書き出す。レビュー後に `AGENT/IDENTITY.md` へ反映するかは手動判断

### til_promoter [TIL 昇格]
- スクリプト: `scripts/system/til_promoter.py`
- Cron: `0 1 * * *`（深夜 1:00）
- Env: `FEATURE_TRAINER=true`
- 動作: 会話中に出現した学習内容を `data/notes/til_*.md` として保存。`TRAINER_MIN_CONFIDENCE` 以上の confidence で自動昇格

### chat_search [オンデマンド]
- スクリプト: `scripts/integrations/discord/corpus_writer.py`（収集） + 検索は会話駆動
- Cron: `0 3 * * *`（corpus 補填。収集は realtime）
- Env: `FEATURE_CHATSEARCH=true`
- 動作: 全 Discord message を SQLite（`DISCORD_CORPUS_DB`）に蓄積。「〇〇について前に話した内容を探して」で自然言語検索を実行する
