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

### 0-1. VPS 契約時に選ぶ項目

Xserver VPS（or 他 VPS）の契約画面で以下を選びます。

| 項目 | 推奨設定 |
|---|---|
| **OS** | **Ubuntu 24.04 LTS**（本テンプレートの動作確認 OS、 これ以外だと apt パッケージ名等で詰まる場面あり） |
| プラン | 2GB プラン以上（1GB だと Claude Code が OOM Kill される事故あり、 後述 §L 参照） |
| 認証方式 | **SSH 鍵認証**（パスワード認証より安全、 Xserver VPS では `key.pem` をダウンロードする方式） |
| ロケーション | 日本リージョン（cron が JST 前提なので時刻ずれ最小） |

契約完了後、 VPS パネルで以下を確認・入手します:

- **IP アドレス**（`xxx.xxx.xxx.xxx` 形式）
- **秘密鍵ファイル**（`key.pem` or `xxx.pem`、 契約画面 or 「SSH」 タブから 1 回だけダウンロード可、 **再ダウンロード不可なので大事に保管**）
- 初期ユーザー名（Xserver VPS は通常 `root`）

> ⚠️ パスワード認証で契約してしまった人は、 `ssh root@xxx.xxx.xxx.xxx` でパスワード入力ログインも可、 ただし鍵認証の方が安全。 §0-6 で鍵認証に切り替える手順を最後に通る。

他の VPS サービス（Hetzner / Vultr / DigitalOcean 等）でも、 大半が「鍵認証 + key.pem ダウンロード」方式、 同じ手順で動く。

#### 0-1-2. パケットフィルタで SSH [port 22] を許可する [Xserver VPS 必須]

> ⚠️ **これを先にやらないと §0-2 の SSH 接続が `Connection timed out` で詰む**、 contracts する人が高頻度で踏むハマりポイント。

Xserver VPS のデフォルトは **パケットフィルタが有効 + SSH [22] が許可されてない** ことが多い:

1. Xserver VPS パネル → 該当サーバー → **「パケットフィルタ設定」** タブ
2. 現在の設定を確認:
   - 「Web」「Mail」 等の template だけ ON で **SSH [22] 含まれてない**ことが多い
3. **「SSH」 を許可** にチェック ON [or「すべて許可」 で一時的にフルオープン]
4. 設定を保存、 反映に 1-2 分

> 💡 「すべて許可」 で進めると後でセキュリティ意識して個別 ON に絞り直すのを忘れがち、 最初から **「SSH」 のみ ON** が筋。 後の手順 [§I で `webhook_server` を立てる] で port 8781 を追加で開ける場面もあるので、 そこは別途。

到達性確認 [PowerShell or bash いずれでも]:

```powershell
# PowerShell
Test-NetConnection -ComputerName xxx.xxx.xxx.xxx -Port 22
# → TcpTestSucceeded : True なら通る
```

```bash
# Mac / Linux / WSL
nc -zv xxx.xxx.xxx.xxx 22
# → "Connection ... succeeded!" なら通る
```

→ ここで通らなければパケットフィルタ未開放、 VPS パネル戻って確認。

他 VPS [Hetzner / Vultr / DigitalOcean] では「Firewall」「Security Group」 等の名前で同等機能、 同じく SSH [22] 許可を確認する。

### 0-2. ダウンロードした key.pem を使って SSH 接続

手元 PC で作業します。 環境を最初に決める:

| 環境 | 使う shell | 利点 | 欠点 |
|---|---|---|---|
| **Mac / Linux ネイティブ** | bash / zsh | このテンプレのコマンドそのまま動く | — |
| **Windows + WSL2 (Ubuntu)** | bash | このテンプレのコマンドそのまま動く、 開発体験も Linux と同等 | WSL 経由のパス変換 [`/mnt/c/Users/...`] を最初だけ覚える |
| **Windows PowerShell native** | PowerShell | WSL 入れずに動く | `chmod` 等の Linux コマンドが無い、 別構文 [`icacls`] が必要、 後の手順でも WSL or 別ターミナル必須になる場面あり |

> 💡 **Windows なら WSL 推奨**、 後の手順 [B. Claude Code の bun install / cron セットアップ等] も bash 前提。 「とりあえず PowerShell」 で進めると後でハマる。 WSL2 + Ubuntu インストールは Microsoft Store から 5 分で済む。
>
> 既に PowerShell で進めてしまった場合の救済手順は §0-2-1 末尾参照。

#### 0-2-1. key.pem を `~/.ssh/` に配置 + 権限絞る

ダウンロードした秘密鍵ファイル（VPS により名前が違う、 `key.pem` / `xserver-vps-xxxxx.pem` 等）はブラウザの Downloads フォルダにある想定。 以下を実行して `~/.ssh/` に置き、 SSH が要求する権限まで絞ります（権限が緩いと `ssh` コマンドが拒否する）。

##### まずファイル名を確認

実際にダウンロードされたファイル名を確認 [VPS 側で名前は様々]:

```bash
# WSL [Windows + Ubuntu] の場合
ls /mnt/c/Users/$USER/Downloads/*.pem 2>/dev/null

# Mac / Linux ネイティブの場合
ls ~/Downloads/*.pem 2>/dev/null
```

→ 表示されたフルパスをコピー、 次の手順で使う

##### `~/.ssh/my-vps.pem` に配置 + 権限設定

```bash
mkdir -p ~/.ssh

# WSL の場合 [<実ファイル名> を上で確認した名前に置換]
cp /mnt/c/Users/$USER/Downloads/<実ファイル名>.pem ~/.ssh/my-vps.pem

# Mac / Linux ネイティブの場合
# cp ~/Downloads/<実ファイル名>.pem ~/.ssh/my-vps.pem

chmod 600 ~/.ssh/my-vps.pem
```

> 💡 **`mv` じゃなく `cp` を使う**: 秘密鍵は VPS 側で再ダウンロード不可、 元 file を残しておくとバックアップになる。 後で別端末からも接続したい時にもこの元 file が要る。
>
> 💡 ファイル名は `~/.ssh/my-vps.pem` のように分かりやすい名前で置くと後で混乱しない。 複数 VPS 持ちなら `~/.ssh/xserver-tokyo.pem` 等で識別する。

##### Windows PowerShell native の救済 [WSL 使えない / 使いたくない場合]

PowerShell には `chmod` が無いので、 SSH 鍵の権限設定は `icacls` を使う:

```powershell
# Move-Item は PowerShell でも動く、 mv alias でも OK
Move-Item ~/Downloads/key.pem ~/.ssh/my-vps.pem

# chmod 600 相当: 継承を切って自分だけ読み取り権限
$keyPath = "$HOME\.ssh\my-vps.pem"
icacls $keyPath /inheritance:r
icacls $keyPath /grant:r "$($env:USERNAME):(R)"

# SSH 接続テスト
ssh -i $HOME\.ssh\my-vps.pem root@xxx.xxx.xxx.xxx
```

> ⚠️ ただし **後の手順 [B. Claude Code install、 §A の apt 系、 cron 系] は bash 前提**、 PowerShell native だと詰まる。 SSH で VPS 側に入った後は VPS 上で bash が動くので OK だが、 「手元 PC 側で」 何か叩く時は WSL に切り替えるのが楽。

#### 0-2-2. 初回 SSH ログイン

```bash
ssh -i ~/.ssh/my-vps.pem root@xxx.xxx.xxx.xxx
```

- 初回は「続けますか?」と聞かれるので `yes` と入力
- パスフレーズを設定した場合は入力、 設定してなければそのままログイン
- プロンプトが `root@xxx:~#` のような形に変われば成功

#### 0-2-3.（毎回打つのを楽にする）SSH config にエイリアス登録

毎回 `-i ~/.ssh/my-vps.pem` を打つのが面倒なら以下を 1 回だけ登録:

```bash
cat >> ~/.ssh/config <<'EOF'
Host my-vps
    HostName xxx.xxx.xxx.xxx
    User root
    IdentityFile ~/.ssh/my-vps.pem
    ServerAliveInterval 60
EOF
chmod 600 ~/.ssh/config
```

これで `ssh my-vps` だけで接続できる。 `xxx.xxx.xxx.xxx` を実際の IP に置き換えて。

#### 0-2-4. ログイン後にパッケージ最新化

```bash
apt update && apt upgrade -y
```

### 0-3. [任意] 一般ユーザーを作成する [セキュリティ強化、 個人 VPS ならスキップ可]

> 💡 **個人開発 VPS なら 0-3 〜 0-6 全部スキップして §A に進んで OK**:
> - 鍵認証で外部から入れるのは現状 root だけ、 第三者は鍵無いと不可
> - 一般ユーザー + sudo の構成は会社運用 / 複数人運用の作法、 自分 1 人なら過剰
> - ただし pip / apt で常に root 権限の状態、 `rm -rf /` 系の typo 1 発で消えるリスクだけ留意
>
> 厳格化したい場合は以下を順にやる、 不要なら **§A まで飛ばして OK**。

root で作業し続けるのは危険なので、 自分用のユーザーを作ります。
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

### 0-4. 手元 PC の SSH 鍵を一般ユーザーに登録する

§0-2 で使った `key.pem` を一般ユーザーでも使えるよう、 root の authorized_keys を流用するのが最短。

**VPS 側 [root シェル]** で実行:

```bash
mkdir -p /home/shun/.ssh
cp ~/.ssh/authorized_keys /home/shun/.ssh/
chown -R shun:shun /home/shun/.ssh
chmod 700 /home/shun/.ssh
chmod 600 /home/shun/.ssh/authorized_keys
```

これで手元 PC から既存 `key.pem` で一般ユーザーにログイン可能:

```bash
# 手元 PC 側
ssh -i ~/.ssh/my-vps.pem shun@xxx.xxx.xxx.xxx
```

> ⚠️ **`ssh-copy-id` は手元 PC で叩くコマンド** [手元の公開鍵を VPS に送る仕組み]、 VPS 内 root シェルで叩くと「No identities found」 になる、 これは VPS 上に手元の id_*.pub が無いから。 上の手順は **VPS 側で root の authorized_keys を流用** する経路で、 ssh-copy-id 不要。

#### 0-4-代替: 手元 PC で新規鍵を作って ssh-copy-id [`key.pem` 経由じゃなく従来通りやりたい場合]

すでに `~/.ssh/id_ed25519.pub` がある人はこの作成ステップは不要。

```bash
# 手元 PC 側
ssh-keygen -t ed25519 -C "your-email@example.com"
```

- 保存場所は Enter（デフォルトでOK）
- パスフレーズは空 Enter でも入れても OK（入れた方が安全）

作った公開鍵を VPS の一般ユーザーに登録 [手元 PC 側で実行]:

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
sudo apt install -y python3 python3-pip git screen curl lsof at tmux unzip expect
```

> 💡 `expect` は Claude Code の初回起動時に出る UI prompt [Bypass Permissions / Trust this folder] を自動 accept する wrapper [`scripts/claude_wrapper.exp`] が使うので、 入ってないと cron 自動再起動が prompt で詰まる。 必須。

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

Claude Code は bun または npm で配布されています。**素人がハマる定番ポイント**
なので順番にやってください。

### B-1. bun ランタイムを入れる

```bash
curl -fsSL https://bun.sh/install | bash
```

完了すると `~/.bun/bin/` に bun コマンドが置かれます。

### B-2. PATH を通して bun が呼べることを確認

```bash
source ~/.bashrc
which bun
```

**`/home/あなたのユーザー名/.bun/bin/bun` のような行が出れば OK。**

`which bun` が**何も返さない** or `not found` と言われたら、PATH が通って
いません。以下を手動で叩いてください:

```bash
export PATH="$HOME/.bun/bin:$PATH"
echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.bashrc
which bun
```

> 💡 それでも出ない場合は **一度 SSH を切って入り直す**（`exit` → 再度 `ssh shun@xxx.xxx.xxx.xxx`）。
> shell の起動時に `.bashrc` が読み直されるので、これで通ることが多いです。

### B-3. bun 経由で Claude Code を入れる

```bash
bun install -g @anthropic-ai/claude-code
which claude
```

`/home/あなたのユーザー名/.bun/bin/claude` が出れば成功です。

### B-4.（うまくいかなかった場合）npm で代替インストール

bun のインストールやパス通しがどうしても通らないときは npm に切り替えます。

```bash
sudo apt install -y nodejs npm
sudo npm install -g @anthropic-ai/claude-code
which claude
```

`/usr/bin/claude` あるいは `/usr/local/bin/claude` が出れば成功。

### B-5. ログインフローを通す

```bash
claude
```

起動したら `/login` と打って、表示される URL を**手元の PC のブラウザ**で開き、
Claude のアカウントで認証してください（VPS 上にブラウザは無いので、URL を
コピーして自分の Mac/Windows で開く）。

ログインが終わったら `/exit` で一度抜けます。

> ✅ ここまでで `claude --version` が動けば B 完了。次は C へ進みます。

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

**手元 PC から VPS に送る方法**:

> ⚠️ **scp は手元 PC で叩くコマンド**、 VPS 内で叩いても VPS 上の `~/Downloads/` を探して not found になる、 ハマるポイント。 VPS から `exit` で抜けて手元 PC に戻ってから叩く [or 別ターミナル開く]。

##### 方法 A: scp で送る [手元 PC で実行]

> ⚠️ **scp も ssh と同じく `-i` で鍵を指定しないと `Permission denied (publickey)`** で詰む、 §0-2-3 の `~/.ssh/config` エイリアス未設定の場合は明示要。

```bash
# Mac / Linux / WSL の bash
scp -i ~/.ssh/my-vps.pem ~/Downloads/client_secret_xxxxx.json shun@xxx.xxx.xxx.xxx:~/secretary/integrations/gcal/credentials.json
```

```powershell
# Windows PowerShell native
scp -i $HOME\.ssh\my-vps.pem $HOME\Downloads\client_secret_xxxxx.json shun@xxx.xxx.xxx.xxx:~/secretary/integrations/gcal/credentials.json
```

##### 方法 A-代替: `~/.ssh/config` 設定済の場合 [§0-2-3 でやってれば]

```bash
scp ~/Downloads/client_secret_xxxxx.json my-vps:~/secretary/integrations/gcal/credentials.json
```

= alias 経由、 `-i` 不要

##### 方法 B: nano で貼り付ける [scp が動かない / 確実に楽な方法]

VPS の ryu / shun シェルで:

```bash
mkdir -p ~/secretary/integrations/gcal/
nano ~/secretary/integrations/gcal/credentials.json
```

→ nano エディタが開く

手元 PC の `client_secret_xxxxx.json` を **テキストエディタで開いて全文選択 → コピー** [Windows PowerShell で `Get-Content $HOME\Downloads\client_secret_xxxxx.json | Set-Clipboard` でも OK]、 nano に **貼り付け** [PowerShell + ssh の場合は右クリック or マウスホイール、 WSL なら `Ctrl+Shift+V`]

→ `Ctrl+O` → Enter で保存 → `Ctrl+X` で nano 終了

##### 方法 C: cat heredoc で 1 発で書く [json が短い時]

```bash
# VPS シェルで実行、 ペーストしてから Enter Ctrl-D
cat > ~/secretary/integrations/gcal/credentials.json <<'EOF'
{ "installed": { "client_id": "...", ... } }
EOF
```

---

### C3-4-1. credentials.json が置けたか確認

```bash
ls -la ~/secretary/integrations/gcal/credentials.json
cat ~/secretary/integrations/gcal/credentials.json | head -3
```

サイズ ≥ 200 byte + `{ "installed": {` 等の json 開始が見えれば OK。

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

## G2. Notion 連携（タスク・Wishlist を Notion で管理する、任意）

タスク（`pending_tasks.json`）と「行きたい店リスト」「読みたい本リスト」を
Notion DB に同期して、スマホからも見られるようにします。Notion の無料プラン
で十分動きます。**使わない人はこのセクション全部スキップして H に進んで OK。**

### G2-1. Notion Integration を作る

ブラウザ作業:

1. https://www.notion.so/my-integrations を開く
2. `+ New integration` をクリック
3. 名前を適当に（例: `my-secretary`）
4. 関連付ける Workspace は自分の personal を選ぶ
5. `Type` は **`Internal`** を選択
6. `Submit` をクリック
7. 表示された **`Internal Integration Secret`** （`secret_xxxx...` で始まる
   長い文字列）をコピーして安全な場所にメモ（これが `NOTION_TOKEN`）

### G2-2. Notion DB（Tasks 用）を作る

別タブで Notion を開いて作業:

1. 自分のワークスペースの好きなページに `/database` と入力
2. メニューから **`Database - Full page`** を選ぶ
3. ページタイトルを `Tasks` 等に変更
4. デフォルトの `Name` プロパティ（title）はそのまま
5. 右上の `+` で以下のプロパティを順に追加（**全部必須**、型を間違えると同期失敗）:

| プロパティ名 | 型 |
|---|---|
| `Done` | Checkbox |
| `SourceKey` | Text（rich_text） |
| `Created` | Date |
| `Completed` | Date |
| `Remind` | Date |
| `Detail` | Text（rich_text） |
| `Type` | Select（任意。あると便利） |

### G2-3. Integration を DB に許可する

このステップを忘れると API が 403 で弾かれます。

1. Tasks DB ページの右上「**…**」メニューを開く
2. `Connections` または `+ Add connections` をクリック
3. `Connect to` の検索窓に G2-1 で作った Integration 名を打って選択
4. 確認ダイアログで `Confirm`

### G2-4. Tasks DB の ID を取得

Tasks DB ページのブラウザ URL を見ます。例:

```
https://www.notion.so/USERNAME/Tasks-7c2c9b3a4f1e44d8a9f2e8b1d0c7e6f3?v=...
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       この 32 文字が DB ID
```

`Tasks-` の **直後** から `?v=` の **直前** までの 32 文字（ハイフン無し）が
DB ID です。コピーしてメモ。

### G2-5. Wishlist DB も同じ手順で作る（任意）

「行きたい店」「欲しい本」「あとで読みたい記事」用に別 DB を 1 個。
G2-2 と同じ要領で `Wishlist` DB を作り、プロパティを以下に揃えます:

| プロパティ名 | 型 |
|---|---|
| `名前` | Title（デフォルト） |
| `カテゴリ` | Select（飲食店 / Tips / ショッピング 等） |
| `ステータス` | Select（未訪問 / 行った / 不要 等） |
| `エリア` | Text |
| `情報源` | URL or Text |
| `メモ` | Text |
| `追加日` | Date |

G2-3, G2-4 を同様に行って、ID をメモします。

### G2-6. `.env` に追記

VPS 側で:

```bash
nano ~/secretary/.env
```

ファイル末尾に追記して保存（`Ctrl+O` → Enter → `Ctrl+X`）:

```
NOTION_TOKEN=secret_paste_here
NOTION_DB_TASKS=paste_tasks_db_id_here
NOTION_DB_WISHLIST=paste_wishlist_db_id_here
```

### G2-7. 同期スクリプトを 1 回手動実行して確認

```bash
python3 ~/secretary/scripts/integrations/notion/sync_pending_to_notion.py
```

`✅ sync 完了: created=N / updated=M / failed=0` のような行が出れば成功。
Notion の Tasks DB を見ると、ローカルの pending_tasks.json の中身が反映
されているはずです。

### G2-8. 5 分おきに自動同期する cron を追加

```bash
crontab -e
```

末尾に 1 行追加（`YOUR_USER` を自分のユーザー名に書き換え）:

```
*/5 * * * * /usr/bin/python3 /home/YOUR_USER/secretary/scripts/integrations/notion/sync_pending_to_notion.py >> /tmp/sync_notion.log 2>&1
```

> ⚠️ `python3` ではなく **絶対パスの `/usr/bin/python3`** を使うこと。
> cron の PATH には `python3` が無いことがあります。

### G2-9. Wishlist 追加コマンドの動作確認（任意）

```bash
python3 ~/secretary/scripts/integrations/notion/wishlist_add.py \
  --name "テスト追加" --category "Tips" --memo "セットアップ確認"
```

`✅ 追加成功` が出れば OK。Notion の Wishlist DB に新規ページが見えるはず。

ここまで終わったら H に進みます。

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

#### ✅ 初回起動の UI 壁 [Bypass Permissions / Trust this folder] は **自動突破される**

Claude Code は起動時に 2 種類の UI prompt を出す:
- **壁1**: `--dangerously-skip-permissions` 起動時の `Bypass Permissions` 確認 [初回のみ、 下矢印 + Enter で accept]
- **壁2**: `Trust this folder?` ダイアログ [初回のみ、 Enter で accept]

このテンプレートでは `scripts/claude_wrapper.exp` [expect script] が両方を自動 accept するので、 **手動 attach は不要**。 §A で `apt install expect` 入れていれば、 `start_server.sh` / `weekly_restart.sh` は壁を素通りで起動する。

> 💡 受諾状態は `~/.claude.json` の `projects[$HOME/secretary].hasTrustDialogAccepted` に永続化される、 2 回目以降は expect も即抜ける [timeout=30s]。
>
> 💡 中身を覗きたい時は `screen -r secretary` でアタッチ可、 `Ctrl+A` を押して離してから `D` でデタッチ。
>
> 💡 自動化の仕組み詳細は [ペパボの記事](https://zenn.dev/pepabo/articles/claude-code-cron-autonomous-ui-walls) 参照。

初回起動直後に Claude Code が `/login` を求めてくることはまずありませんが、
もし `API Error: 401` 等が出ていたら `screen -r secretary` で `/login` を
叩いて通してください。

### Discord プラグインの初期設定

`screen -r secretary` で秘書のセッションに入ってから、 まず Discord プラグインを install + reload する [これを忘れると `/discord:configure` が「コマンド無し」 で詰む]:

#### 1. プラグインを install + 有効化

```
/plugins
```

→ プラグイン list が表示される、 **`discord`** を選んで install [or enable]

[既に install 済の場合 `enabled` 表示、 そのまま次へ]

#### 2. プラグインを reload [認識させる]

`/plugins` 画面を抜けた後:

```
/reload
```

[or 一度 `Ctrl+A D` で screen から抜けて、 `screen -r secretary` で入り直す。 reload 系は Claude Code バージョンによって挙動違うことあり、 ダメなら一旦 exit + 再起動が確実]

#### 3. Discord 設定 + ch allowlist

```
/discord:configure
```

これで Discord 接続が確立する [bot token を読み込んで Gateway 接続]。

#### 4. ch allowlist の登録 [2 経路、 どっちか]

##### 4-A. 自動 [`.env` 値を使って 1 発設定、 推奨]

screen から `Ctrl+A D` で一旦抜けて、 通常のシェルに戻ってから:

```bash
python3 ~/secretary/scripts/discord_access_apply_env.py
```

これで:
- `DISCORD_CHANNEL_RANDOM` を allowlist に追加
- `requireMention: false` [mention 不要、 ch のメッセージ全部に応答]
- `DISCORD_USER_ID` を DM allow にも追加

複数 ch 一括許可したい場合は env で追加:
```bash
DISCORD_CHANNEL_EXTRA="111,222,333" python3 ~/secretary/scripts/discord_access_apply_env.py
```

設定反映には `screen -r secretary` でセッションに戻って `/reload` [or 一旦 exit + 再起動]

##### 4-B. 対話 [元の方式、 細かく制御したい時]

`screen -r secretary` で秘書のセッションに入った状態で:

```
/discord:access
```

→ 対話で許可するチャンネル / DM を 1 つずつ選ぶ
→ **mention 必須 / 不要** も対話で指定 [allowlist 対象 ch なら mention 不要に倒すのが楽]

> ⚠️ **この操作はターミナルからユーザー自身がやる必要があります**（安全上の理由で、 AI 側から代行できません）

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
