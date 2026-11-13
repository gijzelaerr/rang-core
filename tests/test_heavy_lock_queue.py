"""tools/heavy_lock.py: waiters take the lock first come, first served."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "heavy_lock", ROOT / "tools" / "heavy_lock.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["heavy_lock"] = mod
    spec.loader.exec_module(mod)
    return mod


hl = _load()


def test_waiters_acquire_in_ticket_order(tmp_path):
    d = tmp_path / "heavy"
    assert hl.try_acquire(d, ["holder"])
    order: list[int] = []

    def waiter(i: int) -> None:
        hl.acquire(d, [f"w{i}"], poll=0.02)
        order.append(i)
        time.sleep(0.05)
        hl.release(d)

    threads = []
    for i in range(4):
        t = threading.Thread(target=waiter, args=(i,))
        t.start()
        threads.append(t)
        time.sleep(0.05)  # distinct tickets, in start order
    hl.release(d)
    for t in threads:
        t.join(timeout=10)
    assert order == [0, 1, 2, 3]
    assert not list(hl.queue_dir(d).glob("*.json"))


def test_stale_ticket_is_skipped(tmp_path):
    d = tmp_path / "heavy"
    q = hl.queue_dir(d)
    q.mkdir(parents=True)
    dead = q / f"{1:020d}-windows-1.json"
    dead.write_text("{}", encoding="utf-8")
    old = time.time() - 10 * hl.STALE_TICKET_S
    os.utime(dead, (old, old))
    hl.acquire(d, ["me"], poll=0.02)
    assert d.exists()
    assert not dead.exists()
    hl.release(d)


def test_shared_jobs_run_together_within_capacity(tmp_path, monkeypatch):
    d = tmp_path / "heavy"
    monkeypatch.setattr(hl, "CAPACITY_SLOTS", 8)
    a = hl.acquire_shared(d, ["a"], 0.02, 4, 1.0)
    b = hl.acquire_shared(d, ["b"], 0.02, 4, 1.0)  # fits: 8 of 8
    assert len(hl.live_shared(d)) == 2
    got = []
    t = threading.Thread(
        target=lambda: got.append(hl.acquire_shared(d, ["c"], 0.02, 2, 1.0))
    )
    t.start()
    time.sleep(0.2)
    assert not got  # 10 > 8: waits
    a.unlink()
    t.join(timeout=5)
    assert got
    for f in (b, got[0]):
        f.unlink()


def test_exclusive_waits_for_shared_and_blocks_later_shared(tmp_path):
    d = tmp_path / "heavy"
    s = hl.acquire_shared(d, ["s"], 0.02, 2, 1.0)
    order = []
    tx = threading.Thread(
        target=lambda: (hl.acquire(d, ["x"], 0.02), order.append("x"))
    )
    tx.start()
    time.sleep(0.1)
    ty = threading.Thread(
        target=lambda: order.append(("y", hl.acquire_shared(d, ["y"], 0.02, 1, 1.0)))
    )
    ty.start()
    time.sleep(0.2)
    assert order == []  # x waits for s; y queues behind x
    s.unlink()
    tx.join(timeout=5)
    assert order == ["x"]
    time.sleep(0.1)
    assert len(order) == 1  # y still waits while x holds the host
    hl.release(d)
    ty.join(timeout=5)
    assert order[1][0] == "y"
    order[1][1].unlink()


# The priority lane (research/speedup-tools.md).
OLD_HELPER = "097588b"  # main before the priority lane


def _load_old(where: Path):
    """The helper as running waiters loaded it, or None (shallow clone)."""
    import subprocess

    try:
        text = subprocess.run(
            ["git", "show", f"{OLD_HELPER}:tools/heavy_lock.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    path = where / "heavy_lock_old.py"
    path.write_bytes(text)
    spec = importlib.util.spec_from_file_location("heavy_lock_old", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["heavy_lock_old"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_critical_ticket_keeps_the_name_shape_and_sorts_first():
    import re

    now = time.time_ns()
    normal = hl.ticket_name("normal", now - 10**12)  # an older normal ticket
    critical = hl.ticket_name("critical", now)
    later = hl.ticket_name("critical", now + 1)
    shape = re.compile(r"^\d{20}-[a-z0-9]+-\d+\.json$")
    assert shape.match(normal) and shape.match(critical)
    assert sorted([normal, later, critical]) == [critical, later, normal]


def test_old_helper_serves_critical_first(tmp_path):
    import pytest

    old = _load_old(tmp_path)
    if old is None:
        pytest.skip(f"{OLD_HELPER} not in this clone")
    d = tmp_path / "heavy"
    normal = old.take_ticket(d, 4, 1.0)  # an old waiter, queued first
    time.sleep(0.01)
    critical = hl.take_ticket(d, None, 0.0, "critical")
    assert old.first_live_ticket(d) == critical
    assert hl.first_live_ticket(d) == critical
    critical.unlink()
    assert old.first_live_ticket(d) == normal == hl.first_live_ticket(d)
    normal.unlink()


def test_critical_jumps_queued_normal_waiters(tmp_path):
    d = tmp_path / "heavy"
    assert hl.try_acquire(d, ["holder"])
    order: list[str] = []

    def waiter(name: str, priority: str) -> None:
        hl.acquire(d, [name], poll=0.02, priority=priority)
        order.append(name)
        time.sleep(0.05)
        hl.release(d)

    threads = []
    for name, priority in (
        ("n0", "normal"),
        ("n1", "normal"),
        ("c0", "critical"),
        ("c1", "critical"),
    ):
        t = threading.Thread(target=waiter, args=(name, priority))
        t.start()
        threads.append(t)
        time.sleep(0.05)
    assert order == []  # nothing preempts the running holder
    hl.release(d)
    for t in threads:
        t.join(timeout=10)
    assert order == ["c0", "c1", "n0", "n1"]


def test_critical_exclusive_drains_shared_and_holds_back_normal(tmp_path, monkeypatch):
    d = tmp_path / "heavy"
    monkeypatch.setattr(hl, "CAPACITY_SLOTS", 8)
    s = hl.acquire_shared(d, ["s"], 0.02, 6, 1.0)
    got: list = []
    tn = threading.Thread(  # queued first; 6 + 4 > 8, so it waits
        target=lambda: got.append(("n", hl.acquire_shared(d, ["n"], 0.02, 4, 1.0)))
    )
    tn.start()
    time.sleep(0.1)
    tx = threading.Thread(
        target=lambda: (
            hl.acquire(d, ["x"], 0.02, priority="critical"),
            got.append("x"),
        )
    )
    tx.start()
    time.sleep(0.2)
    assert got == []  # x waits for s; nothing is preempted
    s.unlink()
    tx.join(timeout=5)
    assert got == ["x"]  # x, not the older normal ticket, got the host
    time.sleep(0.1)
    assert len(got) == 1  # n still waits while x holds the host
    hl.release(d)
    tn.join(timeout=5)
    assert got[1][0] == "n"
    got[1][1].unlink()
