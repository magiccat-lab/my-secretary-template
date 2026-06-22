"""秘書設定のロードユーティリティ。

secretaries.yaml から秘書定義を読み込み、シングル/マルチ秘書モードを
自動判定する。yaml が無い場合はデフォルト1体で動作（後方互換）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _secretary_dir() -> Path:
    return Path(os.environ.get("SECRETARY_DIR", Path.home() / "secretary"))


def _load_raw_config() -> dict[str, Any]:
    config_path = _secretary_dir() / "secretaries.yaml"
    if not config_path.exists():
        return {}

    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            f"secretaries.yaml が存在しますが PyYAML がインストールされていません。"
            f" pip install PyYAML>=6.0 を実行してください。"
        )

    text = config_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise RuntimeError(f"secretaries.yaml のパースに失敗: {e}")

    if not isinstance(data, dict):
        raise RuntimeError(f"secretaries.yaml のトップレベルが dict ではありません: {type(data)}")

    return data


def _resolve_env(env_name: str, default: str = "") -> str:
    """_env フィールドの値を実際の環境変数から解決する。"""
    if not env_name:
        return default
    return os.environ.get(env_name, default)


def _default_secretary_entry() -> dict[str, Any]:
    return {
        "id": "default",
        "display_name": "Secretary",
        "identity": "AGENT/IDENTITY.md",
        "sender": {"kind": "bot_token", "webhook_url_env": ""},
        "channels": {
            "default_env": "DISCORD_CHANNEL_RANDOM",
            "allowlist_envs": [],
        },
        "state": {
            "data_dir": "data",
            "tasks": "data/pending_tasks.json",
            "handoff": "data/handoff.md",
        },
        "jobs": {"enabled_tags": ["all"]},
    }


def load_config() -> dict[str, Any]:
    """設定全体を返す。yaml が無ければデフォルト構造を生成。"""
    raw = _load_raw_config()
    if not raw or "secretaries" not in raw:
        return {
            "version": 1,
            "default_secretary": "default",
            "runtime": {"mode": "single"},
            "secretaries": {"default": _default_secretary_entry()},
        }
    return raw


def load_secretaries() -> dict[str, dict[str, Any]]:
    """秘書 ID → 定義の dict を返す。"""
    config = load_config()
    secs = config.get("secretaries", {})
    if not secs:
        return {"default": _default_secretary_entry()}
    result = {}
    for sec_id, entry in secs.items():
        result[sec_id] = {
            "id": sec_id,
            "display_name": entry.get("display_name", sec_id),
            "identity": entry.get("identity", "AGENT/IDENTITY.md"),
            "sender": entry.get("sender", {"kind": "bot_token"}),
            "channels": entry.get("channels", {}),
            "state": entry.get("state", {}),
            "jobs": entry.get("jobs", {"enabled_tags": ["all"]}),
        }
    return result


def resolve_secretary(
    secretary_id: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """秘書を解決する。

    優先順: 引数 secretary_id > SECRETARY_ID env > channel ルーティング > default
    CLI 明示引数が最優先（env が残っていても上書きされない）。
    """
    config = load_config()
    secs = load_secretaries()

    if secretary_id and secretary_id in secs:
        return secs[secretary_id]

    env_id = os.environ.get("SECRETARY_ID", "")
    if env_id and env_id in secs:
        return secs[env_id]

    if channel_id:
        for sec_id, sec in secs.items():
            channels = sec.get("channels", {})
            allowlist_envs = channels.get("allowlist_envs", [])
            if not allowlist_envs:
                continue
            for env_name in allowlist_envs:
                if _resolve_env(env_name) == channel_id:
                    return sec

    default_id = config.get("default_secretary", "")
    if default_id and default_id in secs:
        return secs[default_id]

    return next(iter(secs.values())) if secs else _default_secretary_entry()


def get_secretary_for_job(job_name: str, job_tags: list[str] | None = None) -> dict[str, Any]:
    """指定ジョブを担当する秘書を返す。"""
    secs = load_secretaries()
    tags = job_tags or [job_name]

    for sec_id, sec in secs.items():
        enabled = sec.get("jobs", {}).get("enabled_tags", ["all"])
        if "all" in enabled:
            return sec
        if any(t in enabled for t in tags):
            return sec

    config = load_config()
    default_id = config.get("default_secretary", "")
    if default_id in secs:
        return secs[default_id]
    return next(iter(secs.values())) if secs else _default_secretary_entry()


def get_tasks_path(secretary_id: str | None = None) -> str:
    """秘書のタスクファイルパスを返す。

    secretary_id 指定時は config の state.tasks を使う（PENDING_TASKS_PATH は無視）。
    未指定時のみ PENDING_TASKS_PATH をレガシー互換として参照。
    """
    if not secretary_id:
        env_path = os.environ.get("PENDING_TASKS_PATH")
        if env_path:
            p = Path(env_path)
            if not p.is_absolute():
                p = _secretary_dir() / p
            return str(p)
    sec = resolve_secretary(secretary_id=secretary_id)
    state = sec.get("state", {})
    rel = state.get("tasks", "data/pending_tasks.json")
    return str(_secretary_dir() / rel)


def get_sender_config(secretary_id: str | None = None) -> dict[str, Any]:
    """秘書の送信設定を返す。"""
    sec = resolve_secretary(secretary_id=secretary_id)
    sender = sec.get("sender", {"kind": "bot_token"})
    if sender.get("kind") == "webhook":
        url = _resolve_env(sender.get("webhook_url_env", ""))
        return {"kind": "webhook", "webhook_url": url, "display_name": sec["display_name"]}
    return {"kind": "bot_token", "display_name": sec["display_name"]}


def is_multi_secretary() -> bool:
    return len(load_secretaries()) > 1
