#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import sys
from email import message_from_bytes
from email.header import decode_header
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[2]
TOKEN_PATH = Path(os.environ.get("GOOGLE_TOKEN_PATH", ROOT / "integrations" / "gcal" / "token.json"))
GMAIL_TOKEN_PATH = Path(os.environ.get("GMAIL_TOKEN", ROOT / "integrations" / "gmail" / "token.json"))
RULES_PATH = Path(os.environ.get("GMAIL_RULES_PATH", ROOT / "integrations" / "gmail" / "filter_rules.yaml"))
STATE_PATH = Path(os.environ.get("GMAIL_STATE_PATH", ROOT / "data" / "gmail_monitor_state.json"))
QUERY = os.environ.get("GMAIL_QUERY", "is:unread newer_than:7d")
MAX_RESULTS = int(os.environ.get("GMAIL_MAX_RESULTS", "10"))
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def decode_value(value: str) -> str:
    out = ""
    for part, enc in decode_header(value or ""):
        if isinstance(part, bytes):
            out += part.decode(enc or "utf-8", errors="replace")
        else:
            out += part
    return out


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"seen_ids": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen_ids": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def simple_yaml(path: Path) -> dict:
    data: dict[str, dict[str, list[str] | bool]] = {"notify": {}, "exclude": {}}
    section = ""
    key = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            section = stripped[:-1]
            data.setdefault(section, {})
            key = ""
        elif section and line.startswith("  ") and stripped.endswith(":"):
            key = stripped[:-1]
            data[section][key] = []
        elif section and key and stripped.startswith("- "):
            value = stripped[2:].strip().strip('"').strip("'")
            target = data[section].setdefault(key, [])
            if isinstance(target, list):
                target.append(value)
        elif ":" in stripped:
            left, right = stripped.split(":", 1)
            data[left.strip()] = right.strip().lower() == "true"  # type: ignore[assignment]
    return data


def load_rules() -> dict:
    if not RULES_PATH.exists():
        return {"notify": {"senders": [], "keywords": [], "labels": []}, "exclude": {"senders": [], "keywords": []}, "mark_read_after_notify": True}
    try:
        import yaml  # type: ignore

        return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return simple_yaml(RULES_PATH)


def gmail_service():
    primary_path = TOKEN_PATH if TOKEN_PATH.is_absolute() else ROOT / TOKEN_PATH
    fallback_path = GMAIL_TOKEN_PATH if GMAIL_TOKEN_PATH.is_absolute() else ROOT / GMAIL_TOKEN_PATH
    credentials_path = primary_path if primary_path.exists() else fallback_path
    creds = Credentials.from_authorized_user_file(str(credentials_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        credentials_path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def message_text(payload: dict) -> str:
    raw = payload.get("raw", "")
    if not raw:
        return ""
    msg = message_from_bytes(base64.urlsafe_b64decode(raw.encode("utf-8")))
    return "\n".join(
        [
            decode_value(msg.get("From", "")),
            decode_value(msg.get("Subject", "")),
            payload.get("snippet", ""),
        ]
    )


def matches(values: list[str], text: str) -> bool:
    low = text.lower()
    return any(value.lower() in low for value in values if value)


def should_notify(item: dict, rules: dict) -> bool:
    text = item["text"]
    labels = " ".join(item.get("labelIds", []))
    exclude = rules.get("exclude", {})
    if matches(exclude.get("senders", []), item["from"]) or matches(exclude.get("keywords", []), text):
        return False
    notify = rules.get("notify", {})
    senders = notify.get("senders", [])
    keywords = notify.get("keywords", [])
    rule_labels = notify.get("labels", [])
    if not senders and not keywords and not rule_labels:
        return True
    return matches(senders, item["from"]) or matches(keywords, text) or matches(rule_labels, labels)


def post_discord(text: str) -> None:
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if discord_webhook:
        requests.post(discord_webhook, json={"content": text}, timeout=10)
        return
    local_webhook = os.environ.get("WEBHOOK_URL", "http://localhost:8781/gmail_notify")
    if local_webhook:
        requests.post(local_webhook, json={"message": text}, timeout=10)
        return
    channel_id = os.environ.get("DISCORD_CHANNEL_RANDOM", "")
    if not channel_id:
        print("No Discord destination configured", file=sys.stderr)
        return
    sys.path.insert(0, str(ROOT))
    from scripts.lib.discord_post import post

    result = post(channel_id=channel_id, text=text)
    if not result.get("ok"):
        print(result.get("error"), file=sys.stderr)


def main() -> int:
    if not env_bool("FEATURE_GMAIL"):
        print("FEATURE_GMAIL is not true; skipping")
        return 0
    rules = load_rules()
    state = load_state()
    seen = set(state.get("seen_ids", []))
    service = gmail_service()
    response = service.users().messages().list(userId="me", q=QUERY, maxResults=MAX_RESULTS).execute()
    messages = response.get("messages", [])
    if not STATE_PATH.exists():
        state["seen_ids"] = [row["id"] for row in messages][-500:]
        save_state(state)
        print(f"initialized seen_ids={len(state['seen_ids'])}")
        return 0
    new_seen = set()
    for row in messages:
        mid = row["id"]
        if mid in seen:
            continue
        detail = service.users().messages().get(userId="me", id=mid, format="raw").execute()
        msg = message_from_bytes(base64.urlsafe_b64decode(detail["raw"].encode("utf-8")))
        item = {
            "id": mid,
            "from": decode_value(msg.get("From", "")),
            "subject": decode_value(msg.get("Subject", "")),
            "snippet": detail.get("snippet", ""),
            "labelIds": detail.get("labelIds", []),
            "text": message_text(detail),
        }
        new_seen.add(mid)
        if not should_notify(item, rules):
            continue
        text = f"Email matched rule\nFrom: {item['from'][:160]}\nSubject: {item['subject'][:160]}\nSnippet: {item['snippet'][:500]}"
        post_discord(text)
        if rules.get("mark_read_after_notify", True):
            service.users().messages().modify(userId="me", id=mid, body={"removeLabelIds": ["UNREAD"]}).execute()
    state["seen_ids"] = list((seen | new_seen))[-500:]
    save_state(state)
    print(f"checked={len(messages)} new={len(new_seen)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
