# systemd Setup

watchdog や webhook server を systemd unit として常駐させる手順です。

## ゴール

- unit template を配置する
- user service として起動する
- journalctl で log を見る
- reboot 後も復旧する

## 1. user service と system service

この template では user service を基本にします。
root 権限を減らし、home directory の venv や `.env` を扱いやすくするためです。

確認:

    systemctl --user status

WSL で失敗する場合は systemd が有効ではない可能性があります。

## 2. template を確認

unit template:

    scripts/system/my-secretary-watchdog.service.tpl

確認する項目:
- WorkingDirectory
- ExecStart
- EnvironmentFile
- Restart
- RestartSec

## 3. install directory

    mkdir -p ~/.config/systemd/user

template を自分の path に置換して service file を作ります。

    cp scripts/system/my-secretary-watchdog.service.tpl ~/.config/systemd/user/my-secretary-watchdog.service
    nano ~/.config/systemd/user/my-secretary-watchdog.service

## 4. service file 例

    [Unit]
    Description=My Secretary watchdog
    After=network-online.target

    [Service]
    Type=simple
    WorkingDirectory=/home/app/my-secretary-template
    EnvironmentFile=/home/app/my-secretary-template/.env
    ExecStart=/home/app/my-secretary-template/.venv/bin/python /home/app/my-secretary-template/scripts/system/watchdog.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=default.target

path は自分の環境に合わせます。

## 5. reload

    systemctl --user daemon-reload
    systemctl --user enable my-secretary-watchdog
    systemctl --user start my-secretary-watchdog

確認:

    systemctl --user status my-secretary-watchdog --no-pager

## 6. journalctl

直近 log:

    journalctl --user -u my-secretary-watchdog -n 100 --no-pager

追跡:

    journalctl --user -u my-secretary-watchdog -f

起動直後に exit する場合、journal の最初の traceback を見ます。

## 7. reboot 後も起動する

user service を login なしで動かす場合:

    sudo loginctl enable-linger app

確認:

    loginctl show-user app | grep Linger

## 8. 手動 command と同じ条件で試す

systemd で落ちる時は ExecStart を手動実行します。

    cd /home/app/my-secretary-template
    source .venv/bin/activate
    .venv/bin/python scripts/system/watchdog.py

手動で落ちるなら app 側の問題です。
手動で動き systemd で落ちるなら service file の path / env / permission を疑います。

## 9. restart

    systemctl --user restart my-secretary-watchdog
    systemctl --user status my-secretary-watchdog --no-pager

## 10. stop / disable

    systemctl --user stop my-secretary-watchdog
    systemctl --user disable my-secretary-watchdog

## 11. よくあるミス

- `~` を service file に書いて展開されない
- `.venv/bin/python` の path が違う
- `.env` が存在しない
- `.env` の permission が厳しすぎて別 user から読めない
- WorkingDirectory が repo root ではない
- process が foreground に残らず exit する
- WSL で systemd が無効

## 12. health check

watchdog と webhook の両方を見る場合:

    curl -s http://localhost:8781/health
    systemctl --user status my-secretary-watchdog --no-pager
    journalctl --user -u my-secretary-watchdog -n 50 --no-pager

## 13. 次の章

service が常駐したら `docs/setup/sanitize.md` で公開前 check を入れます。
