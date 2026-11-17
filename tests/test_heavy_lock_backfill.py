# SPDX-License-Identifier: MIT
"""tools/heavy_lock.py: conservative backfill (research/lock-backfill.md).

A ticket further back may start while the head does not fit, if it fits what
is free now, until the head has waited its drain limit; never past a critical
head. Every test uses a lock directory under tmp_path, never the live lock.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "heavy_lock_bf", ROOT / "tools" / "heavy_lock.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["heavy_lock_bf"] = mod
    spec.loader.exec_module(mod)
    return mod


hl = _load()


@pytest.fixture(autouse=True)
def _no_host_drain_setting(monkeypatch):
    """The host's own RANG_HEAVY_DRAIN_MIN must not change these tests."""
    monkeypatch.delenv(hl.DRAIN_VAR, raising=False)


MIN = 60 * 10**9  # one minute in ns
NOW = 1_800_000_000 * 10**9


def _t(q: Path, at_ns: int, priority: str = "normal") -> Path:
    return q / hl.ticket_name(priority, at_ns)


def _shared(slots: int, mem: float) -> dict:
    return {"slots": slots, "mem": mem, "pid": 1, "system": hl.system()}


def _new(slots, mem, drain_min=15.0) -> dict:
    return {"slots": slots, "mem": mem, "drain_s": drain_min * 60.0}


def _capacity(monkeypatch, slots=16, mem=48.0):
    monkeypatch.setattr(hl, "CAPACITY_SLOTS", slots)
    monkeypatch.setattr(hl, "CAPACITY_MEM_GB", mem)


# --- the rule itself (`decide`, no threads, no clock) -----------------------


def test_incident_small_ticket_backfills_past_a_head_that_does_not_fit(
    tmp_path, monkeypatch
):
    """2026-11-16: a 4-slot 46 GB head with one 6 GB hold running (42 of 48 GB
    free) blocked 1-slot 2 GB tickets for about an hour."""
    _capacity(monkeypatch)
    head, small = _t(tmp_path, NOW - 5 * MIN), _t(tmp_path, NOW - 4 * MIN)
    queue = [(head, _new(4, 46.0)), (small, _new(1, 2.0))]
    running = [_shared(1, 6.0)]
    assert hl.decide(queue, head, running, False, NOW)[0] is None
    verdict, why = hl.decide(queue, small, running, False, NOW)
    assert verdict == "backfill", why
    # Strict FIFO before this change, and with drain limit 0 now.
    queue0 = [(head, _new(4, 46.0, drain_min=0)), (small, _new(1, 2.0))]
    assert hl.decide(queue0, small, running, False, NOW)[0] is None


def test_no_backfill_once_the_head_waited_past_its_drain_limit(tmp_path, monkeypatch):
    _capacity(monkeypatch)
    head, small = _t(tmp_path, NOW - 16 * MIN), _t(tmp_path, NOW - 1 * MIN)
    queue = [(head, _new(4, 46.0)), (small, _new(1, 2.0))]
    running = [_shared(1, 6.0)]
    verdict, why = hl.decide(queue, small, running, False, NOW)
    assert verdict is None and "draining" in why and "min drain limit" in why
    # The head's own limit decides, not the backfiller's.
    queue = [(head, _new(4, 46.0, drain_min=30)), (small, _new(1, 2.0, 1))]
    assert hl.decide(queue, small, running, False, NOW)[0] == "backfill"
    # An older helper's head (no drain_s): this helper's default, from the env.
    monkeypatch.setenv(hl.DRAIN_VAR, "20")
    queue = [(head, {"slots": 4, "mem": 46.0}), (small, _new(1, 2.0))]
    assert hl.decide(queue, small, running, False, NOW)[0] == "backfill"
    monkeypatch.setenv(hl.DRAIN_VAR, "10")
    assert hl.decide(queue, small, running, False, NOW)[0] is None


def test_no_backfill_while_the_head_fits_or_into_too_little_room(tmp_path, monkeypatch):
    _capacity(monkeypatch)
    head, a, b = (_t(tmp_path, NOW - k * MIN) for k in (3, 2, 1))
    running = [_shared(1, 6.0)]
    fits = [(head, _new(4, 40.0)), (a, _new(1, 2.0))]
    assert hl.decide(fits, a, running, False, NOW)[0] is None  # head goes first
    big = [(head, _new(4, 46.0)), (a, _new(1, 43.0))]
    assert hl.decide(big, a, running, False, NOW)[0] is None  # 6 + 43 > 48
    # An earlier backfill-aware ticket that fits gets its room reserved first.
    queue = [(head, _new(4, 46.0)), (a, _new(8, 30.0)), (b, _new(1, 13.0))]
    assert hl.decide(queue, a, running, False, NOW)[0] == "backfill"
    assert hl.decide(queue, b, running, False, NOW)[0] is None  # 6 + 30 + 13 > 48
    queue = [(head, _new(4, 46.0)), (a, _new(8, 30.0)), (b, _new(1, 4.0))]
    assert hl.decide(queue, b, running, False, NOW)[0] == "backfill"
    # A ticket of an older helper starts only at the head: no reservation.
    queue = [(head, _new(4, 46.0)), (a, {"slots": 8, "mem": 30.0}), (b, _new(1, 10))]
    assert hl.decide(queue, b, running, False, NOW)[0] == "backfill"
    # Nothing starts while the exclusive lock is held.
    queue = [(head, _new(4, 46.0)), (a, _new(1, 2.0))]
    assert hl.decide(queue, a, [], True, NOW)[0] is None


def test_exclusive_tickets_never_backfill_and_are_backfilled_past(
    tmp_path, monkeypatch
):
    _capacity(monkeypatch)
    head, a = _t(tmp_path, NOW - 3 * MIN), _t(tmp_path, NOW - 2 * MIN)
    running = [_shared(2, 6.0)]
    # An exclusive head waits for the shared jobs; a small ticket backfills.
    queue = [(head, _new(None, 0.0)), (a, _new(1, 2.0))]
    assert hl.decide(queue, head, running, False, NOW)[0] is None
    assert hl.decide(queue, a, running, False, NOW)[0] == "backfill"
    # ... until the exclusive head's drain limit, then the jobs drain.
    late = NOW + 13 * MIN
    assert hl.decide(queue, a, running, False, late)[0] is None
    # An exclusive ticket never backfills.
    queue = [(head, _new(4, 46.0)), (a, _new(None, 0.0))]
    verdict, why = hl.decide(queue, a, running, False, NOW)
    assert verdict is None and "exclusive" in why


def test_critical_head_is_never_backfilled_past(tmp_path, monkeypatch):
    _capacity(monkeypatch)
    crit = _t(tmp_path, NOW - 1 * MIN, "critical")
    small = _t(tmp_path, NOW - 9 * MIN)  # older, but sorts after the critical
    queue = sorted([(crit, _new(None, 0.0)), (small, _new(1, 2.0))])
    assert queue[0][0] == crit
    running = [_shared(2, 6.0)]
    verdict, why = hl.decide(queue, small, running, False, NOW)
    assert verdict is None and "critical" in why
    assert abs(hl.waited_s(crit, NOW) - 60.0) < 1e-6


def test_the_head_starts_as_before(tmp_path, monkeypatch):
    _capacity(monkeypatch)
    head = _t(tmp_path, NOW)
    assert hl.decide([(head, _new(4, 46.0))], head, [], False, NOW)[0] == "head"
    # An oversized head still runs alone; a backfill never does.
    over = [(head, _new(32, 100.0))]
    assert hl.decide(over, head, [_shared(1, 1.0)], False, NOW)[0] is None
    assert hl.decide(over, head, [], False, NOW)[0] == "head"
    excl = [(head, _new(None, 0.0))]
    assert hl.decide(excl, head, [_shared(1, 1.0)], False, NOW)[0] is None
    assert hl.decide(excl, head, [], False, NOW)[0] == "head"


# --- waiters on a temporary lock directory -----------------------------------


def _wait_tickets(d: Path, n: int) -> None:
    q = hl.queue_dir(d)
    deadline = time.monotonic() + 30
    while len(list(q.glob("*.json"))) < n:
        assert time.monotonic() < deadline, f"fewer than {n} tickets"
        time.sleep(0.005)


def _next_ns() -> None:
    """Threads share a pid: let the clock pass so ticket names differ."""
    seen = time.time_ns()
    while time.time_ns() <= seen:
        time.sleep(0.001)


def _wait_for(cond, timeout=10.0) -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def _held_head(d: Path, slots, mem, at_ns=None, drain_s=None, priority="normal"):
    """A head ticket held by this test process (refreshed by `keep`)."""
    q = hl.queue_dir(d)
    q.mkdir(parents=True, exist_ok=True)
    t = q / hl.ticket_name(priority, at_ns)
    info = {"pid": os.getpid(), "system": hl.system(), "slots": slots, "mem": mem}
    info["drain_s"] = hl.default_drain_s() if drain_s is None else drain_s
    t.write_text(json.dumps(info), encoding="utf-8")
    return t


def test_waiter_backfills_and_is_marked(tmp_path, monkeypatch, capsys):
    """The incident on a temporary lock directory: the 1-slot ticket starts
    while the 46 GB head waits; status marks it backfilled."""
    _capacity(monkeypatch)
    d = tmp_path / "heavy"
    hold = hl.acquire_shared(d, ["hold"], 0.02, 1, 6.0)
    got: list = []
    head = threading.Thread(
        target=lambda: got.append(("head", hl.acquire_shared(d, ["h"], 0.02, 4, 46))),
        daemon=True,
    )
    head.start()
    _wait_tickets(d, 1)
    _next_ns()
    small = threading.Thread(
        target=lambda: got.append(("small", hl.acquire_shared(d, ["s"], 0.02, 1, 2))),
        daemon=True,
    )
    small.start()
    small.join(timeout=10)
    assert [g[0] for g in got] == ["small"]
    info = json.loads(got[0][1].read_text(encoding="utf-8"))
    assert info["backfill"] is True
    hl.status(d, sample_s=0.01)
    out = capsys.readouterr().out
    assert "backfilled" in out and "waited 0 min" in out
    assert "queue 1:" in out and "4 slots 46 GB" in out
    hl._unlink(got[0][1])
    hl._unlink(hold)
    head.join(timeout=10)
    assert got[1][0] == "head"
    assert "backfill" not in json.loads(got[1][1].read_text(encoding="utf-8"))
    hl._unlink(got[1][1])


def test_waiter_does_not_backfill_past_a_head_beyond_its_drain_limit(
    tmp_path, monkeypatch
):
    _capacity(monkeypatch)
    d = tmp_path / "heavy"
    hold = hl.acquire_shared(d, ["hold"], 0.02, 1, 6.0)
    head = _held_head(d, 4, 46.0, at_ns=time.time_ns() - 20 * MIN)
    got: list = []
    t = threading.Thread(
        target=lambda: got.append(hl.acquire_shared(d, ["s"], 0.02, 1, 2.0)),
        daemon=True,
    )
    t.start()
    _wait_tickets(d, 2)
    for _ in range(20):  # 0.4 s of polls at 0.02 s
        os.utime(head)
        time.sleep(0.02)
    assert not got  # draining: the small job waits behind the head
    hl._unlink(head)  # the head leaves; the small job is now the head
    t.join(timeout=10)
    assert got
    assert "backfill" not in json.loads(got[0].read_text(encoding="utf-8"))
    for f in (got[0], hold):
        hl._unlink(f)


def test_exclusive_head_is_backfilled_past_then_drains(tmp_path):
    d = tmp_path / "heavy"
    s = hl.acquire_shared(d, ["s"], 0.02, 2, 1.0)
    order: list = []
    tx = threading.Thread(
        target=lambda: (hl.acquire(d, ["x"], 0.02), order.append("x")), daemon=True
    )
    tx.start()
    _wait_tickets(d, 1)
    _next_ns()
    got: list = []
    ty = threading.Thread(  # backfills past x at once
        target=lambda: got.append(hl.acquire_shared(d, ["y"], 0.02, 1, 1.0)),
        daemon=True,
    )
    ty.start()
    ty.join(timeout=10)
    (y,) = got
    assert json.loads(y.read_text(encoding="utf-8"))["backfill"] is True
    assert order == []  # x waits for s and y
    hl._unlink(s)
    time.sleep(0.2)
    assert order == []
    hl._unlink(y)
    tx.join(timeout=10)
    assert order == ["x"]
    hl.release(d)


def test_critical_exclusive_head_holds_back_a_ticket_that_would_fit(
    tmp_path, monkeypatch
):
    """Unlike test_critical_exclusive_drains_shared_and_holds_back_normal, the
    normal ticket here would fit beside the running job: it still waits."""
    _capacity(monkeypatch, slots=8)
    d = tmp_path / "heavy"
    s = hl.acquire_shared(d, ["s"], 0.02, 2, 1.0)
    got: list = []
    tn = threading.Thread(
        target=lambda: got.append(("n", hl.acquire_shared(d, ["n"], 0.02, 1, 1.0))),
        daemon=True,
    )
    crit = _held_head(d, None, 0.0, priority="critical")
    tn.start()
    _wait_tickets(d, 2)
    for _ in range(20):
        os.utime(crit)
        time.sleep(0.02)
    assert got == []  # 1 slot would fit beside s, but the head is critical
    tx = threading.Thread(
        target=lambda: (
            hl.acquire(d, ["x"], 0.02, priority="critical"),
            got.append("x"),
        ),
        daemon=True,
    )
    tx.start()
    _wait_tickets(d, 3)
    hl._unlink(crit)  # the real critical waiter x is now the head
    time.sleep(0.2)
    assert got == []
    hl._unlink(s)
    tx.join(timeout=10)
    assert got == ["x"]
    time.sleep(0.1)
    assert len(got) == 1  # n waits while x holds the host
    hl.release(d)
    tn.join(timeout=10)
    assert got[1][0] == "n"
    hl._unlink(got[1][1])


def test_drain_option_and_variable(monkeypatch):
    monkeypatch.delenv(hl.DRAIN_VAR, raising=False)
    assert hl.default_drain_s() == 15 * 60
    monkeypatch.setenv(hl.DRAIN_VAR, "2.5")
    assert hl.default_drain_s() == 150
    monkeypatch.setenv(hl.DRAIN_VAR, "nonsense")
    assert hl.default_drain_s() == 15 * 60
    seen = {}
    monkeypatch.setattr(hl, "run", lambda *a: seen.setdefault("args", a) and 0)
    hl.main(["run", "--slots", "2", "--mem", "3", "--drain", "0", "--", "x"])
    assert seen["args"][-1] == 0.0
    seen.clear()
    hl.main(["run", "--slots", "2", "--", "x"])
    assert seen["args"][-1] is None
