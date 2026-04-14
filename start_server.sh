#!/bin/bash
# 秘書（secretary）の起動スクリプト
# 使い方: bash ~/secretary/start_server.sh

export HOME="/home/$(whoami)"
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"

SECRETARY_DIR="$HOME/secretary"

# 既存のセッション / webhook を落とす
screen -S secretary -X quit 2>/dev/null
pkill -f webhook_server.py 2>/dev/null

# webhook のポートを解放
lsof -ti:8781 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Claude Code を screen セッションで起動（Discord プラグイン付き）
screen -dmS secretary bash -c 'claude --dangerously-skip-permissions --channels plugin:discord@claude-plugins-official'
sleep 2

SECRETARY_SESSION=$(screen -ls | grep secretary | head -1 | awk '{print $1}')
echo "$SECRETARY_SESSION" > /tmp/secretary_session.txt

# 同じ screen 内（別ウィンドウ）で webhook サーバーを起動
screen -S secretary -X screen -t webhook python3 "$SECRETARY_DIR/scripts/webhook_server.py"

# キューウォッチャー（オプション）
if [ -f "$SECRETARY_DIR/scripts/queue_watcher.sh" ]; then
  bash "$SECRETARY_DIR/scripts/queue_watcher.sh" &
fi

echo "secretary を起動しました (session: $SECRETARY_SESSION)"
screen -list | grep secretary
