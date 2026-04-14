#!/usr/bin/env python3
"""今日のカレンダー予定を出力する。

環境変数:
    GOOGLE_TOKEN_PATH  token.json のパス（デフォルト: integrations/gcal/token.json）
    GCAL_CALENDAR_ID   読み出すカレンダー ID（デフォルト: "primary"）
"""

from __future__ import annotations

import datetime
import os

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN_PATH = os.path.expanduser(
    os.getenv("GOOGLE_TOKEN_PATH", os.path.join(_REPO_ROOT, "integrations/gcal/token.json"))
)
CALENDAR_ID = os.getenv("GCAL_CALENDAR_ID", "primary")


def get_today_events() -> None:
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    service = build("calendar", "v3", credentials=creds)

    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    events_result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])

    if not events:
        print("今日の予定はありません")
        return

    for event in events:
        start_time = event["start"].get("dateTime", event["start"].get("date"))
        if "T" in start_time:
            dt = datetime.datetime.fromisoformat(start_time)
            print(f"{dt.strftime('%H:%M')} {event.get('summary', '(タイトルなし)')}")
        else:
            print(f"終日 {event.get('summary', '(タイトルなし)')}")


if __name__ == "__main__":
    get_today_events()
