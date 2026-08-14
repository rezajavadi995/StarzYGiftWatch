# CODEX_TASK.md — Initial v1 implementation

Build StarzYGiftWatch from this repository contract. Keep it lightweight and production-usable; do not turn it into StarzYFire.

## Deliverables

Implement roughly this shape (adjust names only when it materially simplifies things):

```text
starzygiftwatch/
  __init__.py
  config.py
  db.py
  watcher.py
  alerts.py
  telegram_admin.py
  cli.py
  main.py
scripts/check.sh
install.sh
requirements.txt
.env.example
.gitignore
tests/
.github/workflows/ci.yml
```

## Core behavior

1. Use aiogram's official Bot API support for `getAvailableGifts`.
2. Poll on a configurable interval, default 5s, validated to a safe range (2..3600s).
3. First successful response becomes a durable baseline with no NEW alerts.
4. Normalize each Gift into JSON-safe data keyed by gift ID. Preserve relevant official fields, including price and limited/personal counts, and safely include newly exposed simple serializable fields.
5. Compare successful snapshots and create durable events for:
   - new gift ID (highest priority)
   - removed/unavailable gift ID
   - price change
   - total/remaining global count change
   - total/remaining personal count change
   - other meaningful normalized field changes
6. Ignore ordering-only differences.
7. Event table has a deterministic fingerprint/unique constraint. Commit event before Telegram send.
8. Alert worker sends pending events to `ADMIN_ID`; mark sent only after success. Retry transient failures with bounded exponential backoff; honor Telegram `retry_after` exactly/conservatively.
9. Watcher ON/OFF is durable. Disabling polling must not destroy baseline/history.
10. SQLite WAL, schema versioning/migration small enough for v1, short transactions, no network I/O inside write transactions.

## Telegram admin UI

Owner-only. `/start` or `/admin` opens a compact inline panel with watcher status, last successful poll, interval, gift count, pending alert count and last change. Include controls for ON/OFF, interval, current gifts, recent changes, test alert and confirmed baseline rebuild. Non-admin users get no admin panel.

## Terminal `watch` menu

Create a friendly numbered menu callable from any directory after install. It must configure Bot Token, Admin ID and interval; show service/health; enable/disable watcher; show baseline; send test alert; rebuild baseline with confirmation; show recent logs; restart service; exit. Mask token output.

Important: system `/usr/bin/watch` already exists. Install `/usr/local/bin/watch` wrapper without deleting it. No args launch our CLI. Any args must `exec` the original watch binary with the exact argument vector.

## Installer

`install.sh` is idempotent for Ubuntu/Debian. It should:

- require/elevate to root cleanly;
- install minimal OS prerequisites (`python3`, venv, git/curl as needed);
- install/update repository at `/opt/starzygiftwatch`;
- create `.venv` and install pinned Python requirements;
- create `starzygiftwatch` system user and `/opt/starzygiftwatch/data` ownership;
- create `/etc/starzygiftwatch.env` if absent and preserve existing values on rerun;
- install systemd unit with practical hardening and writable data path;
- install the compatibility `watch` wrapper;
- run lightweight self-checks;
- do not start a restart loop when token/admin config is missing;
- finish by telling the operator to run `watch`.

A public-repo one-liner from README must work after `install.sh` exists.

## Tests / acceptance

Cover at least:

- first baseline produces no NEW alerts;
- new ID produces exactly one durable alert event;
- restart/re-poll does not duplicate that event;
- ordering changes produce no event;
- price/count changes produce clear events;
- failed alert remains pending and retries;
- 429 uses `retry_after`;
- non-admin cannot use Telegram admin controls;
- invalid token/admin/interval config fails closed;
- wrapper with arguments delegates to original system watch;
- installer passes `bash -n` and is idempotent in its file-generation logic.

Create `scripts/check.sh` that runs deterministic local checks (compile, tests, shell syntax; lint only if added as a dependency). GitHub CI should call this script on Python 3.12.

## Guardrails

Do not add purchasing, Stars balance/spend, Redis/PostgreSQL, Docker orchestration, web dashboard, user accounts, plugin system, distributed workers, or abstractions not required above.

Do not deploy, restart a real host, merge main, or use a live Bot Token during implementation.

## Final report

Report: architecture chosen, files added, checks run and exact pass/fail counts, installer behavior, `watch` compatibility behavior, and any known limitation. If any acceptance item is not proven, state it explicitly instead of declaring complete.