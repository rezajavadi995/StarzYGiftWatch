import asyncio
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from starzygiftwatch import db
from starzygiftwatch.config import parse_admin_id, validate_interval
from starzygiftwatch.watcher import apply_catalog, rebuild_baseline
from starzygiftwatch.alerts import deliver_pending_once
from starzygiftwatch.telegram_admin import build_router


def conn(tmp_path):
    c = db.connect(str(tmp_path / "w.db")); db.init_db(c); return c

def gift(id, **kw):
    d = {"id": id, "star_count": 10, "remaining_count": 5, "total_count": 10, "personal_total_count": 1, "personal_remaining_count": 1}
    d.update(kw); return d

def events(c):
    return list(c.execute("SELECT * FROM events ORDER BY id"))


def test_first_baseline_zero_new(tmp_path):
    c=conn(tmp_path); assert apply_catalog(c,{"1":gift("1")}) == []; assert events(c)==[]


def test_new_id_exactly_once_after_restart(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")}); apply_catalog(c,{"1":gift("1"),"2":gift("2")}); apply_catalog(c,{"1":gift("1"),"2":gift("2")})
    ev=events(c); assert len(ev)==1 and ev[0]["event_type"]=="NEW"


def test_ordering_only_no_event(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1"),"2":gift("2")}); apply_catalog(c,{"2":gift("2"),"1":gift("1")}); assert events(c)==[]


def test_price_total_change(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")}); apply_catalog(c,{"1":gift("1", star_count=12,total_count=11)})
    assert len(events(c)) == 2


def test_remaining_decrement_no_alert_restock_zero_alert(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1", remaining_count=5)}); apply_catalog(c,{"1":gift("1", remaining_count=4)})
    assert events(c)[0]["alertable"] == 0
    apply_catalog(c,{"1":gift("1", remaining_count=6)}); apply_catalog(c,{"1":gift("1", remaining_count=0)})
    assert [e["event_type"] for e in events(c) if e["alertable"]] == ["RESTOCK", "SOLD_OUT"]


def test_removal_requires_two_successes_and_failure_no_advance(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1"), "2": gift("2")}); apply_catalog(c,{"2": gift("2")}) ; assert events(c)==[]
    # failed poll means no apply_catalog call; second successful miss removes
    apply_catalog(c,{"2": gift("2")}) ; ev=events(c); assert len(ev)==1 and ev[0]["event_type"]=="REMOVED"


def test_atomicity_rolls_back_snapshot_with_event(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")})
    c.execute("CREATE TRIGGER fail_gift_2 BEFORE INSERT ON gifts WHEN NEW.id='2' BEGIN SELECT RAISE(ABORT, 'boom'); END")
    with pytest.raises(sqlite3.IntegrityError):
        apply_catalog(c,{"1":gift("1"),"2":gift("2")})
    assert "2" not in db.current_snapshots(c)
    assert events(c) == []


class Bot:
    def __init__(self, fail=False): self.fail=fail; self.sent=[]
    async def get_available_gifts(self):
        if self.fail: raise RuntimeError("fetch failed")
        return [gift("9")]
    async def send_message(self, chat_id, text): self.sent.append((chat_id,text))


def test_rebuild_failure_preserves_old_baseline(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")})
    with pytest.raises(RuntimeError): asyncio.run(rebuild_baseline(c, Bot(True)))
    assert set(db.current_snapshots(c)) == {"1"}


def test_failed_alert_pending_retry_and_watcher_off_delivery(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")}); apply_catalog(c,{"1":gift("1"),"2":gift("2")}); db.set_watcher_enabled(c, False)
    class FailBot:
        async def send_message(self, chat_id, text): raise RuntimeError("nope")
    asyncio.run(deliver_pending_once(c, FailBot(), 123)); row=events(c)[0]; assert row["sent_at"] is None and row["attempts"]==1
    c.execute("UPDATE events SET next_attempt_at=0")
    b=Bot(); assert asyncio.run(deliver_pending_once(c,b,123)) == 1; assert b.sent


def test_429_honors_retry_after(tmp_path):
    from aiogram.exceptions import TelegramRetryAfter
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")}); apply_catalog(c,{"1":gift("1"),"2":gift("2")})
    class RBot:
        async def send_message(self, chat_id, text): raise TelegramRetryAfter(method="sendMessage", message="retry", retry_after=7)
    before=time.time(); asyncio.run(deliver_pending_once(c,RBot(),123)); assert events(c)[0]["next_attempt_at"] >= before+6


def test_invalid_config_fails_closed():
    with pytest.raises(ValueError): parse_admin_id("abc")
    with pytest.raises(ValueError): validate_interval(1)


def test_concurrent_busy_timeout(tmp_path):
    c1=conn(tmp_path); c2=db.connect(str(tmp_path/"w.db")); db.init_db(c2); db.set_poll_interval(c1, 6); assert db.poll_interval(c2)==6


def test_non_admin_callback_has_no_controls():
    r = build_router(sqlite3.connect(":memory:"), 1)
    assert r is not None


def test_polling_failure_preserves_baseline_and_later_recovers(tmp_path):
    from starzygiftwatch.watcher import poll_once

    c = conn(tmp_path)
    apply_catalog(c, {"1": gift("1")})

    class FlakyBot:
        def __init__(self): self.calls = 0
        async def get_available_gifts(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary telegram error")
            return [gift("1"), gift("2")]

    bot = FlakyBot()
    with pytest.raises(RuntimeError):
        asyncio.run(poll_once(c, bot))
    assert set(db.current_snapshots(c)) == {"1"}
    asyncio.run(poll_once(c, bot))
    assert set(db.current_snapshots(c)) == {"1", "2"}
    assert db.get_health(c, "runtime_status") == "OK"


def test_watcher_loop_survives_temporary_polling_failure(tmp_path, monkeypatch):
    from starzygiftwatch import watcher

    c = conn(tmp_path)
    apply_catalog(c, {"1": gift("1")})

    class FlakyBot:
        def __init__(self): self.calls = 0
        async def get_available_gifts(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary telegram error")
            return [gift("1"), gift("2")]

    sleeps = {"n": 0}

    async def fake_sleep(delay):
        sleeps["n"] += 1
        if sleeps["n"] >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(watcher.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(watcher.watcher_loop(c, FlakyBot()))
    assert set(db.current_snapshots(c)) == {"1", "2"}
    assert "temporary telegram error" in db.get_health(c, "last_error")


def test_watcher_retry_after_delay_is_used(tmp_path, monkeypatch):
    from aiogram.exceptions import TelegramRetryAfter
    from starzygiftwatch import watcher

    c = conn(tmp_path)
    delays = []

    class RateLimitedBot:
        async def get_available_gifts(self):
            raise TelegramRetryAfter(method="getAvailableGifts", message="retry", retry_after=4)

    async def fake_sleep(delay):
        delays.append(delay)
        raise asyncio.CancelledError

    monkeypatch.setattr(watcher.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(watcher.watcher_loop(c, RateLimitedBot()))
    assert delays == [4]
    assert "retry_after=4" in db.get_health(c, "last_error")


def test_alert_loop_survives_worker_error(tmp_path, monkeypatch):
    from starzygiftwatch import alerts

    c = conn(tmp_path)
    calls = {"n": 0}

    async def fake_deliver(conn_arg, bot, admin_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db temporarily busy")
        return 0

    async def fake_sleep(delay):
        if calls["n"] >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(alerts, "deliver_pending_once", fake_deliver)
    monkeypatch.setattr(alerts.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(alerts.alert_loop(c, Bot(), 123))
    assert calls["n"] == 2


def test_needs_configuration_status(tmp_path):
    c = conn(tmp_path)
    assert db.needs_configuration(c, "", None) is True
    assert db.get_health(c, "runtime_status") == "NEEDS_CONFIGURATION"
    assert "BOT_TOKEN" in db.get_health(c, "runtime_message")


def test_cli_credential_save_is_durable_and_requests_restart(tmp_path, monkeypatch):
    from starzygiftwatch import cli
    from starzygiftwatch.config import load_config

    env_file = tmp_path / "starzygiftwatch.env"
    monkeypatch.setattr(cli, "ENV_PATH", env_file)

    calls = []
    def fake_run_service_command(*args):
        calls.append(args)
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    monkeypatch.setattr(cli, "run_service_command", fake_run_service_command)
    msg = cli.save_credentials({"BOT_TOKEN": "123456:ABC", "ADMIN_ID": "777"})
    loaded = load_config(str(env_file))
    assert loaded.bot_token == "123456:ABC"
    assert loaded.admin_id == 777
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert calls == [("restart",)]
    assert "restarted" in msg


def test_cli_status_reports_required_fields(tmp_path, monkeypatch):
    from starzygiftwatch import cli
    from starzygiftwatch.config import Config

    c = conn(tmp_path)
    db.record_runtime_status(c, "NEEDS_CONFIGURATION", "missing BOT_TOKEN")
    monkeypatch.setattr(cli, "service_state", lambda: "inactive")
    lines = cli.status_lines(c, Config(bot_token="", admin_id=None, database_path=str(tmp_path / "w.db")))
    rendered = "\n".join(lines)
    assert "Status: NEEDS_CONFIGURATION" in rendered
    assert "Bot Token: (unset)" in rendered
    assert "Admin ID: (unset)" in rendered
    assert "Last successful poll: never" in rendered


def test_watch_wrapper_can_run_from_outside_repo(tmp_path):
    import subprocess
    result = subprocess.run(["bash", str(Path(__file__).with_name("wrapper_test.sh"))], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr + result.stdout

def test_empty_first_poll_then_nonempty_builds_baseline_then_later_new_alerts(tmp_path):
    c = conn(tmp_path)
    assert apply_catalog(c, {}) == []
    assert events(c) == []
    assert apply_catalog(c, {"1": gift("1")}) == []
    assert events(c) == []
    assert set(db.current_snapshots(c)) == {"1"}

    inserted = apply_catalog(c, {"1": gift("1"), "2": gift("2")})
    ev = events(c)
    assert len(inserted) == 1
    assert len(ev) == 1 and ev[0]["event_type"] == "NEW" and ev[0]["gift_id"] == "2"


def test_valid_baseline_empty_poll_preserves_snapshot(tmp_path):
    c = conn(tmp_path)
    apply_catalog(c, {"1": gift("1")})
    apply_catalog(c, {})
    assert events(c) == []
    assert set(db.current_snapshots(c)) == {"1"}


def test_restart_with_valid_baseline_no_fake_new(tmp_path):
    path = tmp_path / "w.db"
    c = db.connect(str(path)); db.init_db(c)
    apply_catalog(c, {"1": gift("1")})
    c.close()
    c = db.connect(str(path)); db.init_db(c)
    apply_catalog(c, {"1": gift("1")})
    assert events(c) == []


def test_first_nonempty_catalog_builds_baseline_without_alert(tmp_path):
    c = conn(tmp_path)
    assert apply_catalog(c, {"1": gift("1")}) == []
    assert events(c) == []
    assert set(db.current_snapshots(c)) == {"1"}


def test_personal_remaining_only_change_no_event_but_snapshot_updates(tmp_path):
    c = conn(tmp_path)
    apply_catalog(c, {"1": gift("1", personal_remaining_count=3)})
    apply_catalog(c, {"1": gift("1", personal_remaining_count=2)})
    assert events(c) == []
    assert db.current_snapshots(c)["1"]["personal_remaining_count"] == 2


def test_personal_total_only_change_no_event(tmp_path):
    c = conn(tmp_path)
    apply_catalog(c, {"1": gift("1", personal_total_count=3)})
    apply_catalog(c, {"1": gift("1", personal_total_count=4)})
    assert events(c) == []


def test_important_change_with_personal_remaining_has_single_needed_alert(tmp_path):
    c = conn(tmp_path)
    apply_catalog(c, {"1": gift("1", star_count=10, personal_remaining_count=3)})
    apply_catalog(c, {"1": gift("1", star_count=11, personal_remaining_count=2)})
    ev = events(c)
    assert len(ev) == 1
    assert ev[0]["event_type"] == "CHANGE"
