"""scripts/setup_claude_token.sh のテスト。

`claude setup-token` の直後の read が空で返り「トークンが空」で止まることがある
（対話 CLI が端末を返した直後は入力が残っているため）。今は script(1) で
setup-token の画面出力を記録し、そこから sk-ant-oat01-... を拾う。本物の claude は
使わず、Ink 風の出力（ANSI 制御列 + 端末幅で折り返されたトークン）を出す偽の claude を
PATH に置いて回す。

テストで使うトークンは全て明らかな偽物（"FAKETESTTOKEN" の繰り返し + "-END"）。
本物のトークンらしき文字列は書かない。
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "setup_claude_token.sh")

# 明らかに偽物と分かるダミートークン（本物のトークン文字列は書かない）
TOKEN_HEAD = "sk-ant-oat01-" + "FAKETESTTOKEN" * 4
TOKEN_TAIL = "FAKETESTTOKEN" * 3 + "-END"
TOKEN = TOKEN_HEAD + TOKEN_TAIL

INK_LIKE_OUTPUT = (
    "printf '\\033[?25l\\033[1mSetting up long-lived auth token\\033[0m\\n\\n'\n"
    "printf ' This will guide you through long-lived (1-year) auth token setup for your\\n"
    " Claude account.\\n\\n'\n"
    "printf ' \\033[32m\u2713\\033[0m Long-lived authentication token created successfully!\\n\\n'\n"
    "printf ' Your OAuth token (valid for 1 year):\\n\\n'\n"
    f"printf ' {TOKEN_HEAD}\\n {TOKEN_TAIL}\\n\\n'\n"
    "printf ' Store this token securely. You won'\"'\"'t be able to see it again.\\n\\n'\n"
    "printf ' Use this token by setting: export CLAUDE_CODE_OAUTH_TOKEN=<token>\\n\\033[?25h'\n"
)

needs_script = unittest.skipUnless(shutil.which("script"), "util-linux の script が無い")


class SetupClaudeTokenTest(unittest.TestCase):
    def setUp(self):
        self.tmp_path = tempfile.mkdtemp(prefix="setup_claude_token_test_")
        self.addCleanup(shutil.rmtree, self.tmp_path, ignore_errors=True)

    def _fake_claude(self, bin_dir, body):
        path = os.path.join(bin_dir, "claude")
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\n")
            f.write('[ "${1:-}" = setup-token ] || { echo unexpected >&2; exit 2; }\n')
            f.write(body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def _run(self, args, stdin="", fake_body=INK_LIKE_OUTPUT, home=None):
        home = home or os.path.join(self.tmp_path, "home")
        secretary = os.path.join(home, "secretary")
        os.makedirs(secretary, exist_ok=True)
        bin_dir = os.path.join(self.tmp_path, "bin")
        if not os.path.isdir(bin_dir):
            os.makedirs(bin_dir)
        self._fake_claude(bin_dir, fake_body)
        env = dict(os.environ, HOME=home, SECRETARY_DIR=secretary,
                   PATH=f"{bin_dir}:{os.environ['PATH']}", TERM="xterm")
        proc = subprocess.run(["bash", SCRIPT, *args], input=stdin, capture_output=True,
                               text=True, env=env, cwd=secretary, timeout=120)
        secrets_dir = os.path.join(secretary, "data", "secrets")
        return proc, secrets_dir, home

    @needs_script
    def test_token_is_captured_from_setup_token_output_even_when_wrapped(self):
        proc, secrets, _ = self._run([], stdin="Y\n")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("トークンを拾った: " + TOKEN[:16], proc.stdout)
        token_file = os.path.join(secrets, "claude_oauth_token")
        with open(token_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), TOKEN)
        self.assertEqual(stat.S_IMODE(os.stat(token_file).st_mode), 0o600)
        with open(token_file + ".issued_at", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), date.today().isoformat())

    @needs_script
    def test_following_prose_line_is_not_glued_to_the_token(self):
        body = (
            f"printf ' Your OAuth token (valid for 1 year):\\n\\n {TOKEN_HEAD}\\n {TOKEN_TAIL}\\n"
            " Store this token securely.\\n'\n"
        )
        proc, secrets, _ = self._run([], stdin="Y\n", fake_body=body)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(os.path.join(secrets, "claude_oauth_token"), encoding="utf-8") as f:
            self.assertEqual(f.read(), TOKEN)

    @needs_script
    def test_declining_the_confirmation_saves_nothing(self):
        proc, secrets, _ = self._run([], stdin="n\n")
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(secrets, "claude_oauth_token")))

    @needs_script
    def test_setup_token_failure_stops_without_saving(self):
        proc, secrets, _ = self._run([], stdin="Y\n", fake_body="echo boom >&2; exit 3\n")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("正常終了しなかった", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(secrets, "claude_oauth_token")))

    def test_file_mode_joins_wrapped_lines(self):
        src = os.path.join(self.tmp_path, "tok.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(f"{TOKEN_HEAD}\n {TOKEN_TAIL}\n")
        proc, secrets, _ = self._run(["--file", src])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(os.path.join(secrets, "claude_oauth_token"), encoding="utf-8") as f:
            self.assertEqual(f.read(), TOKEN)

    def test_paste_mode_reads_the_token_from_stdin(self):
        proc, secrets, _ = self._run(["--paste"], stdin=TOKEN + "\n")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(os.path.join(secrets, "claude_oauth_token"), encoding="utf-8") as f:
            self.assertEqual(f.read(), TOKEN)

    def test_same_day_rerun_is_refused_without_force(self):
        src = os.path.join(self.tmp_path, "tok.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(TOKEN)
        proc, secrets, home = self._run(["--file", src])
        self.assertEqual(proc.returncode, 0)
        second = subprocess.run(
            ["bash", SCRIPT, "--file", src], capture_output=True, text=True, timeout=60,
            env=dict(os.environ, HOME=home, SECRETARY_DIR=os.path.join(home, "secretary")),
        )
        self.assertEqual(second.returncode, 1)
        self.assertIn("--force", second.stderr)

    def test_force_overwrites_same_day_rerun(self):
        src = os.path.join(self.tmp_path, "tok.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(TOKEN)
        proc, secrets, home = self._run(["--file", src])
        self.assertEqual(proc.returncode, 0)
        second = subprocess.run(
            ["bash", SCRIPT, "--file", src, "--force"], capture_output=True, text=True, timeout=60,
            env=dict(os.environ, HOME=home, SECRETARY_DIR=os.path.join(home, "secretary")),
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        with open(os.path.join(secrets, "claude_oauth_token"), encoding="utf-8") as f:
            self.assertEqual(f.read(), TOKEN)


if __name__ == "__main__":
    unittest.main()
