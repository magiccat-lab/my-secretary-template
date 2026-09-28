#!/bin/bash
# doctor.sh - 起動前チェック。✅/❌ を日本語で一覧表示する。
#
# 使い方:
#   bash scripts/doctor.sh            # 全項目表示
#   bash scripts/doctor.sh --quiet    # ❌ の行だけ表示
#
# ❌ が1件でもあれば exit 1、無ければ exit 0。
# start_server.sh から `bash scripts/doctor.sh --quiet || echo "..."` の形で
# 呼ばれる想定（あくまで警告。起動そのものは止めない）。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETARY_DIR="${SECRETARY_DIR:-$ROOT}"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

FAIL=0
RESULTS=()  # LINES / COLUMNS は bash の予約変数 (checkwinsize) なのでこの名前は使わない

pass() { RESULTS+=("✅ $1"); }
fail() { RESULTS+=("❌ $1"); FAIL=$((FAIL + 1)); }
note() { RESULTS+=("・ $1"); }

# --- .env を読む（判定用。プロセス環境そのものは変更しない） ---
ENV_FILE="$SECRETARY_DIR/.env"
declare -A ENV_VALS=()
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r k v; do
        case "$k" in ''|\#*) continue ;; esac
        ENV_VALS["$k"]="$v"
    done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE")
fi

# 1. コマンド存在確認
for c in claude screen expect python3 curl lsof flock; do
    if command -v "$c" >/dev/null 2>&1; then
        pass "コマンド: $c"
    else
        fail "コマンド: $c が見つからない"
    fi
done

# 2. python import
for m in fastapi uvicorn requests dotenv; do
    if python3 -c "import $m" >/dev/null 2>&1; then
        pass "python import: $m"
    else
        fail "python import: $m が入っていない（pip install -r requirements.txt）"
    fi
done

# 3. .env 存在 + 必須キー（.env.template の非コメント KEY= 行と突き合わせる）
if [ -f "$ENV_FILE" ]; then
    pass ".env が存在する"
else
    fail ".env が無い（cp .env.template .env）"
fi

# 本当に無いと動かない最小限だけを必須扱いにする。.env.templateの残りは
# 任意機能（Google/Notion/Brave等）なので未設定でも❌にしない
REQUIRED_ENV_KEYS="DISCORD_USER_ID DISCORD_CHANNEL_RANDOM WEBHOOK_TOKEN"
is_required_env_key() {
    case " $REQUIRED_ENV_KEYS " in
        *" $1 "*) return 0 ;;
        *) return 1 ;;
    esac
}

TEMPLATE="$SECRETARY_DIR/.env.template"
if [ -f "$TEMPLATE" ]; then
    while IFS='=' read -r key _; do
        case "$key" in ''|\#*) continue ;; esac
        val="${ENV_VALS[$key]:-}"
        if is_required_env_key "$key"; then
            if [ -n "$val" ]; then
                pass ".envキー(必須): $key"
            else
                fail ".envキー(必須): $key が未設定"
            fi
        else
            if [ -n "$val" ]; then
                note ".envキー(任意): $key 設定済み"
            else
                note ".envキー(任意): $key 未設定"
            fi
        fi
    done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$TEMPLATE")
else
    fail ".env.template が無い"
fi

# 4. Discordプラグイン設定
DISCORD_ENV="$HOME/.claude/channels/discord/.env"
if [ -f "$DISCORD_ENV" ] && grep -q '^DISCORD_BOT_TOKEN=.' "$DISCORD_ENV" 2>/dev/null; then
    pass "Discordプラグイン設定 ($DISCORD_ENV) に DISCORD_BOT_TOKEN あり"
else
    fail "Discordプラグイン設定 ($DISCORD_ENV) が無いか DISCORD_BOT_TOKEN 未設定"
fi

# 5. Claude認証トークン（無くてもOK。/login認証中の正常な状態のため fail にはしない）
TOKEN_FILE="${CLAUDE_OAUTH_TOKEN_FILE:-$SECRETARY_DIR/data/secrets/claude_oauth_token}"
ISSUED_AT_FILE="${TOKEN_FILE}.issued_at"
if [ -s "$TOKEN_FILE" ]; then
    if [ -f "$ISSUED_AT_FILE" ]; then
        issued_epoch=$(date -d "$(cat "$ISSUED_AT_FILE")" +%s 2>/dev/null || echo 0)
        now_epoch=$(date +%s)
        age_days=$(( (now_epoch - issued_epoch) / 86400 ))
        pass "Claude認証トークン: setup-token ファイルあり（発行から${age_days}日）"
    else
        pass "Claude認証トークン: setup-token ファイルあり（発行日不明）"
    fi
else
    pass "Claude認証トークン: なし → /login 認証"
fi

# 6. crontab に health_check.sh の登録があるか
if command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -q 'health_check\.sh'; then
    pass "crontab に health_check.sh の行あり"
else
    fail "crontab に health_check.sh の行が無い（bash scripts/install_crons.sh で登録）"
fi

# 7. ディスク空き容量（/ が1GB超）
avail_kb=$(df -kP / 2>/dev/null | awk 'NR==2{print $4}')
if [ -n "${avail_kb:-}" ] && [ "$avail_kb" -gt 1048576 ] 2>/dev/null; then
    pass "ディスク空き: $((avail_kb / 1024))MB"
else
    fail "ディスク空きが1GB未満（${avail_kb:-不明}KB）"
fi

# 8. data/ が書き込み可能
d="$SECRETARY_DIR/data"
mkdir -p "$d" 2>/dev/null
testfile="$d/.doctor_write_test"
if touch "$testfile" 2>/dev/null; then
    rm -f "$testfile"
    pass "書き込み可能: $d"
else
    fail "書き込み不可: $d"
fi

# 9. secrets ファイルのパーミッション（600 推奨。無ければスキップ）
for f in "$ENV_FILE" "$DISCORD_ENV"; do
    if [ -f "$f" ]; then
        mode="$(stat -c '%a' "$f" 2>/dev/null || stat -f '%Lp' "$f" 2>/dev/null)"
        if [ "$mode" = "600" ]; then
            pass "パーミッション600: $f"
        else
            fail "パーミッションが600でない (${mode:-不明}): $f （chmod 600 推奨）"
        fi
    fi
done

# 10. trust設定（無くてもfailにしない。start_server.sh の ensure_trust が起動時に直す）
if [ -f "$HOME/.claude.json" ] && python3 -c '
import json, sys
home_claude_json, secretary_dir = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(home_claude_json))
except Exception:
    sys.exit(1)
p = d.get("projects", {}).get(secretary_dir, {})
sys.exit(0 if p.get("hasTrustDialogAccepted") else 1)
' "$HOME/.claude.json" "$SECRETARY_DIR" >/dev/null 2>&1; then
    pass "trust設定: ~/.claude.json に $SECRETARY_DIR の hasTrustDialogAccepted あり"
else
    note "trust設定: ~/.claude.json に $SECRETARY_DIR の hasTrustDialogAccepted 無し（start_server.sh の ensure_trust が起動時に直す）"
fi

for l in "${RESULTS[@]}"; do
    if [ "$QUIET" -eq 1 ]; then
        case "$l" in
            ❌*) echo "$l" ;;
        esac
    else
        echo "$l"
    fi
done

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
