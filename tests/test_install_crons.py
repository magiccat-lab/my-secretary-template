"""scripts/install_crons.sh のテスト。

必須 cron 5 本の managed block は、既に登録済みなら何もしない（ユーザーが
block 内の時刻を好みで調整していても、起動のたびに上書きしない）。
デフォルトに戻したいときだけ --force で明示的に上書きする。
本物の crontab は一切触らず、fake crontab（ファイルに保存するだけ）で確認する。
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "install_crons.sh")

FAKE_CRONTAB = """#!/bin/bash
# テスト用の偽 crontab。ファイルに保存するだけで本物の crontab には触らない
STORE="${FAKE_CRONTAB_FILE:?FAKE_CRONTAB_FILE not set}"
case "${1:-}" in
    -l)
        if [ -f "$STORE" ]; then
            cat "$STORE"
            exit 0
        fi
        echo "no crontab for tester" >&2
        exit 1
        ;;
    -)
        cat > "$STORE"
        exit 0
        ;;
    *)
        echo "fake crontab: unsupported args: $*" >&2
        exit 1
        ;;
esac
"""


class InstallCronsTest(unittest.TestCase):
    def setUp(self):
        self.tmp_path = tempfile.mkdtemp(prefix="install_crons_test_")
        self.addCleanup(shutil.rmtree, self.tmp_path, ignore_errors=True)

        bin_dir = os.path.join(self.tmp_path, "bin")
        os.makedirs(bin_dir)
        crontab_bin = os.path.join(bin_dir, "crontab")
        with open(crontab_bin, "w", encoding="utf-8") as f:
            f.write(FAKE_CRONTAB)
        os.chmod(crontab_bin, os.stat(crontab_bin).st_mode | stat.S_IEXEC)

        self.crontab_store = os.path.join(self.tmp_path, "crontab_store.txt")
        self.secretary_dir = os.path.join(self.tmp_path, "secretary")
        os.makedirs(self.secretary_dir, exist_ok=True)

        self.env = dict(
            os.environ,
            SECRETARY_DIR=self.secretary_dir,
            FAKE_CRONTAB_FILE=self.crontab_store,
            PATH=f"{bin_dir}:{os.environ['PATH']}",
        )

    def _run(self, args=()):
        return subprocess.run(
            ["bash", SCRIPT, *args], capture_output=True, text=True, env=self.env, timeout=30,
        )

    def _store_text(self):
        if not os.path.exists(self.crontab_store):
            return ""
        with open(self.crontab_store, encoding="utf-8") as f:
            return f.read()

    def test_first_run_registers_the_five_managed_jobs(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("登録しました", proc.stdout)
        store = self._store_text()
        self.assertIn("# >>> my-secretary-template managed crons >>>", store)
        self.assertIn("# <<< my-secretary-template managed crons <<<", store)
        for script_name in (
            "health_check.sh", "session_watchdog.py", "task_remind.py",
            "restart.sh", "discord_log_to_library.py",
        ):
            self.assertIn(script_name, store)

    def test_second_run_keeps_user_edited_schedule(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        store = self._store_text()
        edited = store.replace("*/5 * * * * /bin/bash", "*/7 * * * * /bin/bash")
        self.assertNotEqual(edited, store, "置換対象が見つからなかった")
        with open(self.crontab_store, "w", encoding="utf-8") as f:
            f.write(edited)

        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("登録済み", proc.stdout)
        self.assertIn("--force", proc.stdout)
        self.assertEqual(self._store_text(), edited, "ユーザーが変えた時刻が上書きされた")

    def test_force_restores_default_schedule(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        store = self._store_text()
        edited = store.replace("*/5 * * * * /bin/bash", "*/7 * * * * /bin/bash")
        with open(self.crontab_store, "w", encoding="utf-8") as f:
            f.write(edited)

        proc = self._run(["--force"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("--force", proc.stdout)
        store_after = self._store_text()
        self.assertIn("*/5 * * * * /bin/bash", store_after)
        self.assertNotIn("*/7 * * * * /bin/bash", store_after)

    def test_preserves_unrelated_existing_cron_lines(self):
        with open(self.crontab_store, "w", encoding="utf-8") as f:
            f.write("0 9 * * * /usr/bin/echo unrelated-job\n")
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        store = self._store_text()
        self.assertIn("unrelated-job", store)
        self.assertIn("# >>> my-secretary-template managed crons >>>", store)


if __name__ == "__main__":
    unittest.main()
