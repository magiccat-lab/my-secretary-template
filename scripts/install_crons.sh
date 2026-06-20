#!/bin/bash
# install_crons.sh — 必須 cron ジョブを自動登録する
# 使い方: bash ~/secretary/scripts/install_crons.sh
# 既に登録済みのエントリは重複しない

export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
SECRETARY_DIR="$HOME/secretary"

REQUIRED_CRONS=(
    "*/5 * * * * /bin/bash $SECRETARY_DIR/scripts/health_check.sh >> /tmp/health_check.log 2>&1"
    "*/2 * * * * /usr/bin/python3 $SECRETARY_DIR/scripts/session_watchdog.py >> /tmp/session_watchdog.log 2>&1"
    "0 3 * * * /bin/bash $SECRETARY_DIR/scripts/restart.sh >> /tmp/restart.log 2>&1"
    "50 23 * * * /usr/bin/python3 $SECRETARY_DIR/scripts/integrations/notion/discord_log_to_library.py >> /tmp/discord_log_to_library.log 2>&1"
)

existing=$(crontab -l 2>/dev/null || true)
added=0

for entry in "${REQUIRED_CRONS[@]}"; do
    # スクリプト名で重複チェック
    script_name=$(echo "$entry" | grep -oP '[^ ]+\.(sh|py)' | head -1)
    if echo "$existing" | grep -q "$script_name"; then
        echo "skip (already registered): $script_name"
        continue
    fi
    existing="$existing"$'\n'"$entry"
    added=$((added + 1))
    echo "add: $script_name"
done

if [ "$added" -gt 0 ]; then
    echo "$existing" | crontab -
    echo "=== $added 件の cron を登録しました ==="
else
    echo "=== 全て登録済み ==="
fi

crontab -l | grep -v '^#' | grep -v '^$'
