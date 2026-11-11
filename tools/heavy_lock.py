# SPDX-License-Identifier: GPL-3.0-or-later
"""One CPU-heavy job at a time across native Windows and WSL on this host.

Usage (from Windows or WSL, any Python 3.10+):

    python tools/heavy_lock.py run -- <command> [args...]            # exclusive
    python tools/heavy_lock.py run --slots 4 --mem 8 -- <command>    # shared
    python tools/heavy_lock.py status
    python tools/heavy_lock.py break     # only after checking the owner is gone

The lock is a directory on D: (``D:\\rang\\locks\\heavy``, ``/mnt/d/rang/locks/heavy``
from WSL; ``RANG_HEAVY_LOCK`` overrides). Creating a directory is atomic on NTFS
and through WSL's drive mount, whereas ``flock`` taken inside WSL is invisible to
Windows processes. The directory holds ``owner.json`` (system, host, pid,
command, start time). From WSL an exclusive run also takes
``flock ~/.rang-heavy.lock``, so older scripts that lock only that file still
wait for it.

A lock left by a dead process on the same system is removed automatically; one
left by the other system is reported and waited on, never broken silently.

Waiters queue first come, first served (added 2026-11-11, after a check-all
waited three hours while later jobs won the 10 s polling race). Each waiter
writes a ticket ``<time_ns>-<system>-<pid>.json`` in the sibling directory
``heavy-queue``; only the oldest live ticket may start. A waiter refreshes its
ticket's modification time at every poll; a ticket not refreshed for
``STALE_TICKET_S`` seconds (its waiter crashed or was killed) is removed.

Shared jobs (added 2026-11-11: one job at a time left 80-90 % of the 16
threads idle). ``run --slots N --mem G`` runs alongside other shared jobs while
the total stays within ``CAPACITY_SLOTS`` threads and ``CAPACITY_MEM_GB`` GB;
each shared job keeps a heartbeat file in ``heavy-slots``. A plain ``run`` (or
``--exclusive``) is exclusive as before: it waits until no shared job runs, then
holds the whole host. Use exclusive for timing and tuning runs, shared for
builds, tests, check-all and scoring. The head of the queue starts as soon as
it fits and later tickets wait behind it, so an exclusive job is never starved.
Older copies of this helper know nothing of shared jobs or tickets: call the
main checkout's copy.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

STALE_TICKET_S = 120.0
CAPACITY_SLOTS = int(os.environ.get("RANG_HEAVY_SLOTS", "16"))
CAPACITY_MEM_GB = float(os.environ.get("RANG_HEAVY_MEM_GB", "48"))


def system() -> str:
    if sys.platform == "win32":
        return "windows"
    if "microsoft" in platform.release().lower():
        return "wsl"
    return sys.platform


def lock_dir() -> Path:
    env = os.environ.get("RANG_HEAVY_LOCK")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(r"D:\rang\locks\heavy")
    return Path("/mnt/d/rang/locks/heavy")


def queue_dir(d: Path) -> Path:
    return d.parent / (d.name + "-queue")


def slots_dir(d: Path) -> Path:
    return d.parent / (d.name + "-slots")


def mutex_dir(d: Path) -> Path:
    return d.parent / (d.name + "-mutex")


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_owner(d: Path) -> dict | None:
    try:
        return json.loads((d / "owner.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def describe(owner: dict | None) -> str:
    if owner is None:
        return "owner unknown (owner.json missing or being written)"
    return f"{owner['system']} pid {owner['pid']} since {owner['start']}: {owner['command']}"


def try_acquire(d: Path, command: list[str]) -> bool:
    d.parent.mkdir(parents=True, exist_ok=True)
    try:
        d.mkdir()
    except FileExistsError:
        return False
    owner = {
        "system": system(),
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "command": " ".join(command),
        "start": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (d / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
    return True


def release(d: Path) -> None:
    (d / "owner.json").unlink(missing_ok=True)
    d.rmdir()


def stale(d: Path) -> bool:
    if not d.exists():
        return False
    owner = read_owner(d)
    if owner is None:
        # A just-created lock has no owner.json yet; treat as stale only if old.
        try:
            return time.time() - d.stat().st_mtime > 60
        except OSError:
            return False
    return owner["system"] == system() and not pid_alive(int(owner["pid"]))


def _fresh(path: Path, stale_s: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= stale_s
    except OSError:
        return False


def take_ticket(d: Path, slots: int | None = None, mem: float = 0.0) -> Path:
    q = queue_dir(d)
    q.mkdir(parents=True, exist_ok=True)
    t = q / f"{time.time_ns():020d}-{system()}-{os.getpid()}.json"
    info = {"pid": os.getpid(), "system": system(), "slots": slots, "mem": mem}
    t.write_text(json.dumps(info), encoding="utf-8")
    return t


def first_live_ticket(d: Path, stale_s: float = STALE_TICKET_S) -> Path | None:
    q = queue_dir(d)
    if not q.exists():
        return None
    for t in sorted(q.glob("*.json")):
        try:
            info = json.loads(t.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        dead = info.get("system") == system() and not pid_alive(
            int(info.get("pid", 0) or 0)
        )
        if dead or not _fresh(t, stale_s):
            t.unlink(missing_ok=True)
            continue
        return t
    return None


def live_shared(d: Path, stale_s: float = STALE_TICKET_S) -> list[dict]:
    jobs: list[dict] = []
    sd = slots_dir(d)
    if not sd.exists():
        return jobs
    for f in sd.glob("*.json"):
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        dead = info.get("system") == system() and not pid_alive(int(info["pid"]))
        if dead or not _fresh(f, stale_s):
            f.unlink(missing_ok=True)
            continue
        jobs.append(info)
    return jobs


class _Mutex:
    """A short critical section around the fit check and the registration."""

    def __init__(self, d: Path) -> None:
        self.m = mutex_dir(d)

    def __enter__(self) -> _Mutex:  # noqa: PYI034
        self.m.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                self.m.mkdir()
                return self
            except FileExistsError:
                if not _fresh(self.m, 30.0):  # left by a crashed holder
                    try:
                        self.m.rmdir()
                    except OSError:
                        pass
                if time.time() - t0 > 120:
                    raise TimeoutError(
                        f"heavy_lock: mutex {self.m} held for 120 s"
                    ) from None
                time.sleep(0.05)

    def __exit__(self, *exc: object) -> None:
        try:
            self.m.rmdir()
        except OSError:
            pass


def _register_shared(d: Path, command: list[str], slots: int, mem: float) -> Path:
    sd = slots_dir(d)
    sd.mkdir(parents=True, exist_ok=True)
    f = sd / f"{system()}-{os.getpid()}-{time.time_ns()}.json"
    info = {
        "system": system(),
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "slots": slots,
        "mem": mem,
        "command": " ".join(command),
        "start": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    f.write_text(json.dumps(info), encoding="utf-8")
    return f


def _wait(
    d: Path, command: list[str], poll: float, slots: int | None, mem: float
) -> Path | None:
    ticket = take_ticket(d, slots, mem)
    stale_s = max(STALE_TICKET_S, 3 * poll)
    last = None
    try:
        while True:
            os.utime(ticket)
            head = first_live_ticket(d, stale_s)
            if head is None or head == ticket:
                with _Mutex(d):
                    if stale(d):
                        print(
                            f"heavy_lock: removing stale lock ({describe(read_owner(d))})",
                            file=sys.stderr,
                        )
                        try:
                            release(d)
                        except OSError:
                            pass
                    shared = live_shared(d, stale_s)
                    if slots is None:
                        if not shared and try_acquire(d, command):
                            return None
                    elif not d.exists():
                        used = sum(int(j.get("slots") or 0) for j in shared)
                        used_mem = sum(float(j.get("mem") or 0) for j in shared)
                        fits = (
                            used + slots <= CAPACITY_SLOTS
                            and used_mem + mem <= CAPACITY_MEM_GB
                        )
                        if fits or not shared:  # an oversized job runs alone
                            return _register_shared(d, command, slots, mem)
            state = describe(read_owner(d)) if d.exists() else "shared jobs to fit"
            if head not in (None, ticket):
                state += f" (queue: behind {head.name})"
            if state != last:
                print(f"heavy_lock: waiting for {state}", file=sys.stderr, flush=True)
                last = state
            time.sleep(poll)
    finally:
        ticket.unlink(missing_ok=True)


def acquire(d: Path, command: list[str], poll: float) -> None:
    """Take the whole host (the original behaviour)."""
    _wait(d, command, poll, None, 0.0)


def acquire_shared(
    d: Path, command: list[str], poll: float, slots: int, mem: float
) -> Path:
    """Take ``slots`` threads and ``mem`` GB; returns the job's heartbeat file."""
    f = _wait(d, command, poll, slots, mem)
    assert f is not None
    return f


def _heartbeat(path: Path, stop: threading.Event, every: float) -> None:
    while not stop.wait(every):
        try:
            os.utime(path)
        except OSError:
            return


def run(
    command: list[str], poll: float, slots: int | None = None, mem: float = 0.0
) -> int:
    d = lock_dir()
    if slots is not None:
        hb = acquire_shared(d, command, poll, slots, mem)
        stop = threading.Event()
        threading.Thread(target=_heartbeat, args=(hb, stop, 20.0), daemon=True).start()
        try:
            return subprocess.call(command)
        finally:
            stop.set()
            hb.unlink(missing_ok=True)
    wsl_lock = None
    if sys.platform != "win32":
        import fcntl

        wsl_lock = open(Path.home() / ".rang-heavy.lock", "a")  # noqa: SIM115
        fcntl.flock(wsl_lock, fcntl.LOCK_EX)
    acquire(d, command, poll)
    try:
        return subprocess.call(command)
    finally:
        release(d)
        if wsl_lock is not None:
            wsl_lock.close()


def status(d: Path) -> None:
    print(f"exclusive: {describe(read_owner(d))}" if d.exists() else "exclusive: free")
    shared = live_shared(d)
    used = sum(int(j.get("slots") or 0) for j in shared)
    used_mem = sum(float(j.get("mem") or 0) for j in shared)
    print(f"shared: {used}/{CAPACITY_SLOTS} slots, {used_mem:g}/{CAPACITY_MEM_GB:g} GB")
    for j in shared:
        print(
            f"  {j['slots']} slots {j['mem']:g} GB pid {j['pid']}: {j['command'][:140]}"
        )
    q = queue_dir(d)
    waiting = sorted(q.glob("*.json")) if q.exists() else []
    for i, t in enumerate(waiting, 1):
        try:
            info = json.loads(t.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        kind = f"{info['slots']} slots" if info.get("slots") else "exclusive"
        print(f"queue {i}: {t.stem} ({kind})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("run", help="run a command holding the lock")
    r.add_argument("--poll", type=float, default=10.0, help="seconds between checks")
    r.add_argument(
        "--slots",
        type=int,
        default=None,
        help=f"run shared on this many of {CAPACITY_SLOTS} threads (default: exclusive)",
    )
    r.add_argument("--mem", type=float, default=4.0, help="GB a shared job may use")
    r.add_argument(
        "--exclusive", action="store_true", help="the whole host (the default)"
    )
    r.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("status", help="show the exclusive owner, shared jobs and the queue")
    sub.add_parser("break", help="remove the exclusive lock")
    a = p.parse_args(argv)
    d = lock_dir()
    if a.action == "status":
        status(d)
        return 0
    if a.action == "break":
        if d.exists():
            print(f"removing: {describe(read_owner(d))}")
            release(d)
        return 0
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        p.error("run needs a command after --")
    slots = None if a.exclusive else a.slots
    return run(command, a.poll, slots, a.mem)


if __name__ == "__main__":
    sys.exit(main())
