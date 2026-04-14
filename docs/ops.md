# ops.md — 運用（死活監視・handoff・再起動・ログ・トラブル）

24/7稼働を回すための運用情報と、壊れたときのランブック。

> 初回起動・セットアップ直後の疎通確認は `/SETUP.md` I〜J を参照。
> このファイルは運用中の切り分けと深いトラブルシューティングが主務。

---

## 1. 起動・再起動（運用中の操作）

```bash
bash ~/secretary/start_server.sh     # 起動 or 再起動
screen -list                          # secretary が出れば screen は OK
curl -s http://localhost:8781/health  # {"status":"ok",...} が返れば webhook OK
screen -r secretary                   # 中身を見る（Ctrl+A D でデタッチ）
```

落ちているときは以下でクリーンに落として起動し直す:
```bash
screen -S secretary -X quit
pkill -f "claude --dangerously-skip-permissions"
bash ~/secretary/start_server.sh
```

---

## 2. 死活監視

`scripts/health_check.sh` を `*/5 * * * *` で回す。webhook / screen / claude
のどれかが落ちていたら再起動する。cron登録行は `docs/cron.md` 参照。

監視役自体が落ちたら5分後のcronで再試行。心配なら
UptimeRobot / BetterStack 等から `/health` を外部ping。

---

## 3. デイリー handoff

`scripts/daily_handoff.py` を `0 3 * * *`（または停止前に手動実行）。
`data/handoff.md` を書いて、次のセッションが引き継げるようにする。

`AGENT/AGENTS.md` の「セッション引き継ぎ」ルールと連動: 起動直後に
`data/handoff.md` があれば読んでDiscordに要約を送る。

---

## 4. 週次再起動（オプション）

`scripts/weekly_restart.sh` が日曜03:10にコールドリスタート。
デフォルトはコメントアウト。1〜2週間問題なく回せたら有効化推奨。

```cron
10 3 * * 0 /bin/bash /home/YOUR_USER/secretary/scripts/weekly_restart.sh >> /tmp/weekly_restart.log 2>&1
```

---

## 5. ログ

`/tmp/*.log` がデフォルト。再起動で消える。永続化したいなら:

```bash
mkdir -p ~/secretary/logs
```

cronのリダイレクト先を `~/secretary/logs/` に変更し、logrotateを設定:

```bash
sudo tee /etc/logrotate.d/secretary > /dev/null <<'EOF'
/home/YOUR_USER/secretary/logs/*.log {
    daily
    rotate 7
    missingok
    compress
    notifempty
}
EOF
```

---

## 6. バックアップ

`~/secretary/data/` だけをプライベートGitHubリポに毎晩push:

```cron
45 0 * * * cd /home/YOUR_USER/secretary && git add data memory 2>/dev/null && git commit -m "auto backup $(date +\%F)" 2>/dev/null && git push 2>&1 >> /tmp/git_push.log
```

`.gitignore` で `integrations/*/token.json`,
`integrations/*/credentials.json`, `.env` を除外（テンプレート設定済み）。

---

## 7. モニタリング（error_db / metrics_db）

`scripts/lib/error_db.py` と `scripts/lib/metrics_db.py` は同梱済み。
SQLiteに失敗・実行時間を記録する。

### 7.1 使い方（自作スクリプトに付ける）
```python
from scripts.lib.error_db import track_errors
from scripts.lib.metrics_db import track_metrics

@track_errors("my_cron_job")
@track_metrics("my_cron_job")
def main():
    ...
```

### 7.2 問い合わせ
```bash
python3 scripts/lib/error_db.py recent --hours 24
python3 scripts/lib/error_db.py summary
python3 scripts/lib/metrics_db.py stats --hours 168
```

### 7.3 デイリーダイジェスト
ユーザーが「エラー通知が欲しい」と言ったら `scripts/daily_error_digest.py`
をWrite:

```python
#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.lib.error_db import recent_errors, error_summary
from scripts.lib.discord_post import post

errs = recent_errors(hours=24, limit=200)
if errs:
    post(os.environ["DISCORD_CHANNEL_RANDOM"], f"Errors in last 24h: {error_summary(errs)}")
```

cron:
```cron
0 8 * * * /usr/bin/python3 /home/YOUR_USER/secretary/scripts/daily_error_digest.py
```

### 7.4 保持期間
週次クリーンアップ:
```cron
0 4 * * 0 /usr/bin/python3 /home/YOUR_USER/secretary/scripts/lib/error_db.py cleanup --days 30
0 4 * * 0 /usr/bin/python3 /home/YOUR_USER/secretary/scripts/lib/metrics_db.py cleanup --days 30
```

### 7.5 もっと欲しいとき
ジョブごとの失敗しきい値、レート制限付きアラート、重大度ルーティングが
必要になったら `alert_manager.py` 相当を移植する。テンプレートは最小化の
ため意図的に外している。

---

## 8. screen vs systemd

- **screen（テンプレートのデフォルト）**: `start_server.sh` が
  `screen -dmS secretary` で起動。`screen -r secretary` でアタッチ可能。
- **systemd**: 別解。堅牢だが見通しが悪い。テンプレート外。
  （webhookだけ systemd化する手順は `docs/webhook.md` セクション5参照）

---

## 9. トラブルシューティング

### 9.1 「bot が返信しない」

順番に確認:

**a. screen は生きてる？**
```bash
screen -list
```
無ければ `bash ~/secretary/start_server.sh`。

**b. webhook は上がってる？**
```bash
curl -s http://localhost:8781/health
```
返らないなら:
```bash
lsof -i :8781
python3 ~/secretary/scripts/webhook_server.py
```

**c. Claude Code はログイン済み？**
```bash
screen -r secretary
# "API Error: 401" / "Please run /login" が出てないか
```
出てたら `/login` → 終わったら Ctrl+A D。

**d. Discord プラグインの設定**
screen内で `/discord:configure` / `/discord:access`。allowlist確認。
詳細は `docs/discord.md`。

**e. cron は動いてる？**
```bash
sudo grep CRON /var/log/syslog | tail
tail -n 50 /tmp/task_remind.log
```

### 9.2 「cron スクリプトが黙って落ちる」
ほぼ以下のどれか:
- `PATH` 未設定 → フルパスで（`/usr/bin/python3`）
- `HOME` 未設定 → シェル先頭で `export HOME=...`
- リダイレクト無し → `>> /tmp/xxx.log 2>&1`

詳細ルールは `docs/cron.md` セクション3。

### 9.3 「Google API 403 / トークン失効」
```bash
python3 ~/secretary/integrations/gcal/reauth.py
```
URL開いて、リダイレクトURLを貼り戻す。詳細: `docs/google.md`。

### 9.4 「Claude Code が固まった」
```bash
screen -r secretary
# Ctrl+C → /exit
```
強制kill:
```bash
screen -S secretary -X quit
pkill -f "claude --dangerously-skip-permissions"
bash ~/secretary/start_server.sh
```

### 9.5 「Discord プラグインが拒否する」
- `~/.claude/channels/discord/.env` がある？読める？
- トークンまだ有効？（漏れた場合は開発者ポータルでローテート）
- botにチャンネル権限がある？

### 9.6 「health_check.sh が再起動ループする」
```bash
tail -n 50 /tmp/health_check.log
```
よくある原因:
- webhookポートが別プロセスに掴まれている
- Claude Codeが起動時に失敗（screenで確認）
- OAuth失効でAPI 401ループ

### 9.7 「タスクファイルが上書き / リセットされる」
詳細は `docs/tasks.md` セクション末尾。`fcntl.flock` と `update_tasks`
コンテキストマネージャを使う。

### 9.8 報告用テンプレ
ユーザーが「何か壊れた」と言ったら以下を集めてもらう:
```bash
screen -list
curl -s http://localhost:8781/health
tail -n 50 /tmp/health_check.log
tail -n 50 /tmp/task_remind.log
```
トークン伏字で Issue / Discord に貼ってもらう。
