#!/bin/bash
# health_check.sh - secretaryの死活監視 + 自動復旧スクリプト
# cron: */5 * * * *

# HOMEを明示的にセット（別ユーザー環境からの呼び出し対策）
export HOME="/home/$(whoami)"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../.env"

LOG=/tmp/health_check.log
WEBHOOK_URL="http://localhost:8781/health"
DISCORD_CHANNEL="${DISCORD_CHANNEL_RANDOM}"
MAX_FAILURES=2
FAILURE_FILE=/tmp/health_check_failures.txt

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

# webhook経由でDiscord通知
notify_discord() {
    curl -s -X POST http://localhost:8781/remind \
        -H "Content-Type: application/json" \
        -d "{\"message\": \"$1\", \"channel\": \"$DISCORD_CHANNEL\"}" > /dev/null 2>&1
}

# webhook死亡時のフォールバック: Discord APIに直接送信
notify_discord_direct() {
    local token_file="$HOME/.claude/channels/discord/.env"
    local token=""
    if [ -f "$token_file" ]; then
        token=$(grep "^DISCORD_BOT_TOKEN=" "$token_file" | cut -d'=' -f2-)
    fi
    if [ -z "$token" ]; then return; fi
    curl -s -X POST "https://discord.com/api/v10/channels/${DISCORD_CHANNEL}/messages" \
        -H "Authorization: Bot $token" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"$1\"}" > /dev/null 2>&1
}

# 失敗カウント読み込み
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

# 4. Claude APIの認証状態確認（screen出力から401エラーを検知）
api_ok=true
if $screen_ok; then
    screen -S secretary -X hardcopy /tmp/health_check_screen.txt 2>/dev/null
    if grep -q "API Error: 401\|authentication_error\|Please run /login" /tmp/health_check_screen.txt 2>/dev/null; then
        api_ok=false
        log "Claude API認証エラー検知"
    fi
    rm -f /tmp/health_check_screen.txt
fi

log "webhook=$webhook_ok screen=$screen_ok claude=$claude_ok api=$api_ok failures=$failures"

# API認証エラー → 再起動では直らないので通知のみ
if ! $api_ok; then
    notify_discord_direct "🚨 Claude APIの認証が切れています。ターミナルで \`screen -r secretary\` → \`/login\` を実行してください"
    exit 0
fi

# すべて正常 → カウンタリセット + ハートビート更新
if $webhook_ok && $screen_ok && $claude_ok; then
    echo 0 > "$FAILURE_FILE"
    date '+%Y-%m-%dT%H:%M:%S' > /tmp/secretary_last_alive.txt
    exit 0
fi

# 異常検知 → カウンタ加算
failures=$((failures + 1))
echo "$failures" > "$FAILURE_FILE"
log "異常検知 (failures=$failures): webhook=$webhook_ok screen=$screen_ok claude=$claude_ok"

# MAX_FAILURES回連続で異常 → 再起動（リトライ付き）
if [ "$failures" -ge "$MAX_FAILURES" ]; then
    log "再起動開始"
    echo 0 > "$FAILURE_FILE"

    for attempt in 1 2 3; do
        # screenセッションが落ちている or claudeが死んでいる → 全体再起動
        if ! screen -list 2>/dev/null | grep -q "secretary" || ! pgrep -f "claude --dangerously-skip-permissions" > /dev/null 2>&1; then
            screen -S secretary -X quit 2>/dev/null
            sleep 2
            bash "$HOME/secretary/start_server.sh" >> "$LOG" 2>&1
            sleep 10
        fi

        # 再起動後の確認
        response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$WEBHOOK_URL")
        if [ "$response" = "200" ] && screen -S secretary -X select . > /dev/null 2>&1; then
            log "再起動成功 (attempt $attempt)"
            notify_discord "⚡ secretaryが落ちてたので自動再起動したよ。今は正常です"
            break
        fi

        log "再起動試行 $attempt 失敗"
        if [ $attempt -eq 3 ]; then
            log "再起動3回失敗 - 手動確認が必要"
            notify_discord_direct "🚨 secretary再起動が3回失敗しました。手動確認してください"
        fi
    done
fi
