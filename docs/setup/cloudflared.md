# Cloudflared Tunnel

Cloudflared tunnel を使うと、VPS の inbound port を開けずに外部 URL から webhook server へ到達できます。

## ゴール

- cloudflared を install する
- tunnel を作る
- hostname を tunnel に route する
- systemd service として常駐させる
- health endpoint を外から確認する

## 1. install

Ubuntu 例:

    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
    sudo dpkg -i cloudflared.deb
    cloudflared --version

package 名や install URL は更新されることがあるため、失敗したら公式 docs の最新手順を確認します。

## 2. login

    cloudflared tunnel login

表示された URL を browser で開き、対象 domain を選びます。
VPS 上で browser が開かない場合は URL を手元 PC にコピーします。

## 3. tunnel 作成

    cloudflared tunnel create my-secretary

確認:

    cloudflared tunnel list
    ls ~/.cloudflared

credentials json が作成されます。
この file は secret 扱いです。

## 4. config file

    mkdir -p ~/.cloudflared
    nano ~/.cloudflared/config.yml

例:

    tunnel: TUNNEL_ID
    credentials-file: /home/app/.cloudflared/TUNNEL_ID.json

    ingress:
      - hostname: assistant.example.com
        service: http://localhost:8781
      - service: http_status:404

`TUNNEL_ID`、user name、hostname、port は自分の環境に合わせます。

## 5. DNS route

    cloudflared tunnel route dns my-secretary assistant.example.com

確認:

    dig assistant.example.com
    cloudflared tunnel route ip show

既に同じ hostname の A record がある場合は衝突に注意します。

## 6. local server の確認

先に local webhook server が動いている必要があります。

    cd ~/my-secretary-template
    source .venv/bin/activate
    python scripts/webhook_server.py

別 terminal で:

    curl -s http://localhost:8781/health

## 7. tunnel を手動起動

    cloudflared tunnel run my-secretary

外部から確認:

    curl -s https://assistant.example.com/health

ここで 502 なら local service 側、名前解決失敗なら DNS 側、404 なら ingress rule を確認します。

## 8. service install

cloudflared の service install を使う場合:

    sudo cloudflared service install
    sudo systemctl status cloudflared --no-pager
    sudo journalctl -u cloudflared -n 100 --no-pager

user ごとの config を使っている場合、service がどの config を読んでいるか確認します。
root service と user home の credentials path がずれることがあります。

## 9. service file を確認

    systemctl cat cloudflared

確認項目:
- ExecStart の tunnel 名
- config path
- credentials path
- service user

## 10. restart

    sudo systemctl restart cloudflared
    sudo systemctl enable cloudflared
    sudo systemctl status cloudflared --no-pager

## 11. よくある障害

- tunnel id と credentials file が違う
- hostname が config と DNS route で違う
- local port が違う
- webhook server が起動していない
- Cloudflare 側 SSL が pending
- root service が user home の credentials を読めない

## 12. secret 管理

secret 扱い:
- tunnel token
- credentials json
- private hostname
- internal service URL

`.env` と同じ扱いで、公開 repository に入れません。

## 13. 次の章

外部 URL が `/health` まで通ったら `docs/setup/notion.md` に進みます。
