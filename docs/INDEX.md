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

## 既存ジョブ・これから追加するジョブ

cronで動いている定期ジョブ一覧・追加の流れは `AGENT/JOBS.md` を参照。
