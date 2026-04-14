#!/bin/bash
# Claude メッセージキューウォッチャー
# ポーリング方式でファイル置き換え・truncateに強い実装

QUEUE=/tmp/claude_queue.txt
PROCESSED=/tmp/claude_queue_processed.txt
touch "$QUEUE" "$PROCESSED"

echo "queue_watcher 起動: $QUEUE を監視中"

while true; do
    # キューに未処理行がある場合に処理
    queue_lines=$(wc -l < "$QUEUE" 2>/dev/null || echo 0)
    processed_lines=$(wc -l < "$PROCESSED" 2>/dev/null || echo 0)

    if [ "$queue_lines" -gt "$processed_lines" ]; then
        # 未処理の行を取得
        tail -n "+$((processed_lines + 1))" "$QUEUE" | while IFS= read -r encoded; do
            [ -z "$encoded" ] && continue
            message=$(printf '%s' "$encoded" | base64 -d 2>/dev/null)
            [ -z "$message" ] && continue
            SESSION=$(cat /tmp/secretary_session.txt 2>/dev/null || echo "secretary")
            tmp=$(mktemp)
            printf '%s\n' "$message" > "$tmp"
            screen -S "$SESSION" -X readreg p "$tmp"
            screen -S "$SESSION" -X paste p
            rm -f "$tmp"
            sleep 0.3
            screen -S "$SESSION" -X stuff $'\015'
            sleep 0.5
        done
        # 処理済みカウントを更新
        cp "$QUEUE" "$PROCESSED"
    fi

    # キューファイルがリセット（行数が減った）場合は処理済みもリセット
    if [ "$queue_lines" -lt "$processed_lines" ]; then
        cp "$QUEUE" "$PROCESSED"
    fi

    sleep 1
done
