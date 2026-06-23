"""Webhook server への認証付き HTTP client helper."""
from __future__ import annotations

import os

import requests


def _headers() -> dict[str, str]:
    token = os.getenv("WEBHOOK_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def post(url: str, *, json: dict, timeout: int = 10) -> requests.Response:
    return requests.post(url, json=json, headers=_headers(), timeout=timeout)
