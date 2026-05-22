#!/usr/bin/env python3
from __future__ import annotations
"""Lock / quiet-hours / interval gate for cron jobs (fail-open)."""

import argparse
import contextlib
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get("CRON_GATE_STATE", ROOT / "data" / "cron_gate_state.json"))
LOCK_DIR = Path(os.environ.get("CRON_GATE_LOCK_DIR", ROOT / "data" / "locks"))

def parse_hhmm(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)

def in_quiet_hours(spec: str, now: dt.datetime) -> bool:
    if not spec or "-" not in spec:
        return False
    start_s, end_s = spec.split("-", 1)
    start = parse_hhmm(start_s)
    end = parse_hhmm(end_s)
    cur = now.hour * 60 + now.minute
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end

def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE)

@contextlib.contextmanager
def lock(name: str, ttl: int):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCK_DIR / f"{name}.lock"
    now = time.time()
    if path.exists():
        age = now - path.stat().st_mtime
        if age < ttl:
            raise RuntimeError(f"locked: {path} age={age:.0f}s ttl={ttl}s")
    path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job")
    parser.add_argument("--min-interval", type=int, default=int(os.environ.get("CRON_GATE_MIN_INTERVAL", "0")))
    parser.add_argument("--quiet-hours", default=os.environ.get("CRON_GATE_QUIET_HOURS", ""))
    parser.add_argument("--lock-ttl", type=int, default=int(os.environ.get("CRON_GATE_LOCK_TTL", "3600")))
    parser.add_argument("--allow-quiet", action="store_true")
    args = parser.parse_args()

    now = dt.datetime.now()
    if args.quiet_hours and not args.allow_quiet and in_quiet_hours(args.quiet_hours, now):
        print(f"[cron_gate] skip {args.job}: quiet hours {args.quiet_hours}", file=sys.stderr)
        return 1

    state = load_state()
    item = state.get(args.job, {})
    last = item.get("last_allowed_at")
    if last and args.min_interval > 0:
        last_dt = dt.datetime.fromisoformat(last)
        elapsed = (now - last_dt).total_seconds()
        if elapsed < args.min_interval:
            print(f"[cron_gate] skip {args.job}: min interval {elapsed:.0f}/{args.min_interval}s", file=sys.stderr)
            return 1

    try:
        with lock(args.job, args.lock_ttl):
            state[args.job] = {"last_allowed_at": now.isoformat(timespec="seconds")}
            save_state(state)
    except RuntimeError as exc:
        print(f"[cron_gate] skip {args.job}: {exc}", file=sys.stderr)
        return 1

    print(f"[cron_gate] allow {args.job}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
