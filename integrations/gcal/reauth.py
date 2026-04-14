#!/usr/bin/env python3
"""Calendar / Gmail / Sheets 用の Google OAuth を再認証する。

URL コピー貼り付け方式（ローカル Web サーバー不要）:
  1. このスクリプトを実行
  2. 表示された URL をブラウザで開く
  3. アクセスを許可すると、Google が http://localhost:8080/?code=... にリダイレクト
  4. そのリダイレクト URL 全体をコピーして、プロンプトに貼り付け
  5. token.json が integrations/gcal/token.json に書き込まれる

先に OAuth クライアントファイルを integrations/gcal/credentials.json に置いてください。
"""

from __future__ import annotations

import os
import sys
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow

_THIS_DIR = os.path.dirname(os.path.realpath(__file__))
CREDS_PATH = os.path.join(_THIS_DIR, "credentials.json")
TOKEN_PATH = os.path.join(_THIS_DIR, "token.json")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]

REDIRECT_URI = "http://localhost:8080/"


def main() -> int:
    if not os.path.exists(CREDS_PATH):
        print(f"{CREDS_PATH} が見つかりません", file=sys.stderr)
        print("先に Google Cloud Console から OAuth クライアント JSON をダウンロードしてください。")
        return 1

    flow = Flow.from_client_secrets_file(CREDS_PATH, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    print("以下の URL をブラウザで開いてアクセスを許可してください:\n")
    print(auth_url)
    print()
    redirect_url = input("リダイレクト後の localhost の URL 全体をここに貼り付けてください: ").strip()

    try:
        q = parse_qs(urlparse(redirect_url).query)
        code = q["code"][0]
    except Exception:
        print("URL から code をパースできませんでした", file=sys.stderr)
        return 1

    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"トークンを書き込みました: {TOKEN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
