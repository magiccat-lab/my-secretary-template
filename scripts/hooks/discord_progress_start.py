#!/usr/bin/env python3
"""UserPromptSubmit hook: Discordから来たターンの進行表示を早めに開始する(ベストエフォート)。

やること(見つかって DISCORD_PROGRESS_ENABLED != "0" の時だけ):
  1. promptの中のchannelタグから(chat_id, message_id)を取る
  2. 受信メッセージに📨をリアクション
  3. 状態が無ければstate.ensure_startedで新規作成し、editorを起動する
     (B1対策: 二重起動防止のflockはensure_started側で持つ)

注意: このhookがDiscord由来のchannel messageで本当に発火するかは未確認。
発火しなくても scripts/hooks/discord_progress_posttool.py (PostToolUse) が
最初のreply/edit_message成功時に同じ状態を作ってeditorも起動するので、
進行表示の正しさはこのhookに依存しない(📨が少し遅れて▶から始まるだけ)。

UserPromptSubmitのstdoutはモデルのcontextに注入されるため、何も出力しない。
失敗しても必ずexit 0(モデルのターンを止めない)。lib importが失敗しても
(requestsが無い等)ImportErrorを外に漏らさずno-opにする。
"""
import json
import os
import sys

try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from lib import discord_rest                     # noqa: E402
    from lib import discord_progress_state as state  # noqa: E402
    _IMPORT_OK = True
except Exception:
    _IMPORT_OK = False


def _enabled():
    return os.environ.get("DISCORD_PROGRESS_ENABLED", "1") != "0"


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

    prompt = payload.get("prompt") or ""
    parsed = state.parse_channel_tag(prompt)
    if not parsed:
        return
    chat_id, message_id = parsed

    discord_rest.react(chat_id, message_id, "📨")
    state.ensure_started(chat_id, message_id)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
