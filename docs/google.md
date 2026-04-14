# google.md — Google 連携（Calendar / Gmail / Sheets）

3つのAPIは1つのOAuthトークン（`integrations/gcal/token.json`）を共有する。
Sheetsまわりのタスクミラーは `docs/tasks.md` に分離。

---

## 1. トリガーフレーズ
- 「カレンダー繋ぎたい」「Gmail 監視させたい」「Sheets でタスク見たい」
- `invalid_grant` / `token expired` / 403 が出ているとき

---

## 2. Google Cloud 側の準備（ユーザー操作）

1. https://console.cloud.google.com → プロジェクト作成
2. **APIs & Services → Enabled APIs** で以下を有効化:
   - Google Calendar API
   - Gmail API
   - Google Sheets API（タスクシート機能を使うときだけ）
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
4. アプリケーションタイプ: **Desktop app**
5. JSONをダウンロード → エージェントに「DLしたファイルどこ？」と聞いて
   `integrations/gcal/credentials.json` に置く（ユーザーがscp / sftpで
   送ってもらう、もしくは内容をテキストで貼ってもらってエージェントがWrite）

---

## 3. 認証フロー実行

```bash
python3 ~/secretary/integrations/gcal/reauth.py
```

スクリプトの動き:
1. 認証URLを出力
2. ユーザーがブラウザで開いてアクセス許可
3. Googleが `http://localhost:8080/?code=...` にリダイレクト
   （ブラウザは「アクセスできません」でも問題なし、URLバーから取れればOK）
4. **URL全体**をスクリプトのプロンプトに貼り戻す
5. `token.json` が書き込まれる

---

## 4. ヘッドレス VPS の場合（GUI ブラウザがない）

### A. SSHトンネル（推奨）
```bash
# 手元のPCで別ターミナル
ssh -L 8080:localhost:8080 user@your-vps
# VPSでreauth.py実行 → 表示URLを手元ブラウザで開く → 自動で認証完了
```

### B. URL 手貼り
1. VPSで `reauth.py` 実行 → URLコピー
2. 任意の端末のブラウザで開く → 承認
3. Googleがリダイレクトした `http://localhost:8080/?code=...` のURLを
   そのままコピー
4. VPSのスクリプトのプロンプトに貼る

---

## 5. `.env` を埋める

```
GOOGLE_TOKEN_PATH=integrations/gcal/token.json
GCAL_CALENDAR_ID=primary           # または your-calendar@gmail.com
GCAL_REMIND_ENABLED=true
GMAIL_ENABLED=true                 # Gmail も使うなら
```

---

## 6. テスト

```bash
python3 ~/secretary/integrations/gcal/gcal_today.py
python3 ~/secretary/integrations/gmail/gmail_monitor.py
```

---

## 7. cron 登録

```cron
* * * * * /usr/bin/python3 /home/YOUR_USER/secretary/integrations/gcal/gcal_remind.py >> /tmp/gcal_remind.log 2>&1
* * * * * /usr/bin/python3 /home/YOUR_USER/secretary/integrations/gmail/gmail_monitor.py >> /tmp/gmail_monitor.log 2>&1
```

cron全般の注意点（フルパス・HOME・JST）は `docs/cron.md` 参照。

---

## 8. 再認証

refresh tokenが生きていれば自動更新。`invalid_grant` 等が出たら:

```bash
python3 ~/secretary/integrations/gcal/reauth.py
```

新しい `token.json` ができればCalendar / Gmailスクリプトは自動で読む。

---

## 9. 課金

- Calendar API: 無料（標準クォータ）
- Gmail API: 無料（250 quota units / user / sec）
- Sheets API: 無料（300 req / min）

このテンプレートはGoogle側に課金が発生する処理を一切しない。
