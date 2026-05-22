# Domain and DNS

この章では domain を取得し、VPS または Cloudflared tunnel に向ける準備をします。

## ゴール

- 管理できる domain がある
- DNS の A record / CNAME record の違いが分かる
- Cloudflared を使う場合の DNS route が理解できる
- 反映待ちで慌てない

## 1. domain を取得する

任意の registrar で取得します。
短く、入力しやすく、用途が分かる domain を推奨します。

避けたいもの:
- 個人名そのもの
- project 外の private 情報が入る文字列
- typo しやすい長い名前

## 2. DNS 管理先を決める

選択肢:
- registrar の DNS をそのまま使う
- Cloudflare に nameserver を移す
- VPS provider の DNS を使う

Cloudflared tunnel を使うなら Cloudflare 管理が最も扱いやすいです。

## 3. A record を設定する場合

VPS へ直接向ける構成です。

例:
- Type: A
- Name: `secretary`
- Value: `SERVER_IP`
- TTL: Auto

結果:
- `secretary.example.com` が VPS IP を指す

確認:

    dig secretary.example.com
    nslookup secretary.example.com

ただし直接公開する場合は VPS firewall、TLS、web server の管理が必要です。

## 4. Cloudflared を使う場合

Cloudflared tunnel では、外から VPS の port を直接開けずに hostname を tunnel へ向けます。
通常は `cloudflared tunnel route dns` が DNS record を作ります。

    cloudflared tunnel route dns TUNNEL_NAME secretary.example.com

この場合、手作業の A record は不要です。
同じ hostname に A record と tunnel route を混在させないでください。

## 5. DNS 反映確認

    dig secretary.example.com
    dig +short secretary.example.com

Cloudflare dashboard の表示と `dig` の結果が一致するまで待ちます。
反映直後は resolver により結果が違うことがあります。

## 6. TTL と待ち時間

TTL が短いほど変更は早く反映されます。
ただし、世界中の resolver が完全に同じタイミングで更新されるわけではありません。

詰まった時:
- 5 分待つ
- 別 network で確認する
- `dig @1.1.1.1 hostname` で確認する
- browser cache と DNS cache を疑う

## 7. hostname の設計

推奨例:
- `assistant.example.com`
- `bot.example.com`
- `webhook.example.com`

用途ごとに分ける場合:
- `webhook.example.com`
- `status.example.com`
- `admin.example.com`

template 初期運用では 1 hostname で十分です。

## 8. SSL の考え方

Cloudflared tunnel を使うと、外部 HTTPS は Cloudflare 側が面倒を見ます。
VPS 内部の local server は `localhost:8781` のような HTTP でも運用できます。

直接公開する場合は reverse proxy と証明書更新が必要です。
初日は tunnel 構成を推奨します。

## 9. よくあるミス

- A record を古い IP に向けたまま
- Cloudflare nameserver へ切り替えていない
- `www` と root domain を混同
- hostname の typo
- tunnel route と A record が衝突
- DNS 反映待ちを障害と誤解

## 10. 次の章

Cloudflare 管理の hostname が用意できたら、`docs/setup/cloudflared.md` に進みます。
