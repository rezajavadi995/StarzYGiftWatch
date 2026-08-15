from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MIN_INTERVAL = 2
MAX_INTERVAL = 3600
DEFAULT_INTERVAL = 5


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int | None
    database_path: str
    log_level: str = "INFO"


def _read_env_file(path: str = "/etc/starzygiftwatch.env") -> dict[str, str]:
    data: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return data
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def mask_token(token: str) -> str:
    if not token:
        return "(unset)"
    if len(token) <= 10:
        return token[:2] + "…"
    return token[:6] + "…" + token[-4:]


def parse_admin_id(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        admin = int(value)
    except ValueError as exc:
        raise ValueError("ADMIN_ID must be an integer") from exc
    if admin <= 0:
        raise ValueError("ADMIN_ID must be positive")
    return admin


def validate_interval(value: int) -> int:
    if not (MIN_INTERVAL <= value <= MAX_INTERVAL):
        raise ValueError(f"poll interval must be {MIN_INTERVAL}..{MAX_INTERVAL} seconds")
    return value


def write_env_file(updates: dict[str, str], path: str = "/etc/starzygiftwatch.env") -> None:
    current: dict[str, str] = {
        "BOT_TOKEN": "",
        "ADMIN_ID": "",
        "DATABASE_PATH": "/opt/starzygiftwatch/data/watch.db",
        "LOG_LEVEL": "INFO",
    }
    current.update(_read_env_file(path))
    current.update(updates)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"{k}={v}" for k, v in current.items() if k in {"BOT_TOKEN", "ADMIN_ID", "DATABASE_PATH", "LOG_LEVEL"}) + "\n")
    p.chmod(0o600)


def load_config(env_file: str = "/etc/starzygiftwatch.env") -> Config:
    file_values = _read_env_file(env_file)
    values = {**file_values, **{k: v for k, v in os.environ.items() if k in {"BOT_TOKEN", "ADMIN_ID", "DATABASE_PATH", "LOG_LEVEL"}}}
    return Config(
        bot_token=values.get("BOT_TOKEN", ""),
        admin_id=parse_admin_id(values.get("ADMIN_ID")),
        database_path=values.get("DATABASE_PATH", "/opt/starzygiftwatch/data/watch.db"),
        log_level=values.get("LOG_LEVEL", "INFO") or "INFO",
    )
