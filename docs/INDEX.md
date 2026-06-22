# docs/INDEX.md — ドキュメント索引

起動時はこのファイルだけ読まれます。具体的なセットアップ・運用タスクが
来たら、下の表から該当ファイルを Read して参照してください。各ファイルは
スタンドアロンで完結しつつ、必要なときだけ相互リンクしています。

> 人間向けの**初回セットアップ手順**はリポジトリ直下の `SETUP.md` にあります。
> 「clone 直後〜 Discord で会話できるまで」はそちらが正。本 `docs/` 以下は
> **動き始めた後**の運用・再構築用のリファレンス。

## ルーティング表

| ユーザーが言いそうなこと | 読むファイル | 1行概要 |
|---|---|---|
| 「再構築したい」「別 VPS に移したい」「シークレット再発行」 | `docs/bootstrap.md` | 起動後の作り直し・移行・ローテーション |
| 「キャラ作って」「秘書の口調決めたい」「IDENTITY埋め直して」「自分のこと教える」 | `docs/bootstrap.md` §1 | `AGENT/IDENTITY.md` / `USER.md` の再構築と口調育成 |
| 「Discord bot作りたい」「チャンネルID教えた」「返信こない」「bot token取った」 | `docs/discord.md` | bot作成・token保管・チャンネルID・Discord返信の原則 |
| 「Googleカレンダー繋ぎたい」「Gmail監視」「Sheetsで見たい」「OAuth通らない」「invalid_grant」 | `docs/google.md` | Calendar/Gmail/Sheets共通の OAuth・再認証・ヘッドレスVPS手順 |
| 「cron追加して」「毎朝〇時にX」「定期実行」「時刻ずれてる」 | `docs/cron.md` | crontab構文・JST・フルパス/HOME等の落とし穴・推奨ジョブ一覧 |
| 「webhookで〇〇させたい」「systemdで常駐」「エンドポイント増やして」 | `docs/webhook.md` | webhook_server.pyのエンドポイント仕様・認証・systemdユニット |
| 「bot落ちた」「死活監視」「再起動」「ログ見たい」「何か壊れた」 | `docs/ops.md` | health_check/daily_handoff/週次再起動/トラブルシューティング |
| 「タスクどう保存してる」「スマホからタスク見たい」「スプシと同期」 | `docs/tasks.md` | pending_tasks.json の構造と Google Sheets 双方向同期 |
| 「Notion と繋ぎたい」「タスク Notion で見たい」「Wishlist 追加して」「Notion 同期失敗」 | `docs/notion.md` | Notion DB との同期・Wishlist 追加・トラブルシュート |

| 「秘書をもう1体追加したい」「チャンネルごとに分けたい」「2体目のセットアップ」 | `docs/multi-secretary.md` | 複数秘書モードの設定・ルーティング・ジョブ割り当て |

## Phase 1 拡張 docs [初回セットアップ後の reference]

`SETUP.md` の A-L 章で動かしたあと、 各機能を深掘りするときに参照する。

| トピック | 読むファイル | 1行概要 |
|---|---|---|
| 「VPS まだ買ってない」「Xserver 契約から」 | `docs/setup/xserver-vps.md` | Xserver VPS 契約 + 初期 SSH 設定 |
| 「ドメイン取りたい」「DNS どう書く」 | `docs/setup/domain.md` | ドメイン取得 + A レコード |
| 「tunnel 使いたい」「外から呼びたい」 | `docs/setup/cloudflared.md` | Cloudflared install + service 化 |
| 「Notion 連動したい」「integration 権限分からん」 | `docs/setup/notion.md` | Integration 作成 + Delete 権限剥奪 + DB 共有 |
| 「Claude Code 動かない」「login できない」 | `docs/setup/claude-code.md` | install / login / Discord plugin |
| 「bot 反応しない」「intents って何」 | `docs/setup/discord-bot.md` | Developer Portal + token + intents |
| 「VPS で常駐させたい」「死んでも復活させて」 | `docs/setup/systemd.md` | systemd unit + watchdog |
| 「公開前に個人情報チェック」 | `docs/setup/sanitize.md` | sanitize_lint + pre-commit |
| 「動かない」「詰まった」「エラー出た」 | `docs/setup/troubleshooting.md` | Q&A 30+ [bun / cloudflared / Notion 403 / cron / systemd 等] |
## Phase 2 拡張 docs [Phase 2 機能の reference]

`SETUP.md` の P 章で各 `FEATURE_*=true` を立てたあと、機能の詳細を確認するときに参照する。

| トピック | 読むファイル | 1行概要 |
|---|---|---|
| 「引き継ぎ自動生成したい」「handoff がうまくいかない」「毎晩何時に走るの」 | `docs/setup/handoff.md` | nightly_handoff の設定・出力フォーマット・時刻変更 |
| 「過去の会話を検索したい」「チャット履歴に聞きたい」「chat search の仕組み」 | `docs/setup/chat_search.md` | Discord corpus SQLite 構築・検索コマンド |
| 「Gmail 監視したい」「メール通知が来ない」「フィルタルール書きたい」 | `docs/setup/gmail.md` | Gmail monitor のルール定義・FEATURE_GMAIL の設定 |
| 「日記を付けたい」「毎晩 diary プロンプトを送って」「日記が溜まってる場所は」 | `docs/setup/diary.md` | diary prompt の時刻・保存先・フォーマット |
| 「persona を育てたい」「TIL を昇格させて」「trainer の動作を確認したい」 | `docs/setup/trainer.md` | memory_extractor / persona_evolution / til_promoter の設定 |


## 既存ジョブ・これから追加するジョブ

cronで動いている定期ジョブ一覧・追加の流れは `AGENT/JOBS.md` を参照。
