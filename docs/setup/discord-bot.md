# Discord Bot Setup

Discord Developer Portal で bot を作り、token、intents、invite、channel ID を設定します。

## ゴール

- Discord application を作る
- bot token を取得する
- required intents を有効化する
- server に invite する
- command / log / alert の channel ID を取得する

## 1. application 作成

Developer Portal で New Application を作ります。
名前は用途が分かるものにします。

作成後、Bot menu で bot user を追加します。

## 2. token

Bot menu で token を reset / copy します。
token は一度しか表示されないことがあります。

`.env`:

    DISCORD_BOT_TOKEN=YOUR_TOKEN

注意:
- token を chat に貼らない
- screenshot に載せない
- 漏れたら reset
- `.env` は commit しない

## 3. intents

Bot menu で必要な intents を有効化します。

推奨:
- Message Content Intent: 有効
- Server Members Intent: 必要な設計なら有効
- Presence Intent: 通常は不要

message 本文を読む bot では Message Content Intent の漏れがよくあります。

## 4. OAuth2 invite URL

OAuth2 URL Generator で scope を選びます。

scope:
- bot
- applications.commands が必要なら追加

permission:
- View Channels
- Send Messages
- Read Message History
- Add Reactions
- Use Slash Commands が必要なら追加

生成された URL を browser で開き、対象 server に invite します。

## 5. channel permission

server に bot が入っていても、channel 権限が無いと動きません。
対象 channel ごとに確認します。

必要:
- View Channel
- Send Messages
- Read Message History
- Add Reactions

private channel では role / member permission を個別に確認します。

## 6. Developer Mode

Discord client の設定で Developer Mode を有効化します。
これで channel / message / server の ID を copy できます。

## 7. channel ID 3 種

`.env` 例:

    DISCORD_COMMAND_CHANNEL_ID=111111111111111111
    DISCORD_LOG_CHANNEL_ID=222222222222222222
    DISCORD_ALERT_CHANNEL_ID=333333333333333333

用途:
- command: 利用者が bot と会話する場所
- log: script 実行や同期結果を流す場所
- alert: 障害や復旧通知を流す場所

初期は 1 channel にまとめても構いません。
運用が安定したら分けます。

## 8. token test

    python scripts/discord_send.py --channel "$DISCORD_ALERT_CHANNEL_ID" --message "health check"

script の引数仕様が違う場合は `--help` を確認します。

    python scripts/discord_send.py --help

## 9. bot が online にならない

確認:
- token が正しい
- bot process が起動している
- `.env` を読めている
- network が外に出られる
- library version が合っている

## 10. bot が online だが反応しない

確認:
- Message Content Intent
- channel permission
- allowlist
- channel ID
- plugin 側 access
- bot が見る event と script の event が一致しているか

## 11. security

- token reset 手順を把握する
- `.env` は `chmod 600`
- CI log に token を出さない
- debug print で token を出さない
- 公開前に sanitize を実行する

## 12. 次の章

bot が server に入り、test 送信できたら `docs/setup/systemd.md` に進みます。
