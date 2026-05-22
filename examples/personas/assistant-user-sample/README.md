# assistant-user-sample — generic persona example

このディレクトリは秘書の persona [AGENT/] の **generic な雛形** です。
fork した直後に `AGENT/` を 自分用に書き換えるとき、 ここをコピーして
始めると速いです。

## ファイル

| ファイル | 役割 |
|---|---|
| `IDENTITY.md` | 秘書のキャラクター [名前 / 一人称 / 口調 / 性格] |
| `USER.md` | ユーザー [自分自身] の情報 [秘書が知っておくべき profile] |
| `AGENTS.md` | 秘書の振る舞いルール [禁止事項 / Discord 返答ルール 等] |
| `JOBS.md` | 秘書が動かす定期ジョブの索引 |

## 使い方

```bash
# generic な雛形を AGENT/ にコピー [既存を上書きする前にバックアップ]
cp -r examples/personas/assistant-user-sample/* AGENT/

# プレースホルダ {{xxx}} を埋める
# claude.ai を使うと楽: SETUP.md セクション H 参照
```

または `scripts/onboarding.py` を 走らせれば対話式で埋まる:

```bash
python3 scripts/onboarding.py
```

## 注意

- このディレクトリの中身は **完全に generic**、 個人情報・固有名詞は含まれない
- 自分用 persona を作るときは `AGENT/` 配下に置き、 ここ [examples/] には commit しない
- `IDENTITY.md` の `ASSISTANT_NAME` 等の placeholder は、 自分の好きな名前に置き換えて OK
