# Diary Setup

Diary capture sends a daily Discord prompt and writes the first later corpus reply into the existing Notion Diary database.

## Enable

```env
FEATURE_DIARY=true
DIARY_PROMPT_TIME=21:30
NOTION_DB_DIARY=
```

## Required Notion Schema

Use the Phase 1 `Diary` database. Required properties are:

- `Title`
- `SourceKey`
- `Status`
- `CreatedAt`
- `UpdatedAt`
- `Source`
- `ExternalId`
- `Date`
- `Mood`
- `Summary`
- `Highlights`
- `NextActions`

Do not create a duplicate Diary database.

## Flow

1. `scripts/diary/daily_prompt.py` posts the question.
2. Phase 1 corpus capture stores the reply in `data/discord_corpus.sqlite3`.
3. `scripts/diary/diary_writer.py` writes one Notion page for the day.
