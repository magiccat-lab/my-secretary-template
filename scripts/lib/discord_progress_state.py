#!/usr/bin/env python3
"""Discord進行状況表示の状態ファイルI/O、channelタグのパース、配信成否の判定。

状態ファイル: $SECRETARY_DIR/data/discord_progress/<chat_id>.json (デフォルト ~/secretary)
  {
    "message_id": "...",          # 受信メッセージ(reactionを付ける対象)のID。不明ならnull
    "started_at": 1234567890.0,   # そのターンを受け取った時刻(epoch秒)
    "stage": "received" | "working" | "done",
    "progress_message_id": "..." | null,  # 🔄吹き出しのメッセージID(まだ無ければnull)
    "editor_pid": 12345 | null,           # discord_progress_editor.pyのPID
  }
"""
import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time

STAGE_RECEIVED = "received"
STAGE_WORKING = "working"
STAGE_DONE = "done"

_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_CHANNEL_TAG_RE = re.compile(r"<channel\s+([^>]*)>")


def _secretary_dir():
    return os.environ.get("SECRETARY_DIR") or os.path.expanduser("~/secretary")


def _state_dir():
    return os.path.join(_secretary_dir(), "data", "discord_progress")


def _state_path(chat_id):
    # chat_idをそのままファイル名にする。区切り文字混入への念のための保険
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", str(chat_id))
    return os.path.join(_state_dir(), f"{safe}.json")


def _lock_path(chat_id):
    return _state_path(chat_id) + ".lock"


@contextlib.contextmanager
def locked(chat_id):
    """chat_idの状態ファイルに対する排他ロック(fcntl.flock、プロセス間で効く)。

    editorのbubble投稿後の書き戻しや、hook側のeditor起動を1つのchat_idにつき
    1回だけにするための排他区間で使う(with文)。
    """
    path = _lock_path(chat_id)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def log_path(name):
    """$SECRETARY_DIR/data/logs/<name> を返す(ディレクトリは作っておく)。"""
    path = os.path.join(_secretary_dir(), "data", "logs", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


# --- channelタグのパース ---------------------------------------------------

def parse_channel_tag(text):
    """本文中の<channel source="...">タグから(chat_id, message_id)を取る。無ければNone。

    sourceは "discord" 単体でも "plugin:discord:discord" でも拾う。属性の並び順は問わない
    (chat_id/message_idがsourceの前でも後でも良い)。最初に見つかった一致を返す。
    """
    if not text:
        return None
    for m in _CHANNEL_TAG_RE.finditer(text):
        attrs_str = m.group(1)
        attrs = dict(_ATTR_RE.findall(attrs_str))
        source = attrs.get("source")
        if source not in ("discord", "plugin:discord:discord"):
            continue
        chat_id = attrs.get("chat_id")
        message_id = attrs.get("message_id")
        if chat_id and message_id:
            return (chat_id, message_id)
    return None


# --- transcript読み取り(require_discord_reply.pyと同じ探索ロジック) -----------
# discord_turn_end.py / discord_progress_posttool.py の両方が、状態ファイルが
# 無い時のフォールバックとして「直近の人間由来userメッセージ」を探すのに使う。
# require_discord_reply.py自体は変更しない(このモジュールへコピーしただけ)。

def is_human_user_msg(row):
    """tool_resultではない、人間(またはDiscord)由来のuserメッセージか。"""
    if row.get("type") != "user":
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(b.get("type") == "tool_result" for b in content if isinstance(b, dict))
    return False


def text_of(row):
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def find_latest_inbound_index(rows):
    """rows中の直近の人間由来userメッセージのindexを返す。無ければNone。"""
    for i in range(len(rows) - 1, -1, -1):
        if is_human_user_msg(rows[i]):
            return i
    return None


def load_transcript_rows(path):
    """jsonl transcriptを読んでdictのlistにする。読めなければ空list。"""
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except Exception:
        return []


# --- 状態ファイルI/O ---------------------------------------------------------

def load(chat_id):
    """状態を読む。無い/壊れていればNone。"""
    path = _state_path(chat_id)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save(chat_id, state):
    """tmp書き込み+os.replaceで原子的に保存する。"""
    path = _state_path(chat_id)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return state


def clear(chat_id):
    """状態ファイルを消す。無くてもエラーにしない。"""
    path = _state_path(chat_id)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def clear_if_owned(chat_id, message_id):
    """flock内で現在の状態を読み直し、message_idが一致する時だけ消す。

    TOCTOU対策: 「消してよいか」を判定した時点と実際に消す時点の間に、
    別turnがensure_started等でstateを作り直しているかもしれない。そのため
    削除の直前にもう一度ロック内でmessage_id一致を確認してから消す。
    一致しなければ何もしない(他turnの状態・bubbleには触れない)。
    戻り値: 実際に消せたか。
    """
    with locked(chat_id):
        current = load(chat_id)
        if current is None:
            return False
        if current.get("message_id") != message_id:
            return False
        try:
            os.remove(_state_path(chat_id))
        except FileNotFoundError:
            pass
        return True


def update(chat_id, mutate):
    """load→mutate→saveをflockで排他しつつ行う、原子的な読み書き。

    mutateは現在の状態(無ければNone)を受け取り、保存したい新しい辞書を返す関数。
    Noneを返すと何も書かずに終わる(中止。他プロセスが先に消した/進めた時など)。
    保存する辞書には毎回 "generation" を +1 して書き込む(古いスナップショットの
    書き戻し=stateの復活を検知するための版数。呼び出し側で比較に使う)。
    戻り値: 実際に保存した状態(中止時はNone)。
    """
    with locked(chat_id):
        current = load(chat_id)
        new_state = mutate(current)
        if new_state is None:
            return None
        new_state["generation"] = (current.get("generation", 0) if current else 0) + 1
        save(chat_id, new_state)
        return new_state


# --- プロセス管理 ------------------------------------------------------------

def pid_alive(pid):
    """pidが生きているか(シグナル0で確認。他ユーザ所有でも生存扱い)。"""
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def editor_script_path():
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_progress_editor.py")
    )


def spawn_editor(chat_id, message_id):
    """discord_progress_editor.pyをデタッチで起動し、pidを返す(失敗はNone)。

    message_idが不明(None/空)でも呼んでよい。editor側が該当reactionだけskipする。
    stdout/stderrは $SECRETARY_DIR/data/logs/discord_progress_editor.log に流す。
    """
    try:
        logf = open(log_path("discord_progress_editor.log"), "a", encoding="utf-8")
    except Exception:
        logf = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            [sys.executable, editor_script_path(), str(chat_id), str(message_id or "")],
            start_new_session=True,
            stdout=logf,
            stderr=logf,
        )
        return proc.pid
    except Exception:
        return None


def ensure_started(chat_id, message_id):
    """状態が無ければstage=receivedで新規作成してeditorを起動する。あればそのまま返す。

    B1対策: 「状態が無いか確認する」〜「editor_pidを書き込む」までをflockで排他するので、
    複数のhookがほぼ同時に呼んでも(chat_id, message_id)につきeditorは1つしか起動しない。
    先にeditor_pid=Noneで保存してからeditorを起動し、起動後にpidを書き戻す
    (起動直後にStop側が先に走ってeditor_pid不明のまま孤児化する隙間を短くするため)。
    """
    with locked(chat_id):
        current = load(chat_id)
        if current is not None:
            return current
        fresh = {
            "message_id": message_id,
            "started_at": time.time(),
            "stage": STAGE_RECEIVED,
            "progress_message_id": None,
            "editor_pid": None,
            "generation": 1,
        }
        save(chat_id, fresh)
        pid = spawn_editor(chat_id, message_id)
        fresh["editor_pid"] = pid
        fresh["generation"] = 2
        save(chat_id, fresh)
        return fresh


# --- 配信成否の判定 -----------------------------------------------------------
# reply / edit_message のtool_result(またはPostToolUseのtool_response)から、
# 「本当に配信できたか」をfail-closedで判定する。is_error/isErrorがtrueなら即失敗。
# それ以外は「falseや欠落だから成功」とは見なさず、プラグインが返す成功パターン
# (reply: "sent (id:" / edit_message: "edited (id:")が本文に無ければ配信済みとしない。
# None・空応答も未確認=未配信扱い(誤って✅にする方が、差し戻しが1回増えるより害が大きい)。

SUCCESS_PATTERNS = {
    "mcp__plugin_discord_discord__reply": "sent (id:",
    "mcp__plugin_discord_discord__edit_message": "edited (id:",
}


def extract_result_text(obj):
    """tool_result/tool_responseのcontentからテキストを取り出す(形が揺れても拾う)。"""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        if "content" in obj:
            return extract_result_text(obj["content"])
        text = obj.get("text")
        if isinstance(text, str):
            return text
        return ""
    if isinstance(obj, list):
        parts = []
        for item in obj:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def _error_flag_true(obj):
    """is_error/isErrorのどちらの綴りでもtrueが立っていれば真。"""
    if not isinstance(obj, dict):
        return False
    for key in ("is_error", "isError"):
        if obj.get(key):
            return True
    return False


def is_delivered(tool_name, obj):
    """tool_response/tool_resultから、その呼び出しが本当に配信できたかを判定する。

    is_error(/isError)フラグがtrueなら即False。それ以外は本文にtool_nameに
    対応する成功パターンがあるかで判定する(falseや欠落だけでは成功と認めない)。
    tool_nameが未知、またはobjがNoneならFalse(fail-closed)。
    """
    if obj is None:
        return False
    if _error_flag_true(obj):
        return False
    pattern = SUCCESS_PATTERNS.get(tool_name)
    if not pattern:
        return False
    return pattern in extract_result_text(obj)
