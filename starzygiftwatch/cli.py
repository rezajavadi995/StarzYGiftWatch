from __future__ import annotations

import os
import subprocess
from pathlib import Path

from aiogram import Bot

from . import db
from .alerts import deliver_pending_once
from .config import load_config, mask_token, parse_admin_id, validate_interval
from .watcher import rebuild_baseline

ENV = Path("/etc/starzygiftwatch.env")


def _write_env(updates: dict[str, str]) -> None:
    current = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); current[k] = v
    current.update(updates)
    ENV.write_text("\n".join(f"{k}={v}" for k, v in current.items()) + "\n")
    os.chmod(ENV, 0o600)


def main() -> None:
    cfg = load_config()
    conn = db.connect(cfg.database_path); db.init_db(conn)
    while True:
        print("\nStarzYGiftWatch")
        print(f"1 status 2 token({mask_token(cfg.bot_token)}) 3 admin({cfg.admin_id}) 4 interval({db.poll_interval(conn)}) 5 on/off 6 baseline 7 test alert 8 rebuild 9 logs 10 restart 0 exit")
        choice = input("> ").strip()
        if choice == "0": return
        if choice == "1":
            print(f"watcher={'ON' if db.watcher_enabled(conn) else 'OFF'} gifts={conn.execute('SELECT COUNT(*) c FROM gifts').fetchone()['c']}")
            subprocess.run(["systemctl", "status", "starzygiftwatch", "--no-pager"], check=False)
        elif choice == "2":
            token = input("Bot token: ").strip(); _write_env({"BOT_TOKEN": token}); cfg = load_config()
        elif choice == "3":
            admin = input("Admin ID: ").strip(); parse_admin_id(admin); _write_env({"ADMIN_ID": admin}); cfg = load_config()
        elif choice == "4":
            db.set_poll_interval(conn, validate_interval(int(input("Seconds 2..3600: ").strip())))
        elif choice == "5":
            db.set_watcher_enabled(conn, not db.watcher_enabled(conn))
        elif choice == "6":
            print(f"baseline gifts={conn.execute('SELECT COUNT(*) c FROM gifts').fetchone()['c']}")
        elif choice == "7":
            import asyncio; asyncio.run(deliver_pending_once(conn, Bot(cfg.bot_token), cfg.admin_id)) if cfg.bot_token else print("token missing")
        elif choice == "8":
            if input("Type REBUILD to confirm: ") == "REBUILD":
                import asyncio; asyncio.run(rebuild_baseline(conn, Bot(cfg.bot_token)))
        elif choice == "9":
            subprocess.run(["journalctl", "-u", "starzygiftwatch", "-n", "80", "--no-pager"], check=False)
        elif choice == "10":
            subprocess.run(["systemctl", "restart", "starzygiftwatch"], check=False)
        for suffix in ("", "-wal", "-shm"):
            try: os.chmod(cfg.database_path + suffix, 0o660)
            except FileNotFoundError: pass

if __name__ == "__main__": main()
