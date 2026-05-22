# Troubleshooting

初日に詰まりやすい箇所を、症状から逆引きできるようにまとめた Q&A です。
原因を一つずつ潰すため、まずはエラーメッセージをそのまま保存してください。
トークン、API key、Cookie、認証 URL は共有前に必ず伏字にします。

## まず確認する 5 コマンド

    cd ~/my-secretary-template
    pwd
    python3 --version
    test -f .env && echo ".env exists" || echo ".env missing"
    systemctl --user status my-secretary-watchdog --no-pager

## Q&A

### Q01. bun が未インストールで Claude Code を評価できない

症状:
- `bun: command not found`
- `claude: command not found`
- Claude Code の install 手順で止まる

確認:

    which bun
    which claude
    echo "$PATH"

対応:
1. 公式手順で bun を入れます。
2. shell を開き直します。
3. `~/.bun/bin` が PATH に入っているか確認します。

    export PATH="$HOME/.bun/bin:$PATH"
    bun --version

恒久対応は `~/.bashrc` に PATH を追加して、再ログイン後に再確認します。

### Q02. Claude Code に Discord plugin が入っておらず reaction しない

症状:
- Discord から送っても Claude Code が反応しない
- `/discord:access` が使えない
- allowlist の話が出ない

確認:
- Claude Code 内で plugin 一覧を確認します。
- Discord 関連 command が見えるか確認します。
- bot 側と Claude Code 側を混同しないようにします。

対応:
1. Claude Code に Discord plugin を install します。
2. Claude Code を再起動します。
3. 対象 channel で access 許可をやり直します。

### Q03. Cloudflared tunnel の DNS 反映待ちで外から見えない

症状:
- local では health が通る
- 外部 URL だけ 404 / 502 / 名前解決失敗
- DNS を設定した直後

確認:

    cloudflared tunnel list
    cloudflared tunnel route dns <TUNNEL_NAME> <HOSTNAME>
    dig <HOSTNAME>

対応:
- DNS 反映には数分から数十分かかることがあります。
- 先に local tunnel が起動しているか確認します。
- hostname と tunnel id の対応を見直します。

### Q04. Cloudflare SSL が pending のまま

症状:
- HTTPS 接続が不安定
- Cloudflare dashboard で証明書が pending
- ブラウザで証明書警告が出る

対応:
1. DNS が Cloudflare 管理下にあるか確認します。
2. proxy 設定と tunnel route を確認します。
3. 反映直後なら待ちます。
4. hostname の typo を修正します。

### Q05. Notion integration を DB に共有し忘れて 403 になる

症状:
- `Notion API error: 403`
- integration は作ったのに DB が読めない
- token は正しい

確認:
- Notion の対象 database を開く
- 右上 menu から Connections を確認
- 作成した integration が入っているか見る

対応:
1. 対象 DB ごとに integration を共有します。
2. parent page だけでなく database 自体を確認します。
3. 再実行します。

### Q06. Anthropic API key と Claude Code login を混同している

症状:
- API key を入れたのに Claude Code が login を求める
- Claude Code に login したのに API script が 401 になる

整理:
- Claude Code login: Claude Code CLI の利用認証
- Anthropic API key: API を直接叩く script 用の secret

対応:
- Claude Code は `/login` で browser 認証します。
- API script は `.env` に `ANTHROPIC_API_KEY` を設定します。
- 片方だけでは両方は動きません。

### Q07. WSL 内 cron が動かない

症状:
- `crontab -l` はあるが実行されない
- reboot 後に cron が止まる
- WSL を閉じると動かない

確認:

    ps aux | grep cron
    systemctl status cron --no-pager

対応:
- WSL で systemd を有効化します。
- `/etc/wsl.conf` に systemd 設定を入れ、WSL を再起動します。
- 常時運用は VPS の systemd を推奨します。

### Q08. Discord bot token を漏らしそうで怖い

症状:
- `.env` を commit しそう
- chat に token を貼りそう
- error log に token が出た

対応:
1. `.env` は `.gitignore` に含めます。
2. token は chat に貼らず、端末で `.env` に手入力します。
3. 漏れた可能性がある token は Developer Portal で reset します。
4. `scripts/lib/sanitize_lint.py` を実行します。

### Q09. `.env.template` から `.env` へコピーし忘れた

症状:
- `KeyError`
- `missing environment variable`
- token を入れたつもりなのに読まれない

対応:

    cd ~/my-secretary-template
    cp .env.template .env
    chmod 600 .env
    nano .env

確認:

    test -f .env && echo ok
    grep -n "DISCORD" .env

### Q10. opencv-python など重い依存の install に失敗する

症状:
- build に長時間かかる
- memory error
- wheel が見つからない

対応:
- まず Python version を確認します。
- 不要なら重い package を requirements から外します。
- headless 環境では `opencv-python-headless` を検討します。
- VPS の memory が少ない場合は swap を追加します。

### Q11. permission denied で script が動かない

症状:
- `Permission denied`
- shell script が実行できない
- `.env` が読めない

対応:

    chmod +x scripts/*.sh
    chmod 600 .env
    ls -la scripts .env

systemd から動かす場合は user、working directory、file owner を確認します。

### Q12. port が既に使用中

症状:
- `Address already in use`
- webhook server が起動しない
- health endpoint が別 process を向く

確認:

    lsof -i :8781
    ss -ltnp | grep 8781

対応:
- 既存 process が不要なら停止します。
- 必要なら `.env` の port を変えます。
- Cloudflared の転送先 port も合わせます。

### Q13. Cloudflared tunnel id が一致しない

症状:
- tunnel はあるのに route が効かない
- service が別 tunnel を起動している
- credentials file が見つからない

確認:

    cloudflared tunnel list
    ls ~/.cloudflared
    systemctl status cloudflared --no-pager

対応:
- service file の tunnel 名/id を確認します。
- credentials json の path を合わせます。
- 古い tunnel route を整理します。

### Q14. Notion 403 が直らない

症状:
- DB 共有済みでも 403
- 一部 DB だけ失敗する

原因候補:
- integration capability 不足
- database id が違う
- page と database を取り違えている
- workspace が違う

対応:
1. integration capability を Read / Insert / Update にします。
2. Delete は外したままで構いません。
3. 対象 DB へ integration を共有します。
4. URL から正しい database id を取り直します。

### Q15. `pip install -r requirements.txt` が失敗する

確認:

    python3 --version
    python3 -m pip --version
    python3 -m pip install --upgrade pip wheel setuptools

対応:
- venv を作り直します。
- error の最初の package 名を確認します。
- OS package が必要な場合は apt で入れます。

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

### Q16. Claude Code login が browser を開かない

症状:
- `/login` しても browser が開かない
- SSH / VPS / WSL 上で login URL が出るだけ

対応:
- 表示された URL を手元の browser にコピーします。
- code 入力が必要なら CLI の指示に従います。
- SSH session が切れないように screen / tmux 内で作業します。

### Q17. Discord bot が反応しない

症状:
- bot は online だが message に反応しない
- mention しても無反応
- reaction が付かない

確認:
- Developer Portal の intents
- server invite scope
- channel permission
- bot process log

対応:
1. Message Content Intent を有効化します。
2. Server Members Intent が必要な設計なら有効化します。
3. bot を invite し直します。
4. channel ID が `.env` と一致しているか確認します。

### Q18. systemd service が start 直後に exit する

確認:

    systemctl --user status my-secretary-watchdog --no-pager
    journalctl --user -u my-secretary-watchdog -n 100 --no-pager

原因候補:
- working directory が違う
- venv path が違う
- `.env` がない
- command が foreground で維持されない
- Python import error

対応:
- ExecStart を絶対 path にします。
- `Restart=always` を入れます。
- まず手動で同じ command を実行します。

### Q19. Python version mismatch

症状:
- `match` syntax error
- type hint error
- package が対応していない

確認:

    python3 --version
    which python3
    .venv/bin/python --version

対応:
- Python 3.11 以上を推奨します。
- venv 作成時の Python を固定します。
- systemd / cron でも同じ venv を使います。

### Q20. Notion integration の権限不足

症状:
- read はできるが create/update が失敗
- properties 更新だけ失敗する

対応:
- capability は Read content / Insert content / Update content を付けます。
- Delete は不要なので外します。
- capability 変更後に integration の接続状態を確認します。

### Q21. Google Calendar OAuth refresh token が切れた

症状:
- calendar script が 401 / invalid_grant
- 以前は動いていた
- password 変更や consent 変更後に発生

対応:
1. 古い token file を退避します。
2. reauth script を実行します。
3. browser で consent をやり直します。
4. cron / systemd の user から token が読めるか確認します。

### Q22. cron で env が読み込まれない

症状:
- 手動では動くが cron では落ちる
- environment variable missing
- PATH が違う

対応:
- cron では shell の login 設定を期待しません。
- script 内で `.env` を読む実装にします。
- crontab では絶対 path を使います。

例:

    * * * * * cd /home/USER/my-secretary-template && /home/USER/my-secretary-template/.venv/bin/python scripts/task_remind.py

### Q23. WSL2 と WSL1 の違いで network が合わない

症状:
- Windows から localhost が見えない
- systemd が使えない
- network 挙動が説明と違う

対応:
- WSL version を確認します。

    wsl -l -v

- WSL2 を推奨します。
- 本番運用は Linux VPS へ寄せると切り分けが楽です。

### Q24. VPS の packet filter / firewall で port が閉じている

症状:
- server は起動している
- 外部から接続できない
- SSH 以外が通らない

確認:
- VPS 管理画面の packet filter
- OS 側の ufw
- Cloudflared 使用時は公開 port が本当に必要か

対応:
- SSH port は維持します。
- Cloudflared tunnel なら外部公開 port を最小化できます。
- 直接公開する port だけ許可します。

### Q25. `ssh -i` の path を間違える

症状:
- identity file not accessible
- Permission denied publickey
- Windows terminal から鍵が見えない

対応:
- 絶対 path を使います。
- path に空白がある場合は quote します。
- 鍵 file の permission を確認します。

PowerShell では変数と path のつなぎ方で誤解しやすいため、まず絶対 path で成功確認します。

### Q26. Discord channel ID が 3 種類あって混乱する

使い分け:
- command channel: 利用者が話しかける場所
- log channel: bot の処理 log
- alert channel: 障害通知

対応:
- Developer Mode を有効化します。
- channel を右 click して Copy Channel ID します。
- `.env` に用途別に入れます。

### Q27. invite URL の scope / permission が不足している

症状:
- bot は server にいるが送信できない
- slash command が出ない
- reaction できない

対応:
- `bot` scope を付けます。
- 必要なら `applications.commands` も付けます。
- Send Messages / Read Message History / Add Reactions を許可します。

### Q28. `.env` の quote や空白で値が壊れる

症状:
- token があるのに unauthorized
- channel ID が一致しない
- 値の末尾に空白が入る

対応:
- `KEY=value` 形式にします。
- token 前後に不要な quote や空白を入れません。
- multiline secret は使いません。

### Q29. Notion database id と page id を取り違える

症状:
- 404 object not found
- DB を作ったはずなのに schema が読めない

対応:
- database を full page で開きます。
- URL の database id を取り出します。
- inline DB と page の id を混同しないようにします。

### Q30. onboarding.py を実行したが生成先が分からない

確認:

    python3 scripts/onboarding.py --yes
    find AGENT templates/generated -maxdepth 3 -type f

生成物:
- `AGENT/USER.md`
- `templates/generated/anthropic_compatible_prompt.md`

対応:
- 既存の persona を上書きしたくない場合は `--agent-dir` で別名を指定します。

### Q31. sanitize_lint.py が個人情報らしき文字列を検出する

症状:
- CI が sanitize で失敗
- 公開前 check が止まる

対応:
- 検出された語を placeholder に置き換えます。
- `.env` や token file は commit しません。
- 誤検出でも、公開 template では無難な表現に寄せます。

### Q32. CI が py compile で落ちる

確認:

    python3 -m compileall scripts integrations templates

対応:
- traceback の file と行を見ます。
- Python version を CI と local で合わせます。
- 生成された一時 file が混ざっていないか確認します。

### Q33. watchdog は動くが alert が Discord に出ない

確認:
- watchdog service の journal
- Discord token
- alert channel ID
- bot permission

対応:
- `scripts/discord_send.py` を手動実行します。
- `.env` を systemd service から読めているか確認します。
- alert channel で bot に送信権限を付けます。

### Q34. health check は成功するが実処理が動かない

原因候補:
- health endpoint は server 生存だけ見ている
- external API token が壊れている
- queue watcher が別途止まっている

対応:
- script 単体で実行します。
- DB 書き込みや Discord 送信まで含めた end-to-end check を実行します。
- journal と application log の両方を見ます。

### Q35. どこまで伏字にすればよいか分からない

伏字にするもの:
- API key
- bot token
- OAuth token
- tunnel token
- database id
- channel id
- private hostname
- server IP
- real user name

残してよいもの:
- error class
- command name
- package name
- placeholder
- 再現手順

### Q36. 何から調べればよいか分からない

まず集める情報:

    date
    git status --short
    python3 --version
    systemctl --user status my-secretary-watchdog --no-pager
    journalctl --user -u my-secretary-watchdog -n 80 --no-pager
    curl -s http://localhost:8781/health || true

共有前に secret を伏字にして、症状、期待結果、実際の結果、最後に変更した箇所を添えます。
