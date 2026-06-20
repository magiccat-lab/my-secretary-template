#!/bin/bash
# 秘書（secretary）の起動スクリプト
# 使い方: bash ~/secretary/start_server.sh

export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"

SECRETARY_DIR="$HOME/secretary"
LOCKFILE=/tmp/secretary_start.lock

# 多重起動防止
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "start_server.sh already running → exit"
    exit 0
fi

# 古いフラグをリセット
rm -f /tmp/secretary_auth_expired.txt /tmp/health_check_auth_expired_notified.txt

# trust設定を共通関数で修正
source "$SECRETARY_DIR/scripts/ensure_trust.sh"
ensure_trust

# 既存プロセスを安全に停止
if screen -list 2>/dev/null | grep -q "secretary"; then
    screen -S secretary -X quit 2>/dev/null
    for i in $(seq 1 10); do
        screen -list 2>/dev/null | grep -q "secretary" || break
        sleep 0.5
    done
fi

# queue_watcher を停止
if [ -f /tmp/queue_watcher.pid ]; then
    kill "$(cat /tmp/queue_watcher.pid)" 2>/dev/null
    rm -f /tmp/queue_watcher.pid
fi

# webhook を停止
pkill -f "webhook_server.py" 2>/dev/null
sleep 1
if lsof -ti:8781 >/dev/null 2>&1; then
    lsof -ti:8781 | xargs kill -9 2>/dev/null
    sleep 1
fi

# Claude Code を screen セッションで起動（expect wrapper 経由）
# cwd を $SECRETARY_DIR に固定: CLAUDE.md の相対 import 解決 + trust path 一致のため
screen -dmS secretary bash -c "cd $SECRETARY_DIR && expect $SECRETARY_DIR/scripts/claude_wrapper.exp"

# screen セッション確認（最大20秒）
for i in $(seq 1 20); do
    if screen -list 2>/dev/null | grep -q "secretary"; then
        break
    fi
    sleep 1
done
if ! screen -list 2>/dev/null | grep -q "secretary"; then
    echo "ERROR: screen session failed to start"
    exit 1
fi

SECRETARY_SESSION=$(screen -ls | grep secretary | head -1 | awk '{print $1}')
echo "$SECRETARY_SESSION" > /tmp/secretary_session.txt

# 同じ screen 内（別ウィンドウ）で webhook サーバーを起動
screen -S secretary -X screen -t webhook python3 "$SECRETARY_DIR/scripts/webhook_server.py"

# webhook /health 200 確認（最大30秒）
webhook_ready=false
for i in $(seq 1 15); do
    if curl -fsS --max-time 2 http://localhost:8781/health > /dev/null 2>&1; then
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
    bash "$SECRETARY_DIR/scripts/queue_watcher.sh" &
fi

echo "secretary started (session: $SECRETARY_SESSION)"
screen -list | grep secretary
