#!/usr/bin/env python3
"""先輩待ちタスクリマインダー - 未完了タスクがあれば通知"""
import os
import sys

# スクリプトとして実行したときに `from scripts.lib...` でインポートできるようにする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from scripts.lib.task_store import DEFAULT_SECTION, get_active, load_tasks  # noqa: E402
from scripts.lib import webhook_client  # noqa: E402

CHANNEL_ID = os.getenv('DISCORD_CHANNEL_RANDOM', '')

# primary/secondary は昔からの接頭辞規則を維持。それ以外のセクションが増えても
# 拾えるよう汎用フォールバックを用意する
_SECTION_LABELS = {
    DEFAULT_SECTION: '[Primary] ',
    'secondary': '[Secondary] ',
}


def _label(section: str) -> str:
    if section in _SECTION_LABELS:
        return _SECTION_LABELS[section]
    return f'[{section.capitalize()}] '


def _collect_active_tasks() -> list[dict]:
    """primary/secondary 他、全 list セクションから remind_at が未来のものを除いた
    未完了タスクを集める（旧形式 tasks は task_store 側で primary に正規化される）。"""
    data = load_tasks()
    sections = [s for s, v in data.items() if isinstance(v, list)]
    # primary → secondary → その他 の順（旧来の並びを踏襲）
    ordered = [s for s in (DEFAULT_SECTION, 'secondary') if s in sections]
    ordered += [s for s in sections if s not in ordered]

    all_tasks = []
    for section in ordered:
        for t in get_active(section):
            all_tasks.append({**t, 'title': f'{_label(section)}{t["title"]}'})
    return all_tasks


def main():
    all_tasks = _collect_active_tasks()
    if not all_tasks:
        return

    lines = ['**未完了タスク**']
    for t in all_tasks:
        lines.append(f'・{t["title"]}')

    message = '\n'.join(lines)
    webhook_client.remind(message, channel=CHANNEL_ID)


if __name__ == '__main__':
    main()
