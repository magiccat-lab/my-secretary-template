#!/bin/bash
# health_check.sh - secretaryの死活監視 + 自動復旧スクリプト
# cron: */5 * * * *

export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../.env"
source "$SCRIPT_DIR/ensure_trust.sh" 2>/dev/null || true

LOG=/tmp/health_check.log
WEBHOOK_URL="http://localhost:8781/health"
DISCORD_CHANNEL="${DISCORD_CHANNEL_RANDOM}"
MAX_FAILURES=2
FAILURE_FILE=/tmp/health_check_failures.txt
AUTH_EXPIRED_NOTIFIED=/tmp/health_check_auth_expired_notified.txt
AUTH_FLAG=/tmp/secretary_auth_expired.txt

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

notify_discord() {
    notify_discord_direct "$1"
}

notify_discord_direct() {
    local token_file="$HOME/.claude/channels/discord/.env"
    local token=""
    if [ -f "$token_file" ]; then
        token=$(grep "^DISCORD_BOT_TOKEN=" "$token_file" | cut -d'=' -f2-)
    fi
    if [ -z "$token" ]; then return; fi
    local payload
    payload=$(python3 -c "import json,sys; print(json.dumps({'content': sys.argv[1]}))" "$1")
    curl -s -X POST "https://discord.com/api/v10/channels/${DISCORD_CHANNEL}/messages" \
        -H "Authorization: Bot $token" \
        -H "Content-Type: application/json" \
        -d "$payload" > /dev/null 2>&1
}

failures=0
if [ -f "$FAILURE_FILE" ]; then
    failures=$(cat "$FAILURE_FILE")
fi

# 1. webhookサーバーの応答確認
webhook_ok=false
response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$WEBHOOK_URL")
if [ "$response" = "200" ]; then
    webhook_ok=true
fi

# 2. screenセッションの確認
screen_ok=false
if screen -list 2>/dev/null | grep -q "secretary"; then
    screen_ok=true
fi

# 3. Claudeプロセスの確認
claude_ok=false
if pgrep -f "claude --dangerously-skip-permissions" > /dev/null 2>&1; then
    claude_ok=true
fi

# 4. trustプロンプト検知 + 認証状態確認
auth_expired=false
if $screen_ok; then
    HARDCOPY=/tmp/health_check_screen.txt
    screen -S secretary -X hardcopy "$HARDCOPY" 2>/dev/null

    # trust prompt → 自動応答
    if grep -qi "trust\|safety check\|safety.check" "$HARDCOPY" 2>/dev/null; then
        log "trustプロンプト検知 - 自動応答"
        ensure_trust
        screen -S secretary -X stuff $'\n'
        sleep 1
        screen -S secretary -X stuff $'\n'
    fi

    # auth切れ検知
    if grep -qiE "logged out|log.?in (again|required|to continue)|please.{0,10}log.?in|auth.*expir|token.*expir|session.*expir|re.?authenticat|unauthenticated|API Error: 401|authentication_error" "$HARDCOPY" 2>/dev/null; then
        auth_expired=true
        log "Claudeオーソリ切れ検知"
        # auth状態フラグを立てる（queue_watcherが参照）
        touch "$AUTH_FLAG"
        if [ ! -f "$AUTH_EXPIRED_NOTIFIED" ]; then
            notify_discord_direct "⚠️ Claudeのオーソリが切れてます。ターミナルで /login してね"
            touch "$AUTH_EXPIRED_NOTIFIED"
        fi
    else
        # auth正常 → フラグ両方クリア
        rm -f "$AUTH_EXPIRED_NOTIFIED" "$AUTH_FLAG"
    fi
    rm -f "$HARDCOPY"
fi

log "webhook=$webhook_ok screen=$screen_ok claude=$claude_ok auth_expired=$auth_expired failures=$failures"

# auth切れ → 再起動しても直らない
if $auth_expired; then
    log "オーソリ切れのため自動再起動スキップ（ユーザー操作が必要）"
    exit 0
fi

# すべて正常 → カウンタリセット + ハートビート更新
if $webhook_ok && $screen_ok && $claude_ok; then
    if [ "$failures" -gt 0 ]; then
        notify_discord "⚡ secretaryが落ちてたので自動再起動したよ。今は正常です"
    fi
    echo 0 > "$FAILURE_FILE"
    date '+%Y-%m-%dT%H:%M:%S' > /tmp/secretary_last_alive.txt
    exit 0
fi

# 異常検知 → カウンタ加算
failures=$((failures + 1))
echo "$failures" > "$FAILURE_FILE"
log "異常検知 (failures=$failures): webhook=$webhook_ok screen=$screen_ok claude=$claude_ok"

# MAX_FAILURES回連続で異常 → 再起動
if [ "$failures" -ge "$MAX_FAILURES" ]; then
    log "再起動開始"
    echo 0 > "$FAILURE_FILE"
    bash "$HOME/secretary/start_server.sh" >> "$LOG" 2>&1
    sleep 10

    response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$WEBHOOK_URL")
    if [ "$response" = "200" ]; then
        log "再起動成功"
    else
        log "再起動失敗 - 手動確認が必要"
        notify_discord_direct "🚨 secretary再起動失敗。手動確認してください"
    fi
fi
