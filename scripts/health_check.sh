#!/bin/bash
# health_check.sh - secretaryの死活監視 + 自動復旧スクリプト
# cron: */5 * * * *

export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../.env"
source "$SCRIPT_DIR/ensure_trust.sh" 2>/dev/null || true

LOG=/tmp/health_check.log
WEBHOOK_PORT="${WEBHOOK_PORT:-8781}"
WEBHOOK_URL="http://localhost:${WEBHOOK_PORT}/health"
DISCORD_CHANNEL="${DISCORD_CHANNEL_RANDOM}"
MAX_FAILURES=2
FAILURE_FILE=/tmp/health_check_failures.txt
RESTART_HISTORY=/tmp/health_check_restart_history.txt
COOLDOWN_NOTIFIED=/tmp/health_check_cooldown_notified.txt
AUTH_EXPIRED_NOTIFIED=/tmp/health_check_auth_expired_notified.txt
AUTH_FLAG=/tmp/secretary_auth_expired.txt
TOKEN_FILE="${CLAUDE_OAUTH_TOKEN_FILE:-$HOME/secretary/data/secrets/claude_oauth_token}"
TOKEN_ISSUED_AT_FILE="${TOKEN_FILE}.issued_at"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

notify_discord() {
    local msg="$1"
    local payload
    payload=$(python3 -c 'import json,sys; print(json.dumps({"message": sys.argv[1], "channel": sys.argv[2]}))' "$msg" "$DISCORD_CHANNEL")
    curl -s -X POST "http://localhost:${WEBHOOK_PORT}/remind" \
        -H "Content-Type: application/json" \
        -H "X-Webhook-Token: ${WEBHOOK_TOKEN}" \
        -d "$payload" > /dev/null 2>&1
}

notify_discord_direct() {
    local msg="$1"
    local token_file="$HOME/.claude/channels/discord/.env"
    local token=""
    if [ -f "$token_file" ]; then
        token=$(grep "^DISCORD_BOT_TOKEN=" "$token_file" | cut -d'=' -f2-)
    fi
    if [ -z "$token" ]; then return; fi
    local payload
    payload=$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1]}))' "$msg")
    curl -s -X POST "https://discord.com/api/v10/channels/${DISCORD_CHANNEL}/messages" \
        -H "Authorization: Bot $token" \
        -H "Content-Type: application/json" \
        -d "$payload" > /dev/null 2>&1
}

# 暴走防止: 直近30分の再起動回数チェック（このチェック自体より前に何もしない。
# cooldown中はwebhook/screen/claudeの確認も自動再起動もせず、1回だけ通知して抜ける）
restart_count_30min=$(awk -v cutoff="$(date -d '30 min ago' '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" '$0 > cutoff' "$RESTART_HISTORY" 2>/dev/null | wc -l)
if [ "$restart_count_30min" -ge 3 ]; then
    log "暴走検知: 30分で${restart_count_30min}回再起動 → cooldown適用、手動確認待ち"
    if [ ! -f "$COOLDOWN_NOTIFIED" ]; then
        notify_discord_direct "⚠️ secretaryが30分で${restart_count_30min}回再起動しました。暴走モードで一時停止中です。手動確認してください"
        touch "$COOLDOWN_NOTIFIED"
    fi
    exit 0
fi
rm -f "$COOLDOWN_NOTIFIED"

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
if screen -list 2>/dev/null | grep -q "\.secretary[[:space:]]"; then
    screen_ok=true
fi

# 3. Claudeプロセスの確認
claude_ok=false
if pgrep -f "claude --dangerously-skip-permissions" > /dev/null 2>&1; then
    claude_ok=true
fi

# 4. trustプロンプト検知 + 認証状態確認
# 誤発火防止: 会話本文中の "trust"/"token expired" 等に反応しないよう、画面最下部の
# 空行を除いた末尾8行だけ・プロンプト固有文言に限定して判定する
auth_expired=false
auth_healthy_seen=false
if $screen_ok; then
    HARDCOPY=/tmp/health_check_screen.txt
    HARDCOPY_TAIL=/tmp/health_check_screen_tail.txt
    screen -S secretary -X hardcopy "$HARDCOPY" 2>/dev/null
    grep -v '^[[:space:]]*$' "$HARDCOPY" 2>/dev/null | tail -8 > "$HARDCOPY_TAIL" 2>/dev/null

    # trust prompt → 自動応答
    if grep -qiE "Do you trust the files in this folder|Yes, proceed" "$HARDCOPY_TAIL" 2>/dev/null; then
        log "trustプロンプト検知 - 自動応答"
        ensure_trust
        screen -S secretary -X stuff $'\n'
        sleep 1
        screen -S secretary -X stuff $'\n'
    fi

    # auth切れ検知（文言はプロンプト固有のものだけに絞る）
    if grep -qiE "Please run /login|/login to (continue|authenticate)|You are not logged in|Invalid API key|OAuth token (has )?expired|authentication_error|API Error: 401" "$HARDCOPY_TAIL" 2>/dev/null; then
        auth_expired=true
        log "Claudeオーソリ切れ検知"
    fi

    # 生存プロンプト検知: 末尾の空でない行が $ / > / ❯ で終わる時だけ「正常」とみなす
    # （queue_watcher.sh の is_claude_idle と同じ基準。文言が無いだけでは解除しない）
    last_line=$(tail -1 "$HARDCOPY_TAIL" 2>/dev/null)
    if echo "$last_line" | grep -qE '(\$|>|❯)[[:space:]]*$'; then
        auth_healthy_seen=true
    fi

    rm -f "$HARDCOPY" "$HARDCOPY_TAIL"
fi

if $auth_expired; then
    # auth状態フラグを立てる（queue_watcherが参照）
    touch "$AUTH_FLAG"
    if [ ! -f "$AUTH_EXPIRED_NOTIFIED" ]; then
        if [ -s "$TOKEN_FILE" ]; then
            notify_discord_direct "⚠️ Claudeの認証が切れてます。サーバで bash ~/secretary/scripts/setup_claude_token.sh を実行して再発行してね"
        else
            notify_discord_direct "⚠️ Claudeのオーソリが切れてます。ターミナルで /login してね"
        fi
        touch "$AUTH_EXPIRED_NOTIFIED"
    fi
elif $auth_healthy_seen; then
    # 生存プロンプトを確認できたときだけ解除する
    rm -f "$AUTH_EXPIRED_NOTIFIED" "$AUTH_FLAG"
fi

# 4b. トークン期限の事前警告（setup-token は1年で失効。切れる前に更新を促す）
if [ -f "$TOKEN_ISSUED_AT_FILE" ]; then
    issued_epoch=$(date -d "$(cat "$TOKEN_ISSUED_AT_FILE")" +%s 2>/dev/null)
    now_epoch=$(date +%s)
    if [ -n "$issued_epoch" ]; then
        token_age_days=$(( (now_epoch - issued_epoch) / 86400 ))
        if [ "$token_age_days" -gt 350 ]; then
            TOKEN_AGE_NOTIFIED="/tmp/health_check_token_age_notified_$(date '+%Y-%m-%d')"
            if [ ! -f "$TOKEN_AGE_NOTIFIED" ]; then
                log "トークン期限警告: 発行から${token_age_days}日"
                notify_discord_direct "🔑 Claudeのトークンが発行から ${token_age_days} 日。1年で切れるので setup_claude_token.sh で更新して"
                touch "$TOKEN_AGE_NOTIFIED"
            fi
        fi
    fi
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
    date '+%Y-%m-%d %H:%M:%S' >> "$RESTART_HISTORY"
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
