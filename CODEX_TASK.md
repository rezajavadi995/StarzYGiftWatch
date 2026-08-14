# CODEX_TASK.md — Initial v1 implementation

Build StarzYGiftWatch from this repository contract. Keep it lightweight and production-usable; do not turn it into StarzYFire.

## Deliverables

Implement roughly this shape (rename only when it materially simplifies things):

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

## Configuration model

Keep one clear source of truth:

- env file: `BOT_TOKEN`, `ADMIN_ID`, `DATABASE_PATH`, `LOG_LEVEL` only;
- SQLite runtime settings: watcher enabled flag and poll interval (default 5s, valid 2..3600s), plus health/baseline/events.

Telegram admin and terminal `watch` must change the same SQLite runtime settings. Do not require a service restart just to change watcher ON/OFF or poll interval.

## Core behavior

1. Use aiogram's official Bot API support for `getAvailableGifts`.
2. Poll at the durable configured interval.
3. First successful response becomes baseline and creates no NEW events.
4. Normalize by Gift ID into deterministic JSON-safe snapshots. Explicitly preserve official semantic fields such as `id`, `star_count`, `upgrade_star_count`, premium/color flags, `total_count`, `remaining_count`, `personal_total_count`, `personal_remaining_count`, background/variant/publisher metadata when safely serializable. Do not let unstable media/file payload details create noisy false changes.
5. New Gift ID is the highest-priority event and alerts on the first successful poll where it appears.
6. Price, total supply, personal limits, sold-out/availability and meaningful stable-field changes create durable events.
7. Normal global `remaining_count` decrements are high-churn sales telemetry: update the snapshot/history but do not alert on every decrement. Notify meaningful transitions such as an increase/restock or reaching zero/sold-out.
8. A missing Gift ID is not announced as removed until it is absent from two consecutive successful polls. A failed poll never counts toward removal confirmation.
9. Ordering-only differences create no event.
10. Apply each successful catalog atomically in SQLite: event inserts/dedupe and snapshot replacement/version update must commit together. This is required so a crash cannot save the new snapshot while losing its NEW event.
11. Event fingerprints are deterministic and uniquely constrained. Commit before Telegram delivery.
12. Alert worker sends pending events to `ADMIN_ID`, marks sent only after success, honors `TelegramRetryAfter.retry_after`, and uses bounded exponential backoff + jitter otherwise.
13. Watcher OFF stops catalog polling only; it must not destroy baseline/history and must not prevent pending alert retries.
14. SQLite: WAL, foreign keys, practical busy timeout, schema versioning, short write transactions, no network I/O inside write transactions.
15. Document the unavoidable at-least-once notification window: crash after Telegram accepts an alert but before local `sent` commit may duplicate that alert once.

## Baseline rebuild

Both Telegram and CLI rebuild actions require confirmation. Rebuild must:

- fetch Telegram first;
- if fetch fails, keep the previous baseline unchanged;
- atomically replace the baseline on success;
- create no fake NEW events from the rebuild itself;
- preserve event history and pending alerts.

## Telegram admin UI

Owner-only. `/start` or `/admin` opens a compact inline panel showing watcher state, last successful poll, interval, gift count, pending alerts and last change. Include ON/OFF, interval, current gifts, recent changes, test alert and confirmed baseline rebuild.

Re-check `ADMIN_ID` on every command and callback. Non-admin users get no admin controls.

## Terminal `watch` menu

Friendly numbered menu callable from any directory. It must:

- set/validate Bot Token and Admin ID;
- set poll interval;
- show service/health;
- watcher ON/OFF;
- baseline summary;
- test alert;
- confirmed baseline rebuild;
- recent logs;
- restart service;
- exit.

Mask the token.

System `/usr/bin/watch` must remain intact. Install `/usr/local/bin/watch` so:

- no args -> our CLI;
- any args -> `exec` the original system watch with the exact original arguments and exit behavior.

Do not let CLI/root operations leave SQLite, WAL or SHM files unwritable by the `starzygiftwatch` service user.

## Installer

`install.sh` is idempotent for Ubuntu/Debian and supports being executed directly from the README curl one-liner. It should:

- elevate/require root cleanly;
- install minimal OS prerequisites;
- clone/update this repo at `/opt/starzygiftwatch` without touching StarzYFire;
- create `.venv` and install pinned tested requirements;
- create the dedicated `starzygiftwatch` system user and writable data directory;
- create `/etc/starzygiftwatch.env` if absent and preserve existing secrets on rerun;
- install a systemd unit with practical, non-fragile hardening;
- install the `watch` compatibility wrapper;
- run lightweight deterministic self-checks;
- avoid an endless restart loop when token/admin config is missing;
- not contact Telegram automatically unless operator explicitly validates token or sends a test alert;
- finish by telling the operator to run `watch`.

After valid configuration, the menu may enable/start/restart the service explicitly.

## Tests / acceptance

Cover at least:

- first baseline -> zero NEW events;
- new ID -> exactly one durable NEW event;
- crash/restart/re-poll -> no duplicate queued NEW event;
- atomicity: snapshot cannot advance without its associated event transaction committing;
- ordering-only changes -> no event;
- price/total/personal-limit changes -> durable event;
- routine global remaining decrement -> no alert spam;
- restock/increase and zero/sold-out transition -> alertable event;
- one-poll disappearance -> no removal alert; two successful misses -> one removal event;
- failed poll does not advance missing counter/baseline;
- failed alert stays pending and retries;
- 429 honors `retry_after`;
- watcher OFF still allows pending alert delivery;
- baseline rebuild failure preserves old baseline;
- non-admin cannot use any admin callback;
- invalid token/admin/interval fails closed;
- concurrent service/CLI SQLite access respects `busy_timeout` and ownership assumptions;
- wrapper args delegate exactly to system watch;
- `bash -n install.sh` passes and installer file-generation behavior is idempotent.

Create `scripts/check.sh` for deterministic local checks: compile, pytest, shell syntax and lint only if lint is an explicit dependency. GitHub CI should call the same script on Python 3.12.

## Guardrails

No purchasing, Stars balance/spend, Redis/PostgreSQL, Docker orchestration, web dashboard, user accounts, plugin system or distributed workers.

Do not deploy, restart a real host, merge main, or use a live Bot Token during implementation.

## Final report

Report architecture, files added, exact checks/pass-fail counts, installer behavior, `watch` compatibility behavior and known limitations. If an acceptance item is not proven, state that explicitly instead of declaring complete.