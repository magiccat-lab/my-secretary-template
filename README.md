# my-secretary-template

小さな VPS 上で常時稼働する、自分専用の AI 秘書を動かすためのテンプレート。
Claude Code をエンジンに、プライベートな Discord チャンネルから話しかけられます。

初回セットアップ（VPS・Discord・Google 連携・各種トークン）は `SETUP.md` を
上からコピペでこなします。**起動後の日々の運用**（新しい cron の追加、タスク
管理、リマインド設定など）は、ターミナルに戻らず **エージェントとの会話**で
やれます。

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

## セキュリティ上の前提

このテンプレートは **自分だけが使う private VPS** での運用を前提としています。
Claude Code を `--dangerously-skip-permissions` で常駐させるため、同一ホスト上の
他ユーザーや外部ネットワークからの入力が信頼境界を越えて到達しないよう注意してください。

- webhook サーバーはデフォルトで `127.0.0.1` のみにバインドします。
  外部公開する場合は `WEBHOOK_HOST` + reverse proxy (HTTPS) を設定してください。
- メール通知はデータとして扱われますが、LLM への入力である以上、
  完全なプロンプトインジェクション耐性は保証されません。

## ライセンス

MIT。[LICENSE](LICENSE) を参照。
