"""scripts/doctor.sh の回帰テスト。

端末 (シリアルコンソール等) で実行すると、結果を溜める配列の名前が LINES だと
bash の checkwinsize（5.x では非対話シェルでも既定 on）が外部コマンドの後に
端末の行数を LINES に代入し、配列の先頭要素を上書きすることがある
（例: 先頭行が「✅ コマンド: claude」ではなく「24」になる）。pty 無しのテストでは
再現しないので、`script` で pty を付けて実行して確かめる。
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCTOR = os.path.join(ROOT, "scripts", "doctor.sh")


class DoctorShTest(unittest.TestCase):
    def test_doctor_does_not_use_bash_reserved_names(self):
        with open(DOCTOR, encoding="utf-8") as f:
            text = f.read()
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for name in ("LINES", "COLUMNS"):
            self.assertIsNone(
                re.search(rf"(^|[^A-Za-z0-9_]){name}(=|\+=|\[)", code, re.M),
                f"{name} は bash の予約変数",
            )
            self.assertNotIn(f"${{{name}[", code)
            self.assertNotIn(f"${name}", code)

    @unittest.skipUnless(shutil.which("script"), "util-linux の script が無い (pty を作れない)")
    def test_doctor_first_line_survives_a_tty(self):
        tmp_path = tempfile.mkdtemp(prefix="doctor_sh_test_")
        try:
            secretary_dir = os.path.join(tmp_path, "secretary")
            os.makedirs(secretary_dir, exist_ok=True)
            env = dict(os.environ, HOME=tmp_path, SECRETARY_DIR=secretary_dir, TERM="xterm")
            # pty の窓が 0x0 だと bash は LINES を触らないので、シリアルコンソール相当の
            # 24x80 にしてから実行する
            proc = subprocess.run(
                ["script", "-qec", f"stty rows 24 cols 80; bash {DOCTOR}", "/dev/null"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
            )
            lines = [line.strip() for line in proc.stdout.replace("\r", "").splitlines() if line.strip()]
            self.assertTrue(lines, proc.stdout)
            self.assertTrue(
                lines[0].startswith(("✅ コマンド: claude", "❌ コマンド: claude")),
                lines[:3],
            )
            self.assertFalse(
                any(re.fullmatch(r"\d+", line) for line in lines),
                "端末の行数が結果に混ざっている",
            )
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
