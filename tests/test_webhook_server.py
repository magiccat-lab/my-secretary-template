"""scripts/webhook_server.py の統合テスト。ネットワークには出ない。

webhook_server.py 本体とその依存(scripts/lib/task_store.py,
scripts/lib/secret_redact.py, scripts/lib/__init__.py)を一時 dir にコピーし、
一時 dir の .env から設定を読ませた状態で subprocess として起動して HTTP で叩く。
load_dotenv の読み込み先(../.env、webhook_server.py 基準)は変えない契約なので、
本物の repo の .env に触れずに済むようこの方式を取る。

偽 Discord API(http.server)を 127.0.0.1 の空きポートに立て、DISCORD_API_BASE
でそこへ向ける。
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ダミー値（公開テンプレなので個人情報は入れない。example.com は IANA 予約の
# ドキュメント用ドメイン）
VALID_TOKEN = "test-token"
WRONG_TOKEN = "wrong-test-token"
VALID_CHANNEL = "123456789012345678"  # 18桁のダミー Discord snowflake
SHORT_CHANNEL = "12345"               # 桁不足の無効な値
DUMMY_EMAIL = "sender@example.com"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeDiscordHandler(BaseHTTPRequestHandler):
    """偽 Discord API: /channels/<id>/messages への POST を記録して 200 を返す。"""

    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler の命名規則に合わせる)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except json.JSONDecodeError:
            payload = None
        self.server.requests.append(
            {
                "path": self.path,
                "headers": {k: v for k, v in self.headers.items()},
                "json": payload,
            }
        )
        body = b'{"id": "111111111111111111"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 標準出力を汚さない
        pass


def _build_sandbox(tmp_root: str) -> str:
    """webhook_server.py + 依存する scripts/lib/* を一時 dir にコピーする。
    戻り値: コピー後の webhook_server.py の絶対パス。
    """
    scripts_src = os.path.join(REPO_ROOT, "scripts")
    scripts_dst = os.path.join(tmp_root, "scripts")
    os.makedirs(os.path.join(scripts_dst, "lib"), exist_ok=True)
    shutil.copy2(os.path.join(scripts_src, "webhook_server.py"), scripts_dst)
    for name in ("__init__.py", "task_store.py", "secret_redact.py"):
        shutil.copy2(os.path.join(scripts_src, "lib", name), os.path.join(scripts_dst, "lib", name))
    return os.path.join(scripts_dst, "webhook_server.py")


def _write_env(tmp_root: str, *, webhook_token: str, webhook_port: int, discord_api_base: str) -> None:
    with open(os.path.join(tmp_root, ".env"), "w", encoding="utf-8") as f:
        f.write("WEBHOOK_HOST=127.0.0.1\n")
        f.write(f"WEBHOOK_PORT={webhook_port}\n")
        f.write(f"WEBHOOK_TOKEN={webhook_token}\n")
        f.write(f"DISCORD_API_BASE={discord_api_base}\n")
        f.write(f"DISCORD_CHANNEL_RANDOM={VALID_CHANNEL}\n")


def _write_discord_bot_env(home_dir: str) -> None:
    d = os.path.join(home_dir, ".claude", "channels", "discord")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
        f.write("DISCORD_BOT_TOKEN=test-bot-token\n")


def _child_env(home_dir: str) -> dict:
    return {
        "HOME": home_dir,
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONIOENCODING": "utf-8",
    }


def _wait_for_health(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if r.status_code == 200:
                return
        except requests.RequestException as e:
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(f"webhook_server が時間内に健全化しなかった: {last_err}")


class WebhookServerTest(unittest.TestCase):
    """(a)〜(g),(i): 正常起動した webhook_server.py に対する疎通テスト
    （発注書 B7 の項目ラベルに対応。1 プロセスを使い回す）。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="webhook_server_test_")
        cls._home = os.path.join(cls._tmp, "home")
        os.makedirs(cls._home, exist_ok=True)
        _write_discord_bot_env(cls._home)

        cls._fake_discord = HTTPServer(("127.0.0.1", 0), _FakeDiscordHandler)
        cls._fake_discord.requests = []
        cls._fake_discord_port = cls._fake_discord.server_address[1]
        cls._fake_discord_thread = threading.Thread(target=cls._fake_discord.serve_forever, daemon=True)
        cls._fake_discord_thread.start()

        cls._queue_file = os.path.join(cls._tmp, "claude_queue.txt")
        cls._port = _free_port()
        script_path = _build_sandbox(cls._tmp)
        _write_env(
            cls._tmp,
            webhook_token=VALID_TOKEN,
            webhook_port=cls._port,
            discord_api_base=f"http://127.0.0.1:{cls._fake_discord_port}",
        )

        env = _child_env(cls._home)
        env["QUEUE_FILE"] = cls._queue_file

        # stdout/stderr は PIPE のまま放置すると長時間プロセスでバッファが
        # 詰まって固まるので、ログファイルへリダイレクトする
        cls._log_path = os.path.join(cls._tmp, "webhook_server_stdout.log")
        cls._log_fh = open(cls._log_path, "w", encoding="utf-8")
        cls._proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=cls._tmp,
            env=env,
            stdout=cls._log_fh,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_health(cls._port)
        except Exception:
            cls._proc.terminate()
            try:
                cls._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls._proc.kill()
            cls._log_fh.flush()
            with open(cls._log_path, encoding="utf-8", errors="replace") as f:
                log_content = f.read()
            raise RuntimeError(f"webhook_server 起動失敗。ログ:\n{log_content}")

    @classmethod
    def tearDownClass(cls):
        proc = getattr(cls, "_proc", None)
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log_fh = getattr(cls, "_log_fh", None)
        if log_fh is not None:
            log_fh.close()
        fake = getattr(cls, "_fake_discord", None)
        if fake is not None:
            fake.shutdown()
            fake.server_close()
        thread = getattr(cls, "_fake_discord_thread", None)
        if thread is not None:
            thread.join(timeout=5)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self._port}{path}"

    # --- (a)(b): トークン無し／違うトークンは 401 ---

    def test_no_token_is_401(self):
        r = requests.post(self._url("/remind"), json={"message": "hi", "channel": VALID_CHANNEL})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"status": "unauthorized"})

    def test_wrong_token_is_401(self):
        r = requests.post(
            self._url("/remind"),
            json={"message": "hi", "channel": VALID_CHANNEL},
            headers={"X-Webhook-Token": WRONG_TOKEN},
        )
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"status": "unauthorized"})

    # --- (c): 桁不足の channel は 400 ---

    def test_short_channel_is_400(self):
        r = requests.post(
            self._url("/remind"),
            json={"message": "hi", "channel": SHORT_CHANNEL},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )
        self.assertEqual(r.status_code, 400)

    # --- (d): 正常系は 200 + 偽 Discord が allowed_mentions 付き payload を受ける ---

    def test_valid_request_is_200_and_discord_gets_allowed_mentions(self):
        before = len(self._fake_discord.requests)
        r = requests.post(
            self._url("/remind"),
            json={"message": "正常系テスト", "channel": VALID_CHANNEL},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})
        reqs = self._fake_discord.requests[before:]
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["path"], f"/channels/{VALID_CHANNEL}/messages")
        self.assertEqual(reqs[0]["json"]["allowed_mentions"], {"parse": ["users"]})
        self.assertEqual(reqs[0]["json"]["content"], "正常系テスト")

    # --- (e): message 2001文字は400、2000文字は通る ---

    def test_message_too_long_is_400(self):
        r = requests.post(
            self._url("/remind"),
            json={"message": "a" * 2001, "channel": VALID_CHANNEL},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )
        self.assertEqual(r.status_code, 400)

    def test_message_at_2000_limit_is_ok(self):
        r = requests.post(
            self._url("/remind"),
            json={"message": "a" * 2000, "channel": VALID_CHANNEL},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )
        self.assertEqual(r.status_code, 200)

    # --- (f): Bearer 形式でも通る ---

    def test_bearer_header_is_accepted(self):
        r = requests.post(
            self._url("/remind"),
            json={"message": "bearerテスト", "channel": VALID_CHANNEL},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        self.assertEqual(r.status_code, 200)

    # --- (g): /health は無認証 ---

    def test_health_requires_no_auth(self):
        r = requests.get(self._url("/health"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "ok")

    # --- (i): 制御文字入り gmail_notify は 200 + キューに base64 で1行追記 ---

    def test_gmail_notify_strips_control_chars_and_queues_base64(self):
        # ベル(\x07)・ESC(\x1b)は落ち、tab/改行は残る想定
        dirty_subject = "件名\x07です\x1b[31m\t続き\nあり"
        r = requests.post(
            self._url("/gmail_notify"),
            json={"sender": DUMMY_EMAIL, "subject": dirty_subject, "body": "本文\x00です"},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )
        self.assertEqual(r.status_code, 200)

        # send_to_claude は ThreadPoolExecutor 経由の非同期書き込みなので少し待つ
        deadline = time.time() + 5
        lines: list[str] = []
        while time.time() < deadline:
            if os.path.exists(self._queue_file):
                with open(self._queue_file, encoding="utf-8") as f:
                    lines = [ln for ln in f.read().splitlines() if ln.strip()]
                if lines:
                    break
            time.sleep(0.1)

        self.assertTrue(lines, "QUEUE_FILE に行が追記されなかった")
        decoded = base64.b64decode(lines[-1]).decode("utf-8")
        self.assertNotIn("\x07", decoded)
        self.assertNotIn("\x1b", decoded)
        self.assertNotIn("\x00", decoded)
        self.assertIn("続き", decoded)
        self.assertIn("以下はメールの内容", decoded)


class WebhookServerMissingTokenTest(unittest.TestCase):
    """(h): WEBHOOK_TOKEN が空だと起動時に exit code 非0 でエラーを出す。"""

    def test_empty_token_fails_fast_on_startup(self):
        tmp = tempfile.mkdtemp(prefix="webhook_server_test_missing_token_")
        try:
            home = os.path.join(tmp, "home")
            os.makedirs(home, exist_ok=True)
            _write_discord_bot_env(home)
            script_path = _build_sandbox(tmp)
            _write_env(
                tmp,
                webhook_token="",
                webhook_port=_free_port(),
                discord_api_base="http://127.0.0.1:1",
            )
            env = _child_env(home)
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("WEBHOOK_TOKEN", combined)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
