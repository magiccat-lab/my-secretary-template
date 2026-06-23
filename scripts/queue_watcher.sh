#!/bin/bash
# Claude メッセージキューウォッチャー
# Claude がプロンプト待ちの時だけ入力を送る。idle確認できなければ送らない

# 多重起動防止
PIDFILE=/tmp/queue_watcher.pid
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "queue_watcher already running (PID $OLD_PID) → exit"
        exit 0
    fi
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

QUEUE=/tmp/claude_queue.txt
PROCESSED=/tmp/claude_queue_processed.txt
QUEUE_DIR=/tmp/claude_queue_state
AUTH_FLAG=/tmp/secretary_auth_expired.txt

mkdir -p "$QUEUE_DIR"
touch "$QUEUE" "$PROCESSED"

echo "queue_watcher 起動: $QUEUE を監視中"

is_claude_idle() {
    local hardcopy="/tmp/queue_watcher_hardcopy.txt"
    local session
    session=$(cat /tmp/secretary_session.txt 2>/dev/null || echo "secretary")

    if ! screen -list 2>/dev/null | grep -q "$session"; then
        return 1
    fi

    screen -S "$session" -X at "0#" hardcopy "$hardcopy" 2>/dev/null
    if [ ! -f "$hardcopy" ]; then
        return 1
    fi

    local content
    content=$(cat "$hardcopy" 2>/dev/null)
    rm -f "$hardcopy"

    # auth切れ中は入力しない
    if echo "$content" | grep -qiE "logged out|log.?in (again|required|to continue)|auth.*expir|unauthenticated"; then
        return 1
    fi

    # Claude プロセスが生きていなければ idle とみなさない（shell fallback 防止）
    if ! pgrep -f "claude" > /dev/null 2>&1; then
        return 1
    fi

    # Claude Code のプロンプト待ち: 末尾行に > か ❯ がある
    local last_line
    last_line=$(echo "$content" | grep -v '^$' | tail -1)
    if echo "$last_line" | grep -qE '(>|❯)\s*$'; then
        return 0
    fi

    return 1
}

while true; do
    # auth切れ中はスキップ
    if [ -f "$AUTH_FLAG" ]; then
        sleep 5
        continue
    fi

    queue_lines=$(wc -l < "$QUEUE" 2>/dev/null || echo 0)
    processed_lines=$(wc -l < "$PROCESSED" 2>/dev/null || echo 0)

    if [ "$queue_lines" -gt "$processed_lines" ]; then
        next_line=$((processed_lines + 1))
        encoded=$(sed -n "${next_line}p" "$QUEUE")

        if [ -n "$encoded" ]; then
            message=$(printf '%s' "$encoded" | base64 -d 2>/dev/null)

            if [ -n "$message" ]; then
                # Claude がidle になるまで待つ（最大60秒）
                waited=0
                idle_ok=false
                while [ "$waited" -lt 60 ]; do
                    if is_claude_idle; then
                        idle_ok=true
                        break
                    fi
                    sleep 3
                    waited=$((waited + 3))
                done

                if ! $idle_ok; then
                    echo "[$(date)] Claude not idle after 60s, will retry next loop"
                    sleep 5
                    continue
                fi

                SESSION=$(cat /tmp/secretary_session.txt 2>/dev/null || echo "secretary")

                claim_id=$(date +%s%N)
                echo "$message" > "$QUEUE_DIR/pasted_${claim_id}.txt"

                tmp=$(mktemp)
                printf '%s\n' "$message" > "$tmp"
                if ! screen -S "$SESSION" -X readreg p "$tmp"; then
                    echo "[$(date)] ERROR: screen readreg failed"
                    rm -f "$tmp" "$QUEUE_DIR/pasted_${claim_id}.txt"
                    sleep 3
                    continue
                fi
                if ! screen -S "$SESSION" -X paste p; then
                    echo "[$(date)] ERROR: screen paste failed"
                    rm -f "$tmp" "$QUEUE_DIR/pasted_${claim_id}.txt"
                    sleep 3
                    continue
                fi
                rm -f "$tmp"
                sleep 0.3

                if ! screen -S "$SESSION" -X stuff $'\015'; then
                    echo "[$(date)] ERROR: screen stuff failed, clearing input"
                    screen -S "$SESSION" -X stuff $'\025' 2>/dev/null
                    rm -f "$QUEUE_DIR/pasted_${claim_id}.txt"
                    sleep 3
                    continue
                fi

                date +%s > /tmp/last_claude_input.txt
                rm -f /tmp/last_input_hung_checked.txt

                find "$QUEUE_DIR" -name "pasted_*" -mmin +60 -delete 2>/dev/null

                sleep 1
            fi
        fi

        head -n "$next_line" "$QUEUE" > "$PROCESSED"
    fi

    if [ "$queue_lines" -lt "$processed_lines" ]; then
        cp "$QUEUE" "$PROCESSED"
    fi

    sleep 1
done
