# StarzYGiftWatch

Lightweight standalone Telegram Gift watcher for fast detection and admin alerts.

It uses the official Bot API `getAvailableGifts`, keeps a durable local baseline, detects meaningful catalog changes, and alerts only the configured admin. It is intentionally independent from StarzYFire.

## v1 scope

- New Gift ID detection is the highest-priority event.
- Meaningful changes include price, total supply, personal limits, availability/sold-out/restock and newly exposed stable Gift fields.
- Routine global `remaining_count` decrements are observed but are not allowed to spam an alert every poll.
- Durable baseline/event history across restarts.
- Telegram admin panel + local terminal admin menu.
- One process + SQLite. No Redis/PostgreSQL/NATS.
- No purchasing, wallet, Stars spending, userbot, API ID/Hash, or user session.

Telegram's official Bot API exposes `getAvailableGifts` without parameters. Current `Gift` objects include `star_count`, optional global limited-supply counts (`total_count`, `remaining_count`) and optional per-bot counts (`personal_total_count`, `personal_remaining_count`).

## Platform

Ubuntu/Debian, Python 3.12+, systemd.

## One-line installer

The implementation will provide `install.sh`. Until that file lands, do not run this command.

```bash
curl -fsSL https://raw.githubusercontent.com/rezajavadi995/StarzYGiftWatch/main/install.sh | sudo bash
```

The installer is required to be idempotent and isolated. It may manage only StarzYGiftWatch-owned paths/services and must never modify StarzYFire.

## Terminal admin menu

After installation:

```bash
watch
```

Ubuntu/Debian already provides `/usr/bin/watch`. We do **not** overwrite or delete it. The installer creates `/usr/local/bin/watch`:

- no arguments -> StarzYGiftWatch admin/config menu;
- any arguments -> delegate unchanged to the original system `watch` binary.

If the shell had previously cached `/usr/bin/watch`, start a new shell or run `hash -r` once.

Minimum menu:

- service/health status
- set or validate Bot Token
- set Admin Telegram ID
- set poll interval
- watcher ON/OFF
- baseline summary
- test alert
- rebuild baseline with confirmation
- recent application logs
- restart service
- exit

Secrets are never printed in full.

## Telegram admin panel

Only `ADMIN_ID` is authorized, and authorization is checked on every command/callback. Minimum controls: watcher ON/OFF, status/last success, poll interval, current gifts, recent changes, test alert and confirmed baseline rebuild.

## Detection rules

The first successful poll creates the baseline and sends **no fake NEW alerts** for existing gifts. Later successful polls compare canonical snapshots keyed by Gift ID; ordering alone creates no event.

New IDs alert immediately. Removal is confirmed only after two consecutive successful polls miss the same ID. Failed polls never count toward removal confirmation.

For each successful catalog, durable event creation/deduplication and snapshot advancement are committed atomically. This prevents a crash from saving the new baseline while losing its alert event.

Events are persisted before Telegram delivery. Failed alerts retry with bounded backoff and Telegram `retry_after` is honored. Delivery is intentionally at-least-once: a crash after Telegram accepted an alert but before SQLite marked it sent can cause one duplicate.

## Configuration

Static/bootstrap configuration:

```text
/etc/starzygiftwatch.env
```

```dotenv
BOT_TOKEN=
ADMIN_ID=
DATABASE_PATH=/opt/starzygiftwatch/data/watch.db
LOG_LEVEL=INFO
```

Mutable runtime settings such as watcher ON/OFF and poll interval live in SQLite so the Telegram panel and terminal `watch` menu use one source of truth. Default poll interval is 5 seconds; accepted range is 2..3600 seconds.

## Runtime layout

```text
/opt/starzygiftwatch/
/etc/starzygiftwatch.env
/etc/systemd/system/starzygiftwatch.service
/usr/local/bin/watch
```

SQLite uses WAL, foreign keys, a practical busy timeout and short transactions. Network I/O is never performed while a SQLite write transaction is held.

## Agent contract

Read in this order before implementation:

1. `AGENTS.md`
2. `RULES.md`
3. `CODEX_TASK.md`

v1 is monitoring/alerting only.