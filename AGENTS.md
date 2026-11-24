# Project interaction logging

The user requests that work in this folder be logged before other work.

At the start of each chat, before project work, run:

```sh
python3 scripts/interaction_log.py start
```

This idempotently starts the local background collector. It catches up from Codex
session records and continuously captures this project's conversation, tools,
commands, edits, model selections, reported tokens, and related sub-agent runs.
Use `python3 scripts/interaction_log.py status` to check collection health.
If the collector is unavailable or failing, fix it or disclose the gap before
continuing. Never invent token counts or model identities.

Read `logs/README.md` for operation and coverage. Keep generated logs local and
out of commits. Do not read full logs back into chat context; use `summary.json`
or narrowly filtered records to avoid recursive log growth. Do not copy private
reasoning, internal instructions, or credentials into logs. This logging rule
does not independently authorize spawning sub-agents.
