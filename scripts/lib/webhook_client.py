"""webhook_server.py への POST ラッパー。

task_remind.py / gcal_remind.py / gmail_monitor.py 等の呼び出し側はこれ経由で
webhook を叩く。WEBHOOK_PORT / WEBHOOK_TOKEN の変更をここ1箇所に閉じ込め、
トークン未設定のまま黙って401を食らう事故を防ぐ。

使い方:

    from scripts.lib import webhook_client

    webhook_client.post("/gmail_notify", {"sender": "...", "subject": "...", "body": "..."})
    webhook_client.remind("30分後に予定があります", channel=DISCORD_CHANNEL_RANDOM)

環境変数:
    WEBHOOK_BASE   webhook サーバーのベース URL（例: http://127.0.0.1:8781）。
                   未設定なら http://127.0.0.1:{WEBHOOK_PORT or 8781} を使う
    WEBHOOK_PORT   webhook サーバーの port（デフォルト 8781。WEBHOOK_BASE 未設定時のみ使う）
    WEBHOOK_TOKEN  必須。空だと WebhookConfigError を投げる
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# env が優先（load_dotenv はデフォルトで既存の環境変数を上書きしない）
load_dotenv(os.path.join(_REPO_ROOT, ".env"))


class WebhookConfigError(RuntimeError):
    """WEBHOOK_TOKEN 未設定など、呼び出し前提が満たされていない時に投げる。"""


def _base_url() -> str:
    base = os.environ.get("WEBHOOK_BASE")
    if base:
        return base.rstrip("/")
    port = os.environ.get("WEBHOOK_PORT", "8781")
    return f"http://127.0.0.1:{port}"


def post(path: str, payload: dict, timeout: int = 10) -> requests.Response:
    """webhook_server.py の POST エンドポイントを叩く。

    WEBHOOK_TOKEN が空なら黙って401を食らう前に WebhookConfigError を投げる。
    """
    token = os.environ.get("WEBHOOK_TOKEN", "")
    if not token:
        raise WebhookConfigError(
            "WEBHOOK_TOKEN が未設定。.env に書く（SETUP.md F）"
        )
    if not path.startswith("/"):
        path = "/" + path
    url = f"{_base_url()}{path}"
    headers = {"X-Webhook-Token": token}
    return requests.post(url, json=payload, headers=headers, timeout=timeout)


def remind(message: str, channel: str | None = None, task: str | None = None) -> requests.Response:
    """/remind の薄いヘルパー"""
    payload: dict = {"message": message}
    if channel:
        payload["channel"] = channel
    if task:
        payload["task"] = task
    return post("/remind", payload)
