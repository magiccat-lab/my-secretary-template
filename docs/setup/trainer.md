# Trainer Setup

The trainer kit proposes memory and persona improvements from local sanitized data. It is review-first: persona files are never rewritten automatically.

## Enable

```env
FEATURE_TRAINER=true
TRAINER_LOOKBACK_DAYS=14
TRAINER_MIN_CONFIDENCE=0.60
```

## Commands

```bash
python3 scripts/trainer/memory_extractor.py
python3 scripts/trainer/persona_evolution.py
python3 scripts/trainer/til_promoter.py
```

## Outputs

- Memory candidates are written to the existing Notion Memory database.
- Persona suggestions are written to `data/notes/persona_suggestions.md`.
- Repeated failure patterns are written to `data/notes/knowledge.md`.

## Required Notion Schema

Use the Phase 1 `Memory` database. Required properties are:

- `Title`
- `SourceKey`
- `Status`
- `CreatedAt`
- `UpdatedAt`
- `Source`
- `ExternalId`
- `Kind`
- `Confidence`
- `Summary`
- `Evidence`
- `ExpiresAt`

Do not create a duplicate Memory database.
