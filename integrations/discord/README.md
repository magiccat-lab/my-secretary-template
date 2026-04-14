# Discord インテグレーション

Claude Code の `plugin:discord` プラグインが会話返信を担当し、cron スクリプト
からは `scripts/lib/discord_post.py` / `scripts/discord_send.py` が直接 REST
で送信します。bot トークンは `~/.claude/channels/discord/.env` に保存（両方
ここから読む）。

セットアップ・運用手順は `docs/SETUP.md` セクション 4 を参照。
