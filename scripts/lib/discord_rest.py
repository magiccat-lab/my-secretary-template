#!/usr/bin/env python3
"""Discord REST APIを直叩きする薄いラッパー(進行状況表示: reaction/メッセージ編集用)。

呼び出し側には例外を投げない。失敗は全部 ~/secretary/data/logs/discord_rest.log
(パスは環境変数 SECRETARY_DIR で上書き可) に書いて False / None を返すだけにする。
hookの中から呼ばれる前提なので、ここで例外を漏らすとモデルのターンごと壊れる。

トークン読み込み(scripts/discord_send.pyと同じ流儀):
  1. 環境変数 DISCORD_BOT_TOKEN があればそれを使う
  2. 無ければ環境変数 DISCORD_ENV_FILE (デフォルト ~/.claude/channels/discord/.env) の
     `DISCORD_BOT_TOKEN=...` 行から読む
"""
import os
import time
import urllib.parse
from datetime import datetime, timezone

import requests

API_BASE = "https://discord.com/api/v10"
_TIMEOUT = 10
_MAX_RETRY_AFTER = 5.0


def _secretary_dir():
    return os.environ.get("SECRETARY_DIR") or os.path.expanduser("~/secretary")


def _log_path():
    return os.path.join(_secretary_dir(), "data", "logs", "discord_rest.log")


def _log(message):
    """失敗をログファイルに書く。ログ自体の失敗は握りつぶす(呼び出し側には伝えない)。"""
    try:
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _read_token_from(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1]
    return None


def load_token():
    """DISCORD_BOT_TOKENを取得する。見つからなければNone(例外は投げない)。

    優先順位: 環境変数 DISCORD_BOT_TOKEN
      → $DISCORD_ENV_FILE
      → $DISCORD_STATE_DIR/.env (専用botの.envを別途置きたいセッション向け。
        本体のトークンとは混ざらない)
      → ~/.claude/channels/discord/.env (デフォルト)
    """
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if token:
        return token

    candidates = []
    env_file = os.environ.get("DISCORD_ENV_FILE")
    if env_file:
        candidates.append(os.path.expanduser(env_file))
    state_dir = os.environ.get("DISCORD_STATE_DIR")
    if state_dir:
        candidates.append(os.path.join(os.path.expanduser(state_dir), ".env"))
    candidates.append(os.path.expanduser("~/.claude/channels/discord/.env"))

    last_error = None
    for path in candidates:
        try:
            token = _read_token_from(path)
        except Exception as e:
            last_error = e
            continue
        if token:
            return token
    if last_error is not None:
        _log(f"load_token失敗: {last_error}")
    return None


def _headers(token):
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def _request(method, url, token, json_body=None, retry=True):
    """1回だけ429リトライする内部呼び出し。例外は握りつぶしてNoneを返す。"""
    try:
        r = requests.request(method, url, headers=_headers(token), json=json_body, timeout=_TIMEOUT)
    except requests.RequestException as e:
        _log(f"{method} {url}: 通信エラー {e}")
        return None
    if r.status_code == 429 and retry:
        try:
            retry_after = float(r.json().get("retry_after", 1))
        except Exception:
            retry_after = 1.0
        time.sleep(min(retry_after, _MAX_RETRY_AFTER))
        return _request(method, url, token, json_body=json_body, retry=False)
    return r


def react(chat_id, message_id, emoji):
    """chat_id(=channel_id)のmessage_idにemojiでリアクションを付ける。成功でTrue。"""
    try:
        token = load_token()
        if not token:
            _log("react: token無し")
            return False
        q = urllib.parse.quote(emoji, safe="")
        url = f"{API_BASE}/channels/{chat_id}/messages/{message_id}/reactions/{q}/@me"
        r = _request("PUT", url, token)
        if r is not None and r.status_code in (200, 204):
            return True
        _log(f"react失敗: chat_id={chat_id} message_id={message_id} emoji={emoji} "
             f"status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:200]}")
        return False
    except Exception as e:
        _log(f"react例外: {e}")
        return False


def unreact(chat_id, message_id, emoji):
    """自分が付けたリアクションを外す(DELETE .../reactions/{emoji}/@me)。成功でTrue。"""
    try:
        token = load_token()
        if not token:
            _log("unreact: token無し")
            return False
        q = urllib.parse.quote(emoji, safe="")
        url = f"{API_BASE}/channels/{chat_id}/messages/{message_id}/reactions/{q}/@me"
        r = _request("DELETE", url, token)
        if r is not None and r.status_code in (200, 204):
            return True
        _log(f"unreact失敗: chat_id={chat_id} message_id={message_id} emoji={emoji} "
             f"status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:200]}")
        return False
    except Exception as e:
        _log(f"unreact例外: {e}")
        return False


def post(chat_id, text):
    """chat_id(=channel_id)に新規メッセージを送る。成功したらmessage_idを返す、失敗はNone。"""
    try:
        token = load_token()
        if not token:
            _log("post: token無し")
            return None
        url = f"{API_BASE}/channels/{chat_id}/messages"
        r = _request("POST", url, token, json_body={"content": text})
        if r is not None and r.status_code in (200, 201):
            try:
                return r.json().get("id")
            except Exception:
                _log("post: 応答JSONの解析に失敗")
                return None
        _log(f"post失敗: chat_id={chat_id} status={getattr(r, 'status_code', None)} "
             f"body={getattr(r, 'text', '')[:200]}")
        return None
    except Exception as e:
        _log(f"post例外: {e}")
        return None


def edit(chat_id, message_id, text):
    """既存メッセージの本文を差し替える。成功でTrue。"""
    try:
        token = load_token()
        if not token:
            _log("edit: token無し")
            return False
        url = f"{API_BASE}/channels/{chat_id}/messages/{message_id}"
        r = _request("PATCH", url, token, json_body={"content": text})
        if r is not None and r.status_code in (200, 201):
            return True
        _log(f"edit失敗: chat_id={chat_id} message_id={message_id} "
             f"status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:200]}")
        return False
    except Exception as e:
        _log(f"edit例外: {e}")
        return False


def delete(chat_id, message_id):
    """メッセージを削除する。成功でTrue(404=既に無い、も冪等に成功扱い)。"""
    try:
        token = load_token()
        if not token:
            _log("delete: token無し")
            return False
        url = f"{API_BASE}/channels/{chat_id}/messages/{message_id}"
        r = _request("DELETE", url, token)
        if r is not None and r.status_code in (200, 204, 404):
            return True
        _log(f"delete失敗: chat_id={chat_id} message_id={message_id} "
             f"status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:200]}")
        return False
    except Exception as e:
        _log(f"delete例外: {e}")
        return False
