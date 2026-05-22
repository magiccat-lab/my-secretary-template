#!/usr/bin/env python3
from __future__ import annotations
"""Detect dead daemons (port / pgrep) and emit Discord alert."""

import argparse
import os
import socket
import subprocess
import sys
import time

def port_ok(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False

def pgrep_ok(pattern: str) -> bool:
    return subprocess.run(["pgrep", "-f", pattern], stdout=subprocess.DEVNULL).returncode == 0

def alert(message: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print(message, file=sys.stderr)
        return
    import requests
    requests.post(webhook, json={"content": message[:1900]}, timeout=15).raise_for_status()

def restart(command: str) -> None:
    subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def check(args) -> bool:
    ok = True
    if args.pgrep:
        ok = ok and pgrep_ok(args.pgrep)
    if args.port:
        ok = ok and port_ok(args.port)
    return ok

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pgrep", default=os.environ.get("WATCHDOG_PGREP", ""))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WATCHDOG_PORT", "0") or "0"))
    parser.add_argument("--restart-cmd", default=os.environ.get("WATCHDOG_RESTART_CMD", ""))
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not args.pgrep and not args.port:
        print("Set --pgrep or --port.", file=sys.stderr)
        return 2

    while True:
        if not check(args):
            alert("watchdog: target is down; attempting restart")
            if args.restart_cmd:
                restart(args.restart_cmd)
            else:
                alert("watchdog: WATCHDOG_RESTART_CMD is not set")
        if args.once:
            return 0
        time.sleep(args.interval)

if __name__ == "__main__":
    sys.exit(main())
