# my-secretary-template

小さな VPS 上で常時稼働する、自分専用の AI 秘書を動かすためのテンプレート。
Claude Code をエンジンに、プライベートな Discord チャンネルから話しかけられます。
セットアップ後は、cron 登録・Google 連携・トークン管理まで、すべて起動後の
**エージェントとの会話**でやります。ターミナルで長文を貼ったりエディタを
開いたりしません。

## はじめに読むもの

- **[`SETUP.md`](SETUP.md)** — 人間向けの初回セットアップ手順。
  VPS を借りたばかりの状態から Discord で会話できるまで、そのまま上から
  順にやれば動くように書いてあります。まずここを見てください。

- **[`docs/INDEX.md`](docs/INDEX.md)** — エージェント（起動後の秘書）が
  運用時に参照するリファレンス群の索引。仕組みが気になったときに覗く用。

## 必要なもの

| | |
|---|---|
| Claude Pro プラン | https://claude.ai |
| Linux VPS（Xserver / Hetzner / Raspberry Pi 等） | 月 $5〜10 |
| Discord アカウント + bot | 無料 |
| Google アカウント（Calendar / Gmail を使う場合のみ） | 無料 |

## ライセンス

MIT。[LICENSE](LICENSE) を参照。
