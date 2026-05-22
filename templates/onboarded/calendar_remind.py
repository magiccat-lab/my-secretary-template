#!/usr/bin/env python3
from __future__ import annotations
"""Sample task: send daily calendar agenda."""

import datetime as dt
import os
import sys

def main() -> int:
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        print("GOOGLE_CALENDAR_ID is not set. Configure Google Calendar before enabling this sample.", file=sys.stderr)
        return 1

    now = dt.datetime.now()
    print(f"Calendar reminder sample for {calendar_id} at {now.isoformat(timespec='seconds')}")
    print("For production use, use scripts/integrations/gcal/gcal_remind.py.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
