# Xserver VPS Setup

Xserver VPS を借りて、初回 SSH login から template を置ける状態まで進める手順です。
他の VPS でも考え方は同じですが、管理画面の名称は読み替えてください。

## ゴール

- Linux VPS に SSH 接続できる
- sudo が使える一般 user で作業できる
- Python / git / basic tools が入っている
- firewall の考え方を理解している
- `~/my-secretary-template` を置ける

## 1. 契約時の選択

推奨:
- OS: Ubuntu LTS
- Memory: 1GB 以上
- Storage: 20GB 以上
- Region: 利用者に近い region
- Root password login: 初回だけ使い、後で SSH key に寄せる

小さい VPS でも動きますが、browser 認証、package install、重い Python package で詰まる場合があります。
余裕を見るなら 2GB memory が扱いやすいです。

## 2. SSH key を準備

手元 PC で key を作ります。

    ssh-keygen -t ed25519 -f ~/.ssh/my-secretary-vps

公開鍵を VPS 管理画面へ登録できる場合は、`.pub` の中身を登録します。

    cat ~/.ssh/my-secretary-vps.pub

秘密鍵は共有しません。
チャット、Issue、スクリーンショットに秘密鍵を載せないでください。

## 3. 初回 SSH

    ssh -i ~/.ssh/my-secretary-vps root@SERVER_IP

Windows から接続する場合は、秘密鍵 path を絶対 path で指定すると事故が減ります。

    ssh -i C:\Users\YOUR_USER\.ssh\my-secretary-vps root@SERVER_IP

接続できない時は以下を確認します。
- IP address が正しい
- VPS が起動中
- 管理画面の packet filter で SSH が許可されている
- 秘密鍵と公開鍵の組が一致している

## 4. apt update

    apt update
    apt upgrade -y

再起動を求められた場合:

    reboot

再接続して作業を続けます。

## 5. 作業 user を作る

root 常用は避け、一般 user を作ります。

    adduser app
    usermod -aG sudo app

SSH key を引き継ぎます。

    mkdir -p /home/app/.ssh
    cp /root/.ssh/authorized_keys /home/app/.ssh/authorized_keys
    chown -R app:app /home/app/.ssh
    chmod 700 /home/app/.ssh
    chmod 600 /home/app/.ssh/authorized_keys

以後は一般 user で入ります。

    ssh -i ~/.ssh/my-secretary-vps app@SERVER_IP

## 6. 基本 package

    sudo apt install -y git curl wget unzip jq lsof ca-certificates gnupg build-essential python3 python3-venv python3-pip

systemd service や journal を見るため、Ubuntu 標準の systemd 環境を前提にします。

## 7. timezone

利用者の生活圏に合わせます。

    timedatectl list-timezones | grep Tokyo
    sudo timedatectl set-timezone Asia/Tokyo
    date

別 timezone を使う場合は `.env`、cron、Notion の timestamp 表示も合わせます。

## 8. firewall

Cloudflared tunnel を使うなら、外部公開 port は最小限で済みます。
まず SSH だけを確実に残します。

    sudo ufw allow OpenSSH
    sudo ufw enable
    sudo ufw status verbose

直接 HTTP/HTTPS を公開する構成でなければ、80/443 を開ける必要はありません。
Cloudflare tunnel が外向き接続を作ります。

## 9. repo 配置

    cd ~
    git clone REPOSITORY_URL my-secretary-template
    cd my-secretary-template

配布 zip の場合:

    cd ~
    unzip my-secretary-template.zip
    cd my-secretary-template

## 10. Python venv

    cd ~/my-secretary-template
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip wheel setuptools
    pip install -r requirements.txt

失敗したら `docs/setup/troubleshooting.md` の pip と重い依存の項目を見ます。

## 11. env file

    cp .env.template .env
    chmod 600 .env
    nano .env

この時点で secret を全部埋める必要はありません。
Discord、Notion、Cloudflared の章で取得した値を順に埋めます。

## 12. 動作確認

    python3 -m compileall scripts integrations templates
    python3 scripts/onboarding.py --yes

生成 file ができたら OK です。

    ls AGENT templates/generated

## 13. 運用前 check

- root ではなく一般 user で動かす
- `.env` は `chmod 600`
- repository に secret を commit しない
- SSH が切れても systemd で復旧できる
- alert 用 Discord channel を用意する

次は `docs/setup/domain.md` で domain を準備します。
