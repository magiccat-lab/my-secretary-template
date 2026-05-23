#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TIL_DIR = Path(os.environ.get("TRAINER_TIL_DIR", ROOT / "data" / "notes"))
OUT = Path(os.environ.get("TRAINER_KNOWLEDGE_PATH", ROOT / "data" / "notes" / "knowledge.md"))
FAILURE_RE = re.compile(r"\b(error|failed|failure|bug|regression|timeout|blocked|missing|forgot)\b", re.I)


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def note_files() -> list[Path]:
    base = TIL_DIR if TIL_DIR.is_absolute() else ROOT / TIL_DIR
    if not base.exists():
        return []
    return [path for path in base.rglob("*.md") if path.resolve() != (OUT if OUT.is_absolute() else ROOT / OUT).resolve()]


def normalize(line: str) -> str:
    line = re.sub(r"`[^`]+`", "`code`", line)
    line = re.sub(r"\b\d+\b", "N", line)
    return line.strip("-* \t")[:220]


def collect() -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in note_files():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if FAILURE_RE.search(line):
                text = normalize(line)
                if len(text) >= 20:
                    counts[text] += 1
    return counts


def render(counts: Counter[str]) -> str:
    now = dt.datetime.now().isoformat(timespec="seconds")
    lines = ["# Knowledge", "", f"UpdatedAt: {now}", "", "## Promoted Failure Patterns", ""]
    promoted = [(text, count) for text, count in counts.most_common() if count >= 3]
    if not promoted:
        lines.append("(no repeated patterns yet)")
    for text, count in promoted:
        lines.append(f"- seen {count} times: {text}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not env_bool("FEATURE_TRAINER"):
        print("FEATURE_TRAINER is not true; skipping")
        return 0
    path = OUT if OUT.is_absolute() else ROOT / OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(collect()), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
