"""One CPU-heavy job at a time across native Windows and WSL on this host.

Usage (from Windows or WSL, any Python 3.10+):

    python tools/heavy_lock.py run -- <command> [args...]
    python tools/heavy_lock.py status
    python tools/heavy_lock.py break     # only after checking the owner is gone

The lock is a directory on D: (``D:\\rang\\locks\\heavy``, ``/mnt/d/rang/locks/heavy``
from WSL; ``RANG_HEAVY_LOCK`` overrides). Creating a directory is atomic on NTFS
and through WSL's drive mount, whereas ``flock`` taken inside WSL is invisible to
Windows processes. The directory holds ``owner.json`` (system, host, pid,
command, start time). From WSL the helper also takes ``flock ~/.rang-heavy.lock``,
so older scripts that lock only that file still wait for it.

A lock left by a dead process on the same system is removed automatically; one
left by the other system is reported and waited on, never broken silently.

Waiters queue first come, first served (added 2026-11-11, after a check-all
waited three hours while later jobs won the 10 s polling race). Each waiter
writes a ticket ``<time_ns>-<system>-<pid>.json`` in the sibling directory
``heavy-queue`` and takes the lock only when its ticket is the oldest live one.
A waiter refreshes its ticket's modification time at every poll; a ticket not
refreshed for ``STALE_TICKET_S`` seconds (its waiter crashed or was killed) is
skipped and removed. Waiters started by an older copy of this helper hold no
ticket and can still take a free lock out of turn.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


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


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
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
    owner = read_owner(d)
    if owner is None:
        # A just-created lock has no owner.json yet; treat as stale only if old.
        try:
            return time.time() - d.stat().st_mtime > 60
        except OSError:
            return False
    return owner["system"] == system() and not pid_alive(int(owner["pid"]))


STALE_TICKET_S = 120.0


def queue_dir(d: Path) -> Path:
    return d.parent / (d.name + "-queue")


def take_ticket(d: Path) -> Path:
    q = queue_dir(d)
    q.mkdir(parents=True, exist_ok=True)
    t = q / f"{time.time_ns():020d}-{system()}-{os.getpid()}.json"
    t.write_text(json.dumps({"pid": os.getpid(), "system": system()}), encoding="utf-8")
    return t


def first_live_ticket(d: Path, stale_s: float = STALE_TICKET_S) -> Path | None:
    now = time.time()
    for t in sorted(queue_dir(d).glob("*.json")):
        try:
            age = now - t.stat().st_mtime
        except OSError:
            continue
        if age > stale_s:
            t.unlink(missing_ok=True)
            continue
        return t
    return None


def acquire(d: Path, command: list[str], poll: float) -> None:
    ticket = take_ticket(d)
    try:
        _acquire(d, command, poll, ticket)
    finally:
        ticket.unlink(missing_ok=True)


def _acquire(d: Path, command: list[str], poll: float, ticket: Path) -> None:
    last = None
    while True:
        os.utime(ticket)
        head = first_live_ticket(d, max(STALE_TICKET_S, 3 * poll))
        if (head is None or head == ticket) and try_acquire(d, command):
            return
        if stale(d):
            print(f"heavy_lock: removing stale lock ({describe(read_owner(d))})", file=sys.stderr)
            try:
                release(d)
            except OSError:
                pass
            continue
        owner = describe(read_owner(d))
        if head not in (None, ticket):
            owner += f" (queue: behind {head.name})"
        if owner != last:
            print(f"heavy_lock: waiting for {owner}", file=sys.stderr, flush=True)
            last = owner
        time.sleep(poll)


def run(command: list[str], poll: float) -> int:
    d = lock_dir()
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("run", help="run a command holding the lock")
    r.add_argument("--poll", type=float, default=10.0, help="seconds between checks")
    r.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("status", help="show the current owner")
    sub.add_parser("break", help="remove the lock")
    a = p.parse_args(argv)
    d = lock_dir()
    if a.action == "status":
        print(describe(read_owner(d)) if d.exists() else "free")
        q = queue_dir(d)
        waiting = sorted(q.glob("*.json")) if q.exists() else []
        for i, t in enumerate(waiting, 1):
            print(f"queue {i}: {t.stem}")
        return 0
    if a.action == "break":
        if d.exists():
            print(f"removing: {describe(read_owner(d))}")
            release(d)
        return 0
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        p.error("run needs a command after --")
    return run(command, a.poll)


if __name__ == "__main__":
    sys.exit(main())
