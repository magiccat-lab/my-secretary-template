# my-secretary-template

小さな VPS 上で常時稼働する、自分専用の AI 秘書を動かすためのテンプレート。
Claude Code をエンジンに、プライベートな Discord チャンネルから話しかけられます。
セットアップ後は、cron 登録・Google 連携・トークン管理まで、すべて起動後の
**エージェントとの会話**でやります。ターミナルで長文を貼ったりエディタを
開いたりしません。

## はじめに読むもの

- **[`SETUP.md`](SETUP.md)** — 人間向けの初回セットアップ手順。
  VPS を借りたばかりの状態から Discord で会話できるまで、そのまま上から
  順にやれば動くように書いてあります。まずここを見てください。

- **[`docs/INDEX.md`](docs/INDEX.md)** — エージェント（起動後の秘書）が
  運用時に参照するリファレンス群の索引。仕組みが気になったときに覗く用。

## 必要なもの

| | |
|---|---|
| Claude Pro プラン | https://claude.ai |
| Linux VPS（Xserver / Hetzner / Raspberry Pi 等） | 月 $5〜10 |
| Discord アカウント + bot | 無料 |
| Google アカウント（Calendar / Gmail を使う場合のみ） | 無料 |

## ライセンス

MIT。[LICENSE](LICENSE) を参照。

## Phase 1 拡張

Phase 1 拡張では、初回セットアップ後に「自分用の秘書」として育て始めるための土台を追加しています。
既存の `SETUP.md` は上から順に進める flow、この section と `docs/setup/` は仕組みを理解するための reference です。

### 追加された主なもの

- **8 DB sketch**: Notion 上に Tasks / Diary / Memory / Action Log / Conversation Log / Script Invocations / Cron Invocations / Channels を作る想定の schema 群です。
- **Onboarding**: `scripts/onboarding.py` で user profile と assistant prompt の初期 file を生成できます。
- **Sample scripts**: `templates/onboarded/` に daily brief、task digest、calendar reminder、health ping などの出発点があります。
- **sanitize_lint**: 公開 template に個人情報や secret が混ざらないように検査します。
- **CI**: Python compile と sanitize check を自動化する前提の workflow があります。

### 初回に見る file

- [`SETUP.md`](SETUP.md) — まず上から順に実行する本編です。
- [`docs/setup/xserver-vps.md`](docs/setup/xserver-vps.md) — VPS 契約後の初期設定を詳しく説明します。
- [`docs/setup/domain.md`](docs/setup/domain.md) — domain と DNS の設定です。
- [`docs/setup/cloudflared.md`](docs/setup/cloudflared.md) — tunnel、DNS route、service 化の手順です。
- [`docs/setup/notion.md`](docs/setup/notion.md) — Notion integration、capability、DB 共有の説明です。
- [`docs/setup/claude-code.md`](docs/setup/claude-code.md) — Claude Code install、login、Discord plugin の説明です。
- [`docs/setup/discord-bot.md`](docs/setup/discord-bot.md) — Discord bot、token、intents、channel ID の説明です。
- [`docs/setup/systemd.md`](docs/setup/systemd.md) — watchdog を systemd service として動かす手順です。
- [`docs/setup/sanitize.md`](docs/setup/sanitize.md) — sanitize_lint と pre-commit hook の説明です。
- [`docs/setup/troubleshooting.md`](docs/setup/troubleshooting.md) — 初日に詰まりやすい Q&A 集です。

### Onboarding

対話式で初期 profile を作る場合:

    python3 scripts/onboarding.py

default 値で試す場合:

    python3 scripts/onboarding.py --yes

生成される代表 file:

- `AGENT/USER.md`
- `templates/generated/anthropic_compatible_prompt.md`

既存 persona を保護したい場合は、別 directory を指定します。

    python3 scripts/onboarding.py --agent-dir AGENT_LOCAL

### Example persona

最小 persona は [`AGENT/IDENTITY.md`](AGENT/IDENTITY.md) と [`AGENT/AGENTS.md`](AGENT/AGENTS.md) から始められます。
公開 template では、固有の人物設定ではなく、利用者が自分で置き換えられる placeholder として扱います。

### Sample scripts

初期改造の入口:

- `templates/onboarded/daily_brief.py`
- `templates/onboarded/task_digest.py`
- `templates/onboarded/calendar_remind.py`
- `templates/onboarded/memory_capture.py`
- `templates/onboarded/discord_log_sync.py`
- `templates/onboarded/health_ping.py`

まず 1 つだけ動かし、Discord 通知、Notion 書き込み、cron 登録を順に足すと切り分けしやすいです。

### 公開前 check

    python3 scripts/lib/sanitize_lint.py .
    python3 -m compileall scripts integrations templates

CI が落ちた場合は、先に local で同じ command を実行します。
secret、database id、channel id、private hostname は repository に入れないでください。

## Phase 2 拡張

Phase 2 では秘書を「育てる・記録する・学習させる」フェーズの機能を追加しています。
すべてオプションで、`.env` の `FEATURE_*=true` フラグで個別に有効化します。

### 追加された主な機能

- **handoff** — 毎晩の引き継ぎ自動生成。`scripts/system/nightly_handoff.py` が `data/claude/handoff.md` を書き出し、次のセッションが前日の文脈を即座に把握できます。
- **chat search** — Discord 会話ログを SQLite に蓄積し、自然言語で横断検索できます。`data/discord_corpus.sqlite3` がローカル全文検索のバックエンドです。
- **gmail** — Gmail をポーリングしてフィルタルールに沿った通知・自動返信を行います。`integrations/gmail/filter_rules.yaml` でルールを定義します。
- **diary** — 毎晩 21:30 に「今日どうだった？」をDiscordで問いかけ、回答を `data/notes/` に蓄積します。
- **trainer** — 会話ログと TIL から persona の成長提案・知識ファイル更新を自動化します。

### 有効化の流れ

1. `.env` の `FEATURE_*` フラグを `true` に変更
2. `python3 scripts/onboarding.py` を再実行（5つの追加質問が表示されます）
3. `python3 scripts/system/install_cron.py add` で cron を再インストール
4. 各機能の詳細は `docs/setup/` 配下を参照してください
