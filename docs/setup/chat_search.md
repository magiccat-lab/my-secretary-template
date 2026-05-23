# Chat Search Setup

Chat search reads the local Discord corpus database from Phase 1. It uses deterministic substring scoring and does not require a vector database.

## Enable

```env
FEATURE_CHATSEARCH=true
DISCORD_CORPUS_DB=data/discord_corpus.sqlite3
```

## CLI

```bash
python3 scripts/search/chat_search.py "invoice" --limit 5
```

Optional local reasoning:

```bash
python3 scripts/search/chat_search.py "invoice" --limit 5 --reason
```

The `--reason` mode uses the local Claude Code CLI only when available. Search results still work without it.

## Agent Import

```python
from scripts.search.chat_search import search_corpus

hits = search_corpus("deadline", limit=5)
```
