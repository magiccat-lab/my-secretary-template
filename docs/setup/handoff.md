# Handoff Setup

The handoff feature writes `data/claude/handoff.md` every night from local repository activity, pending tasks, and the sanitized Discord corpus.

## Enable

Set:

```env
FEATURE_HANDOFF=true
HANDOFF_TIME=03:30
HANDOFF_RESTART_COMMAND=
```

`HANDOFF_RESTART_COMMAND` is optional. Leave it empty to generate the handoff without restarting anything. If your deployment has a service manager, set it to the local restart command used by that machine.

## Install Cron

Run:

```bash
python3 scripts/system/install_cron.py add
```

The generated cron line sources `.env`, skips when `FEATURE_HANDOFF` is not `true`, then uses `scripts/lib/cron_gate.py`.

## Inputs

- `data/pending_tasks.json`
- `data/discord_corpus.sqlite3`
- today's `git log`

## Output

- `data/claude/handoff.md`

No external LLM API is required.
