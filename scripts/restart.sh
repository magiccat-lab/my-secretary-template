#!/bin/bash
# コールドリスタート（cron で実行する想定。推奨は毎日 03:00 の nightly）
#
# 理由: Claude Code を screen で長期間動かすと会話コンテキストやステートが
# 溜まって重く・不安定になる。定期コールドリスタートで handoff を残しつつ
# クリーンな状態に戻す。
#
# ステップ:
#   1. handoff.md を生成
#   2. start_server.sh で全プロセスを安全に再起動
#   3. 「resumed!」をキュー投入（新セッションが handoff.md を読むように）
#
# 有効化するには crontab に以下を追加（推奨: 毎日 03:00 の nightly）:
#   0 3 * * * /bin/bash $HOME/secretary/scripts/restart.sh >> /tmp/restart.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

screen -wipe > /dev/null 2>&1

log "=== 再起動 開始 ==="

# 1. handoff を生成
python3 "$SCRIPT_DIR/daily_handoff.py" >> "$LOG_FILE" 2>&1 || log "handoff 生成失敗（続行します）"

# 2. 通知
discord_send "$CH_NOTIFY" "再起動を開始します ($(date '+%H:%M'))"

# 3. start_server.sh に全プロセス管理を委譲（flock で二重起動防止済み）
log "secretary を再起動中..."
bash "$HOME/secretary/start_server.sh" >> "$LOG_FILE" 2>&1
start_result=$?

if [ "$start_result" -ne 0 ]; then
    log "start_server.sh 失敗 (exit $start_result)"
    discord_send "$CH_NOTIFY" "再起動が失敗しました — 手動確認してください"
    log "=== 再起動 失敗 ==="
    exit 1
fi

# 4. handoff 再開シグナル（webhook ready確認後に投入）
for i in $(seq 1 15); do
    if curl -fsS --max-time 2 http://localhost:8781/health > /dev/null 2>&1; then
        queue_message "/tmp/claude_queue.txt" "resumed! (nightly restart) — data/handoff.md を読んでください"
        log "再起動 OK"
        discord_send "$CH_NOTIFY" "再起動 完了"
        break
    fi
    sleep 2
done

log "=== 再起動 完了 ==="
