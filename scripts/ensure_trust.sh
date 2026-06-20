#!/bin/bash
# .claude.json の trust 設定を確認・修正する共通関数
# 使い方: source scripts/ensure_trust.sh && ensure_trust

ensure_trust() {
    python3 -c "
import json, os
path = os.path.expanduser('~/.claude.json')
secretary = os.path.expanduser('~/secretary')
try:
    with open(path) as f: d = json.load(f)
    for p in [os.path.expanduser('~'), secretary]:
        d.setdefault('projects', {}).setdefault(p, {})['hasTrustDialogAccepted'] = True
    with open(path, 'w') as f: json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
except Exception as e:
    print(f'trust fix error: {e}')
" 2>/dev/null || true
}
