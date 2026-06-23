# 複数秘書モード（experimental）

> ⚠️ この機能は experimental です。設定ファイルの雛形は用意していますが、
> runtime 側の自動読み込み（`secretaries.yaml` → ルーティング/state分離）は
> まだ実装されていません。現時点では手動構成になります。

1体の秘書を使い慣れたら、2体目を追加して役割を分けられます。

## 前提

- 1体目の秘書が正常に動作していること
- Discord で秘書ごとに別の Webhook を作成済み（アイコン・名前を分けたい場合）

## セットアップ

### 1. secretaries.yaml を作成

```bash
cp secretaries.yaml.template secretaries.yaml
```

### 2. 2体目の秘書ディレクトリを作成

```bash
cp -r AGENT/secretaries/example AGENT/secretaries/rin
```

`AGENT/secretaries/rin/IDENTITY.md` を編集して2体目のキャラクターを定義。

### 3. secretaries.yaml に2体目を追加

```yaml
secretaries:
  haru:
    display_name: "ハル"
    identity: "AGENT/IDENTITY.md"
    sender:
      kind: bot_token
    channels:
      default_env: DISCORD_CHANNEL_RANDOM
      allowlist_envs:
        - DISCORD_CHANNEL_RANDOM
    state:
      data_dir: "data"
      tasks: "data/pending_tasks.json"
      handoff: "data/handoff.md"
    jobs:
      enabled_tags: [core, diary]

  rin:
    display_name: "リン"
    identity: "AGENT/secretaries/rin/IDENTITY.md"
    sender:
      kind: webhook
      webhook_url_env: DISCORD_WEBHOOK_RIN
    channels:
      default_env: DISCORD_CHANNEL_WORK
      allowlist_envs:
        - DISCORD_CHANNEL_WORK
        - DISCORD_CHANNEL_MAIL
    state:
      data_dir: "data/secretaries/rin"
      tasks: "data/secretaries/rin/pending_tasks.json"
      handoff: "data/secretaries/rin/handoff.md"
    jobs:
      enabled_tags: [gmail, task_remind]
```

### 4. .env に2体目の Webhook URL を追加

```
DISCORD_WEBHOOK_RIN=https://discord.com/api/webhooks/...
DISCORD_CHANNEL_WORK=123456789012345678
```

### 5. データディレクトリを作成

```bash
mkdir -p data/secretaries/rin
```

## 動作モード

### single モード（推奨）

`runtime.mode: single` — 1つの Claude Code セッションが全秘書を処理。
`SECRETARY_ID` 環境変数で「今どの秘書として動いているか」を切り替えます。

cron ジョブは `SECRETARY_ID` 環境変数で担当秘書を指定（将来対応予定）:
```
SECRETARY_ID=haru python3 ~/secretary/scripts/health_check.sh
SECRETARY_ID=rin python3 ~/secretary/scripts/health_check.sh
```

### multi モード（将来対応）

`runtime.mode: multi` — 秘書ごとに別の screen セッションを起動。
完全に独立したプロセスで動作しますが、リソースを多く消費します。
将来の `start_server.sh --secretary <id>` で対応予定。

## ジョブの割り当て

`AGENT/JOBS.md` の各ジョブにタグを付けて、`secretaries.yaml` の
`jobs.enabled_tags` でどの秘書が担当するかを制御します。

```
# JOBS.md のジョブテーブル
| トリガー | スクリプト | タグ | 動作 |
|---------|--------|------|--------|
| cron: */5 * * * * | health_check.sh | core | 死活監視 |
| cron: * * * * * | gmail_monitor.py | gmail | メール監視 |
```

```yaml
# secretaries.yaml
secretaries:
  haru:
    jobs:
      enabled_tags: [core, diary]    # haru は core と diary を担当
  rin:
    jobs:
      enabled_tags: [gmail]          # rin は gmail を担当
```

## チャンネルルーティング

`channels.allowlist_envs` で秘書ごとの担当チャンネルを定義。
メッセージが来たとき、そのチャンネルを担当する秘書が応答します。

同じチャンネルを複数秘書が担当する場合、`default_secretary` が優先されます。
