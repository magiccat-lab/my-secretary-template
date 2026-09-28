# webhook.md — webhook_server.py

cron・スマホショートカット・ホームオートメーションからのHTTP pingを
受けて、Discordに直接送るか Claude Code にプロンプトとして渡すFastAPI。
既定は `127.0.0.1:8781`（`WEBHOOK_HOST`）のみ待受。外部公開は6節参照。

---

## 1. エンドポイント

| パス | 用途 | 認証 |
|------|------|------|
| `POST /remind` | スクリプト用リマインド送信、必要ならタスクも追加 | 要トークン |
| `POST /gmail_notify` | `gmail_monitor.py` が新着メール時に叩く | 要トークン |
| `GET  /health` | ヘルスチェック（`health_check.sh` が使う） | 不要 |

---

## 2. 起動

通常は `start_server.sh` の中で `secretary` screenセッションが起動する。
手動で動かすなら:

```bash
python3 ~/secretary/scripts/webhook_server.py
```

---

## 3. 認証（組み込み）

`.env` の `WEBHOOK_TOKEN`（SETUP.md F で生成した物）を全 POST エンドポイント
が検証する。`WEBHOOK_TOKEN` が空だとサーバーは起動時にエラーを出して
終了する（`sys.exit(1)`。手で `python3 scripts/webhook_server.py` した時も
同じ）。

ヘッダはどちらでも通る:

```
X-Webhook-Token: <WEBHOOK_TOKEN>
```
または
```
Authorization: Bearer <WEBHOOK_TOKEN>
```

一致しない・欠落している場合は 401 `{"status": "unauthorized"}`。
`GET /health` だけは無認証（`health_check.sh` の死活監視用）。

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
Editして以下のような関数を足す（`dependencies=[Depends(require_token)]` を
付けると他のエンドポイントと同じ認証がかかる）:

```python
@app.post("/my_feature", dependencies=[Depends(require_token)])
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

既定は `WEBHOOK_HOST=127.0.0.1` のみ待受（外から直接は繋がらない）。
外に出すなら:
1. `WEBHOOK_HOST=0.0.0.0` にする + 手前に TLS 付き reverse proxy
   （nginx / Caddy）を必ず置く
2. `WEBHOOK_TOKEN` は必須（未設定だと起動しない。セクション3参照）

それ以外（reverse proxy を用意しない・一時的に手元から叩きたいだけ）は
`WEBHOOK_HOST` を `127.0.0.1` のままにして `ssh -L 8781:localhost:8781`
でトンネル。

---

## 7. トラブル

落ちている・返らないときは `docs/ops.md` のトラブルシューティングを参照。

最初に確認:
```bash
curl -s http://localhost:8781/health
lsof -i :8781
```

401 が返る時は呼ぶ側のヘッダを疑う。`X-Webhook-Token` か
`Authorization: Bearer` のどちらかが必要で、値は `.env` の
`WEBHOOK_TOKEN` と一致している必要がある（呼び出し元が古い値を
キャッシュ・ハードコードしていないかも確認）。
