import asyncio
import os
import sqlite3
import tempfile
import time

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


def test_price_total_personal_change(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")}); apply_catalog(c,{"1":gift("1", star_count=12,total_count=11,personal_total_count=2)})
    assert len(events(c)) >= 3


def test_remaining_decrement_no_alert_restock_zero_alert(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1", remaining_count=5)}); apply_catalog(c,{"1":gift("1", remaining_count=4)})
    assert events(c)[0]["alertable"] == 0
    apply_catalog(c,{"1":gift("1", remaining_count=6)}); apply_catalog(c,{"1":gift("1", remaining_count=0)})
    assert [e["event_type"] for e in events(c) if e["alertable"]] == ["RESTOCK", "SOLD_OUT"]


def test_removal_requires_two_successes_and_failure_no_advance(tmp_path):
    c=conn(tmp_path); apply_catalog(c,{"1":gift("1")}); apply_catalog(c,{}) ; assert events(c)==[]
    # failed poll means no apply_catalog call; second successful miss removes
    apply_catalog(c,{}) ; ev=events(c); assert len(ev)==1 and ev[0]["event_type"]=="REMOVED"


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
