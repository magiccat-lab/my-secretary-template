#!/usr/bin/env python3
from __future__ import annotations
"""Sample task: append a memory snippet to the Memory DB."""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "memory_capture.jsonl"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="+")
    parser.add_argument("--kind", default="fact", choices=["fact", "preference", "decision", "style", "constraint"])
    args = parser.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "kind": args.kind,
        "text": " ".join(args.text),
        "source": "cli",
    }
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"captured memory: {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
