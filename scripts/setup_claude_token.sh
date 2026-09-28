#!/bin/bash
# setup_claude_token.sh - Claude Code の1年トークン(setup-token)をサーバに保存する
#
# 背景: `/login` で発行される OAuth refresh token は30日で失効し、月1で
#       「ログイン認証切れ」が起きる（health_check.sh が検知してDiscord通知）。
#       `claude setup-token` で発行する1年トークンに切り替えれば、年1回の更新で済む。
#
# 使い方:
#   bash scripts/setup_claude_token.sh                  # 対話実行（claude setup-token を起動し、出たトークンを自動で拾う）
#   bash scripts/setup_claude_token.sh --file PATH       # 発行済みトークンをファイルから読み込む
#   bash scripts/setup_claude_token.sh --paste           # 自動で拾わず、表示されたトークンを手で貼る
#   bash scripts/setup_claude_token.sh --force           # 発行したてのトークンでも強制上書き
#
# setup-token の直後の read が空で返って「トークンが空」で止まることがある
# （対話 CLI が端末を返した直後は入力が残っていて、貼る前に Enter が消費される）。
# そのため script(1) で setup-token の画面出力を記録し、そこから sk-ant-oat01-... を拾う。
# 画面幅で折り返されていても（CLI は端末幅で改行を入れる）連結して 1 本にする。
#
# 制限: token認証中は claude.ai の connectors と Remote Control が使えない。
#       Discordプラグイン(bun経由のlocal MCP)はclaude.aiサブスク認証で動く想定なので影響なし。
#       詳細は docs/claude_auth_token.md 参照。

set -uo pipefail

SECRETARY_DIR="${SECRETARY_DIR:-$HOME/secretary}"
SECRETS_DIR="$SECRETARY_DIR/data/secrets"
TOKEN_FILE="$SECRETS_DIR/claude_oauth_token"
ISSUED_AT_FILE="$TOKEN_FILE.issued_at"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"   # テストでは偽物に差し替える

FROM_FILE=""
FORCE=0
PASTE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --file)
            FROM_FILE="${2:-}"
            shift 2
            ;;
        --file=*)
            FROM_FILE="${1#--file=}"
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --paste)
            PASTE=1
            shift
            ;;
        *)
            echo "使い方: $0 [--file <トークンファイルのパス>] [--paste] [--force]" >&2
            exit 2
            ;;
    esac
done

# 既存トークンが「今日以降」発行済み（＝今日すでに実行済みの可能性が高い）なら、
# --force なしでは上書きしない。事故での二重実行・誤クリック対策。
if [ -f "$ISSUED_AT_FILE" ] && [ "$FORCE" -ne 1 ]; then
    existing_date="$(tr -d '[:space:]' < "$ISSUED_AT_FILE" 2>/dev/null)"
    today="$(date '+%Y-%m-%d')"
    # 日付 (YYYY-MM-DD) の文字列比較。以前は発行日 0 時の epoch と今を比べていたので
    # 同じ日でも 0 時を過ぎれば通ってしまい、二重実行の抑止になっていなかった
    if [[ "$existing_date" == "$today" || "$existing_date" > "$today" ]]; then
        echo "エラー: 既存トークンの発行日が今日以降($existing_date)。事故防止のため --force なしでは上書きしない" >&2
        exit 1
    fi
fi

# 対話 CLI が端末を返した直後に残っている入力（Enter や端末の応答）を捨てる。
# 端末でない stdin（テストのパイプ等）はそのまま使うので触らない
drain_stdin() {
    [ -t 0 ] || return 0
    while read -r -t 0.2 _junk; do :; done
}

# script(1) の記録から sk-ant-oat01-... を取り出す。ANSI 制御列を落とし、CLI が端末幅で
# 折り返した続きの行（トークン文字だけの行）を連結する。一番長い候補を採る
extract_token() {
    python3 - "$1" <<'EOF'
import re
import sys

raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
raw = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", raw)   # OSC
raw = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", raw)           # CSI
raw = raw.replace("\r", "")
best = ""
pattern = r"sk-ant-oat01-[A-Za-z0-9_\-]+(?:\n[ \t]*[A-Za-z0-9_\-]+[ \t]*(?=\n|$))*"
for m in re.finditer(pattern, raw):
    token = re.sub(r"\s+", "", m.group(0))
    if len(token) > len(best):
        best = token
if len(best) < 40:
    sys.exit(1)
print(best)
EOF
}

echo "=== Claude Code 1年トークン設定 ==="
echo "このスクリプトはサーバー上で年1回実行する想定。"
echo "/login のOAuthトークンは30日で失効するが、setup-token の1年トークンに切り替えると"
echo "この作業だけで1年もつ（token認証中は claude.ai の connectors / Remote Control が使えなくなる）。"
echo

token=""
if [ -n "$FROM_FILE" ]; then
    if [ ! -f "$FROM_FILE" ]; then
        echo "エラー: ファイルが無い: $FROM_FILE" >&2
        exit 1
    fi
    token="$(tr -d '\n\r ' < "$FROM_FILE")"
    echo "ファイルからトークンを読み込んだ: $FROM_FILE"
elif [ "$PASTE" -eq 1 ] || ! command -v script >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    echo "1. これから claude setup-token を起動する。ブラウザでの認証を終えると画面にトークンが表示される"
    echo "2. 表示されたトークンをコピーする（折り返されていても 1 本につなげる）"
    echo "3. 次のプロンプトに貼り付けて Enter（画面には表示されません）"
    echo
    if command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
        "$CLAUDE_BIN" setup-token
    else
        echo "警告: claude コマンドが見つからない。別ターミナルで claude setup-token を実行してから戻ってきてください" >&2
    fi
    echo
    drain_stdin
    read -rsp "表示されたトークンを貼り付けて Enter: " token
    echo
else
    echo "1. これから claude setup-token を起動する。表示された URL をブラウザで開き、秘書の Claude アカウントで認証する"
    echo "2. ブラウザに出たコードを端末に貼って Enter"
    echo "3. 表示されたトークンはこのスクリプトが自動で拾う（手でコピーしなくてよい）"
    echo
    if ! command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
        echo "エラー: claude コマンドが見つからない。export PATH=\"\$HOME/.bun/bin:\$PATH\" してから再実行" >&2
        exit 1
    fi
    umask 077
    capture="$(mktemp "${TMPDIR:-/tmp}/claude_setup_token.XXXXXX")"
    trap 'rm -f "$capture"' EXIT
    # 端末から実行している時は script(1) で pty ごと記録する（setup-token は対話 CLI なので
    # pty が要る。-q: ヘッダ無し / -e: 子の終了コードを返す）。stdin が端末でない時
    # （テストや自動化）は script が stdin を全部食ってしまうので、素の出力を tee で記録する。
    # 記録先はトークンを含むので 600 のまま最後に消す
    if [ -t 0 ]; then
        script -q -e -c "$CLAUDE_BIN setup-token" "$capture"
        rc=$?
    else
        "$CLAUDE_BIN" setup-token 2>&1 | tee "$capture"
        rc=${PIPESTATUS[0]}
    fi
    echo
    if [ "$rc" -ne 0 ]; then
        echo "エラー: claude setup-token が正常終了しなかった (exit $rc)。もう一度実行する" >&2
        exit 1
    fi
    token="$(extract_token "$capture")" || token=""
    if [ -n "$token" ]; then
        echo "トークンを拾った: ${token:0:16}... (${#token} 文字)"
        drain_stdin
        read -rp "これで保存する? [Y/n]: " ans
        case "$ans" in
            n|N|no) echo "保存しなかった"; exit 1 ;;
        esac
    else
        echo "画面からトークンを拾えなかった。表示されたトークンを貼り付ける（画面には出ない）:"
        drain_stdin
        read -rsp "表示されたトークンを貼り付けて Enter: " token
        echo
    fi
fi

if [ -z "$token" ]; then
    echo "エラー: トークンが空。中止する" >&2
    exit 1
fi

if [ "${#token}" -le 20 ]; then
    echo "警告: トークンが短すぎる（${#token}文字）。コピーミスの可能性があるので内容を確認してください" >&2
fi

umask 077
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# 書き込み中に他プロセスが不完全なファイルを読まないよう、一時ファイル→mvで原子的に置き換える
tmp_token="$(mktemp "$SECRETS_DIR/.claude_oauth_token.XXXXXX")"
chmod 600 "$tmp_token"
printf '%s' "$token" > "$tmp_token"
mv -f "$tmp_token" "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"

tmp_issued="$(mktemp "$SECRETS_DIR/.claude_oauth_token.issued_at.XXXXXX")"
chmod 600 "$tmp_issued"
date '+%Y-%m-%d' > "$tmp_issued"
mv -f "$tmp_issued" "$ISSUED_AT_FILE"
chmod 600 "$ISSUED_AT_FILE"
unset token

echo "保存した。bash ~/secretary/start_server.sh で再起動して"
