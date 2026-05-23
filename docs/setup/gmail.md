# Gmail Setup

The Gmail monitor polls unread mail, applies local rules, and sends matched summaries to Discord.

## Enable

```env
FEATURE_GMAIL=true
GOOGLE_TOKEN_PATH=integrations/gcal/token.json
GMAIL_RULES_PATH=integrations/gmail/filter_rules.yaml
```

The monitor reuses the Google OAuth token from the calendar setup. The token must include Gmail modify scope.

## Rules

Edit `integrations/gmail/filter_rules.yaml`.

- `notify.senders`: sender substrings to notify
- `notify.keywords`: subject or snippet substrings to notify
- `notify.labels`: Gmail label names to notify
- `exclude.senders`: sender substrings to skip
- `exclude.keywords`: subject or snippet substrings to skip

## Test

```bash
FEATURE_GMAIL=true python3 integrations/gmail/gmail_monitor.py
```

No raw email body is stored in the repository.
