# cron.md — cron 運用

定期実行の作法とハマりどころ。

---

## 1. 構文の最低限

```
* * * * * command
| | | | |
| | | | +--- 曜日（0〜6、日曜=0）
| | | +----- 月（1〜12）
| | +------- 日（1〜31）
| +--------- 時（0〜23）
+----------- 分（0〜59）
```

例:
- `*/5 * * * *` — 5分おき
- `30 6 * * *` — 毎日 06:30
- `0 9 * * MON` — 毎週月曜 09:00
- `0 3 * * 0` — 毎週日曜 03:00

---

## 2. 登録

ユーザーに `crontab -e` を打ってもらい、エージェントは追加すべき行を
コードブロックで提示する。または以下を生成して `crontab` コマンドで一括
登録:

```bash
( crontab -l 2>/dev/null; cat <<'EOF'
*/5 * * * * /bin/bash /home/YOUR_USER/secretary/scripts/health_check.sh >> /tmp/health_check.log 2>&1
30 6,22 * * * /usr/bin/python3 /home/YOUR_USER/secretary/scripts/task_remind.py >> /tmp/task_remind.log 2>&1
EOF
) | crontab -
```

---

## 3. ハマりどころ（必ず守る）

- **フルパスを使う**（`python3` ではなく `/usr/bin/python3`、`bash` ではなく `/bin/bash`）。
  cronの PATH は `/usr/bin:/bin` しかない
- **`~` は展開されないことがある** → `/home/YOUR_USER/...` を使う
- **HOMEがセットされない** → 必要なシェルスクリプトは頭で `export HOME="/home/$(whoami)"`
- **stderrもログに飛ばす** → `>> /tmp/xxx.log 2>&1` を必ず付ける
- **登録前に手で同じコマンドを叩いて成功するか確認する**

---

## 4. タイムゾーン

cronはシステムTZを使う。`Asia/Tokyo` にしておく（`docs/bootstrap.md` のセクション2参照）。
このテンプレートの全cronはJST前提。`at` コマンドも同様にJSTで指定する。

---

## 5. 確認・デバッグ

```bash
crontab -l
sudo grep CRON /var/log/syslog | tail
tail -n 100 /tmp/health_check.log
```

---

## 6. 推奨ジョブ一覧

### 最小セット
```cron
*/5 * * * * /bin/bash /home/YOUR_USER/secretary/scripts/health_check.sh >> /tmp/health_check.log 2>&1
30 6,22 * * * /usr/bin/python3 /home/YOUR_USER/secretary/scripts/task_remind.py >> /tmp/task_remind.log 2>&1
0 3 * * * /usr/bin/python3 /home/YOUR_USER/secretary/scripts/daily_handoff.py >> /tmp/daily_handoff.log 2>&1
```

### オプション
```cron
# 週次再起動（24/7 で7日以上回すなら有効化）
10 3 * * 0 /bin/bash /home/YOUR_USER/secretary/scripts/weekly_restart.sh >> /tmp/weekly_restart.log 2>&1

# Google Calendar 30分前リマインダー
* * * * * /usr/bin/python3 /home/YOUR_USER/secretary/integrations/gcal/gcal_remind.py >> /tmp/gcal_remind.log 2>&1

# Gmail モニター
* * * * * /usr/bin/python3 /home/YOUR_USER/secretary/integrations/gmail/gmail_monitor.py >> /tmp/gmail_monitor.log 2>&1

# Sheets タスク同期
*/15 * * * * cd /home/YOUR_USER/secretary && /usr/bin/python3 scripts/task_sheet_sync.py push >> /tmp/task_sheet.log 2>&1

# 毎晩バックアップ git push
45 0 * * * cd /home/YOUR_USER/secretary && git add data memory 2>/dev/null && git commit -m "auto backup $(date +\%F)" 2>/dev/null && git push 2>&1 >> /tmp/git_push.log
```

---

## 7. 落ちたとき

cronが黙って落ちる理由はほぼ以下のどれか:
- `PATH` 未設定 → フルパスで（`/usr/bin/python3`）
- `HOME` 未設定 → シェル先頭で `export HOME=...`
- リダイレクト無し → `>> /tmp/xxx.log 2>&1`

詳細な切り分けは `docs/ops.md` のトラブルシューティング参照。

---

## 8. ジョブを追加するときの流れ

ユーザーが「X を Y の頻度でやって」と言ってきたら:

1. `AGENT/JOBS.md` に1行の仕様をEditで足す（トリガー・スクリプト・動作）
2. `scripts/` にスクリプトをWrite（既存スタイルに合わせる: `__main__` で
   `track_errors` / `track_metrics` デコレータを付ける）
3. cronに登録（セクション2の heredoc パターン）— ユーザーに同意を取ってから
4. 手動で1回叩いて成功するか確認、ログにエラーが出ないかチェック
5. 動いたらユーザーに簡潔に「追加しました」と reply で報告

5行以上の手順を踏むジョブは `AGENT/skills/<name>.md` にスキルファイルとして
切り出す。`JOBS.md` には1行サマリーとスキルファイルへのポインタだけ残す。
