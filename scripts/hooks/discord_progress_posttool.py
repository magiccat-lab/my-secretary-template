#!/usr/bin/env python3
"""PostToolUse hook (matcher: mcp__plugin_discord_discord__reply|...__edit_message)。

進行表示の主経路。UserPromptSubmit(discord_progress_start.py)が発火するとは限らない
(Discordのchannel messageで本当に発火するか未確認)ので、こちらを「確実な入口」として
状態を作る側にする:

  - reply/edit_messageの呼び出しが**配信できた**(state.is_deliveredがTrue。
    is_error/isErrorがtrueでなく、本文に成功パターンがある)時だけ動く
    (PreToolUse=着手であって配信ではないので見ない。ここはPostToolUse=結果を見る)
  - 既に状態がある場合、この呼び出しが本当にそのmessage_idのものかを確認してから
    でないと一切触らない(A3のownership確認)。確認の材料はreply_to(reply toolに
    明示的な返信先が指定されていれば)、無ければtranscriptの直近受信タグ。
    どちらも取れない/既存状態と食い違う場合は既存状態には一切触れない
    (以前はreply_to無し=edit_message呼び出し全般で確認自体をskipしており、
    別turnの状態を誤って進めてしまう穴があった)
  - 状態ファイルが無ければここで新規に作る(message_idの決め方は上と同じ優先順位。
    それでも不明ならNoneのまま進める)
    (state.ensure_startedが新規作成とeditor起動をflockで排他しつつ行う。B1対策)
  - stage==received なら 📨を外して▶を付けてstage=workingにする。この昇格も
    flock内でmessage_id一致を再確認してから行う(TOCTOU対策。所有権確認と実際の
    書き込みの間に別turnへ置き換わる余地があるため、確認済みでも書き込みは常に
    ロック付きのstate.updateを通す)

message_idが不明な時は「その情報が要る操作」だけ静かにskipする(reaction系)。
バブルの投稿・編集はchat_idだけで出来るのでeditorは起動して構わない。

Print nothing, always exit 0(permission判定には関与しない)。lib importが失敗しても
(requestsが無い等)ImportErrorを外に漏らさずno-opにする。
"""
import json
import os
import sys

try:
    HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(HOOKS_DIR, ".."))
    from lib import discord_rest                     # noqa: E402
    from lib import discord_progress_state as state  # noqa: E402
    _IMPORT_OK = True
except Exception:
    _IMPORT_OK = False

REPLY_TOOL = "mcp__plugin_discord_discord__reply"
EDIT_TOOL = "mcp__plugin_discord_discord__edit_message"


def _enabled():
    return os.environ.get("DISCORD_PROGRESS_ENABLED", "1") != "0"


def _recover_message_id(transcript_path, chat_id):
    """transcriptから同じchat_idの直近受信タグのmessage_idを復元する。"""
    rows = state.load_transcript_rows(transcript_path)
    idx = state.find_latest_inbound_index(rows)
    if idx is None:
        return None
    parsed = state.parse_channel_tag(state.text_of(rows[idx]))
    if parsed and str(parsed[0]) == str(chat_id):
        return parsed[1]
    return None


def _resolve_message_id(tool_name, tool_input, transcript_path, chat_id):
    """この呼び出しが本当にどのmessage_idのものかを決める。

    reply_toが使えればそれを優先(安い)。無ければ(edit_messageも含め)
    transcriptの直近受信タグから復元する。どちらも取れなければNone。
    状態が既にある場合はNoneや不一致を「既存状態には触ってはいけない」の
    合図として使う(A3のownership確認)。
    """
    if tool_name == REPLY_TOOL:
        reply_to = tool_input.get("reply_to")
        if reply_to:
            return reply_to
    return _recover_message_id(transcript_path, chat_id)


def main(payload=None):
    if not _IMPORT_OK:
        return
    if payload is None:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            return

    if not _enabled():
        return

    tool_name = payload.get("tool_name")
    if tool_name not in (REPLY_TOOL, EDIT_TOOL):
        return

    tool_input = payload.get("tool_input") or {}
    chat_id = tool_input.get("chat_id")
    if not chat_id:
        return

    if not state.is_delivered(tool_name, payload.get("tool_response")):
        return  # 失敗 or 未確認の呼び出しでは状態を進めない

    transcript_path = payload.get("transcript_path")
    existing = state.load(chat_id)

    if existing is None:
        # 新規。ensure_started自体がflockで二重作成を防ぐ(B1)
        message_id = _resolve_message_id(tool_name, tool_input, transcript_path, chat_id)
        state.ensure_started(chat_id, message_id)
    else:
        # A3: ownership確認。この呼び出しが既存状態と同じmessage_idのものだと
        # 確認できない限り、既存状態には一切触らない(壊さない・進めない)
        message_id = _resolve_message_id(tool_name, tool_input, transcript_path, chat_id)
        if not message_id:
            return  # どのturnの呼び出しか確認できない
        if str(message_id) != str(existing.get("message_id")):
            return  # 別turn(古いmessage_id)の状態。触らない

    # received→workingへの昇格は、ここまでの確認だけに頼らずflock内で
    # message_id一致を再確認してから行う(TOCTOU対策。確認と書き込みの間に
    # 別turnへ置き換わっている可能性を毎回ここで潰す)
    def _claim_working(current):
        if current is None:
            return None
        if message_id and current.get("message_id") != message_id:
            return None  # ロック取得までの間に別turnへ置き換わっていた
        if current.get("stage") != state.STAGE_RECEIVED:
            return None  # 既に他の呼び出しが進めた。何もしない(二重reactionを避ける)
        current["stage"] = state.STAGE_WORKING
        return current

    claimed = state.update(chat_id, _claim_working)
    if claimed is None:
        return

    if message_id:
        discord_rest.unreact(chat_id, message_id, "📨")
        discord_rest.react(chat_id, message_id, "▶")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
