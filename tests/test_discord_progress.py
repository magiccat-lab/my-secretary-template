#!/usr/bin/env python3
"""Discord進行状況表示(2026-09-21導入、09-21 codexレビュー分の修正込み)の検証。

ネットワーク不要。discord_rest の関数をフェイクに差し替えて、実際のDiscord APIは
一切叩かない。

実行:
  python3 -m unittest discover -s tests -p 'test_discord_progress.py'
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from io import StringIO
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
for p in (
    os.path.join(ROOT, "scripts"),
    os.path.join(ROOT, "scripts", "hooks"),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib import discord_rest                       # noqa: E402
from lib import discord_progress_state as state     # noqa: E402
import discord_progress_start as start_hook         # noqa: E402
import discord_progress_posttool as posttool_hook   # noqa: E402
import discord_turn_end as turn_end_hook            # noqa: E402
import discord_progress_editor as editor            # noqa: E402


REPLY_TOOL = "mcp__plugin_discord_discord__reply"
EDIT_TOOL = "mcp__plugin_discord_discord__edit_message"


def channel_tag(chat_id, message_id, body="お願い", source="plugin:discord:discord"):
    return (f'<channel source="{source}" chat_id="{chat_id}" message_id="{message_id}" '
            f'user="user1" ts="2026-09-21T00:00:00Z">{body}</channel>')


def reply_success_text(msg_id="1"):
    """プラグインがreply成功時に返す想定のテキスト。"""
    return f"sent (id: {msg_id})"


def edit_success_text(msg_id="1"):
    """プラグインがedit_message成功時に返す想定のテキスト。"""
    return f"edited (id: {msg_id})"


def failure_text(reason="unknown error"):
    return f"reply failed: {reason}"


def row_user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def row_tool_use(tool_use_id, name, tool_input):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_use_id, "name": name, "input": tool_input}
    ]}}


def row_tool_result(tool_use_id, text, is_error=None):
    block = {"type": "tool_result", "tool_use_id": tool_use_id,
             "content": [{"type": "text", "text": text}]}
    if is_error is not None:
        block["is_error"] = is_error
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def write_transcript(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


class FakeRest:
    """discord_rest.react/unreact/post/edit/deleteの記録付きフェイク。"""

    def __init__(self):
        self.calls = []
        self._next_id = 9000

    def react(self, chat_id, message_id, emoji):
        self.calls.append(("react", str(chat_id), str(message_id), emoji))
        return True

    def unreact(self, chat_id, message_id, emoji):
        self.calls.append(("unreact", str(chat_id), str(message_id), emoji))
        return True

    def post(self, chat_id, text):
        self._next_id += 1
        mid = str(self._next_id)
        self.calls.append(("post", str(chat_id), text))
        return mid

    def edit(self, chat_id, message_id, text):
        self.calls.append(("edit", str(chat_id), str(message_id), text))
        return True

    def delete(self, chat_id, message_id):
        self.calls.append(("delete", str(chat_id), str(message_id)))
        return True


class RestPatchedTestCase(unittest.TestCase):
    """SECRETARY_DIRを一時dirへ差し替え、discord_restをフェイクにし、editor起動も止める。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="dp_test_")
        self._old_secretary_dir = os.environ.get("SECRETARY_DIR")
        os.environ["SECRETARY_DIR"] = self.tmpdir

        self.fake = FakeRest()
        self._orig_rest = {}
        for name in ("react", "unreact", "post", "edit", "delete"):
            self._orig_rest[name] = getattr(discord_rest, name)
            setattr(discord_rest, name, getattr(self.fake, name))

        self._orig_spawn = state.spawn_editor
        self.spawned = []

        def fake_spawn(chat_id, message_id):
            self.spawned.append((str(chat_id), message_id))
            return 424242  # 実プロセスは起動しない

        state.spawn_editor = fake_spawn

    def tearDown(self):
        for name, fn in self._orig_rest.items():
            setattr(discord_rest, name, fn)
        state.spawn_editor = self._orig_spawn
        if self._old_secretary_dir is None:
            os.environ.pop("SECRETARY_DIR", None)
        else:
            os.environ["SECRETARY_DIR"] = self._old_secretary_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_transcript(self, rows, name="transcript.jsonl"):
        return write_transcript(os.path.join(self.tmpdir, name), rows)


# --- parse_channel_tag -------------------------------------------------------

class TestParseChannelTag(unittest.TestCase):
    def test_plugin_discord_discord_spelling(self):
        text = channel_tag("100000000000000111", "100000000000000222", source="plugin:discord:discord")
        self.assertEqual(state.parse_channel_tag(text), ("100000000000000111", "100000000000000222"))

    def test_short_discord_spelling(self):
        text = channel_tag("100000000000000333", "100000000000000444", source="discord")
        self.assertEqual(state.parse_channel_tag(text), ("100000000000000333", "100000000000000444"))

    def test_attribute_order_independent(self):
        text = ('<channel chat_id="100000000000000555" message_id="100000000000000666" source="discord" '
                'ts="t" user="user1">hi</channel>')
        self.assertEqual(state.parse_channel_tag(text), ("100000000000000555", "100000000000000666"))

    def test_no_tag_returns_none(self):
        self.assertIsNone(state.parse_channel_tag("ただの雑談だよ"))

    def test_wrong_source_returns_none(self):
        text = '<channel source="plugin:slack:slack" chat_id="1" message_id="2">x</channel>'
        self.assertIsNone(state.parse_channel_tag(text))

    def test_empty_text_returns_none(self):
        self.assertIsNone(state.parse_channel_tag(""))
        self.assertIsNone(state.parse_channel_tag(None))


# --- 状態ファイルI/O ----------------------------------------------------------

class TestStateFileIO(RestPatchedTestCase):
    def test_save_load_roundtrip(self):
        st = {"message_id": "1", "started_at": 100.0, "stage": state.STAGE_RECEIVED,
              "progress_message_id": None, "editor_pid": None}
        state.save("chat-a", st)
        self.assertEqual(state.load("chat-a"), st)

    def test_load_missing_returns_none(self):
        self.assertIsNone(state.load("no-such-chat"))

    def test_clear_is_idempotent(self):
        state.save("chat-b", {"stage": state.STAGE_DONE})
        state.clear("chat-b")
        self.assertIsNone(state.load("chat-b"))
        state.clear("chat-b")  # 2回目もエラーにならない

    def test_atomic_write_leaves_no_tmp_file(self):
        state.save("chat-c", {"stage": state.STAGE_WORKING})
        d = os.path.join(self.tmpdir, "data", "discord_progress")
        leftovers = [f for f in os.listdir(d) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_pid_alive_true_for_self(self):
        self.assertTrue(state.pid_alive(os.getpid()))

    def test_pid_alive_false_for_bogus_pid(self):
        self.assertFalse(state.pid_alive(999999999))

    def test_pid_alive_false_for_none(self):
        self.assertFalse(state.pid_alive(None))

    def test_update_increments_generation_each_write(self):
        state.update("chat-gen", lambda cur: {"stage": state.STAGE_RECEIVED})
        state.update("chat-gen", lambda cur: {**cur, "stage": state.STAGE_WORKING})
        st = state.load("chat-gen")
        self.assertEqual(st["generation"], 2)
        self.assertEqual(st["stage"], state.STAGE_WORKING)

    def test_update_returns_none_and_writes_nothing_when_mutate_aborts(self):
        state.save("chat-gen2", {"stage": state.STAGE_RECEIVED, "generation": 1})
        result = state.update("chat-gen2", lambda cur: None)
        self.assertIsNone(result)
        self.assertEqual(state.load("chat-gen2"), {"stage": state.STAGE_RECEIVED, "generation": 1})


# --- ensure_started (B1: 二重editor起動防止) ----------------------------------

class TestEnsureStarted(RestPatchedTestCase):
    def test_creates_fresh_state_and_spawns_editor(self):
        st = state.ensure_started("chat-x", "msg-x")
        self.assertEqual(st["stage"], state.STAGE_RECEIVED)
        self.assertEqual(st["message_id"], "msg-x")
        self.assertEqual(st["editor_pid"], 424242)
        self.assertEqual(self.spawned, [("chat-x", "msg-x")])

    def test_second_call_reuses_existing_state_without_spawning_again(self):
        first = state.ensure_started("chat-y", "msg-y")
        second = state.ensure_started("chat-y", "msg-y")
        self.assertEqual(first, second)
        self.assertEqual(len(self.spawned), 1)  # 1回しか起動していない


# --- 配信成否の判定(A1) -------------------------------------------------------

class TestIsDelivered(unittest.TestCase):
    def test_sent_pattern_is_delivered(self):
        obj = {"content": [{"type": "text", "text": "sent (id: 1)"}]}
        self.assertTrue(state.is_delivered(REPLY_TOOL, obj))

    def test_edited_pattern_is_delivered_for_edit_tool(self):
        obj = {"content": [{"type": "text", "text": "edited (id: 1)"}]}
        self.assertTrue(state.is_delivered(EDIT_TOOL, obj))

    def test_sent_pattern_does_not_count_for_edit_tool(self):
        obj = {"content": [{"type": "text", "text": "sent (id: 1)"}]}
        self.assertFalse(state.is_delivered(EDIT_TOOL, obj))

    def test_is_error_true_overrides_success_looking_text(self):
        obj = {"is_error": True, "content": [{"type": "text", "text": "sent (id: 1)"}]}
        self.assertFalse(state.is_delivered(REPLY_TOOL, obj))

    def test_is_error_false_does_not_override_failed_text(self):
        # codexレビュー: is_error:falseだけでは成功と認めない。本文の成功パターン必須
        obj = {"is_error": False, "content": [{"type": "text", "text": failure_text()}]}
        self.assertFalse(state.is_delivered(REPLY_TOOL, obj))

    def test_isError_camel_case_key_is_recognized(self):
        obj = {"isError": True, "content": [{"type": "text", "text": "sent (id: 1)"}]}
        self.assertFalse(state.is_delivered(REPLY_TOOL, obj))

    def test_none_is_not_delivered(self):
        self.assertFalse(state.is_delivered(REPLY_TOOL, None))

    def test_empty_text_is_not_delivered(self):
        self.assertFalse(state.is_delivered(REPLY_TOOL, {"content": ""}))

    def test_plain_string_with_success_pattern_is_delivered(self):
        self.assertTrue(state.is_delivered(REPLY_TOOL, "sent (id: 1)"))

    def test_unknown_tool_name_is_not_delivered(self):
        obj = {"content": [{"type": "text", "text": "sent (id: 1)"}]}
        self.assertFalse(state.is_delivered("some_other_tool", obj))


# --- トークン読み込み(B2) -----------------------------------------------------

class TestLoadToken(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="dp_token_test_")
        self._saved_env = {k: os.environ.get(k) for k in
                            ("DISCORD_BOT_TOKEN", "DISCORD_ENV_FILE", "DISCORD_STATE_DIR")}
        for k in self._saved_env:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_env_file(self, name, token):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"DISCORD_BOT_TOKEN={token}\n")
        return path

    def test_env_var_wins_over_everything(self):
        os.environ["DISCORD_BOT_TOKEN"] = "from-env-var"
        os.environ["DISCORD_ENV_FILE"] = self._write_env_file("a.env", "from-env-file")
        self.assertEqual(discord_rest.load_token(), "from-env-var")

    def test_discord_env_file_wins_over_state_dir(self):
        os.environ["DISCORD_ENV_FILE"] = self._write_env_file("a.env", "from-env-file")
        state_dir = os.path.join(self.tmpdir, "state")
        os.makedirs(state_dir)
        with open(os.path.join(state_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("DISCORD_BOT_TOKEN=from-state-dir\n")
        os.environ["DISCORD_STATE_DIR"] = state_dir
        self.assertEqual(discord_rest.load_token(), "from-env-file")

    def test_state_dir_used_when_env_file_unset(self):
        """DISCORD_ENV_FILE未設定でも$DISCORD_STATE_DIR/.envを読む(複数bot使い分け相当)。"""
        state_dir = os.path.join(self.tmpdir, "alt-session")
        os.makedirs(state_dir)
        with open(os.path.join(state_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("DISCORD_BOT_TOKEN=alt-session-token\n")
        os.environ["DISCORD_STATE_DIR"] = state_dir
        self.assertEqual(discord_rest.load_token(), "alt-session-token")


# --- start -> posttool -> turn_end の状態遷移 ---------------------------------

class TestStartPosttoolTurnEndFlow(RestPatchedTestCase):
    def test_start_reacts_received_and_saves_state(self):
        prompt = channel_tag("100000000000000111", "100000000000000222")
        start_hook.main({"prompt": prompt})

        st = state.load("100000000000000111")
        self.assertEqual(st["stage"], state.STAGE_RECEIVED)
        self.assertEqual(st["message_id"], "100000000000000222")
        self.assertIn(("react", "100000000000000111", "100000000000000222", "📨"), self.fake.calls)
        self.assertEqual(self.spawned, [("100000000000000111", "100000000000000222")])

    def test_start_noop_without_channel_tag(self):
        start_hook.main({"prompt": "ただのひとりごと"})
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.spawned, [])

    def test_start_disabled_via_env(self):
        os.environ["DISCORD_PROGRESS_ENABLED"] = "0"
        try:
            start_hook.main({"prompt": channel_tag("1", "2")})
        finally:
            os.environ.pop("DISCORD_PROGRESS_ENABLED", None)
        self.assertEqual(self.fake.calls, [])
        self.assertIsNone(state.load("1"))

    def test_posttool_switches_received_to_working_on_success(self):
        start_hook.main({"prompt": channel_tag("100000000000000111", "100000000000000222")})
        path = self.write_transcript([row_user(channel_tag("100000000000000111", "100000000000000222"))])
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": "100000000000000111", "text": "見てくる"},
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("100000000000000500")}]},
            "transcript_path": path,  # reply_to無しなのでtranscriptから所有権を確認する
        })
        st = state.load("100000000000000111")
        self.assertEqual(st["stage"], state.STAGE_WORKING)
        self.assertIn(("unreact", "100000000000000111", "100000000000000222", "📨"), self.fake.calls)
        self.assertIn(("react", "100000000000000111", "100000000000000222", "▶"), self.fake.calls)

    def test_posttool_ignores_failed_tool_response(self):
        start_hook.main({"prompt": channel_tag("100000000000000111", "100000000000000222")})
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": "100000000000000111", "text": "見てくる"},
            "tool_response": {"content": [{"type": "text", "text": failure_text("rate limited")}]},
        })
        st = state.load("100000000000000111")
        self.assertEqual(st["stage"], state.STAGE_RECEIVED)  # 進んでいない
        self.assertNotIn(("react", "100000000000000111", "100000000000000222", "▶"), self.fake.calls)

    def test_posttool_ignores_is_error_false_with_failed_text(self):
        """A1: is_error:falseだけでは成功扱いしない(本文の成功パターンが必須)。"""
        start_hook.main({"prompt": channel_tag("100000000000000111", "100000000000000222")})
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": "100000000000000111", "text": "見てくる"},
            "tool_response": {"is_error": False,
                               "content": [{"type": "text", "text": failure_text()}]},
        })
        st = state.load("100000000000000111")
        self.assertEqual(st["stage"], state.STAGE_RECEIVED)

    def test_posttool_ignores_none_tool_response(self):
        start_hook.main({"prompt": channel_tag("100000000000000111", "100000000000000222")})
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": "100000000000000111", "text": "見てくる"},
            "tool_response": None,
        })
        st = state.load("100000000000000111")
        self.assertEqual(st["stage"], state.STAGE_RECEIVED)

    def test_turn_end_finalizes_and_clears_state(self):
        start_hook.main({"prompt": channel_tag("100000000000000111", "100000000000000222")})
        rows = [
            row_user(channel_tag("100000000000000111", "100000000000000222")),
            row_tool_use("tu1", REPLY_TOOL, {"chat_id": "100000000000000111", "text": "見てくる"}),
            row_tool_result("tu1", reply_success_text("100000000000000500")),
        ]
        path = self.write_transcript(rows)
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": "100000000000000111", "text": "見てくる"},
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("100000000000000500")}]},
            "transcript_path": path,  # reply_to無しなのでtranscriptから所有権を確認する
        })
        self.assertEqual(state.load("100000000000000111")["stage"], state.STAGE_WORKING)  # posttoolがここまで進めた

        turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})

        self.assertIsNone(state.load("100000000000000111"))
        self.assertIn(("react", "100000000000000111", "100000000000000222", "✅"), self.fake.calls)
        self.assertIn(("unreact", "100000000000000111", "100000000000000222", "▶"), self.fake.calls)

    def test_turn_end_blocks_when_not_delivered(self):
        rows = [row_user(channel_tag("100000000000000030", "100000000000000040"))]  # replyが1回も無い
        path = self.write_transcript(rows)

        out = StringIO()
        with redirect_stdout(out):
            turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})

        printed = json.loads(out.getvalue())
        self.assertEqual(printed["decision"], "block")

    def test_turn_end_guard_disabled_does_not_block(self):
        """DISCORD_REPLY_GUARD_ENABLED=0なら未配信でも差し戻さない。"""
        rows = [row_user(channel_tag("100000000000000030", "100000000000000040"))]  # replyが1回も無い
        path = self.write_transcript(rows)

        os.environ["DISCORD_REPLY_GUARD_ENABLED"] = "0"
        try:
            out = StringIO()
            with redirect_stdout(out):
                turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})
        finally:
            os.environ.pop("DISCORD_REPLY_GUARD_ENABLED", None)

        self.assertEqual(out.getvalue(), "")  # blockのJSONを出していない

    def test_turn_end_blocks_when_result_text_lacks_success_pattern(self):
        """A1: 「failedを含まない」だけでは配信済みと認めない(旧ロジックの穴)。"""
        rows = [
            row_user(channel_tag("100000000000000030", "100000000000000040")),
            row_tool_use("tu1", REPLY_TOOL, {"chat_id": "100000000000000030", "text": "見てくる"}),
            row_tool_result("tu1", "たぶん送った(たぶん)"),  # successパターンを含まない
        ]
        path = self.write_transcript(rows)
        out = StringIO()
        with redirect_stdout(out):
            turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["decision"], "block")

    def test_turn_end_stop_hook_active_does_not_finalize(self):
        rows = [row_user(channel_tag("100000000000000030", "100000000000000040"))]
        path = self.write_transcript(rows)
        out = StringIO()
        with redirect_stdout(out):
            turn_end_hook.main({"transcript_path": path, "stop_hook_active": True})
        self.assertEqual(out.getvalue(), "")   # blockも出さない
        self.assertEqual(self.fake.calls, [])  # 配信済み扱いにもしない
        self.assertIsNone(state.load("100000000000000030"))

    def test_turn_end_delivered_after_one_failed_retry(self):
        rows = [
            row_user(channel_tag("100000000000000030", "100000000000000040")),
            row_tool_use("tu1", REPLY_TOOL, {"chat_id": "100000000000000030", "text": "見てくる"}),
            row_tool_result("tu1", failure_text("rate limited")),
            row_tool_use("tu2", REPLY_TOOL, {"chat_id": "100000000000000030", "text": "見てくる(再送)"}),
            row_tool_result("tu2", reply_success_text("100000000000000999")),
        ]
        path = self.write_transcript(rows)
        out = StringIO()
        with redirect_stdout(out):
            turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})
        self.assertEqual(out.getvalue(), "")  # blockしていない = 配信済みと判定
        self.assertIn(("react", "100000000000000030", "100000000000000040", "✅"), self.fake.calls)

    def test_turn_end_ignores_foreign_state_with_different_message_id(self):
        """A3: 状態のmessage_idが今回の受信メッセージと違うなら、その状態は触らない。"""
        chat_id = "100000000000000042"
        state.save(chat_id, {
            "message_id": "OLD", "started_at": 1.0, "stage": state.STAGE_WORKING,
            "progress_message_id": "bubble-1", "editor_pid": os.getpid(), "generation": 1,
        })
        rows = [
            row_user(channel_tag(chat_id, "NEW")),
            row_tool_use("tu1", REPLY_TOOL, {"chat_id": chat_id, "text": "見てくる"}),
            row_tool_result("tu1", reply_success_text("1")),
        ]
        path = self.write_transcript(rows)
        turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})

        self.assertIn(("react", chat_id, "NEW", "✅"), self.fake.calls)
        # 古いstate(別turn)は触っていない: 消えていない・bubbleも消していない
        remaining = state.load(chat_id)
        self.assertIsNotNone(remaining)
        self.assertEqual(remaining["message_id"], "OLD")
        self.assertNotIn(("delete", chat_id, "bubble-1"), self.fake.calls)
        self.assertNotIn(("unreact", chat_id, "OLD", "📨"), self.fake.calls)

    def test_turn_end_finalize_does_not_clobber_newer_turn_replacing_state_mid_flight(self):
        """TOCTOU対策: unreact()呼び出しの最中に別turnがstateを置き換えても、

        古いfinalizerはそのbubble/stateを壊さない(削除の直前にownershipを再確認する)。
        """
        chat_id = "100000000000000077"
        old_message_id, new_message_id = "OLD", "NEW"
        state.save(chat_id, {
            "message_id": old_message_id, "started_at": 1.0, "stage": state.STAGE_WORKING,
            "progress_message_id": "old-bubble", "editor_pid": os.getpid(), "generation": 1,
        })

        orig_unreact = discord_rest.unreact

        def fake_unreact(cid, mid, emoji):
            if emoji == "📨":
                # unreact()の最中に「別turn(NEW)がstateを置き換えた」ことを模擬する
                state.save(cid, {
                    "message_id": new_message_id, "started_at": 2.0, "stage": state.STAGE_WORKING,
                    "progress_message_id": "new-bubble", "editor_pid": os.getpid(), "generation": 1,
                })
            return orig_unreact(cid, mid, emoji)

        discord_rest.unreact = fake_unreact

        rows = [
            row_user(channel_tag(chat_id, old_message_id)),
            row_tool_use("tu1", REPLY_TOOL, {"chat_id": chat_id, "text": "見てくる"}),
            row_tool_result("tu1", reply_success_text("1")),
        ]
        path = self.write_transcript(rows)
        turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})

        # OLD自身のbubbleは消してよい(自分の物。_claim_doneがロック内で読んだ値)
        self.assertIn(("delete", chat_id, "old-bubble"), self.fake.calls)
        # だがNEWの状態・bubbleは無事残っている(消えていない・上書きされていない)
        remaining = state.load(chat_id)
        self.assertIsNotNone(remaining)
        self.assertEqual(remaining["message_id"], new_message_id)
        self.assertEqual(remaining["progress_message_id"], "new-bubble")
        self.assertNotIn(("delete", chat_id, "new-bubble"), self.fake.calls)

    def test_posttool_and_turn_end_work_without_userpromptsubmit(self):
        """UserPromptSubmitが発火しなくても、PostToolUse+Stopだけで一連の状態遷移が完結する。"""
        chat_id, message_id = "100000000000000777", "100000000000000888"
        # start_hook.main は一度も呼ばない
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": chat_id, "text": "見てくる", "reply_to": message_id},
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("1")}]},
        })
        st = state.load(chat_id)
        self.assertIsNotNone(st, "posttoolだけで状態が新規作成されているはず")
        self.assertEqual(st["stage"], state.STAGE_WORKING)
        self.assertEqual(st["message_id"], message_id)
        self.assertEqual(self.spawned, [(chat_id, message_id)])  # editorもここで起動
        self.assertIn(("react", chat_id, message_id, "▶"), self.fake.calls)

        rows = [
            row_user(channel_tag(chat_id, message_id)),
            row_tool_use("tu1", REPLY_TOOL, {"chat_id": chat_id, "text": "見てくる"}),
            row_tool_result("tu1", reply_success_text("1")),
        ]
        path = self.write_transcript(rows)
        turn_end_hook.main({"transcript_path": path, "stop_hook_active": False})
        self.assertIsNone(state.load(chat_id))
        self.assertIn(("react", chat_id, message_id, "✅"), self.fake.calls)

    def test_posttool_recovers_message_id_from_transcript_when_no_reply_to(self):
        chat_id, message_id = "100000000000000333", "100000000000000444"
        rows = [row_user(channel_tag(chat_id, message_id, body="reply_to無しで送って"))]
        path = self.write_transcript(rows)
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": chat_id, "text": "見てくる"},  # reply_to無し
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("2")}]},
            "transcript_path": path,
        })
        st = state.load(chat_id)
        self.assertEqual(st["message_id"], message_id)

    def test_posttool_skips_reactions_when_message_id_unknown(self):
        chat_id = "100000000000000555"
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": chat_id, "text": "見てくる"},  # reply_to無し
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("3")}]},
            # transcript_pathも無いのでmessage_idは最後まで不明
        })
        st = state.load(chat_id)
        self.assertIsNone(st["message_id"])
        self.assertEqual(st["stage"], state.STAGE_WORKING)
        react_calls = [c for c in self.fake.calls if c[0] in ("react", "unreact")]
        self.assertEqual(react_calls, [])  # message_id不明なのでreaction系は無し
        self.assertEqual(self.spawned, [(chat_id, None)])  # バブルの方は起動する

    def test_posttool_ignores_foreign_state_when_reply_to_mismatches(self):
        """A3: 既存stateのmessage_idとreply_toが食い違うなら、その状態は触らない。"""
        chat_id = "100000000000000042"
        state.save(chat_id, {
            "message_id": "OLD", "started_at": 1.0, "stage": state.STAGE_RECEIVED,
            "progress_message_id": None, "editor_pid": os.getpid(), "generation": 1,
        })
        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": chat_id, "text": "見てくる", "reply_to": "NEW"},
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("1")}]},
        })
        st = state.load(chat_id)
        self.assertEqual(st["message_id"], "OLD")             # 古い状態のまま
        self.assertEqual(st["stage"], state.STAGE_RECEIVED)   # 進めていない
        self.assertEqual(self.fake.calls, [])                 # reactionも一切していない

    def test_posttool_without_reply_to_does_not_clobber_state_for_different_transcript_message(self):
        """TOCTOU対策: reply_to無しでも、transcriptの実際の受信message_idが既存stateと

        食い違うなら既存stateには触れない(以前はreply_to無し=確認自体をskipしていた穴。
        edit_messageは常にこの経路を通る)。
        """
        chat_id = "100000000000000088"
        state.save(chat_id, {
            "message_id": "OLD", "started_at": 1.0, "stage": state.STAGE_RECEIVED,
            "progress_message_id": None, "editor_pid": os.getpid(), "generation": 1,
        })
        # transcriptは別の(新しい)message_idの受信を示している
        path = self.write_transcript([row_user(channel_tag(chat_id, "NEW"))])

        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": chat_id, "text": "見てくる"},  # reply_to無し
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("1")}]},
            "transcript_path": path,
        })

        st = state.load(chat_id)
        self.assertEqual(st["message_id"], "OLD")             # 触られていない
        self.assertEqual(st["stage"], state.STAGE_RECEIVED)   # 進めていない
        self.assertEqual(self.fake.calls, [])                 # reactionもしていない

    def test_posttool_without_reply_to_or_transcript_does_not_touch_existing_state(self):
        """reply_toもtranscriptも無ければ、既存stateがあっても一切触らない。"""
        chat_id = "100000000000000089"
        original = {
            "message_id": "OLD", "started_at": 1.0, "stage": state.STAGE_RECEIVED,
            "progress_message_id": None, "editor_pid": os.getpid(), "generation": 1,
        }
        state.save(chat_id, dict(original))

        posttool_hook.main({
            "tool_name": REPLY_TOOL,
            "tool_input": {"chat_id": chat_id, "text": "見てくる"},  # reply_to無し
            "tool_response": {"content": [{"type": "text", "text": reply_success_text("1")}]},
            # transcript_pathも無い
        })

        self.assertEqual(state.load(chat_id), original)
        self.assertEqual(self.fake.calls, [])

    def test_posttool_edit_message_without_reply_to_advances_same_turn_via_transcript(self):
        """edit_messageにはreply_toが無いので、常にtranscriptで所有権を確認して昇格する。"""
        chat_id, message_id = "100000000000000090", "100000000000000900"
        state.save(chat_id, {
            "message_id": message_id, "started_at": 1.0, "stage": state.STAGE_RECEIVED,
            "progress_message_id": None, "editor_pid": os.getpid(), "generation": 1,
        })
        path = self.write_transcript([row_user(channel_tag(chat_id, message_id))])
        posttool_hook.main({
            "tool_name": EDIT_TOOL,
            "tool_input": {"chat_id": chat_id, "message_id": "bot-own-msg-id", "text": "更新"},
            "tool_response": {"content": [{"type": "text", "text": edit_success_text("1")}]},
            "transcript_path": path,
        })
        st = state.load(chat_id)
        self.assertEqual(st["stage"], state.STAGE_WORKING)
        self.assertIn(("react", chat_id, message_id, "▶"), self.fake.calls)


# --- editorのフォーマット・孤児化対策・排他制御のヘルパー ------------------------

class TestEditorHelpers(RestPatchedTestCase):
    def test_progress_text_zero_minutes(self):
        self.assertEqual(editor.format_progress_text("サンプル", 0), "🔄 サンプルが作業中 (経過 0 分)")

    def test_progress_text_elapsed(self):
        self.assertEqual(editor.format_progress_text("サンプル", 12), "🔄 サンプルが作業中 (経過 12 分)")

    def test_progress_text_without_name(self):
        """SECRETARY_NAME未設定(空文字)なら名前を出さない。"""
        self.assertEqual(editor.format_progress_text("", 5), "🔄 作業中 (経過 5 分)")

    def test_stalled_text(self):
        self.assertEqual(editor.format_stalled_text(90), "⚠️ 応答が止まっています (経過 90 分)")

    def test_should_continue_true_for_own_pid(self):
        st = {"stage": state.STAGE_WORKING, "editor_pid": os.getpid()}
        self.assertTrue(editor._should_continue(st, os.getpid()))

    def test_should_continue_false_when_done(self):
        st = {"stage": state.STAGE_DONE, "editor_pid": os.getpid()}
        self.assertFalse(editor._should_continue(st, os.getpid()))

    def test_should_continue_false_when_superseded(self):
        st = {"stage": state.STAGE_WORKING, "editor_pid": 999999}
        self.assertFalse(editor._should_continue(st, os.getpid()))

    def test_should_continue_false_when_state_missing(self):
        self.assertFalse(editor._should_continue(None, os.getpid()))

    def test_other_editor_alive_true_when_alive_and_different(self):
        st = {"editor_pid": os.getpid()}
        self.assertTrue(editor._other_editor_alive(st, os.getpid() + 1))

    def test_other_editor_alive_false_when_same_pid(self):
        st = {"editor_pid": os.getpid()}
        self.assertFalse(editor._other_editor_alive(st, os.getpid()))

    def test_handle_timeout_clears_state_and_reacts_warning(self):
        state.save("chat-timeout", {"stage": state.STAGE_WORKING, "editor_pid": os.getpid()})
        editor._handle_timeout("chat-timeout", "100000000000000222", "100000000000000999", 90)
        self.assertIsNone(state.load("chat-timeout"))  # 孤児化対策: 消える
        self.assertIn(("edit", "chat-timeout", "100000000000000999", "⚠️ 応答が止まっています (経過 90 分)"),
                       self.fake.calls)
        self.assertIn(("react", "chat-timeout", "100000000000000222", "⚠️"), self.fake.calls)

    def test_handle_timeout_skips_reaction_when_message_id_unknown(self):
        state.save("chat-timeout2", {"stage": state.STAGE_WORKING, "editor_pid": os.getpid()})
        editor._handle_timeout("chat-timeout2", None, "100000000000000999", 90)
        react_calls = [c for c in self.fake.calls if c[0] == "react"]
        self.assertEqual(react_calls, [])
        self.assertIsNone(state.load("chat-timeout2"))

    def test_editor_detects_concurrent_clear_during_post_and_deletes_bubble(self):
        """A2: post()中にStop相当がstateを消したら、投稿済みbubbleを消して終了し、

        古いスナップショットを書き戻してstateを復活させない。
        """
        chat_id, message_id = "100000000000000999", "100000000000001000"
        state.save(chat_id, {
            "message_id": message_id, "started_at": time.time(), "stage": state.STAGE_RECEIVED,
            "progress_message_id": None, "editor_pid": os.getpid(), "generation": 1,
        })

        def fake_post(cid, text):
            # post()の最中に別プロセス(Stop hook相当)がstateを消したと想定する
            state.clear(cid)
            self.fake.calls.append(("post", str(cid), text))
            return "resurrect-bubble-id"

        discord_rest.post = fake_post

        os.environ["DISCORD_PROGRESS_FIRST_DELAY_SEC"] = "0"
        old_argv = sys.argv
        sys.argv = ["discord_progress_editor.py", chat_id, message_id]
        try:
            editor.main()
        finally:
            sys.argv = old_argv
            os.environ.pop("DISCORD_PROGRESS_FIRST_DELAY_SEC", None)

        self.assertIn(("delete", chat_id, "resurrect-bubble-id"), self.fake.calls)
        self.assertIsNone(state.load(chat_id))  # 消えたままで復活していない


# --- .claude/settings.json ---------------------------------------------------

class TestClaudeSettingsJson(unittest.TestCase):
    """リポジトリ同梱の.claude/settings.jsonが進行表示3hookを配線しているか。

    移植元は~/.claude/settings.jsonへ動的に書き込むスクリプトを使っていたが、
    このtemplateでは使わない。start_server.shが~/secretaryをcwdにして
    Claude Codeを起動するので、repo同梱のproject settingsがそのまま効く。
    """

    EXPECTED_MATCHER = "mcp__plugin_discord_discord__reply|mcp__plugin_discord_discord__edit_message"

    @classmethod
    def setUpClass(cls):
        settings_path = os.path.join(ROOT, ".claude", "settings.json")
        with open(settings_path, encoding="utf-8") as f:
            raw = f.read()
        cls.data = json.loads(raw)  # JSONとして読めることの確認を兼ねる

    def _command_of(self, event):
        group = self.data["hooks"][event][0]
        return group["hooks"][0]["command"]

    def test_hooks_key_present(self):
        self.assertIn("hooks", self.data)

    def test_user_prompt_submit_runs_start_hook(self):
        self.assertIn("discord_progress_start.py", self._command_of("UserPromptSubmit"))

    def test_posttool_runs_posttool_hook(self):
        self.assertIn("discord_progress_posttool.py", self._command_of("PostToolUse"))

    def test_stop_runs_turn_end_hook(self):
        self.assertIn("discord_turn_end.py", self._command_of("Stop"))

    def test_posttool_matcher_is_reply_or_edit_message(self):
        group = self.data["hooks"]["PostToolUse"][0]
        self.assertEqual(group.get("matcher"), self.EXPECTED_MATCHER)

    def test_all_three_commands_use_claude_project_dir(self):
        for event in ("UserPromptSubmit", "PostToolUse", "Stop"):
            self.assertIn("$CLAUDE_PROJECT_DIR", self._command_of(event))


if __name__ == "__main__":
    unittest.main()
