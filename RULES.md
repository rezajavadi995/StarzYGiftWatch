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

- Python 3.12+.
- aiogram 3.x.
- SQLite with WAL; no PostgreSQL/Redis/NATS/Celery/Docker requirement.
- One systemd service and one process.
- Prefer standard library plus a small dependency set.

## Safety/reliability

- First successful poll is baseline only; no NEW alert storm.
- Canonicalize snapshots so list ordering does not create false changes.
- Persist events before sending alerts.
- Durable event fingerprint/uniqueness prevents duplicate alert spam after restart.
- Respect Telegram 429/`retry_after`; use bounded exponential backoff with jitter for other transient failures.
- No network I/O while an SQLite write transaction is open.
- Validate configuration and fail closed.
- Token is never shown/logged in full.
- Only configured `ADMIN_ID` gets the Telegram admin UI.

## Installer

- `install.sh` must be idempotent and support Ubuntu/Debian.
- Never overwrite/delete `/usr/bin/watch`.
- Before installing `/usr/local/bin/watch`, identify the original system watch binary. Wrapper behavior: no args opens StarzYGiftWatch CLI; args delegate unchanged to original watch.
- Use a dedicated `starzygiftwatch` system user.
- Environment file permissions must protect the token.
- systemd hardening should be practical: `NoNewPrivileges`, `PrivateTmp`, and restricted writable paths. Do not add fragile hardening that blocks normal operation.
- Missing config must not create an endless restart loop; installation should finish cleanly and direct the admin to run `watch`.

## Admin configuration

Terminal menu must support token/admin ID/poll interval configuration, service status/restart, watcher ON/OFF, test alert, baseline summary/rebuild, and recent logs. Mutating privileged config/service actions may elevate through sudo.

## Quality gate

At minimum: compile check, focused unit tests, installer shell syntax check, and pytest. Add a small local `scripts/check.sh`; CI may call the same script.