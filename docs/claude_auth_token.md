# Claude Code の認証トークン運用

## なぜ必要か

Claude Code の `/login` で発行される OAuth refresh token は30日で失効する。
このテンプレートは Claude Code セッションを screen 上で常駐させて動かして
いるため、30日ごとに「ログイン認証切れ」でセッションが止まる
（`health_check.sh` が検知して Discord 通知する）。

`claude setup-token` で発行する1年トークンに切り替えると、この更新作業が
年1回で済む。`CLAUDE_CODE_OAUTH_TOKEN` 環境変数は `/login` の資格情報より
優先される。

## 年1回の手順

1. サーバーにログインし、以下を実行する:
   ```bash
   bash ~/secretary/scripts/setup_claude_token.sh
   ```
2. `claude setup-token` が起動して認証用 URL が出る。ブラウザで開き、秘書の Claude
   アカウントでログインして許可し、表示されたコードを端末に貼って Enter
3. 画面に出たトークン (`sk-ant-oat01-...`) はスクリプトが自動で拾う（`script(1)` で画面出力を
   記録して取り出す。端末幅で折り返されていても 1 本につなげる）。
   「トークンを拾った: sk-ant-oat01-... (N 文字)」→「これで保存する? [Y/n]」に Enter
4. `data/secrets/claude_oauth_token`（mode 600）に保存され、
   `data/secrets/claude_oauth_token.issued_at` に発行日（YYYY-MM-DD）が記録される
5. 案内どおり `bash ~/secretary/start_server.sh` で再起動する

自動で拾えなかった時はその場で「貼り付けて Enter」に切り替わる（画面には表示されない）。
最初から手で貼りたい場合は `--paste`。発行済みのトークンをファイルから読み込みたい場合:
```bash
bash ~/secretary/scripts/setup_claude_token.sh --file /path/to/token.txt
```
（ファイル内の改行・空白は取り除いてから保存するので、折り返されたまま貼ってよい）

同じ日に誤って二重実行すると事故防止のため上書きを拒否する（`issued_at` が今日以降なら拒否）。
本当に上書きしたい場合だけ `--force` を付ける。

## 何が変わるか

- `start_server.sh` は Claude Code を screen で起動する直前に、
  `data/secrets/claude_oauth_token`（`CLAUDE_OAUTH_TOKEN_FILE` で変更可）を読む
- token file があり中身が空でなければ `CLAUDE_CODE_OAUTH_TOKEN` を export し、
  `ANTHROPIC_API_KEY` は unset する（残っているとサブスク認証でなく API 課金経由の
  認証にすり替わりうるため）。この環境変数は screen セッション（→ `claude_wrapper.exp`
  → `claude` プロセス）にそのまま継承される
- token file が無ければ何も変わらず、従来どおり `/login` 認証で動く
- 起動時のログに `claude auth: setup-token ファイルを使用` /
  `claude auth: /login 認証 (token file なし)` のどちらが出たかで現在の認証方式が分かる
  （トークンの値そのものは絶対にログへ出さない）
- **token認証中に使えなくなるもの**: claude.ai の connectors、Remote Control
- **token認証中も使えるもの**: Discord プラグイン（bun経由のlocal MCP。claude.aiサブスク認証で動く想定）

## 再起動後の確認

1. health_check ログを tail し、オーソリ切れ系のエラーが出ていないか確認する
   ```bash
   tail -30 /tmp/health_check.log
   ```
   （`docs/ops.md` §5 の手順でログを `~/secretary/logs/` に永続化している場合はそちらを見る）
2. Discord の担当チャンネルにメッセージを送り、秘書から応答が返るか確認する
3. `bash ~/secretary/scripts/doctor.sh` でトークンファイルの有無・経過日数を確認する

## 有効期限が近づいたら

`health_check.sh` が、発行から350日を超えると1日1回
「🔑 Claudeのトークンが発行から N 日。1年で切れるので setup_claude_token.sh で更新して」
と Discord に通知する。通知が来たら本手順を再実行して更新する。

## ロールバック（token をやめて /login に戻す）

```bash
rm -f ~/secretary/data/secrets/claude_oauth_token ~/secretary/data/secrets/claude_oauth_token.issued_at
bash ~/secretary/start_server.sh
```
再起動後、screen セッション内で `/login` を実行して認証すれば従来どおりに戻る。
