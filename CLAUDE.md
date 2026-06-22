# CLAUDE.md — 秘書の起動ファイル

このファイルは Claude Code 起動時に自動で読み込まれます。エージェントの
アイデンティティ、ユーザー情報、行動ルール、ジョブ一覧、セットアップ・
運用知識ベースを取り込みます。

## 読み込み順序

@AGENT/IDENTITY.md
@AGENT/USER.md
@AGENT/AGENTS.md
@AGENT/JOBS.md
@docs/INDEX.md

### 複数秘書モード（オプション）
`secretaries.yaml` が存在する場合、秘書ごとに Discord の送信者・
タスクストア・handoff・ジョブ担当を分離できます。single runtime
（1つの Claude Code セッション）では送信者/保存先/ジョブの分離まで。
人格（IDENTITY）を完全に分けるには multi runtime が必要です。
詳細は `docs/multi-secretary.md` を参照。

2体目以降の秘書を追加するには:
1. `cp secretaries.yaml.template secretaries.yaml`
2. `mkdir -p AGENT/secretaries/<id>/` で秘書ディレクトリを作成
3. `cp AGENT/IDENTITY.md AGENT/secretaries/<id>/IDENTITY.md` でコピーして編集
4. `secretaries.yaml` に2体目のエントリを追加

## リポジトリ

- ローカル: `~/secretary/`
- 元のテンプレート: https://github.com/magiccat-lab/my-secretary-template

## 最優先ルール

### Discord 返信（詳細は `AGENT/AGENTS.md` を参照）
- ターミナル出力は Discord に届きません。必ず `reply` を使うこと。
- 長めの処理: 先に「作業中です」と返信して、終わったら**新しい reply** で
  本文を送る。`edit_message` は通知が来ないので頼らない。
- 確認・質問も `reply` で送る。

### よくある失敗
ツールチェーンが終わった後、「完了しました」の1行をターミナル出力だけで
書いてしまうこと。最後は必ず `reply` で締める。

### セットアップ・運用タスク
ユーザーから「Discord 繋いで」「cron 入れて」「カレンダー繋いで」等の
セットアップ依頼が来たら、具体的な手順は `docs/INDEX.md` の表から該当
ファイルを Read して参照する。`nano` / `vi` / `vim` を案内するのは禁止 —
ファイル編集は Write/Edit ツールでエージェント側がやるか、heredoc 一発の
コマンドを渡す。

### 安全
- 外部送信や破壊的コマンドの前に必ず確認する。
- 迷ったら聞く。
