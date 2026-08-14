# RULES.md

Hard project boundaries.

## Isolation

StarzYGiftWatch is fully independent from StarzYFire. Never import its code, reuse its DB, modify its service, ports, environment, files, or deployment state.

Owned runtime paths are limited to:

- `/opt/starzygiftwatch`
- `/etc/starzygiftwatch.env`
- `/etc/systemd/system/starzygiftwatch.service`
- `/usr/local/bin/watch` compatibility wrapper

## Scope

v1 is detection + alerting only. No gift purchase, Stars spending, wallet, Fragment, userbot, API ID/Hash, Telegram user session, or recipient-delivery logic.

## Simplicity

- Python 3.12+ and aiogram 3.x.
- One process + SQLite WAL. No PostgreSQL/Redis/NATS/Celery/Docker requirement.
- Prefer standard library plus a small pinned dependency set.
- Do not invent distributed locks, queues, plugin systems, or web panels.

## Sources of truth

- `/etc/starzygiftwatch.env`: secrets/static bootstrap only (`BOT_TOKEN`, `ADMIN_ID`, DB path, log level).
- SQLite: mutable runtime state such as watcher ON/OFF, poll interval, baseline, health and events.
- Telegram and terminal admin UIs must read/write the same SQLite runtime settings. Do not maintain duplicate interval/watcher settings in env and DB.

## Detection safety

- First successful poll is baseline only; no NEW alert storm.
- A successful fetched catalog is applied atomically: event inserts/dedupe and snapshot/baseline update must commit in the same SQLite transaction. Never update the snapshot first and insert events later.
- Canonicalize by Gift ID so list ordering never creates changes.
- New Gift IDs alert immediately.
- Routine `remaining_count` decrements caused by normal sales must not spam the admin every poll. Persist/observe them, but notify only meaningful transitions such as restock/increase, zero/sold-out, or another explicitly important state change.
- Treat disappearance/removal conservatively; require confirmation across two consecutive successful polls before notifying removal. New-ID detection must not wait for this confirmation.
- Baseline rebuild is confirmed, fetch-first and atomic: if Telegram fetch fails, preserve the old baseline. Rebuild must not erase event history or generate fake NEW events.

## Alert reliability

- Persist an event before attempting Telegram notification.
- Deterministic event fingerprint + unique constraint prevents duplicate queued events after restart.
- Alert delivery is at-least-once: a process crash after Telegram accepted a message but before SQLite marks it sent can produce one duplicate. Document this; do not add heavy infrastructure to pretend exactly-once delivery.
- Respect Telegram 429/`retry_after`; use bounded exponential backoff with jitter for other transient failures.
- No network I/O while an SQLite write transaction is open.

## SQLite / concurrent admin access

- Enable WAL, foreign keys and a practical `busy_timeout` on every connection.
- Keep write transactions short and use atomic updates.
- Service and terminal CLI may access SQLite concurrently; this must be tested.
- Terminal administration must never leave the DB/WAL/SHM files owned by root in a way that prevents the `starzygiftwatch` service user from writing.

## Security

- Validate configuration and fail closed.
- Validate Bot Token using `getMe` only when the operator explicitly requests validation/setup; never log the token.
- Only configured `ADMIN_ID` gets Telegram admin UI. Re-check authorization on every command and callback, not just `/start`.
- Secrets are never printed in full.

## Installer

- `install.sh` must be idempotent and support Ubuntu/Debian.
- Never overwrite/delete `/usr/bin/watch`.
- Install `/usr/local/bin/watch`: no arguments opens StarzYGiftWatch CLI; any arguments must `exec` the original system watch with the exact argument vector.
- Use a dedicated `starzygiftwatch` system user.
- Protect `/etc/starzygiftwatch.env` permissions.
- Practical systemd hardening only: `NoNewPrivileges`, `PrivateTmp`, protected system/home paths and a restricted writable data path. Avoid fragile hardening.
- Missing token/admin config must not create an endless restart loop. Installation finishes cleanly and tells the operator to run `watch`.
- Do not auto-contact a live bot during installation unless the operator chooses token validation or test alert.

## Admin configuration

Terminal menu supports token/admin ID, poll interval, service/health, watcher ON/OFF, test alert, baseline summary/rebuild, recent logs and restart. Privileged config/service changes may use sudo, but SQLite runtime mutations must preserve service-user writability.

## Quality gate

At minimum: compile check, pytest, focused reliability tests, `bash -n install.sh`, wrapper delegation test, and a small `scripts/check.sh` that CI can call unchanged.