# Notion Setup

Notion integration と database 共有の手順です。
この template では Delete 権限を外し、Read / Insert / Update だけを使います。

## ゴール

- Notion integration を作る
- capability を最小権限にする
- database を integration に共有する
- `.env` に token と database id を入れる
- 403 / 404 を切り分けられる

## 1. integration 作成

Notion の integration 管理画面で new integration を作ります。

設定:
- Name: 用途が分かる名前
- Associated workspace: 利用する workspace
- Type: internal integration

作成後に secret を取得します。
この secret は API key なので共有しません。

## 2. capability 設定

有効にする:
- Read content
- Insert content
- Update content

外す:
- Delete content

理由:
- 初期運用では削除操作が不要
- 誤操作時の被害を小さくできる
- log / task / memory の追加更新に必要な権限は満たせる

## 3. database を作る

Phase 1 の schema を使う場合は onboarding / schema 作成 script で作成できます。
手作業で作る場合は、以下のような DB を用意します。

- Tasks
- Diary
- Memory
- Action Log
- Conversation Log
- Script Invocations
- Cron Invocations
- Channels

最初から全部使わなくても構いません。
ただし `.env` の database id と script の期待値は合わせます。

## 4. integration を DB に共有

重要:
integration を作っただけでは database にアクセスできません。

手順:
1. Notion で対象 database を開く
2. 右上 menu を開く
3. Connections から integration を追加
4. DB ごとに共有する

parent page だけでは不十分な場合があります。
database 自体の connection を確認してください。

## 5. database id を取得

database を full page で開き、URL から id を取得します。
hyphen の有無は client により違いますが、値としては同じ ID です。

`.env` 例:

    NOTION_TOKEN=secret_xxx
    NOTION_TASKS_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    NOTION_DIARY_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    NOTION_MEMORY_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

## 6. `.env` permission

    chmod 600 .env
    grep NOTION .env

token を表示した結果は共有しないでください。

## 7. 接続 test

script がある場合:

    python scripts/onboarding.py --yes

または Notion を使う sample script を単体実行します。

    python templates/onboarded/task_digest.py

失敗時は status code を確認します。

## 8. status code 切り分け

401:
- token が違う
- `.env` が読めていない
- token の前後に空白がある

403:
- DB が integration に共有されていない
- capability が足りない

404:
- database id が違う
- page id と database id を混同
- workspace が違う

429:
- rate limit
- 短時間に再試行しすぎ

## 9. schema の注意

Notion property 名を変えると script 側の mapping が壊れることがあります。
schema json を使う場合は、まず自動生成された名前のまま動かします。

変更する場合:
- property 名
- type
- select option
- required 扱い
- script 側の参照名

を一緒に見直します。

## 10. security

- token は `.env` のみに保存
- public repository に database id を載せない
- Delete capability は外す
- 不要になった integration は revoke
- 共有先 DB を定期的に見直す

## 11. よくあるミス

- integration を作っただけで DB 共有していない
- parent page と database の共有を混同
- 別 workspace の integration を使っている
- capability 変更後に再確認していない
- `.env.template` を編集して `.env` を作っていない

## 12. 次の章

Notion が通ったら `docs/setup/claude-code.md` に進みます。
