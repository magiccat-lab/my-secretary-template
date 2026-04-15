# SETUP.md — セットアップ手順（人間向け）

このファイルは「VPSを借りたばかり」の状態から、Discordで自分専用のAI秘書と
会話できるまでを、**頭から順番にやれば動く**ように書いた手順書です。
専門用語は最小限にしています。ターミナルに慣れていなくても大丈夫です。

> 前提: Xserver VPS 等の Ubuntu / Debian 系 VPS を契約済み。
> Claude Pro プラン契約済み。
>
> ハマったら一番下の「L. トラブルシューティング」を先に見てください。

---

## 全体の流れ（最初に地図だけ）

0. VPS 契約直後〜初回ログイン・一般ユーザー作成
A. 前提パッケージを入れる
B. Claude Code をインストール
C. このテンプレートを clone して Python 依存を入れる
C2. 自分の GitHub プライベートリポジトリに切替える（推奨）
C3. Google API 連携をセットアップ（Calendar / Gmail / Sheets / Drive）
D. Discord で bot を作ってトークンを取る
E. 必要な Discord の ID を3つ取る
F. Webhook トークンを生成
G. `.env` を書く（claude.ai に手伝ってもらう）
H. 秘書のキャラと自己紹介を決める（claude.ai に手伝ってもらう）
I. サーバー起動
J. Discord から話しかけて動作確認
K. 動いたあとの遊び方
L. トラブルシューティング

---

## 0. VPS 契約直後〜初回ログイン・一般ユーザー作成

Xserver VPS などを契約した直後の状態から、SSH でログインできるように
なるまでの手順です。既に自分用のユーザーで SSH ログインできる場合は
「A. 前提パッケージを入れる」まで飛ばしてください。

### 0-1. VPS のコンパネで初期情報を確認

Xserver VPS の例:
- VPS パネル (`https://secure.xserver.ne.jp/xapanel/xvps/`) にログイン
- 契約中のサーバーを選び、「SSH」または「サーバー情報」を開く
- 控えるもの:
  - **IP アドレス**（`xxx.xxx.xxx.xxx`）
  - **root の初期パスワード**（契約完了メールにも載っています）

他の VPS サービスでも、「IP アドレス」と「root パスワード」が分かれば OK。

### 0-2. root で初回 SSH ログイン

手元の PC のターミナル（Mac / Linux はそのまま、Windows は PowerShell か
WSL）で以下を実行します。

```bash
ssh root@xxx.xxx.xxx.xxx
```

- 初回は「続けますか?」と聞かれるので `yes` と入力
- パスワードを聞かれたら 0-1 で控えた root パスワードを入れる

ログインできたら、まずはパッケージを最新にしておきます。

```bash
apt update && apt upgrade -y
```

### 0-3. 一般ユーザーを作成する

root で作業し続けるのは危険なので、自分用のユーザーを作ります。
ユーザー名は任意です（例では `shun` としますが、好きな名前で OK）。

```bash
adduser shun
```

- パスワードを 2 回聞かれるので決めて入力
- 名前・部屋番号などはすべて空 Enter で OK

次に sudo 権限（管理者コマンドを使える権限）を付与します。

```bash
usermod -aG sudo shun
```

### 0-4. 手元 PC で SSH 鍵を作って VPS に登録する

パスワードより SSH 鍵の方が安全なので、鍵認証に切り替えます。
以下は**手元 PC 側**（VPS ではない）で実行します。

すでに `~/.ssh/id_ed25519.pub` がある人はこの作成ステップは不要。

```bash
ssh-keygen -t ed25519 -C "your-email@example.com"
```

- 保存場所は Enter（デフォルトでOK）
- パスフレーズは空 Enter でも入れても OK（入れた方が安全）

作った公開鍵を VPS の一般ユーザーに登録します。
**手元 PC 側**で以下を実行:

```bash
ssh-copy-id shun@xxx.xxx.xxx.xxx
```

パスワードを聞かれたら 0-3 で決めた `shun` のパスワードを入力。

### 0-5. 一般ユーザーで入り直して動作確認

```bash
ssh shun@xxx.xxx.xxx.xxx
```

今度はパスワードを聞かれずにログインできれば成功。
以降の作業は**この一般ユーザー**で行います（必要なときだけ `sudo` を付ける）。

### 0-6.（推奨）root ログインとパスワード認証を無効化

鍵でログインできるようになったら、外から root で入られる経路と
パスワード認証を止めておくとぐっと安全になります。

一般ユーザーでログインした状態で:

```bash
sudo nano /etc/ssh/sshd_config
```

以下の 2 行を探して書き換えます（`#` が付いていれば外します）:

```
PermitRootLogin no
PasswordAuthentication no
```

保存して（`Ctrl+O` → Enter → `Ctrl+X`）、SSH を再起動:

```bash
sudo systemctl restart ssh
```

⚠️ **この変更後、別のターミナルウィンドウをもう一つ開いて鍵ログインできる
ことを確認してから、今開いているセッションを閉じてください。**
鍵ログインに失敗する状態で切ってしまうと、コンパネの VNC コンソールから
入り直す羽目になります。

ここまで終わったら、そのまま「A. 前提パッケージを入れる」に進みます。

---

## A. 前提パッケージを入れる

SSH でログインして、以下をそのままコピペして実行します。

```bash
sudo apt update
sudo apt install -y python3 python3-pip git screen curl lsof at tmux unzip
```

次にタイムゾーンを日本時間に合わせます（cron の時刻が JST 前提で書かれて
いるため）。

```bash
sudo timedatectl set-timezone Asia/Tokyo
date   # 確認。JST の時刻が出れば OK
```

最後にファイアウォールで SSH だけ開けておきます。

```bash
sudo ufw allow OpenSSH
sudo ufw enable
```

---

## B. Claude Code をインストール

Claude Code 本体を入れます。

```bash
curl -fsSL https://bun.sh/install | bash
# シェルを再読み込み（PATH を通すため）
source ~/.bashrc

bun install -g @anthropic-ai/claude-code
```

bun が使いたくなければ npm でも OK です。

```bash
# 代替: npm install -g @anthropic-ai/claude-code
```

インストール後、一度だけログインフローを通します。

```bash
claude
```

起動したら `/login` と打って、表示される URL をブラウザで開き、Claude の
アカウントで認証してください。ログインが終わったら `/exit` で一度抜けます。

---

## C. テンプレートを clone して依存を入れる

```bash
git clone https://github.com/magiccat-lab/my-secretary-template.git ~/secretary
cd ~/secretary
pip install -r requirements.txt
```

Ubuntu 24.04 以降だと `pip install` が `externally-managed-environment`
というエラーで弾かれることがあります。その場合は以下を使ってください。

```bash
pip install --break-system-packages -r requirements.txt
```

`~/secretary/` の下に設定ファイルやスクリプトが並んでいれば OK です。

---

## C2. 自分の GitHub プライベートリポジトリに切替える（推奨）

このあと `.env` や自分専用の設定を書き込むので、自分の **プライベート**
リポジトリに置き換えておきます（テンプレートは公開リポなので、そのまま
push してしまうと他人に見られる可能性があります）。

> `.env` や `data/` は `.gitignore` 済みなので、仮に push しても
> シークレットは漏れませんが、口調ファイルやタスク履歴など「他人に
> 読まれたくない個人情報」が増えるので、最初にプライベート化しておく
> のが安全です。

### C2-1. GitHub アカウントを準備

すでに GitHub アカウントを持っている人は飛ばしてください。
持っていない人は https://github.com/signup から無料で作ります。

### C2-2. プライベートリポジトリを新規作成

ブラウザ作業です。

1. https://github.com/new を開く
2. `Repository name` に好きな名前（例: `my-secretary`）
3. **`Private`** を選択（ここ重要）
4. `Initialize this repository with:` の項目は**すべて外す**（README
   も `.gitignore` も付けない）
5. 右下の `Create repository` をクリック

作成後に表示される URL を控えます（例:
`https://github.com/FRIEND_USER/my-secretary.git`）。

### C2-3. Personal Access Token を発行

push するときの認証に使います。

1. https://github.com/settings/tokens?type=beta を開く
2. `Generate new token` をクリック
3. `Token name` に適当に（例: `my-secretary-vps`）
4. `Expiration` は好みで（90 days 推奨）
5. `Repository access` は **`Only select repositories`** を選び、
   C2-2 で作ったリポジトリを選択
6. `Repository permissions` を開いて **`Contents`** を **`Read and write`**
   に変更（ここが重要、これを忘れると push で 403 が出ます）
7. 下の `Generate token` をクリック
8. 表示された `github_pat_xxxx...` の文字列を**安全な場所にコピー**（この
   画面を閉じると二度と表示されません）

### C2-4. remote を切り替えて初回 push

VPS 側で以下を実行します。`FRIEND_USER` と `my-secretary` の部分は
C2-2 で決めた値に書き換えてください。

```bash
cd ~/secretary
git remote set-url origin https://github.com/FRIEND_USER/my-secretary.git
git push -u origin main
```

`Username for 'https://github.com':` と聞かれたら **GitHub のユーザー名**、
`Password for 'https://...':` と聞かれたら **C2-3 で控えた PAT** を
貼り付けます（ここでは GitHub アカウントのログインパスワードではなく、
PAT を使うのがポイントです）。

毎回 PAT を打ちたくない場合は、以下で記憶させられます。

```bash
git config --global credential.helper store
git push   # 一度ここで PAT を入れれば次回以降は保存される
```

> 保存先は `~/.git-credentials` で平文です。VPS をあまり信用できない環境で
> 使う場合はやらず、毎回入れるか SSH 鍵認証に切替えてください。

push が成功したら、GitHub 側のリポジトリに `SETUP.md` などが並んで
いるはずです。以降は `.env` を書いたり設定を調整したあとで、こまめに
`git commit` → `git push` しておけばバックアップとしても機能します。

---

## C3. Google API 連携をセットアップ（Calendar / Gmail / Sheets / Drive）

秘書に Google カレンダーを見せたり、Gmail を監視させたり、Google
ドキュメント／スプレッドシートを操作させるための準備です。**全部有効に
しても Google 側に課金は一切発生しません**（すべて無料枠内）。

使わない機能があってもここで全スコープに権限を通しておくと、あとから
「これもやらせたい」となったときに再セットアップが不要で楽です。

### C3-1. Google Cloud プロジェクトを作成

ブラウザ作業です。

1. https://console.cloud.google.com にアクセス
2. 初回なら利用規約に同意
3. 画面上部のプロジェクト選択 → `New Project`（新しいプロジェクト）
4. プロジェクト名を適当に（例: `my-secretary`）→ `Create`
5. 作成後、上部のプロジェクト選択で新しく作ったプロジェクトを選んでおく

### C3-2. 必要な API を有効化する

1. 左メニュー（横三本線）→ `APIs & Services` → `Library`
2. 検索窓から以下の 5 つを 1 個ずつ検索して、各ページで `Enable` を押す:
   - **Google Calendar API**
   - **Gmail API**
   - **Google Sheets API**
   - **Google Drive API**
   - **Google Docs API**

5つとも `Manage` ボタンに変わったら有効化完了です。

### C3-3. OAuth 同意画面を作成

1. 左メニュー → `APIs & Services` → `OAuth consent screen`
2. `User Type` は **`External`** を選んで `Create`
3. `App name` に適当に（例: `my-secretary`）
4. `User support email` と `Developer contact information` に自分のメール
   アドレスを入れる（他は空欄のまま OK）
5. 下の `Save and Continue` を押す
6. `Scopes` のページはそのまま `Save and Continue`
7. `Test users` のページで `Add Users` → 自分の Google アカウントの
   メールアドレスを追加 → `Save and Continue`
8. 最後のサマリで `Back to Dashboard`
9. Dashboard の `Publishing status` に `Testing` と出ているので、
   **`Publish App`** ボタンを押して `Confirm` → `In production` にする

> ⚠️ **`Testing` のままにすると refresh token が 7 日で切れて、毎週
> `reauth.py` をやり直す羽目になります。必ず `In production` に
> 上げてください。**
>
> Production に上げても、個人用途であれば Google の審査（verification）
> は不要です。「確認されていないアプリ」の警告画面は認証時に出続けますが、
> `詳細 → 安全でないページに移動` で毎回進めば OK。センシティブスコープ
> を使う場合の「100 ユーザー上限」も個人用途なら実質問題になりません。

### C3-4. OAuth クライアント ID を発行

1. 左メニュー → `APIs & Services` → `Credentials`
2. 上部の `+ Create Credentials` → `OAuth client ID`
3. `Application type` で **`Desktop app`** を選ぶ
4. `Name` は適当に（例: `my-secretary-desktop`）
5. `Create` を押す
6. 出てきたダイアログの右下 `Download JSON` をクリック

ダウンロードされた `client_secret_xxxxx.json` を、VPS の
`~/secretary/integrations/gcal/credentials.json` に置きます。

**手元 PC から VPS に送る方法（どちらか1つ）**:

```bash
# 方法A: scp で送る（手元PCで実行）
scp ~/Downloads/client_secret_xxxxx.json shun@xxx.xxx.xxx.xxx:~/secretary/integrations/gcal/credentials.json
```

```bash
# 方法B: VPS側で新規作成して中身を貼り付ける
nano ~/secretary/integrations/gcal/credentials.json
# DLしたJSONをエディタに丸ごと貼り付け → Ctrl+O → Enter → Ctrl+X
```

### C3-5. 認証フローを走らせる

VPS 側で実行します。

```bash
python3 ~/secretary/integrations/gcal/reauth.py
```

スクリプトが認証 URL を表示するので、そのURLをブラウザで開きます。

**ブラウザはVPS上ではなく、手元PC or スマホのブラウザでOK**です。手順:

1. 認証 URL を **手元の端末のブラウザ**で開く
2. Google アカウントを選択（C3-3 でテストユーザーに追加したアカウント）
3. 「確認されていないアプリ」の警告が出たら `詳細` → `安全でない
   ページに移動` で進む（自分で作ったアプリなので安心してOK）
4. すべての権限にチェックを入れて `許可`（カレンダー・Gmail・Sheets・
   Drive にまとめて権限を通しておく）
5. Google が `http://localhost:8080/?code=...` のURLにリダイレクトする
   → ブラウザは「このサイトにアクセスできません」と出てOK、URLバーの
   **URL全体**をコピー
6. VPS 側の `reauth.py` のプロンプトにそのURLを貼って Enter

成功すると `~/secretary/integrations/gcal/token.json` が作成されます。

### C3-6. 動作確認

```bash
python3 ~/secretary/integrations/gcal/gcal_today.py
```

今日の予定が返ってくれば成功。

> ヘッドレス VPS でブラウザが VPS 上にない場合でも、`reauth.py` は
> URL コピー方式に対応しているので上記の手順で問題なく通ります。
> もし SSH トンネルで VPS の localhost:8080 を手元に引きたい場合は
> `docs/google.md` を参照。

---

## D. Discord で bot を作ってトークンを取る

ブラウザでの作業です。PCのブラウザからやってください。

1. https://discord.com/developers/applications を開く
2. 右上の **「New Application」** をクリック → 名前を適当に入れる（例: `my-secretary`）
3. 左メニューの **「Bot」** タブを開く
4. **「Reset Token」** を押す → 出てきた長い文字列を**コピー**して安全な場所にメモ
   （これが `DISCORD_BOT_TOKEN`。他人に見せない）
5. 同じ Bot 画面を下にスクロールして **「Privileged Gateway Intents」** の
   **「MESSAGE CONTENT INTENT」** をオンにして保存
6. 左メニューの **「OAuth2」** → **「URL Generator」** を開く
7. `SCOPES` で **`bot`** にチェック
8. `BOT PERMISSIONS` で以下にチェック
   - Send Messages
   - Read Message History
   - Add Reactions
   - Use Slash Commands
9. 下に出てくる URL をコピーしてブラウザで開く
10. 自分のサーバーを選んで **「認証」** → bot がサーバーに参加する

取ったトークンを VPS に置きます。`ここにトークンを貼る` の部分だけ書き換えて
実行してください。

```bash
mkdir -p ~/.claude/channels/discord
cat > ~/.claude/channels/discord/.env <<'EOF'
DISCORD_BOT_TOKEN=ここにトークンを貼る
EOF
chmod 600 ~/.claude/channels/discord/.env
```

> `~/secretary/.env` の方には bot トークンは書きません。上記1箇所に
> まとめてあります。

---

## E. 必要な Discord の ID を3つ取る

Discord クライアントでの作業です。

### 1. 開発者モードをオン

Discord の設定を開く → 左メニューの **「詳細設定」** → **「開発者モード」** をオン。

### 2. 自分のユーザー ID

自分のアイコン or ユーザー名を右クリック → **「ユーザー ID をコピー」**。
数字の羅列をメモ（これが `DISCORD_USER_ID`）。

### 3. 秘書と話すチャンネル ID

bot を招待したサーバーで、秘書とやり取りするチャンネル（まだなければ
`#bot` みたいな名前で1つ作る）を右クリック → **「チャンネル ID をコピー」**。
これが `DISCORD_CHANNEL_RANDOM`。

用途別にチャンネルを分けたくなったら、同じ要領で追加の ID を控えておいて
ください（任意）。

---

## F. Webhook トークンを生成

これは秘書サーバーの内部認証用です。1コマンドで生成できます。

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

出てきた長い16進文字列をコピーしてメモしてください（これが `WEBHOOK_TOKEN`）。

---

## G. `.env` を書く

ここまでで手元にある情報はこれ:

- `DISCORD_USER_ID`（数字）
- `DISCORD_CHANNEL_RANDOM`（数字）
- `WEBHOOK_TOKEN`（16進文字列）

トークン類を外部に送りたくないので、これは VPS のターミナルだけで完結させます。
下のコマンドの **`paste_*_here` の3箇所だけ書き換えて**、まるごとコピペして実行
してください。

```bash
cat <<'EOF' > ~/secretary/.env
DISCORD_USER_ID=paste_user_id_here
DISCORD_CHANNEL_RANDOM=paste_channel_id_here
WEBHOOK_PORT=8781
WEBHOOK_TOKEN=paste_webhook_token_here
GOOGLE_TOKEN_PATH=integrations/gcal/token.json
GCAL_CALENDAR_ID=primary
TASK_SHEET_ID=
GMAIL_ENABLED=false
GCAL_REMIND_ENABLED=false
BRAVE_API_KEY=
EOF
chmod 600 ~/secretary/.env
```

実行したら完了です。

> Google カレンダーや Gmail、Sheets、Brave 検索はいまは空欄でOKです。後で
> 秘書本人に頼めばセットアップしてくれます（その時に値が追加されます）。

---

## H. 秘書のキャラと自分のプロフィールを決める

`~/secretary/AGENT/IDENTITY.md`（秘書の性格）と `~/secretary/AGENT/USER.md`
（あなた自身の情報）の中身を埋めます。これも claude.ai に手伝ってもらうのが
ラクです。

### 手順

1. https://claude.ai を開く
2. 以下のプロンプトをコピペして送信
3. 質問がくるので順番に答える
4. 最後に `cat <<'EOF'` 形式のコマンドが2つ返ってくる
5. そのコマンドを VPS のターミナルに貼って実行

### 送るプロンプト

```
あなたは AI秘書テンプレート(my-secretary-template) のセットアップを
手伝うアシスタントです。

以下の順で1問ずつ質問してください。短文で聞いて、僕の回答を待ってから
次の質問に進むこと。全部答え終わったら、AGENT/IDENTITY.md と
AGENT/USER.md の中身を埋めた cat <<'EOF' 形式のheredocコマンドを
2つまとめて出力してください。

【IDENTITY用に聞くこと】
- 秘書の名前
- 秘書の一人称（僕 / 私 / 俺 / I など）
- 秘書の背景（年齢・職業・口調に影響する設定）
- 秘書の趣味・興味
- 性格の柱3つ（例: 落ち着いてる / ドライなユーモア / 計画より実装派）
- ユーザーとの関係性（後輩 / 執事 / パートナー等）
- 口調（フォーマル / カジュアル / 混合）
- 句読点ルール（文末「。」つけるか等）
- リアクション語彙: 同意・困惑・提案・謝罪・励ましそれぞれの言い回し例
- 笑い・困惑・感心の定型（www / うーん / なるほど 等）

【USER用に聞くこと】
- ユーザー本人の名前
- 秘書がユーザーを何と呼ぶか
- ユーザーの一人称
- タイムゾーン
- 仕事
- ユーザーの性格・好み・嫌いなこと・関係性の温度感

最終出力は以下の形式:

cat <<'EOF' > ~/secretary/AGENT/IDENTITY.md
# IDENTITY
...（全部埋めた完成版）
EOF

cat <<'EOF' > ~/secretary/AGENT/USER.md
# USER
...（全部埋めた完成版）
EOF

最終コマンドの前後に説明文は入れないでください。heredocだけ出力。
```

埋まった後に中身を確認したいときは:

```bash
cat ~/secretary/AGENT/IDENTITY.md
cat ~/secretary/AGENT/USER.md
```

違和感があれば claude.ai に「〇〇の部分もうちょい△△に」と言えば書き直して
くれます。

---

## I. サーバーを起動

```bash
bash ~/secretary/start_server.sh
```

動作確認:

```bash
screen -list                          # secretary が出れば OK
curl -s http://localhost:8781/health  # {"status":"ok",...} が返れば OK
```

中身を覗きたいときは `screen -r secretary` でアタッチ。`Ctrl+A` を押して
離してから `D` を押すとデタッチ（抜ける）できます。

初回起動直後に Claude Code が `/login` を求めてくることはまずありませんが、
もし `API Error: 401` 等が出ていたら `screen -r secretary` で `/login` を
叩いて通してください。

### Discord プラグインの初期設定

`screen -r secretary` で秘書のセッションに入ってから、以下を順に打ちます。

```
/discord:configure
/discord:access
```

`access` の方で、秘書と話したいチャンネル（or DM）を allowlist に入れて
ください。**この操作はターミナルからユーザー自身がやる必要があります**
（安全上の理由で、AI 側から代行できません）。

終わったら `Ctrl+A D` で抜けます。

---

## J. Discord から話しかけて動作確認

Discord クライアントから、先ほど設定したチャンネル（`DISCORD_CHANNEL_RANDOM`）
に何でもいいのでメッセージを送ってみてください。

秘書が返信してくれれば成功です。

返ってこない場合は「L. トラブルシューティング」を確認してください。

---

## K. 動いたあとの遊び方

ここから先は、**全部 Discord 上で秘書に話しかければ OK** です。
ターミナルに戻ってエディタを開く必要はもうありません。

例えばこんなことが頼めます。

- 「タスク追加しといて」「今あるタスク出して」
- 「毎朝8時に天気とタスクをまとめて送って」（→ cron ジョブを作ってくれる）
- 「Google カレンダーと繋ぎたい」（→ 手順を案内してくれる）
- 「Gmail の新着をここに流して」
- 「口調もうちょい柔らかくして」
- 「handoff 書いて」（セッション引き継ぎ用のメモを自動生成）

秘書は `docs/INDEX.md` をインデックスにして、`docs/` 配下のリファレンスを
必要なときに読む作りになっています。内部仕組みが気になったときは
`docs/INDEX.md` から辿ってください。

---

## L. トラブルシューティング

よくあるやつだけ並べます。もっと深い切り分けは `docs/ops.md` に
書いてあります（そちらは秘書自身も参照します）。

### 1. bot が Discord に返信しない

まず秘書が生きてるか確認。

```bash
screen -list
curl -s http://localhost:8781/health
```

`secretary` が出ていない、または `/health` が返らないときは再起動。

```bash
bash ~/secretary/start_server.sh
```

### 2. `screen` にアタッチしたら `API Error: 401` / `Please run /login`

Claude Code のログインが切れています。

```bash
screen -r secretary
# 中で /login を叩いてブラウザ認証
# 終わったら Ctrl+A D で抜ける
```

### 3. `ModuleNotFoundError: No module named 'xxx'`

依存パッケージが入っていません。

```bash
cd ~/secretary
pip install -r requirements.txt
```

### 4. Discord プラグインが「allowlist にない」と言う

ターミナルから `/discord:access` を叩いていないか、チャンネル ID が間違って
います。`screen -r secretary` で入って再実行してください。

### 5. `curl localhost:8781/health` が接続拒否される

webhook サーバーが落ちています。手動起動で動くか確認:

```bash
python3 ~/secretary/scripts/webhook_server.py
```

同じポートを別プロセスが掴んでいないかも確認:

```bash
lsof -i :8781
```

### 6. cron が動いていない気がする

```bash
crontab -l
sudo grep CRON /var/log/syslog | tail
tail -n 50 /tmp/health_check.log
```

スクリプトは**フルパス**で呼ぶ必要があります（`python3` ではなく
`/usr/bin/python3`）。詳細は `docs/cron.md` を参照。

### 7. `Permission denied` でファイルが読めない

`.env` は `chmod 600` が正解。スクリプトは所有者で実行されているか確認。

```bash
ls -la ~/secretary/.env
ls -la ~/.claude/channels/discord/.env
```

### 8. 何もわからない

秘書が動いているなら、Discord で「〇〇が壊れた、直して」と頼んでください。
秘書自身が `docs/ops.md` を読みながら切り分けを手伝います。

秘書がそもそも起動しないときは、以下3つを集めてから GitHub Issues か
知り合いに相談するのが早いです（**トークンは必ず伏字にしてください**）。

```bash
screen -list
curl -s http://localhost:8781/health
tail -n 50 /tmp/health_check.log
```

---

以上でセットアップは完了です。お疲れ様でした。
