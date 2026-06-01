#!/bin/bash
# コールドリスタート（cron で実行する想定。推奨は毎日 03:00 の nightly）
#
# 理由: Claude Code を screen で長期間動かすと会話コンテキストやステートが
# 溜まって重く・不安定になる。定期コールドリスタートで handoff を残しつつ
# クリーンな状態に戻す。スケジュールは cron 側で決める（毎日 / 週1 どちらでも、
# このスクリプト自体は共通）。
#
# ステップ:
#   1. handoff.md を生成（次セッションが再開位置を分かるように）
#   2. screen セッションを kill
#   3. start_server.sh で起動し直す
#   4. 「resumed!」をキュー投入（新セッションが handoff.md を読むように）
#
# 有効化するには crontab に以下を追加（推奨: 毎日 03:00 の nightly）:
#   0 3 * * * /bin/bash $HOME/secretary/scripts/restart.sh >> /tmp/restart.log 2>&1
# 週1で十分なら（日曜 03:10）:
#   10 3 * * 0 /bin/bash $HOME/secretary/scripts/restart.sh >> /tmp/restart.log 2>&1
#
# Claude Code を自動ローテートする仕組み（systemd timer など）を使ってる
# なら不要。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 実行ユーザーの実ホーム（root なら /root、一般ユーザーなら /home/ユーザー名）
export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

source "$SCRIPT_DIR/../.env"
LOG_FILE="/tmp/restart.log"

DISCORD_TOKEN=$(grep '^DISCORD_BOT_TOKEN=' "$HOME/.claude/channels/discord/.env" 2>/dev/null | cut -d= -f2)
CH_NOTIFY="${DISCORD_CHANNEL_RANDOM}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
    echo "$1"
}

discord_send() {
    local channel="$1"
    local message="$2"
    [ -z "$DISCORD_TOKEN" ] || [ -z "$channel" ] && return
    /usr/bin/curl -s -X POST "https://discord.com/api/v10/channels/${channel}/messages" \
        -H "Authorization: Bot ${DISCORD_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"content\": $(echo "$message" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')}" \
        > /dev/null 2>&1
}

queue_message() {
    local queue_file="$1"
    local message="$2"
    echo "$message" | base64 >> "$queue_file"
}

# 死んだソケットの掃除
screen -wipe > /dev/null 2>&1

log "=== 再起動 開始 ==="

# 1. handoff を生成
python3 "$SCRIPT_DIR/daily_handoff.py" >> "$LOG_FILE" 2>&1 || log "handoff 生成失敗（続行します）"

# 2. ログチャンネルに通知
discord_send "$CH_NOTIFY" "再起動を開始します ($(date '+%H:%M'))"

# 3. secretary の screen を再起動（リトライあり）
log "secretary を再起動中..."
for attempt in 1 2 3; do
    screen -S secretary -X quit 2>/dev/null
    sleep 1

    # expect wrapper を経由して Bypass Permissions / Trust folder の UI 壁を自動 accept
    # cwd 固定は CLAUDE.md の相対 import [@AGENT/IDENTITY.md 等] の解決にも必須
    screen -dmS secretary bash -c "export HOME=$HOME && cd $HOME/secretary && expect $HOME/secretary/scripts/claude_wrapper.exp"
    sleep 2

    elapsed=0
    while [ $elapsed -lt 8 ]; do
        if screen -list 2>/dev/null | grep -q "secretary"; then
            break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    sleep 3
    if screen -S secretary -X select . > /dev/null 2>&1; then
        log "secretary 起動 OK (attempt $attempt)"
        break
    else
        log "secretary 再起動失敗 (attempt $attempt)"
        if [ $attempt -eq 3 ]; then
            discord_send "$CH_NOTIFY" "再起動が3回失敗しました — 手動確認してください"
        fi
    fi
done

# 4. webhook + queue watcher を起動
bash "$HOME/secretary/start_server.sh" >> "$LOG_FILE" 2>&1

# 5. 最終チェック + handoff 再開シグナル
sleep 5
if screen -S secretary -X select . > /dev/null 2>&1; then
    log "再起動 OK"
    sleep 3
    queue_message "/tmp/claude_queue.txt" "resumed! (nightly restart) — data/handoff.md を読んでください"
    discord_send "$CH_NOTIFY" "再起動 完了"
else
    discord_send "$CH_NOTIFY" "再起動 結果不明 — 実行してください: screen -list"
fi

log "=== 再起動 完了 ==="
