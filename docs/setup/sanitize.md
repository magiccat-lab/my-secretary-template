# sanitize_lint

公開 template に個人情報、secret、環境固有値が混ざらないように `sanitize_lint.py` を使います。

## ゴール

- sanitize check を手動実行できる
- CI で落ちた時に直せる
- pre-commit hook で commit 前に検出できる
- secret を repository に入れない

## 1. 対象 script

    scripts/lib/sanitize_lint.py

まず help を見ます。

    python scripts/lib/sanitize_lint.py --help

引数仕様が変わっている場合は help を優先してください。

## 2. 手動実行

repo root で実行します。

    cd ~/my-secretary-template
    python scripts/lib/sanitize_lint.py .

特定 directory だけ見る場合:

    python scripts/lib/sanitize_lint.py docs scripts AGENT

## 3. 検出時の考え方

検出されたら、まず公開 template に必要な情報かを判断します。

置換例:
- 実名 → `USER_NAME`
- assistant 名 → `ASSISTANT_NAME`
- workspace 名 → `WORKSPACE_NAME`
- channel id → `DISCORD_CHANNEL_ID`
- database id → `NOTION_DATABASE_ID`
- server IP → `SERVER_IP`
- hostname → `assistant.example.com`

## 4. secret file を commit しない

commit しないもの:
- `.env`
- OAuth token
- Discord token
- Cloudflared credentials json
- private key
- cookie
- local DB dump

確認:

    git status --short
    git check-ignore -v .env

## 5. `.gitignore`

最低限:

    .env
    *.pem
    *.key
    token.json
    credentials.json
    .cloudflared/
    __pycache__/
    .venv/

## 6. pre-commit hook

`.git/hooks/pre-commit` を作ります。

    nano .git/hooks/pre-commit

内容例:

    #!/usr/bin/env bash
    set -euo pipefail

    python3 scripts/lib/sanitize_lint.py .
    python3 -m compileall scripts integrations templates

実行権限:

    chmod +x .git/hooks/pre-commit

## 7. hook の注意

pre-commit hook は local repository にだけ存在します。
配布したい場合は `scripts/setup_hooks.sh` のような install script を作るか、docs に手順を書きます。

## 8. CI との関係

CI でも同じ check を実行します。

    python3 scripts/lib/sanitize_lint.py .
    python3 -m compileall scripts integrations templates

local で通って CI で落ちる場合:
- Python version 差
- ignore file 差
- line ending 差
- 生成 file が CI にだけ存在

## 9. 誤検出対応

公開 template では、誤検出でも placeholder に寄せる判断が安全です。
どうしても必要な固有名詞なら、sanitize rule 側に allowlist を作る前に、本当に公開 template に必要か見直します。

## 10. commit 前 checklist

- `.env` が unstaged
- token が diff にない
- database id が placeholder
- channel id が placeholder
- private hostname が placeholder
- sanitize が通る
- py compile が通る

## 11. 共有前 checklist

共有する前に実行:

    git status --short
    python scripts/lib/sanitize_lint.py .
    python3 -m compileall scripts integrations templates

log や screenshot を共有する場合も token を伏字にします。

## 12. 次に読むもの

詰まった場合は `docs/setup/troubleshooting.md` の secret / sanitize / CI の項目を見ます。
