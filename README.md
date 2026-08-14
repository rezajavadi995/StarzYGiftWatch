# StarzYGiftWatch

Lightweight standalone Telegram Gift watcher for fast detection and admin alerts.

It uses the official Bot API `getAvailableGifts`, keeps a durable local baseline, detects meaningful catalog changes, and alerts only the configured admin. It is intentionally independent from StarzYFire.

## v1 scope

- New Gift ID detection as the highest-priority event.
- Meaningful changes: price, `total_count`, `remaining_count`, `personal_total_count`, `personal_remaining_count`, availability/removal, and newly exposed serializable Gift fields.
- Durable baseline/event history across restarts.
- Telegram admin panel and a local terminal admin menu.
- One process + SQLite. No Redis/PostgreSQL/NATS.
- No purchasing, wallet, Stars spending, userbot, API ID/Hash, or user session.

Official Bot API currently exposes `getAvailableGifts` without parameters and returns `Gift` objects including optional global and per-bot limited-supply counts.

## Platform

Ubuntu/Debian, Python 3.12+, systemd.

## One-line installer

The initial implementation will provide `install.sh`. Until that file lands, do not run this command.

```bash
curl -fsSL https://raw.githubusercontent.com/rezajavadi995/StarzYGiftWatch/main/install.sh | sudo bash
```

The installer must be idempotent and isolated. It may manage only StarzYGiftWatch-owned paths/services and must never modify StarzYFire.

## Terminal admin menu

After installation:

```bash
watch
```

Ubuntu/Debian already provides `/usr/bin/watch`. We do **not** overwrite/delete it. The installer creates `/usr/local/bin/watch` as a compatibility wrapper:

- no arguments -> StarzYGiftWatch admin/config menu;
- any arguments -> delegate unchanged to the original system `watch` binary.

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

Only `ADMIN_ID` is authorized. Minimum controls: watcher ON/OFF, status/last success, poll interval, current gifts, recent changes, test alert, and confirmed baseline rebuild.

## Detection rules

The first successful poll creates the baseline and sends **no fake NEW alerts** for existing gifts. Later successful polls compare canonical normalized snapshots. Ordering alone must not create events.

Persist each event before attempting its Telegram alert. Durable deduplication must prevent repeated alerts after restart. Failed alerts retry with bounded backoff and Telegram `retry_after` must be honored.

## Configuration

```text
/etc/starzygiftwatch.env
```

```dotenv
BOT_TOKEN=
ADMIN_ID=
POLL_INTERVAL=5
DATABASE_PATH=/opt/starzygiftwatch/data/watch.db
LOG_LEVEL=INFO
```

`POLL_INTERVAL` is validated; default is 5 seconds. Telegram documents general flood limits but no dedicated `getAvailableGifts` polling limit, so the watcher must handle 429s conservatively.

## Runtime layout

```text
/opt/starzygiftwatch/
/etc/starzygiftwatch.env
/etc/systemd/system/starzygiftwatch.service
/usr/local/bin/watch
```

SQLite uses WAL mode and short transactions. No network I/O while holding a write transaction.

## Agent contract

Read in this order before implementation:

1. `AGENTS.md`
2. `RULES.md`
3. `CODEX_TASK.md`

v1 is monitoring/alerting only.