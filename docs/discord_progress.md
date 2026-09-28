# discord_progress.md — Discordの進行状況表示hook

モデルに頼らず、hookとDiscord REST APIだけで機械的にDiscordの進行状況を
出す仕組み。「reply/edit_messageを1度も送らずにターンを終える」誤りも
Stop hookが機械的に差し戻す。

---

## 1. ユーザーから見える動き

1. Discordで話しかけると、そのメッセージに📨が付く（受け取った合図）
2. 秘書が最初の返信を送る（成功した）タイミングで📨が外れて▶が付く（作業中の合図）
3. 短いターンはそのまま。長いターンだけ「🔄 作業中 (経過 N 分)」という吹き出しが
   1分おきに経過時間を更新しながら出る（`SECRETARY_NAME` を設定していれば
   「🔄 {name}が作業中 (経過 N 分)」になる）
4. ターンが終わって返信が届いたことを確認できたら、▶が外れて✅が付き、吹き出しは消える
5. 90分経っても終わらない場合は吹き出しが「⚠️ 応答が止まっています (経過 N 分)」に変わり、
   受信メッセージにも⚠️が付く

---

## 2. しくみ

### 2-1. 使っている部品

- `scripts/lib/discord_rest.py` — Discord REST APIの薄いラッパー（react/unreact/post/edit/delete）。
  例外を投げない。失敗は `$SECRETARY_DIR/data/logs/discord_rest.log` に書くだけ
- `scripts/lib/discord_progress_state.py` — 状態ファイルのI/O、`<channel>`タグのパース、
  配信成否の判定、editorプロセスの起動、transcript読み取りの共通ヘルパー
- 状態ファイル: `$SECRETARY_DIR/data/discord_progress/<chat_id>.json`
  （`message_id` / `started_at` / `stage` / `progress_message_id` / `editor_pid`）
- `scripts/discord_progress_editor.py` — 進行バブルの投稿・編集ループ。hookからデタッチで
  起動され、chat_idごとに1プロセスだけが担当する

### 2-2. hookの役割分担（3本、`.claude/settings.json` に登録済み）

Claude Codeの hook は同じイベントに複数登録されていると**並行実行**される。
「配信を確認してblockする」役と「確認して✅にする」役を別プロセスのままにすると、
blockすべきターンを進行表示側だけが誤って配信済み扱いにする競合が起きる。そのため
Stopの判定は1本に統合してある。

| hook | イベント | 役目 |
|---|---|---|
| `scripts/hooks/discord_progress_start.py` | UserPromptSubmit | 早期着手（ベストエフォート）。📨を付け、状態を作り、editorを起動する |
| `scripts/hooks/discord_progress_posttool.py` | PostToolUse（matcher: `mcp__plugin_discord_discord__reply\|mcp__plugin_discord_discord__edit_message`） | **確実な入口**。reply/edit_messageが**成功**した最初の1回で📨→▶。状態が無ければここで作ってeditorも起動する |
| `scripts/hooks/discord_turn_end.py` | Stop | 配信確認とその後始末を1つに統合したcoordinator。詳細は次項 |

**UserPromptSubmitがDiscordのchannel messageで本当に発火するかは未確認**。発火しなくても
PostToolUseとStopの2つだけで一連の状態遷移が完結するように作ってあるので、進行表示の
正しさはUserPromptSubmitの発火有無に依存しない（発火しない場合は📨が出ず▶から始まるだけ）。
これは `tests/test_discord_progress.py` の
`test_posttool_and_turn_end_work_without_userpromptsubmit` で担保している。

### 2-3. discord_turn_end.py（Stop）の判定

直近の人間由来userメッセージを探し、それ以降で同じchat_id宛のreply/edit_messageの
tool_resultが `state.is_delivered(tool_name, tool_result)` でTrueになれば「配信済み」と
判定する。判定はfail-closed:
- `is_error`/`isError`（どちらの綴りでも）が`true`なら即未配信
- それ以外でも、本文に成功パターン（reply: `"sent (id:"` / edit_message: `"edited (id:"`）
  が無ければ未配信のまま。`is_error: false`や応答が空/Noneだけでは成功と認めない
  （誤って✅にする方が、差し戻しが1回増えるより害が大きいため）

失敗した呼び出しは無視して後続の再送を探し続けるので、1回失敗して2回目で成功した
場合も「配信済み」になる。

判定の結果:
- **配信済み** → 状態ファイルの`message_id`が今回の受信メッセージ（transcriptのタグ）と
  **一致する時だけ**📨/▶を外して✅を付け、進行バブルを消して状態ファイルを消す。
  一致しない（chat_idは同じだが古い別turnの状態が残っている）場合はその状態には
  一切触れず、受信メッセージへの✅だけ付ける。`discord_progress_posttool.py`が
  既存状態を再利用する時も同じ確認をする（`tool_input.reply_to`があればそれを優先、
  無ければ`edit_message`呼び出しも含めてtranscriptの直近受信タグから復元し、
  どちらも取れない/既存状態と食い違う場合は既存状態に一切触れない）
- **未配信 かつ `DISCORD_REPLY_GUARD_ENABLED=0`** → 差し戻さない。何もしない
  （進行表示だけ切りたい`DISCORD_PROGRESS_ENABLED=0`とは別軸のフラグ。配信済みターンの
  後始末はこのフラグと無関係に動く）
- **未配信 かつ stop_hook_activeでない** → 差し戻すJSON（`decision: block`）を出す。
  文言は「reply / edit_messageを1度も呼んでいない、AGENT/AGENTS.md『Discord 返信ルール』
  を見て送り直せ」という内容
- **未配信 かつ stop_hook_active** → 配信済み扱いにしない。何もしない
  （放置されたターンはeditorのMAX_MINUTES経過で⚠️になる）

---

## 3. message_idが分からない場合

`discord_progress_posttool.py` は状態が無いとき、`tool_input.reply_to`（reply toolに
明示的な返信先が指定されていれば）→ それも無ければtranscriptから直近の受信タグを
復元、の順で受信メッセージのIDを探す。どちらも取れなければ `message_id` は `null` のまま
進める。この場合📨/▶/⚠️のreactionは（対象が無いので）静かにskipされるが、
「🔄 作業中」バブルの投稿・編集はchat_idだけで出来るので変わらず動く。

---

## 4. 進行バブル書き戻しの競合対策

`discord_rest.post()`（バブルの最初の投稿）はネットワーク呼び出しなので時間がかかる。
その最中に`discord_turn_end.py`がstateを消す/`stage: done`にする競合が起こり得るため、
投稿後の書き戻しは`lib.discord_progress_state.update()`（`fcntl.flock`で
chat_id単位に排他し、書き込むたびに`generation`を+1する）で行い、投稿前と状態が
変わっていないか（消えていない・`stage`が`done`でない・`editor_pid`が自分のまま・
`message_id`一致・`generation`一致）を確認してから書き戻す。1つでも変わっていたら、
今投稿したbubbleを削除して何も書き戻さずに終了する（古いスナップショットで
消えたはずの状態を復活させない）。

---

## 5. editorの孤児化対策

`discord_progress_editor.py` は次のいずれかで終了する:
- 状態ファイルが消えた
- `stage` が `done` になった
- 状態ファイルの `editor_pid` が自分以外になった（新しいeditorに引き継がれた。
  1つのchat_idに複数のeditorが同時に吹き出しを取り合わないようにするための仕組み）
- 経過が `DISCORD_PROGRESS_MAX_MIN` を超えた（⚠️を出して**状態ファイルも消して**終了。
  孤児のまま90分粘り続けない）

---

## 6. インストール

同梱の `.claude/settings.json` で自動。`start_server.sh` が `~/secretary` を cwd に
して Claude Code セッションを起動するので、リポジトリ同梱の project settings が
そのまま効く（別途スクリプトを実行して `~/.claude/settings.json` に書き込む必要は無い）。

無効化は `.env`:
- `DISCORD_PROGRESS_ENABLED=0` — 📨/▶/✅とバブルを丸ごと止める
- `DISCORD_REPLY_GUARD_ENABLED=0` — reply未送信での差し戻し（block）だけ止める

変更後は `start_server.sh` でセッションを再起動すること（hookの設定はセッション
起動時に読まれる）。

---

## 7. 環境変数（`.env.template` 参照）

| 変数 | デフォルト | 意味 |
|---|---|---|
| `SECRETARY_NAME` | （空） | バブル・reactionに出す秘書の名前。空なら名前を出さず「🔄 作業中 (経過 N 分)」になる |
| `DISCORD_PROGRESS_ENABLED` | 1 | 0で進行状況表示を丸ごと無効化（reply配信確認のblockは無効化されない） |
| `DISCORD_PROGRESS_FIRST_DELAY_SEC` | 30 | 最初のバブルを出すまでの待ち時間（秒） |
| `DISCORD_PROGRESS_INTERVAL_SEC` | 60 | バブルの更新間隔（秒） |
| `DISCORD_PROGRESS_MAX_MIN` | 90 | これを超えたら停滞とみなす経過時間（分） |
| `DISCORD_REPLY_GUARD_ENABLED` | 1 | 0でreply未送信時の差し戻し（`decision: block`）を無効化。配信済みターンの後始末はこのフラグと無関係に動く |

hookは `start_server.sh` が `set -a; source .env; set +a` で読み込んだ環境を引き継いだ
Claude Codeセッションの中で動くので、`.env` に書いた値がそのままhookに渡る。

### bot tokenの読み込み順

`lib.discord_rest.load_token()` は次の順で探す（最初に見つかったものを使う）:
1. 環境変数 `DISCORD_BOT_TOKEN`
2. `$DISCORD_ENV_FILE`
3. `$DISCORD_STATE_DIR/.env`（複数botを使い分けるセッション向け。本体のトークンとは混ざらない）
4. `~/.claude/channels/discord/.env`（デフォルト。`SETUP.md` セクションDで作る場所）

---

## 8. 必要なDiscord bot権限

- **Add Reactions**（reactionを付ける・外すのに必要）。`SETUP.md` セクションDの
  bot権限一覧に既に含まれているので、通常のセットアップをそのまま進めていれば
  追加の権限設定は不要
- ~~Manage Messages~~ は不要。bot自身が投稿したメッセージ（進行バブル）を削除するのは
  自分のメッセージなのでこの権限を要求しない

---

## 9. トラブルシューティング

- **動いているか怪しい** : `$SECRETARY_DIR/data/logs/discord_rest.log` と
  `discord_progress_editor.log` を見る。REST呼び出しの失敗理由（token無し・404など）と
  editorのライフサイクル（開始・終了理由）がそれぞれ書いてある
- **一時的に止めたい** : `.env` の `DISCORD_PROGRESS_ENABLED=0` にしてセッション再起動。
  reactionもバブルも一切出なくなる（reply配信確認のblockはこれとは独立に動き続ける。
  blockだけ止めたいなら `DISCORD_REPLY_GUARD_ENABLED=0`）
- **状態ファイルが残ったままになる** : 通常は `discord_turn_end.py` か
  editorのMAX_MINUTES到達時に自動で消える。手で消したい時は
  `$SECRETARY_DIR/data/discord_progress/<chat_id>.json` を消せばよい（次のターンで作り直される）

---

## 10. テスト

```bash
python3 -m unittest discover -s tests -p 'test_discord_progress.py'
```

ネットワークは使わない（`discord_rest`の関数をフェイクに差し替える）。
