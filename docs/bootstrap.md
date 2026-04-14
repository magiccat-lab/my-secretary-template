# bootstrap.md — セットアップ後の再構築・VPS 移行（エージェント向け）

**人間向けの初回セットアップ手順は、リポジトリ直下の `SETUP.md` に移しました。**
clone 直後〜初めて Discord が繋がるまではそちらを参照してください。

このファイルは、**既に1度動いた後で**ユーザーから依頼されがちな
「作り直し」「再構築」「移行」のランブックに特化しています。

---

## 0. リポジトリ構造（初手の地図）

```
~/secretary/
├── CLAUDE.md                  # 起動ファイル（@ で他を読み込む）
├── SETUP.md                   # 人間向け初回セットアップ（このファイルではない）
├── AGENT/
│   ├── IDENTITY.md            # キャラ + 口調
│   ├── USER.md                # ユーザー情報
│   ├── AGENTS.md              # 行動ルール（Discord、タスク、安全）
│   └── JOBS.md                # 定期実行ジョブ
├── scripts/                   # コアランタイム + cron スクリプト
│   ├── webhook_server.py
│   ├── task_remind.py
│   ├── task_sheet_sync.py
│   ├── daily_handoff.py
│   ├── health_check.sh
│   ├── queue_watcher.sh
│   └── lib/                   # jst, tasks, db, notes, error_db, metrics_db
├── integrations/
│   ├── discord/               # ドキュメントのみ
│   ├── gcal/                  # Calendar スクリプト + OAuth フロー（Gmail と共有）
│   └── gmail/                 # Gmail モニター
├── data/                      # タスク、handoff、notes（gitignore）
├── docs/                      # 本ドキュメント群（INDEXから辿る）
├── .env.template
├── requirements.txt
└── start_server.sh            # screen ベースの起動スクリプト
```

シークレットは2箇所に分かれている:
- `~/secretary/.env` — 秘書本体が読む（チャンネルID、Webhookトークン等）
- `~/.claude/channels/discord/.env` — Discordプラグインと送信ヘルパーが読む
  （`DISCORD_BOT_TOKEN` だけ）

`.env` は両方ともplaintext。`chmod 600` を必ず効かせて、gitには絶対に
commitしない（`.gitignore` 済み）。

---

## 1. キャラクター再構築の依頼が来たとき

トリガー:
- 「キャラ作り直したい」「口調もう一回決めたい」「IDENTITY埋め直して」
- `AGENT/IDENTITY.md` が `{{placeholder}}` のまま残っていることに気付いたとき

秘書が既に起動している前提なら、直接 Edit/Write で対話しながら埋められる。
まだ起動していないケースでは **`SETUP.md` セクション H のプロンプト** を
ユーザーに渡して、claude.ai 側で作ってもらう。

### 起動後の口調育成ループ
1. ユーザーが「『X』みたいに言って」と言ったら即真似る
2. 5個くらい蓄積したら `AGENT/writing/corrections.md` にまとめる（Write）
3. さらに溜まったら `AGENT/writing/style_sample.txt` を作って `CLAUDE.md`
   の読み込み順に `@AGENT/writing/style_sample.txt` を追加

---

## 2. シークレット漏洩時のローテーション

トークンを誤って commit したら **必ず該当 token を再発行する**:
- Discord: 開発者ポータル → Bot → Reset Token → 新トークンを
  `~/.claude/channels/discord/.env` に書き直す
- Google: Cloud Console → Credentials → 該当 OAuth client → Reset secret、
  その後 `python3 integrations/gcal/reauth.py` で再認証（詳細: `docs/google.md`）
- Webhook: `.env` の `WEBHOOK_TOKEN` を再生成（`python3 -c "import secrets; print(secrets.token_hex(32))"`）、
  同じ値を使う呼び出し側（Tasker、ホームオートメーション）も合わせて更新

git history からの完全削除が必要なら `git filter-repo` を案内。ただし
リモートに push 済みなら漏洩前提で再発行が最優先。

---

## 3. 変更を反映した後の再起動

`AGENT/*.md` / `CLAUDE.md` / `docs/` / `scripts/*.py` を編集した後は
基本的に screen ごと再起動する:

```bash
screen -S secretary -X quit
bash ~/secretary/start_server.sh
```

webhook スクリプトだけ触った場合は、webhook ウィンドウ内で Ctrl+C →
上矢印で同じコマンドを再実行すれば充分（詳細は `docs/webhook.md`）。

---

## 4. 新規 VPS への移行 / 別マシンで立ち上げ直し

ユーザーが「引越す」「別の VPS に移す」と言ってきたとき:

1. **現 VPS**: `data/` と `memory/`（あれば）をバックアップ git repo に push、
   `.env` 2つ と `integrations/gcal/token.json` / `credentials.json` を
   安全な場所にコピーしてもらう
2. **新 VPS**: `SETUP.md` の A〜C をそのまま実行してもらう
   （apt、timezone、claude-code、clone、pip install）
3. **新 VPS**: バックアップから `.env` 2つ、`integrations/gcal/token.json` /
   `credentials.json`、`data/pending_tasks.json` を復元（Editツールでユーザー
   から内容を貼ってもらうか、scp で流してもらう）
4. **新 VPS**: `bash ~/secretary/start_server.sh` で起動 → `/discord:access`
   で allowlist 再設定（ここはユーザー操作）
5. cron は `crontab -l` の中身を**新 VPS で再登録**（ユーザー名パスが変わる
   ので `docs/cron.md` のユーザー置換を忘れずに）

### 新規 VPS 初期設定の最小コマンド（クイックリファレンス）
`SETUP.md` A に同じ内容があるが、エージェントが SSH 越しに代行する場合の
コピペ用に再掲。

```bash
sudo timedatectl set-timezone Asia/Tokyo
sudo ufw allow OpenSSH
sudo ufw enable
sudo apt update
sudo apt install -y python3 python3-pip git screen curl lsof at tmux
```

最小スペック目安: 1 vCPU / 512 MB RAM（1 GB あると快適） / 10 GB ディスク /
Ubuntu 22.04+ または Debian 12+。

---

## 5. 依存の再インストール / 追加

```bash
cd ~/secretary
pip install -r requirements.txt
```

新しいパッケージを使いたくなったら `requirements.txt` に追記 → 同コマンド。
venv派なら `python3 -m venv .venv && source .venv/bin/activate` を先に。
cron からは `~/secretary/.venv/bin/python3` を直で叩く。

---

## 6. 参照

- 人間向けの初回セットアップ: **`/SETUP.md`**（リポジトリ直下）
- 機能別ランブック: `docs/INDEX.md` 経由
- ジョブ仕様: `AGENT/JOBS.md`
