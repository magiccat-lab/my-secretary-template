#!/bin/bash
# install_crons.sh — 必須 cron ジョブを自動登録する
# 使い方: bash ~/secretary/scripts/install_crons.sh
# このテンプレートが管理する cron ブロックだけを差し替える

set -euo pipefail
export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
SECRETARY_DIR="$HOME/secretary"

MARKER_BEGIN="# >>> my-secretary-template managed crons >>>"
MARKER_END="# <<< my-secretary-template managed crons <<<"

existing=$(crontab -l 2>/dev/null || true)
managed=$(cat <<EOF
$MARKER_BEGIN
*/5 * * * * /bin/bash $SECRETARY_DIR/scripts/health_check.sh >> /tmp/health_check.log 2>&1
*/2 * * * * /usr/bin/python3 $SECRETARY_DIR/scripts/session_watchdog.py >> /tmp/session_watchdog.log 2>&1
30 6,22 * * * /usr/bin/python3 $SECRETARY_DIR/scripts/task_remind.py >> /tmp/task_remind.log 2>&1
0 3 * * * /bin/bash $SECRETARY_DIR/scripts/restart.sh >> /tmp/restart.log 2>&1
50 23 * * * /usr/bin/python3 $SECRETARY_DIR/scripts/integrations/notion/discord_log_to_library.py >> /tmp/discord_log_to_library.log 2>&1
$MARKER_END
EOF
)

cleaned=$(
    printf "%s\n" "$existing" \
        | sed "/^$MARKER_BEGIN$/,/^$MARKER_END$/d" \
        | grep -Ev "$SECRETARY_DIR/scripts/(health_check\.sh|session_watchdog\.py|task_remind\.py|restart\.sh|integrations/notion/discord_log_to_library\.py)" \
        || true
)

{
    if [ -n "$(printf "%s" "$cleaned" | tr -d '[:space:]')" ]; then
        printf "%s\n" "$cleaned"
    fi
    printf "%s\n" "$managed"
} | crontab -

echo "=== my-secretary-template の必須 cron 5 本を登録/更新しました ==="

crontab -l | grep -v '^#' | grep -v '^$'
