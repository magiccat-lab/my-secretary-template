#!/usr/bin/env python3
"""Discord進行バブル(🔄作業中...)を投稿・編集する長時間ループ。

discord_progress_start.py (UserPromptSubmit) または discord_progress_posttool.py
(PostToolUse) からデタッチで起動される。1つのchat_idにつき常に1プロセスだけが
担当する(状態ファイルのeditor_pidで調停。新しいeditorが状態を上書きしたら古い方は
次のloopで気づいて自分から終了する)。

使い方: python3 discord_progress_editor.py <chat_id> <message_id-or-empty>
        message_idが空文字なら「不明」扱いにして、それが要る操作(⚠️リアクション)だけ省く。

孤児化対策(3つとも):
  - 状態ファイルが消えたら終了
  - stage=="done"になったら終了
  - 状態ファイルのeditor_pidが自分以外になったら終了(新しいeditorに引き継がれた)
  - 経過がMAX_MINUTESを超えたら⚠️を出して状態ファイルを消して終了(孤児のまま90分粘らない)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import discord_rest                     # noqa: E402
from lib import discord_progress_state as state  # noqa: E402

DEFAULT_FIRST_DELAY_SEC = 30.0
DEFAULT_INTERVAL_SEC = 60.0
DEFAULT_MAX_MIN = 90.0


def format_progress_text(name, elapsed_min):
    """nameが空なら秘書名を出さない(SECRETARY_NAME未設定時のフォールバック)。"""
    if name:
        return f"🔄 {name}が作業中 (経過 {elapsed_min} 分)"
    return f"🔄 作業中 (経過 {elapsed_min} 分)"


def format_stalled_text(elapsed_min):
    return f"⚠️ 応答が止まっています (経過 {elapsed_min} 分)"


def _env_float(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _other_editor_alive(st, my_pid):
    """状態ファイルのeditor_pidが自分以外で、かつ生きているか。"""
    if not st:
        return False
    pid = st.get("editor_pid")
    if not pid or pid == my_pid:
        return False
    return state.pid_alive(pid)


def _should_continue(st, my_pid):
    """続けてよいか。state消失/done/自分以外のeditorに引き継がれた、のどれかでFalse。"""
    if not st:
        return False
    if st.get("stage") == state.STAGE_DONE:
        return False
    pid = st.get("editor_pid")
    if pid not in (None, my_pid):
        return False
    return True


def _handle_timeout(chat_id, message_id, last_pmid, elapsed_min):
    """MAX_MINUTES到達時の後始末。⚠️を出して状態ファイルを消す(孤児化対策)。"""
    if last_pmid:
        discord_rest.edit(chat_id, last_pmid, format_stalled_text(elapsed_min))
    if message_id:
        discord_rest.react(chat_id, message_id, "⚠️")
    state.clear(chat_id)


def main():
    if len(sys.argv) < 3:
        return
    chat_id, message_id = sys.argv[1], sys.argv[2]
    my_pid = os.getpid()

    st = state.load(chat_id)
    if _other_editor_alive(st, my_pid):
        print(f"[editor] chat_id={chat_id}: 別のeditor(pid={st.get('editor_pid')})が稼働中なので終了",
              flush=True)
        return

    first_delay = _env_float("DISCORD_PROGRESS_FIRST_DELAY_SEC", DEFAULT_FIRST_DELAY_SEC)
    interval = _env_float("DISCORD_PROGRESS_INTERVAL_SEC", DEFAULT_INTERVAL_SEC)
    max_minutes = _env_float("DISCORD_PROGRESS_MAX_MIN", DEFAULT_MAX_MIN)
    name = os.environ.get("SECRETARY_NAME") or ""

    print(f"[editor] chat_id={chat_id} message_id={message_id!r} pid={my_pid} 開始", flush=True)

    last_pmid = None
    started_at = time.time()

    time.sleep(first_delay)

    st = state.load(chat_id)
    if not _should_continue(st, my_pid):
        print(f"[editor] chat_id={chat_id}: 初回チェックで終了条件(state={st})", flush=True)
        return
    last_pmid = st.get("progress_message_id") or last_pmid
    started_at = st.get("started_at") or started_at
    expected_message_id = st.get("message_id")
    gen_before = st.get("generation")

    pmid = discord_rest.post(chat_id, format_progress_text(name, 0))
    if pmid:
        # A2対策: post()中にStop側がstateを消す/進める競合がありうるので、
        # 書き戻しはflock付きのupdate()で「投稿前と状態が変わっていないか」を
        # 確認してから行う。古いスナップショットをそのまま書き戻して
        # 消えたはずのstateを復活させることは絶対にしない
        def _attach_pmid(current):
            if current is None:
                return None
            if current.get("stage") == state.STAGE_DONE:
                return None
            if current.get("editor_pid") not in (None, my_pid):
                return None
            if current.get("message_id") != expected_message_id:
                return None
            if current.get("generation") != gen_before:
                return None
            current["progress_message_id"] = pmid
            return current

        saved = state.update(chat_id, _attach_pmid)
        if saved is not None:
            last_pmid = pmid
        else:
            print(f"[editor] chat_id={chat_id}: 投稿直後にstateが変わったのでbubbleを消して終了",
                  flush=True)
            discord_rest.delete(chat_id, pmid)
            return
    else:
        print(f"[editor] chat_id={chat_id}: 進行バブルの投稿に失敗", flush=True)

    while True:
        time.sleep(interval)
        st = state.load(chat_id)

        if not _should_continue(st, my_pid):
            if last_pmid:
                discord_rest.delete(chat_id, last_pmid)
            print(f"[editor] chat_id={chat_id}: 終了条件を検知、bubble削除して終了", flush=True)
            return

        last_pmid = st.get("progress_message_id") or last_pmid
        started_at = st.get("started_at") or started_at
        elapsed_min = int((time.time() - started_at) // 60)

        if elapsed_min >= max_minutes:
            _handle_timeout(chat_id, message_id, last_pmid, elapsed_min)
            print(f"[editor] chat_id={chat_id}: MAX_MINUTES到達、停滞警告して終了", flush=True)
            return

        if last_pmid:
            discord_rest.edit(chat_id, last_pmid, format_progress_text(name, elapsed_min))


if __name__ == "__main__":
    main()
