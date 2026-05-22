# Claude Code Setup

Claude Code を install し、login し、Discord plugin を使える状態にします。

## ゴール

- Claude Code CLI が起動する
- browser login が完了する
- Discord plugin が入っている
- 対象 channel で access 許可できる

## 1. 前提

必要:
- Claude account
- Claude Code が使える plan
- bun または公式手順で指定される runtime
- SSH session を維持できる screen / tmux

確認:

    which bun || true
    which claude || true
    echo "$PATH"

## 2. install

Claude Code の install 方法は更新されることがあります。
公式手順に従って install します。

install 後:

    claude --version

command not found の場合は PATH を確認します。

    export PATH="$HOME/.bun/bin:$PATH"

恒久化する場合:

    echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.bashrc

## 3. screen / tmux を使う

SSH が切れても login や起動処理が残るようにします。

    screen -S secretary
    claude

抜ける時:

    Ctrl+A D

戻る時:

    screen -r secretary

## 4. login

Claude Code 内で login command を実行します。

    /login

browser が開かない場合は表示された URL を手元 PC の browser で開きます。
VPS ではこれが普通です。

## 5. API key との違い

Claude Code login は Claude Code CLI 用の認証です。
Anthropic API key は API script 用です。
片方だけ設定しても、もう片方の認証にはなりません。

## 6. Discord plugin install

Claude Code の plugin 管理から Discord plugin を install します。
install 後に Claude Code を再起動し、Discord 関連 command が見えることを確認します。

確認すること:
- `/discord:access` が使える
- plugin が enabled
- channel allowlist を設定できる

## 7. channel access

Discord 側で使う channel ID を取得し、Claude Code 側で access 許可します。

手順:
1. Discord Developer Mode を有効化
2. channel を右 click
3. Copy Channel ID
4. Claude Code 内で Discord access command を実行
5. 対象 channel を allowlist に入れる

## 8. 起動 script との関係

`start_server.sh` や watchdog は、Claude Code 自体の login 済み状態を前提にします。
初回 login 前に daemon 化しても、認証待ちで止まります。

## 9. よくあるミス

- VPS 上で browser が開かないことを障害だと思う
- API key と Claude Code login を混同する
- plugin install 後に再起動していない
- Discord channel ID と server ID を間違える
- allowlist 前の channel から話しかけている

## 10. 動作確認

Claude Code 側:
- prompt に入力できる
- `/login` が不要状態
- Discord command が見える

Discord 側:
- bot が online
- target channel に bot がいる
- message / reaction 権限がある

## 11. 次の章

Discord bot 自体の作成は `docs/setup/discord-bot.md` に進みます。
