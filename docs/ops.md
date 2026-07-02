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

## 4. 定期コールドリスタート（推奨）

`scripts/restart.sh` が handoff を残してからコールドリスタートする。会話コンテキストが
肥大して重く/不安定になるのを防ぐため、**毎日 03:00 の nightly を推奨**（24/7 運用なら
ほぼ必須）。スケジュールは cron 側で決める。

```cron
# 推奨: 毎日 03:00
0 3 * * * /bin/bash /home/YOUR_USER/secretary/scripts/restart.sh >> /tmp/restart.log 2>&1
# 週1で十分なら（日曜 03:10）:
# 10 3 * * 0 /bin/bash /home/YOUR_USER/secretary/scripts/restart.sh >> /tmp/restart.log 2>&1
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
python3 ~/secretary/integrations/google/reauth.py
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

### 9.9 Notion 同期が `failed` で出続ける
専用の切り分け手順は `docs/notion.md` セクション 5 参照。
よくある原因 4 種:
- `NOTION_API_KEY` 未設定 / 失効
- DB ID 間違い（URL から取り直す）
- Integration を DB に許可してない（DB 右上「…」→ Add connections）
- DB プロパティ名 / 型のミス（`docs/notion.md` §3 のスキーマと完全一致が必要）

### 9.10 `database is locked` エラー（SQLite）
`error_db.py` / `metrics_db.py` / `state_store.py` は SQLite に書く。同時実行が
競合するとロックが長引いて読み書き失敗することがある。

```bash
ls -la ~/secretary/data/*.db          # サイズが急に膨らんでないか
fuser ~/secretary/data/errors.db       # どのプロセスが掴んでるか
```

対処:
- 短期: 該当 cron を 1 分ずらして再発回避
- 中期: スクリプト側で `timeout=10` を `connect()` に渡す（テンプレ既定 5 秒）
- 長期: WAL モードに切替（`PRAGMA journal_mode=WAL;`）

### 9.11 cron が動いた形跡が無い
```bash
sudo grep CRON /var/log/syslog | tail -n 30
crontab -l                  # 自分の crontab 一覧
ls -la /tmp/*.log           # ログがそもそも作られてるか
```

cron は出力がリダイレクトされてないと黙って消える。`>> /tmp/xxx.log 2>&1` を
**全行に必ず付ける**（`docs/cron.md` §3）。

### 9.12 Disk が満杯
```bash
df -h /                    # / の使用率
du -sh /tmp/* | sort -h | tail -n 20  # /tmp 巨大ファイル特定
du -sh ~/secretary/data/* | sort -h   # data 内の肥大化を確認
```

応急処置:
```bash
# 古いログを圧縮 or 削除
find /tmp -name "*.log" -mtime +7 -delete

# error_db / metrics_db を 30 日でクリーンアップ
python3 ~/secretary/scripts/lib/error_db.py cleanup --days 30
python3 ~/secretary/scripts/lib/metrics_db.py cleanup --days 30
```

### 9.13 Claude プロセスが OOM Kill された
```bash
sudo dmesg | grep -i "killed process" | tail
free -h                    # メモリ残量
```

VPS の RAM が 1GB 程度だと長時間 Claude session が肥大化して落ちることがある。

対処:
- 定期コールドリスタート（`scripts/restart.sh`、推奨は毎日 03:00）を有効化
- swap を作る:
  ```bash
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

### 9.14 Discord に投稿が届かない（rate limit）
Discord は 1 channel あたり 5 msg / 5 sec が目安。短時間に通知が集中すると
silent drop or 429。

```bash
grep -i "rate" /tmp/*.log | tail
```

対処:
- バースト送信は `time.sleep(1.0)` を挟む
- どうしても多い時は別 channel に分散

### 9.15 VPS 再起動後に自動起動させたい
`start_server.sh` を起動時に走らせる:

**方法 A: `crontab @reboot`（簡単）**
```bash
crontab -e
# 末尾に追加
@reboot /bin/bash /home/YOUR_USER/secretary/start_server.sh >> /tmp/boot.log 2>&1
```

**方法 B: systemd user service（堅牢）**
```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/secretary.service <<'EOF'
[Unit]
Description=secretary screen session
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash %h/secretary/start_server.sh
ExecStop=/usr/bin/screen -S secretary -X quit

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now secretary.service
loginctl enable-linger $USER   # ユーザーがログアウトしてても起動するように
```

### 9.16 全部おかしくなった、どこから取り戻すか
落ち着いて以下の順:

1. **secret は無事か確認**
   ```bash
   ls -la ~/secretary/.env ~/secretary/integrations/*/credentials.json ~/secretary/integrations/*/token.json
   ```
   全部消えていなければ復旧可能。

2. **ローカル変更を退避**
   ```bash
   cd ~/secretary
   git stash push -u -m "panic-stash-$(date +%F)"
   ```

3. **clean な状態に戻す**
   ```bash
   git fetch origin
   git reset --hard origin/main
   ```

4. **依存を入れ直す**
   ```bash
   pip install --break-system-packages -r requirements.txt
   ```

5. **起動して `/login` 通す**
   ```bash
   bash ~/secretary/start_server.sh
   screen -r secretary
   # 中で /login → 終わったら Ctrl+A D
   ```

6. **退避した変更を見て、必要なら戻す**
   ```bash
   git stash list
   git stash show -p stash@{0}     # 中身確認
   git stash pop                   # 戻す
   ```

> ⚠️ `git reset --hard` は破壊的。実行前に必ず `git stash` で退避してください。
