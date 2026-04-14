# webhook.md — webhook_server.py

cron・スマホショートカット・ホームオートメーションからのHTTP pingを
受けて、Discordに直接送るか Claude Code にプロンプトとして渡すFastAPI。
`0.0.0.0:8781` で待つ。

---

## 1. エンドポイント

| パス | 用途 |
|------|------|
| `POST /remind` | スクリプト用リマインド送信、必要ならタスクも追加 |
| `POST /gmail_notify` | `gmail_monitor.py` が新着メール時に叩く |
| `GET  /health` | ヘルスチェック（`health_check.sh` が使う） |

---

## 2. 起動

通常は `start_server.sh` の中で `secretary` screenセッションが起動する。
手動で動かすなら:

```bash
python3 ~/secretary/scripts/webhook_server.py
```

---

## 3. 認証

デフォルトはlocalhostオープン。外に出すなら `.env` の `WEBHOOK_TOKEN`
を必須化する。`webhook_server.py` の各エンドポイントに以下を追加:

```python
token = request.headers.get("X-Webhook-Token")
if token != os.getenv("WEBHOOK_TOKEN"):
    return {"status": "unauthorized"}, 401
```

呼ぶ側はヘッダで送る:

```bash
curl -X POST http://host:8781/remind \
  -H "X-Webhook-Token: $WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"hi","channel":"CH_ID"}'
```

---

## 4. エンドポイントを追加する

ユーザーが「webhookでXしたい」と言ってきたら、`webhook_server.py` を
Editして以下のような関数を足す:

```python
@app.post("/my_feature")
async def my_feature(request: Request):
    body = await request.json()
    # A: 直接送信
    discord_send(CH_RANDOM, f"heard: {body.get('text')}")
    # B: Claude に投げる
    await send_to_claude(f"do X with {body}")
    return {"status": "ok"}
```

編集後はサーバー再起動（`screen -r secretary` でwebhookウィンドウ → Ctrl+C
→ 上矢印で同じコマンド）またはユーザーに `bash ~/secretary/start_server.sh`
を打ってもらう。

---

## 5. systemd でサービス化（VPS 推奨）

ユーザーが「webhookをsystemd化したい」と言ったら以下をWriteする:

```bash
sudo tee /etc/systemd/system/secretary-webhook.service > /dev/null <<'EOF'
[Unit]
Description=Secretary webhook server
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/secretary
ExecStart=/usr/bin/python3 /home/YOUR_USER/secretary/scripts/webhook_server.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable secretary-webhook
sudo systemctl start secretary-webhook
sudo systemctl status secretary-webhook
```

`YOUR_USER` を実usernameに置換してから渡す。
systemd化したら `start_server.sh` の `screen -X screen -t webhook ...`
の行は消して二重起動を防ぐこと（Editで対応）。

---

## 6. ネットワーク公開

webhookサーバーは `0.0.0.0:8781`。外に出すなら:
1. リバースプロキシ（nginx / Caddy）の後ろに置く
2. `WEBHOOK_TOKEN` を必須化（セクション3参照）
3. TLS（Caddyなら自動）

逆に閉じる派なら、localhostのみにバインドして
`ssh -L 8781:localhost:8781` でトンネル。

---

## 7. トラブル

落ちている・返らないときは `docs/ops.md` のトラブルシューティングを参照。

最初に確認:
```bash
curl -s http://localhost:8781/health
lsof -i :8781
```
