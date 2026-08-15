from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from aiogram import Bot

from . import db
from .alerts import deliver_pending_once
from .config import load_config, mask_token, parse_admin_id, validate_interval, write_env_file
from .watcher import rebuild_baseline

SERVICE = "starzygiftwatch"
ENV_PATH = Path(os.environ.get("STARZYGIFTWATCH_ENV", "/etc/starzygiftwatch.env"))


def run_service_command(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", *args, SERVICE], check=False, text=True, capture_output=True)


def restart_service_if_available() -> str:
    result = run_service_command("restart")
    if result.returncode == 0:
        return "service restarted; new credentials are active"
    return "credentials saved; restart service manually when systemd is unavailable"


def service_state() -> str:
    result = run_service_command("is-active")
    if result.returncode == 0:
        return result.stdout.strip() or "active"
    return (result.stdout.strip() or result.stderr.strip() or "unavailable").splitlines()[-1]


def status_lines(conn, cfg) -> list[str]:
    configured = bool(cfg.bot_token and cfg.admin_id)
    runtime = db.get_health(conn, "runtime_status", "NEEDS_CONFIGURATION" if not configured else "UNKNOWN")
    return [
        f"Status: {runtime}",
        f"Service: {service_state()}",
        f"Watcher: {'ON' if db.watcher_enabled(conn) else 'OFF'}",
        f"Bot Token: {mask_token(cfg.bot_token)}",
        f"Admin ID: {cfg.admin_id or '(unset)'}",
        f"Poll interval: {db.poll_interval(conn)}s",
        f"Last successful poll: {db.get_health(conn, 'last_success', 'never')}",
        f"Gift count: {conn.execute('SELECT COUNT(*) c FROM gifts').fetchone()['c']}",
        f"Pending alerts: {conn.execute('SELECT COUNT(*) c FROM events WHERE alertable=1 AND sent_at IS NULL').fetchone()['c']}",
        f"Last new Gift: {db.get_health(conn, 'last_new_gift_id', 'none')}",
        f"Recent error: {db.get_health(conn, 'last_error', 'none') or 'none'}",
    ]


def print_status(conn, cfg) -> None:
    print("\n".join(status_lines(conn, cfg)))


def save_credentials(updates: dict[str, str]) -> str:
    write_env_file(updates, str(ENV_PATH))
    return restart_service_if_available()


def main() -> None:
    cfg = load_config(str(ENV_PATH))
    conn = db.connect(cfg.database_path)
    db.init_db(conn)
    if not cfg.bot_token or not cfg.admin_id:
        db.record_runtime_status(conn, "NEEDS_CONFIGURATION", "missing BOT_TOKEN or ADMIN_ID")
    while True:
        print("\nStarzYGiftWatch admin")
        print_status(conn, cfg)
        print("\n1) Set Bot Token  2) Set Admin ID  3) Set poll interval  4) Toggle ON/OFF")
        print("5) Test Alert     6) Rebuild baseline  7) Recent logs       8) Restart service  0) Exit")
        choice = input("> ").strip()
        if choice == "0":
            return
        if choice == "1":
            token = input("Bot token (will be masked after save): ").strip()
            if not token:
                print("Token unchanged: empty value rejected")
                continue
            print(save_credentials({"BOT_TOKEN": token}))
            cfg = load_config(str(ENV_PATH))
        elif choice == "2":
            admin = input("Admin Telegram ID: ").strip()
            parse_admin_id(admin)
            print(save_credentials({"ADMIN_ID": admin}))
            cfg = load_config(str(ENV_PATH))
        elif choice == "3":
            db.set_poll_interval(conn, validate_interval(int(input("Seconds 2..3600: ").strip())))
            print("Poll interval saved in SQLite; no restart needed")
        elif choice == "4":
            db.set_watcher_enabled(conn, not db.watcher_enabled(conn))
            print(f"Watcher is now {'ON' if db.watcher_enabled(conn) else 'OFF'}")
        elif choice == "5":
            if not cfg.bot_token or not cfg.admin_id:
                print("NEEDS_CONFIGURATION: set Bot Token and Admin ID first")
            else:
                sent = asyncio.run(deliver_pending_once(conn, Bot(cfg.bot_token), cfg.admin_id))
                print(f"Pending alert delivery attempted; sent={sent}")
        elif choice == "6":
            if input("Type REBUILD to fetch and replace baseline: ") == "REBUILD":
                if not cfg.bot_token:
                    print("NEEDS_CONFIGURATION: Bot Token missing")
                else:
                    asyncio.run(rebuild_baseline(conn, Bot(cfg.bot_token)))
                    print("Baseline rebuilt successfully")
        elif choice == "7":
            subprocess.run(["journalctl", "-u", SERVICE, "-n", "80", "--no-pager"], check=False)
        elif choice == "8":
            print(restart_service_if_available())
        for suffix in ("", "-wal", "-shm"):
            try:
                os.chmod(cfg.database_path + suffix, 0o660)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
