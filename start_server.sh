#!/bin/bash
# 秘書（secretary）の起動スクリプト
# 使い方: bash ~/secretary/start_server.sh

export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"

SECRETARY_DIR="${SECRETARY_DIR:-$HOME/secretary}"
LOCKFILE=/tmp/secretary_start.lock

# 多重起動防止。このロックはスクリプト終了まで保持する（≠子プロセスの多重起動防止）。
# fd 200 は子プロセスに渡さない: screen 常駐や queue_watcher（無限ループ）が fd を
# 継承したまま残ると、スクリプト終了後もロックが解放されず、次回の起動が
# 「already running → exit」で空振りする（restart.sh の nightly / health_check.sh の
# 自動復旧が実質的に効かなくなる）。そのため各子起動には必ず `200>&-` を付ける
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "start_server.sh already running → exit"
    exit 0
fi

# .env を読み込み（hook や webhook サーバーが env を継ぐため）
if [ -f "$SECRETARY_DIR/.env" ]; then
    set -a
    source "$SECRETARY_DIR/.env"
    set +a
fi
WEBHOOK_PORT="${WEBHOOK_PORT:-8781}"

# secrets のパーミッションを強制（chmod漏れ対策）
chmod 600 "$SECRETARY_DIR/.env" "$HOME/.claude/channels/discord/.env" 2>/dev/null || true

# 起動前チェック（警告のみ表示。失敗しても起動は続ける）。PATH設定の後で呼ぶ
bash "$SECRETARY_DIR/scripts/doctor.sh" --quiet 200>&- || echo "doctor: 警告あり (起動は続ける)"

# 古いフラグをリセット
rm -f /tmp/secretary_auth_expired.txt /tmp/health_check_auth_expired_notified.txt

# trust設定を共通関数で修正
source "$SECRETARY_DIR/scripts/ensure_trust.sh"
ensure_trust

# 既存プロセスを安全に停止
if screen -list 2>/dev/null | grep -q "\.secretary[[:space:]]"; then
    screen -S secretary -X quit 2>/dev/null
    for i in $(seq 1 10); do
        screen -list 2>/dev/null | grep -q "\.secretary[[:space:]]" || break
        sleep 0.5
    done
fi

# queue_watcher を停止
if [ -f /tmp/queue_watcher.pid ]; then
    kill "$(cat /tmp/queue_watcher.pid)" 2>/dev/null
    rm -f /tmp/queue_watcher.pid
fi

# webhook を停止（ポートを LISTEN しているPIDだけを狙う。pkill -f は grep や
# エディタ等の無関係プロセスを巻き込むので使わない）。TERM → 最大3秒待つ → 残っていればKILL
webhook_pids=$(lsof -tiTCP:${WEBHOOK_PORT} -sTCP:LISTEN 2>/dev/null)
if [ -n "$webhook_pids" ]; then
    kill $webhook_pids 2>/dev/null
    for i in $(seq 1 6); do
        webhook_pids=$(lsof -tiTCP:${WEBHOOK_PORT} -sTCP:LISTEN 2>/dev/null)
        [ -z "$webhook_pids" ] && break
        sleep 0.5
    done
    webhook_pids=$(lsof -tiTCP:${WEBHOOK_PORT} -sTCP:LISTEN 2>/dev/null)
    if [ -n "$webhook_pids" ]; then
        kill -9 $webhook_pids 2>/dev/null
    fi
fi

# Claude 認証: setup-token の1年トークンがあれば優先して使う（/loginのOAuthは30日で
# 失効するため）。無ければ何もしない（従来どおり /login 認証のまま動く）。
# トークンの値そのものは絶対に echo しない
TOKEN_FILE="${CLAUDE_OAUTH_TOKEN_FILE:-$SECRETARY_DIR/data/secrets/claude_oauth_token}"
if [ -s "$TOKEN_FILE" ]; then
    export CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '\n\r ' < "$TOKEN_FILE")"
    unset ANTHROPIC_API_KEY
    echo "claude auth: setup-token ファイルを使用"
else
    echo "claude auth: /login 認証 (token file なし)"
fi

# Claude Code を screen セッションで起動（expect wrapper 経由）
# cwd を $SECRETARY_DIR に固定: CLAUDE.md の相対 import 解決 + trust path 一致のため
screen -dmS secretary bash -c 'cd "$1" && exec expect "$1/scripts/claude_wrapper.exp"' _ "$SECRETARY_DIR" 200>&-

# screen セッション確認（最大20秒）
for i in $(seq 1 20); do
    if screen -list 2>/dev/null | grep -q "\.secretary[[:space:]]"; then
        break
    fi
    sleep 1
done
if ! screen -list 2>/dev/null | grep -q "\.secretary[[:space:]]"; then
    echo "ERROR: screen session failed to start"
    exit 1
fi

SECRETARY_SESSION=$(screen -ls | grep secretary | head -1 | awk '{print $1}')
echo "$SECRETARY_SESSION" > /tmp/secretary_session.txt

# 同じ screen 内（別ウィンドウ）で webhook サーバーを起動
screen -S secretary -X screen -t webhook python3 "$SECRETARY_DIR/scripts/webhook_server.py" 200>&-

# webhook /health 200 確認（最大30秒）
webhook_ready=false
for i in $(seq 1 15); do
    if curl -fsS --max-time 2 "http://localhost:${WEBHOOK_PORT}/health" > /dev/null 2>&1; then
        webhook_ready=true
        break
    fi
    sleep 2
done
if ! $webhook_ready; then
    echo "ERROR: webhook not responding after 30s, aborting"
    exit 1
fi

# queue_watcherを起動（webhook ready確認後のみ）
if [ -f "$SECRETARY_DIR/scripts/queue_watcher.sh" ]; then
    bash "$SECRETARY_DIR/scripts/queue_watcher.sh" 200>&- &
fi

# 必須 cron の自動登録（未登録分のみ追加）
bash "$SECRETARY_DIR/scripts/install_crons.sh" 200>&- 2>/dev/null || true

# 起動後チェック（生存記録 + 落ちてた間の失敗ジョブ検出）をバックグラウンドで実行
bash "$SECRETARY_DIR/scripts/startup_check.sh" 200>&- &

echo "secretary started (session: $SECRETARY_SESSION)"
screen -list | grep secretary
