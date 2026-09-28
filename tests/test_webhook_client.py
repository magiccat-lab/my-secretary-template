"""scripts/lib/webhook_client.py の unittest。ネットワークには出ない
（127.0.0.1 の偽 webhook サーバーを http.server で立てて使う）。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.lib import webhook_client  # noqa: E402

# ダミー値（公開テンプレなので個人情報は入れない）
DUMMY_TOKEN = "test-token"
DUMMY_CHANNEL = "123456789012345678"


class _RecordingHandler(BaseHTTPRequestHandler):
    """偽 webhook サーバー: 受けたリクエストを self.server.last_request に記録して 200 を返す。"""

    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler の命名規則に合わせる)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except json.JSONDecodeError:
            payload = None
        self.server.last_request = {
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "json": payload,
        }
        body = b'{"status": "ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 標準出力を汚さない
        pass


class WebhookClientTest(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.server.last_request = None
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self._env_backup = dict(os.environ)
        os.environ["WEBHOOK_TOKEN"] = DUMMY_TOKEN
        os.environ["WEBHOOK_BASE"] = f"http://127.0.0.1:{self.port}"
        os.environ.pop("WEBHOOK_PORT", None)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_post_sends_token_header_and_reaches_configured_port(self):
        resp = webhook_client.post("/remind", {"message": "hi"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(self.server.last_request)
        self.assertEqual(self.server.last_request["path"], "/remind")
        self.assertEqual(self.server.last_request["headers"].get("X-Webhook-Token"), DUMMY_TOKEN)
        self.assertEqual(self.server.last_request["json"], {"message": "hi"})

    def test_post_prepends_missing_leading_slash(self):
        webhook_client.post("gmail_notify", {"sender": "a"})
        self.assertEqual(self.server.last_request["path"], "/gmail_notify")

    def test_remind_helper_builds_expected_payload(self):
        webhook_client.remind("hello", channel=DUMMY_CHANNEL, task="do it")
        self.assertEqual(self.server.last_request["path"], "/remind")
        self.assertEqual(
            self.server.last_request["json"],
            {"message": "hello", "channel": DUMMY_CHANNEL, "task": "do it"},
        )

    def test_remind_helper_omits_optional_fields_when_absent(self):
        webhook_client.remind("hello only")
        self.assertEqual(
            self.server.last_request["json"],
            {"message": "hello only"},
        )

    def test_webhook_base_wins_over_webhook_port(self):
        # WEBHOOK_BASE がある時は WEBHOOK_PORT を見ない
        os.environ["WEBHOOK_PORT"] = "1"
        webhook_client.post("/remind", {"message": "x"})
        self.assertEqual(self.server.last_request["path"], "/remind")

    def test_empty_token_raises_config_error_without_sending(self):
        os.environ["WEBHOOK_TOKEN"] = ""
        before = self.server.last_request
        with self.assertRaises(webhook_client.WebhookConfigError):
            webhook_client.post("/remind", {"message": "hi"})
        # 401 を黙って食らわず、そもそも送っていないこと
        self.assertEqual(self.server.last_request, before)


if __name__ == "__main__":
    unittest.main()
