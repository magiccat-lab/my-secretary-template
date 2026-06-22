#!/usr/bin/env python3
"""先輩待ちタスクリマインダー - 未完了タスクがあれば通知"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

WEBHOOK_PORT = os.getenv('WEBHOOK_PORT', '8781')
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN', '')
WEBHOOK = f'http://localhost:{WEBHOOK_PORT}/remind'
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_RANDOM', '')


def _resolve_tasks_file() -> str:
    try:
        from config import get_tasks_path
        return get_tasks_path()
    except Exception:
        return os.getenv('PENDING_TASKS_PATH', os.path.expanduser('~/secretary/data/pending_tasks.json'))


def main():
    tasks_file = _resolve_tasks_file()
    if not os.path.exists(tasks_file):
        return

    with open(tasks_file) as f:
        data = json.load(f)

    all_tasks = []
    if 'tasks' in data:
        all_tasks = [t for t in data['tasks'] if not t.get('done')]
    else:
        primary_tasks = [t for t in data.get('primary', []) if not t.get('done')]
        secondary_tasks = [t for t in data.get('secondary', []) if not t.get('done')]
        if primary_tasks:
            all_tasks += [{'title': f'[Primary] {t["title"]}', **t} for t in primary_tasks]
        if secondary_tasks:
            all_tasks += [{'title': f'[Secondary] {t["title"]}', **t} for t in secondary_tasks]

    if not all_tasks:
        return

    lines = ['**未完了タスク**']
    for t in all_tasks:
        lines.append(f'・{t["title"]}')

    message = '\n'.join(lines)
    headers = {}
    if WEBHOOK_TOKEN:
        headers['Authorization'] = f'Bearer {WEBHOOK_TOKEN}'
    requests.post(WEBHOOK, json={
        'channel_id': CHANNEL_ID,
        'message': message
    }, headers=headers, timeout=10)

if __name__ == '__main__':
    main()
