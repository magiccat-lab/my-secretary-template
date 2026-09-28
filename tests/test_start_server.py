"""start_server.sh のテスト。

背景: `exec 200>lock; flock -n 200` の後に `screen -dmS` や `queue_watcher.sh &` を
起動すると、子プロセスが fd 200 を継承してしまい、スクリプト終了後もロックが
解放されなくなる（無限ループの queue_watcher が握り続けるため）。結果として
2 回目以降の start_server.sh が常に「already running」で空振りする。今の版は
子プロセスの起動全部に `200>&-` を付けて fd を継がせない。

このテストは本物の screen / claude / expect を一切起動しない（`screen` だけ偽物に
差し替え、状態ファイルへの記録と `-dmS` に渡された argv・環境変数のダンプだけ行う）。
`curl` / `lsof` / `crontab` も偽物にして外部の待ち時間とネットワーク・実 crontab への
接触を無くす。`expect` / `claude` / `flock` は実物を使うが、`screen` を偽物にしている
ため実際に spawn されることはない。

`getent` も偽物にする（本文で要求されている一覧には無いが、start_server.sh は
`export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"` で実ユーザーの本当の
HOME を強制的に再計算するため、偽物にしないと ensure_trust.sh が実ユーザーの
本物の ~/.claude.json を書き換えてしまう。このホストでは実際に 39KB の本物の
~/.claude.json と本物の Discord bot token を含む ~/.claude/channels/discord/.env が
存在することを確認済みなので、テストの隔離のために getent だけは安全側に倒して偽物にする）。
"""
import collections
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import unittest

_RunResult = collections.namedtuple("_RunResult", "returncode stdout stderr")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
START_SERVER = os.path.join(ROOT, "start_server.sh")
LOCKFILE = "/tmp/secretary_start.lock"

FAKE_SCREEN = r"""#!/bin/bash
# 偽 screen。-dmS は状態ファイルに記録するだけで実際には何も spawn しない。
# -list/-ls は -dmS 済みなら "12345.secretary" を含む行を返す
STATE_DIR="${FAKE_SCREEN_STATE_DIR:?FAKE_SCREEN_STATE_DIR not set}"
mkdir -p "$STATE_DIR"

case "${1:-}" in
    -list|-ls)
        if [ -f "$STATE_DIR/dms_started" ]; then
            echo "There is a screen on:"
            printf '\t12345.secretary\t(Detached)\n'
            echo "1 Socket in /run/screen/S-tester."
            exit 0
        fi
        echo "No Sockets found in /run/screen/S-tester." >&2
        exit 1
        ;;
    -dmS)
        shift
        name="$1"; shift
        {
            echo "===ARGV==="
            printf '%s\n' "$name"
            printf '%s\n' "$@"
            echo "===ENV==="
            env
        } > "$STATE_DIR/dms_dump.txt"
        touch "$STATE_DIR/dms_started"
        exit 0
        ;;
    -S)
        shift
        name="$1"; shift || true
        sub="${1:-}"; shift || true
        action="${1:-}"; shift || true
        case "$action" in
            quit)
                rm -f "$STATE_DIR/dms_started"
                ;;
            screen)
                echo "$name $*" >> "$STATE_DIR/subwindows.txt"
                ;;
        esac
        exit 0
        ;;
    *)
        exit 0
        ;;
esac
"""

FAKE_CURL = r"""#!/bin/bash
# 偽 curl。--max-time 付きの呼び出しは常に成功 (200) を返す
for a in "$@"; do
    if [ "$a" = "--max-time" ]; then
        printf '200'
        exit 0
    fi
done
printf '000'
exit 1
"""

FAKE_LSOF = r"""#!/bin/bash
# 偽 lsof。何も出さず失敗する（LISTEN中のプロセスは無い扱い）
exit 1
"""

FAKE_CRONTAB = r"""#!/bin/bash
# 偽 crontab。ファイルに保存するだけで本物の crontab には一切触らない
STORE="${FAKE_CRONTAB_FILE:?FAKE_CRONTAB_FILE not set}"
case "${1:-}" in
    -l)
        if [ -f "$STORE" ]; then cat "$STORE"; exit 0; fi
        echo "no crontab for tester" >&2
        exit 1
        ;;
    -)
        cat > "$STORE"
        exit 0
        ;;
    *)
        exit 1
        ;;
esac
"""

FAKE_GETENT = r"""#!/bin/bash
# 偽 getent。start_server.sh / install_crons.sh は
# `export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"` で実ユーザーの
# 本当の HOME を再計算するため、これを偽らないとテストが実ユーザーの本物の
# ~/.claude.json 等に触れてしまう。passwd 問い合わせは常に固定のテスト用
# ホームディレクトリを返す
if [ "${1:-}" = "passwd" ]; then
    echo "tester:x:1000:1000:tester:${FAKE_GETENT_HOME:?FAKE_GETENT_HOME not set}:/bin/bash"
    exit 0
fi
exit 2
"""

FAKE_QUEUE_WATCHER = "#!/bin/bash\nwhile true; do sleep 1; done\n"
FAKE_STARTUP_CHECK = "#!/bin/bash\nexit 0\n"


def _write_exec(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


class StartServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp_path = tempfile.mkdtemp(prefix="start_server_test_")
        self.addCleanup(shutil.rmtree, self.tmp_path, ignore_errors=True)

        self.home_dir = os.path.join(self.tmp_path, "home")
        self.secretary_dir = os.path.join(self.home_dir, "secretary")
        os.makedirs(os.path.join(self.secretary_dir, "scripts"), exist_ok=True)

        # このworktreeの実ファイルをそのまま置く（テスト対象そのもの + 直接の依存先）
        for rel in ("start_server.sh",):
            shutil.copyfile(os.path.join(ROOT, rel), os.path.join(self.secretary_dir, rel))
        for rel in ("scripts/ensure_trust.sh", "scripts/doctor.sh", "scripts/install_crons.sh"):
            shutil.copyfile(os.path.join(ROOT, rel), os.path.join(self.secretary_dir, rel))

        # queue_watcher / startup_check / webhook_server は偽物（無限ループ・即終了・空）
        _write_exec(os.path.join(self.secretary_dir, "scripts", "queue_watcher.sh"), FAKE_QUEUE_WATCHER)
        _write_exec(os.path.join(self.secretary_dir, "scripts", "startup_check.sh"), FAKE_STARTUP_CHECK)
        open(os.path.join(self.secretary_dir, "scripts", "webhook_server.py"), "w").close()

        bin_dir = os.path.join(self.tmp_path, "bin")
        os.makedirs(bin_dir)
        _write_exec(os.path.join(bin_dir, "screen"), FAKE_SCREEN)
        _write_exec(os.path.join(bin_dir, "curl"), FAKE_CURL)
        _write_exec(os.path.join(bin_dir, "lsof"), FAKE_LSOF)
        _write_exec(os.path.join(bin_dir, "crontab"), FAKE_CRONTAB)
        _write_exec(os.path.join(bin_dir, "getent"), FAKE_GETENT)

        self.state_dir = os.path.join(self.tmp_path, "screen_state")
        self.crontab_store = os.path.join(self.tmp_path, "crontab_store.txt")

        self.env = dict(
            os.environ,
            HOME=self.home_dir,
            SECRETARY_DIR=self.secretary_dir,
            FAKE_SCREEN_STATE_DIR=self.state_dir,
            FAKE_CRONTAB_FILE=self.crontab_store,
            FAKE_GETENT_HOME=self.home_dir,
            PATH=f"{bin_dir}:{os.environ['PATH']}",
        )
        # setup_claude_token.sh の既定と同じ ANTHROPIC_API_KEY を紛れ込ませておき、
        # 「setup-token使用時はunsetされる」を実際に確認できるようにする
        self.env["ANTHROPIC_API_KEY"] = "sk-ant-example-key-should-be-removed"

        self.addCleanup(self._kill_fake_queue_watcher)

    def _kill_fake_queue_watcher(self):
        pattern = os.path.join(self.secretary_dir, "scripts", "queue_watcher.sh")
        try:
            out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            return
        for pid_str in out.stdout.split():
            try:
                os.kill(int(pid_str), signal.SIGTERM)
            except (ValueError, ProcessLookupError):
                pass

    def _run(self):
        # stdout/stderr は PIPE (capture_output) ではなくファイルに向ける。start_server.sh は
        # queue_watcher/startup_check を `&` でバックグラウンド起動したまま終了するため、
        # PIPE だとその孫プロセス（無限ループの偽 queue_watcher）が書き込み端を握り続けて
        # subprocess.run が EOF を待って永久に固まる（このスクリプト自体が直す fd リークと
        # 同じ種類の「バックグラウンドの子が fd を握ったままになる」問題の、テスト側での再現）。
        # ファイルなら read() 側が EOF を待たないのでこの問題を避けられる
        out_path = os.path.join(self.tmp_path, "run_stdout.txt")
        err_path = os.path.join(self.tmp_path, "run_stderr.txt")
        with open(out_path, "w", encoding="utf-8") as out_f, open(err_path, "w", encoding="utf-8") as err_f:
            proc = subprocess.run(
                ["bash", os.path.join(self.secretary_dir, "start_server.sh")],
                stdout=out_f, stderr=err_f, env=self.env, cwd=self.secretary_dir, timeout=60,
            )
        with open(out_path, encoding="utf-8") as f:
            stdout = f.read()
        with open(err_path, encoding="utf-8") as f:
            stderr = f.read()
        return _RunResult(proc.returncode, stdout, stderr)

    def _dms_dump(self):
        with open(os.path.join(self.state_dir, "dms_dump.txt"), encoding="utf-8") as f:
            return f.read()

    def test_lock_is_released_after_the_script_exits(self):
        """(a) 終了後は flock -n でロックを取れる（子プロセスが fd 200 を握ったままにしない）"""
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # 偽 queue_watcher はまだ動いている（無限ループ）はずなのに、ロックは取れる
        pattern = os.path.join(self.secretary_dir, "scripts", "queue_watcher.sh")
        still_running = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=10)
        self.assertTrue(still_running.stdout.strip(), "偽 queue_watcher が起動していない（テスト前提が崩れている）")

        check = subprocess.run(["flock", "-n", LOCKFILE, "-c", "true"], capture_output=True, text=True, timeout=10)
        self.assertEqual(check.returncode, 0, "flock -n がロックを取れなかった (fd 200 が子プロセスに漏れている)")

    def test_token_file_present_exports_oauth_token_and_strips_api_key(self):
        """(b) token ファイルがあれば CLAUDE_CODE_OAUTH_TOKEN が入り、ANTHROPIC_API_KEY が消える"""
        secrets_dir = os.path.join(self.secretary_dir, "data", "secrets")
        os.makedirs(secrets_dir, exist_ok=True)
        token_value = "sk-ant-oat01-" + "FAKETESTTOKEN" * 4 + "-END"
        with open(os.path.join(secrets_dir, "claude_oauth_token"), "w", encoding="utf-8") as f:
            f.write(token_value + "\n")  # 前後の改行は start_server.sh 側で tr -d する

        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("claude auth: setup-token ファイルを使用", proc.stdout)
        self.assertNotIn(token_value, proc.stdout, "トークンの値をログに出してはいけない")

        dump = self._dms_dump()
        self.assertIn(f"CLAUDE_CODE_OAUTH_TOKEN={token_value}", dump.splitlines())
        self.assertFalse(
            any(line.startswith("ANTHROPIC_API_KEY=") for line in dump.splitlines()),
            "ANTHROPIC_API_KEY が unset されていない",
        )

    def test_token_file_absent_leaves_oauth_token_unset(self):
        """(c) token ファイルが無い時は CLAUDE_CODE_OAUTH_TOKEN が入らない"""
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("claude auth: /login 認証 (token file なし)", proc.stdout)

        dump = self._dms_dump()
        self.assertFalse(
            any(line.startswith("CLAUDE_CODE_OAUTH_TOKEN=") for line in dump.splitlines()),
            "token ファイルが無いのに CLAUDE_CODE_OAUTH_TOKEN が設定されている",
        )

    def test_start_server_body_has_no_pkill(self):
        """(d) start_server.sh の本文に pkill コマンドが無い（無関係プロセスを巻き込む危険が
        あるため撤去済み。「pkill を使わない理由」を書いた説明コメントは対象外）"""
        with open(START_SERVER, encoding="utf-8") as f:
            text = f.read()
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("pkill", code)


if __name__ == "__main__":
    unittest.main()
