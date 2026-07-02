"""アトミックな JSON ステートファイルハンドラー。

cron スクリプトで散らばりがちな load_state / save_state を置き換える。

使い方:

    from scripts.lib.state_store import load_state, save_state, update_state

    state = load_state("/tmp/foo.json", default={"seen_ids": []})
    state["seen_ids"].append("new_id")
    save_state("/tmp/foo.json", state)

    # 安全な read-modify-write:
    with update_state("/tmp/foo.json", default={"count": 0}) as state:
        state["count"] += 1
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any


@contextlib.contextmanager
def _state_lock(p: Path) -> Iterator[None]:
    p.parent.mkdir(parents=True, exist_ok=True)
    lock_path = p.with_suffix(p.suffix + ".lock")
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def _load_state_unlocked(p: Path, default: Any | None = None) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save_state_unlocked(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def load_state(path: str | Path, default: Any | None = None) -> Any:
    """JSON ステートを読み込む。ファイルが無い / 壊れている場合は default"""
    p = Path(path)
    return _load_state_unlocked(p, default=default)


def save_state(path: str | Path, data: Any, *, use_lock: bool = True) -> None:
    """アトミックに JSON ステートを書く（tmp + rename、任意で flock）"""
    p = Path(path)
    if use_lock:
        with _state_lock(p):
            _save_state_unlocked(p, data)
    else:
        _save_state_unlocked(p, data)


@contextlib.contextmanager
def update_state(path: str | Path, default: Any | None = None) -> Iterator[Any]:
    """read-modify-write のコンテキストマネージャ"""
    p = Path(path)
    with _state_lock(p):
        state = _load_state_unlocked(p, default=default)
        try:
            yield state
        except Exception:
            raise
        else:
            _save_state_unlocked(p, state)
