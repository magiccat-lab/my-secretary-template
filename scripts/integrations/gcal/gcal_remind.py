#!/usr/bin/env python3
from __future__ import annotations
"""Sample: push Google Calendar reminders to a Discord channel 30 / 5 min before."""

import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / "data" / "gcal_remind_state.json"

def fail(msg: str) -> int:
    print(msg, file=sys.stderr)
    return 1

def load_state() -> set[str]:
    if not STATE.exists():
        return set()
    return set(json.loads(STATE.read_text(encoding="utf-8")).get("sent", []))

def save_state(sent: set[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"sent": sorted(sent)[-1000:]}, indent=2), encoding="utf-8")

def post_discord(text: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print(text)
        return
    requests.post(webhook, json={"content": text[:1900]}, timeout=15).raise_for_status()

def main() -> int:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return fail("Install google-api-python-client and google-auth before using gcal_remind.py.")

    cal_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
    token_file = os.environ.get("GOOGLE_TOKEN_FILE", str(ROOT / "integrations" / "google" / "token.json"))
    if not Path(token_file).exists():
        return fail(f"Google token file not found: {token_file}")

    creds = Credentials.from_authorized_user_file(token_file)
    service = build("calendar", "v3", credentials=creds)

    now = dt.datetime.now(dt.timezone.utc)
    later = now + dt.timedelta(hours=24)
    events = service.events().list(
        calendarId=cal_id,
        timeMin=now.isoformat(),
        timeMax=later.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])

    sent = load_state()
    reminder_minutes = [int(x) for x in os.environ.get("GCAL_REMINDER_MINUTES", "30,5").split(",")]
    for ev in events:
        start_raw = ev.get("start", {}).get("dateTime")
        if not start_raw:
            continue
        start = dt.datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        minutes = int((start - now).total_seconds() // 60)
        for mark in reminder_minutes:
            key = f"{ev.get('id')}:{mark}"
            if key not in sent and 0 <= minutes <= mark:
                post_discord(f"Calendar reminder: {ev.get('summary', 'Untitled')} starts in about {minutes} min")
                sent.add(key)

    save_state(sent)
    return 0

if __name__ == "__main__":
    sys.exit(main())
