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
