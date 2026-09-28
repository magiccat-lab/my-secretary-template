#!/bin/bash
# install_crons.sh — 必須 cron ジョブを自動登録する
# 使い方: bash ~/secretary/scripts/install_crons.sh [--force]
#
# このテンプレートが管理する cron ブロックだけを差し替える。
# 既に managed block が登録済みなら何もしない（JOBS.md は時刻を「好みで調整」
# してよいと案内しており、start_server.sh のたびに上書きすると調整が毎回
# 消えてしまうため）。デフォルト内容に強制的に戻したいときだけ --force を付ける。

set -euo pipefail
export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
SECRETARY_DIR="${SECRETARY_DIR:-$HOME/secretary}"

FORCE=0
if [ "${1:-}" = "--force" ]; then
    FORCE=1
fi

MARKER_BEGIN="# >>> my-secretary-template managed crons >>>"
MARKER_END="# <<< my-secretary-template managed crons <<<"

existing=$(crontab -l 2>/dev/null || true)

had_block=0
if printf "%s\n" "$existing" | grep -qF "$MARKER_BEGIN"; then
    had_block=1
fi

if [ "$had_block" -eq 1 ] && [ "$FORCE" -ne 1 ]; then
    echo "登録済み。更新するなら --force"
    exit 0
fi

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

if [ "$had_block" -eq 1 ]; then
    echo "=== my-secretary-template の必須 cron 5 本を --force で更新しました ==="
else
    echo "=== my-secretary-template の必須 cron 5 本を登録しました ==="
fi

crontab -l | grep -v '^#' | grep -v '^$'
