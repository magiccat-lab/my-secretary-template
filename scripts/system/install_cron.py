#!/usr/bin/env python3
from __future__ import annotations
"""Idempotent crontab editor (add / list / remove sub-commands)."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER_BEGIN = "# BEGIN my-secretary-template"
MARKER_END = "# END my-secretary-template"

DEFAULT_LINES = [
    "0 8 * * * cd {root} && python3 scripts/lib/cron_gate.py daily_brief --min-interval 82800 || exit 0; python3 templates/onboarded/daily_brief.py",
    "*/5 * * * * cd {root} && python3 scripts/lib/cron_gate.py gcal_remind --min-interval 240 --allow-quiet || exit 0; python3 scripts/integrations/gcal/gcal_remind.py",
    "0 3 * * * cd {root} && python3 scripts/lib/cron_gate.py discord_log_sync --min-interval 82800 || exit 0; python3 scripts/integrations/discord/sync_log_to_notion.py",
    "0 8 * * * cd {root} && python3 scripts/lib/cron_gate.py sample_recommend --min-interval 82800 || exit 0; python3 scripts/recommendations/sample_scrape_recommend.py",
    "*/10 * * * * cd {root} && python3 templates/onboarded/health_ping.py >/tmp/my-secretary-health.log 2>&1",
]

def current_crontab() -> str:
    p = subprocess.run(["crontab", "-l"], text=True, capture_output=True)
    return "" if p.returncode != 0 else p.stdout

def render_block() -> str:
    lines = [MARKER_BEGIN]
    lines.extend(line.format(root=ROOT) for line in DEFAULT_LINES)
    lines.append(MARKER_END)
    return "\n".join(lines) + "\n"

def remove_block(text: str) -> str:
    out = []
    skipping = False
    for line in text.splitlines():
        if line.strip() == MARKER_BEGIN:
            skipping = True
            continue
        if line.strip() == MARKER_END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out).rstrip() + ("\n" if out else "")

def install() -> None:
    text = remove_block(current_crontab())
    new_text = text + ("\n" if text.strip() else "") + render_block()
    subprocess.run(["crontab", "-"], input=new_text, text=True, check=True)

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add")
    sub.add_parser("list")
    sub.add_parser("remove")
    sub.add_parser("print")
    args = parser.parse_args()

    if args.cmd == "print":
        print(render_block(), end="")
    elif args.cmd == "list":
        print(current_crontab(), end="")
    elif args.cmd == "remove":
        subprocess.run(["crontab", "-"], input=remove_block(current_crontab()), text=True, check=True)
    elif args.cmd == "add":
        install()
    return 0

if __name__ == "__main__":
    sys.exit(main())
