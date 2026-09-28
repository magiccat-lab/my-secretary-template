#!/usr/bin/env python3
"""Stop hook: Discord返信の配信確認 と 進行表示の後始末を1つにまとめたcoordinator。

移植元(my-claude)では、配信確認してblockするだけの単機能hookだった旧hookを、
Stopの並行実行競合(blockすべきターンを進行表示側だけ誤って配信済み扱いにする)を
避けるためこのhookへ統合した経緯がある。旧hook自体はこのtemplateには無い。

判定:
  直近の人間由来userメッセージがchannelタグを含まなければ何もしない(Discord外のターン)。
  含む場合、それ以降で同じchat_id宛のreply/edit_messageのtool_resultが
  state.is_delivered(tool_name, tool_result)でTrueになれば「配信済み」
  (is_error/isErrorがtrueでなく、本文に成功パターンがある場合のみ。1回失敗して
  再送で成功したケースも拾う)。

  配信済み                       → 状態のmessage_idが今回の受信メッセージと一致する時だけ
                                     📨/▶を外して✅、進行バブルを消して状態ファイルを消す。
                                     一致しない(古い別turnの状態)なら状態には触れず、
                                     受信メッセージへの✅だけ付ける(A3対策)。この一致確認は
                                     状態を変更・削除する直前にflock内で毎回やり直す
                                     (TOCTOU対策。REST呼び出しの間に別turnへ置き換わっても
                                     古いfinalizerがそのbubble/stateを壊さないようにするため)
  未配信 かつ DISCORD_REPLY_GUARD_ENABLED=0 → 差し戻さない。何もせず終わる
                                     (配信済みの場合の後始末はガードと無関係に動く)
  未配信 かつ stop_hook_activeでない → 差し戻すJSON(decision:block)を出す
  未配信 かつ stop_hook_active      → 配信済み扱いにしない。何もせず終わる
                                     (editorのMAX_MINUTES経過⚠️に任せる)

Print(decision:block時を除いて)なし、always exit 0。lib importが失敗しても
(requestsが無い等)ImportErrorを外に漏らさずno-opにする。discord_progress_stateは
標準ライブラリのみに依存するので、このimportが失敗するのはrequestsを使う
discord_rest側が壊れている場合くらいで、実運用ではまず起きない想定。
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

REPLY_TOOLS = (
    "mcp__plugin_discord_discord__reply",
    "mcp__plugin_discord_discord__edit_message",
)

BLOCK_REASON = (
    "Discordから来たメッセージなのに reply / edit_message を1度も呼んでいない。"
    "ターミナルへの地の文出力は相手に届かない（AGENT/AGENTS.md「Discord 返信ルール」）。"
    "いま書いた返答を mcp__plugin_discord_discord__reply で該当 chat_id へ送り直すこと。"
    "本当に返信が不要なメッセージなら、そのまま終了してよい（次の終了は素通しされる）。"
)


def _delivered_after(rows, start, chat_id):
    """start以降で、chat_id宛のreply/edit_messageが確認できる形で配信されたか。

    tool_use(id, name, input.chat_id) と、それに対応するtool_result(tool_use_id)を
    時系列に追い、state.is_deliveredがTrueになるtool_resultが1つでもあればTrue。
    未確認/失敗した呼び出しは無視して後続の再試行を探し続ける。
    """
    pending = {}  # tool_use_id -> tool_name
    for row in rows[start + 1:]:
        content = (row.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") in REPLY_TOOLS:
                tool_input = b.get("input") or {}
                if str(tool_input.get("chat_id")) == str(chat_id):
                    pending[b.get("id")] = b.get("name")
            elif b.get("type") == "tool_result":
                tuid = b.get("tool_use_id")
                if tuid in pending:
                    tool_name = pending[tuid]
                    if state.is_delivered(tool_name, b):
                        return True
                    pending.pop(tuid, None)
    return False


def _enabled():
    return os.environ.get("DISCORD_PROGRESS_ENABLED", "1") != "0"


def _guard_enabled():
    """0なら「reply未送信で終える」差し戻し(decision:block)を出さない。

    配信済みの場合の進行表示の後始末(_finalize)はこのフラグと無関係に動く。
    """
    return os.environ.get("DISCORD_REPLY_GUARD_ENABLED", "1") != "0"


def _finalize(chat_id, message_id):
    """message_idの受信に対応する状態だけを、ロック内で所有権を再確認しながら後始末する。

    TOCTOU対策: main()の入口でmessage_idの一致を確認しても、その後の
    unreact()等のREST呼び出しは時間がかかるので、その間に別turnへ状態が
    置き換わる余地がある(古いfinalizerが新しいbubble/stateを消してしまう事故)。
    そのため状態の変更・削除はすべて、その場でflockを取り直してmessage_id一致を
    再確認してから行う。一致しなければ何も変更・削除せず、受信メッセージへの
    ✅だけ付けて終わる。
    """
    def _claim_done(current):
        if current is None:
            return None
        if current.get("message_id") != message_id:
            return None  # 置き換わっていた。触らない
        current["stage"] = state.STAGE_DONE
        return current

    done_state = state.update(chat_id, _claim_done)  # editorも次loopでstage==doneを見て自分で消せる

    if done_state is None:
        # 自分の状態は既に無い/別turnに置き換わっている。何も削除・変更せず、
        # 受信メッセージへのreactionだけは(常に安全なので)行う
        discord_rest.react(chat_id, message_id, "✅")
        return

    discord_rest.unreact(chat_id, message_id, "📨")
    discord_rest.unreact(chat_id, message_id, "▶")
    discord_rest.react(chat_id, message_id, "✅")

    pmid = done_state.get("progress_message_id")  # _claim_doneの中でロック付きで読んだ値
    if pmid:
        discord_rest.delete(chat_id, pmid)  # 直接も消す(editorが既に落ちている場合の保険。冪等)

    state.clear_if_owned(chat_id, message_id)  # 消す直前にもmessage_id一致を再確認する


def main(payload=None):
    if not _IMPORT_OK:
        return
    if payload is None:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            return

    rows = state.load_transcript_rows(payload.get("transcript_path"))
    if not rows:
        return

    start = state.find_latest_inbound_index(rows)
    if start is None:
        return

    parsed = state.parse_channel_tag(state.text_of(rows[start]))
    if not parsed:
        return
    chat_id, message_id = parsed

    delivered = _delivered_after(rows, start, chat_id)

    if not delivered:
        if _guard_enabled() and not payload.get("stop_hook_active"):
            print(json.dumps({"decision": "block", "reason": BLOCK_REASON}, ensure_ascii=False))
        return

    # ここから先は進行表示の後始末(配信は確定している)。フラグで丸ごと無効化できる
    if not _enabled():
        return
    if not message_id:
        return

    # 所有権の確認(message_id一致)は_finalize内でロックを取った直後にもう一度
    # 行う(TOCTOU対策)。ここで事前チェックしても後続のREST呼び出しの間に
    # 状態が変わりうるので、事前チェックはせず常に_finalizeへ任せる
    _finalize(chat_id, message_id)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
