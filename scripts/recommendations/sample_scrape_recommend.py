#!/usr/bin/env python3
from __future__ import annotations
"""Sample: daily YouTube search → 3 recs with dedupe state."""

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "recommend_seen.json"

def load_seen() -> set[str]:
    if not STATE.exists():
        return set()
    return set(json.loads(STATE.read_text(encoding="utf-8")).get("seen", []))

def save_seen(seen: set[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"seen": sorted(seen)[-1000:]}, indent=2), encoding="utf-8")

def search_youtube(query: str) -> list[dict]:
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    results = []
    for line in [x.strip() for x in text.splitlines() if x.strip()]:
        if len(line) < 12 or len(line) > 120:
            continue
        key = hashlib.sha256(line.encode()).hexdigest()[:16]
        results.append({"id": key, "title": line, "url": url})
        if len(results) >= 20:
            break
    return results

def post_discord(message: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print(message)
        return
    requests.post(webhook, json={"content": message[:1900]}, timeout=15).raise_for_status()

def main() -> int:
    query = os.environ.get("RECOMMEND_YOUTUBE_QUERY", "productivity tools")
    seen = load_seen()
    picked = []
    for item in search_youtube(query):
        if item["id"] in seen:
            continue
        picked.append(item)
        seen.add(item["id"])
        if len(picked) == 3:
            break

    if not picked:
        print("no new recommendations")
        return 0

    lines = [f"Morning recommendations: {query}"]
    lines.extend(f"- {x['title']}\n  {x['url']}" for x in picked)
    post_discord("\n".join(lines))
    save_seen(seen)
    return 0

if __name__ == "__main__":
    sys.exit(main())
