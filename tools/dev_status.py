# SPDX-License-Identifier: MIT
"""One screen for this checkout's development jobs (research/live-view-scope.md,
owner decision 6): the heavy lock with real CPU use, the GPU bookings of
`~/.gpu` (glacier), the status files of `outputs/status`, and `rang-core watch`
on any directories given.

    python tools/dev_status.py [PATH ...] [--status DIR ...] [--no-lock]

Reads only. The lock and the GPU files are this host's conventions; the
released command for a user's own run is `rang-core watch`.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "python"))

STALE_STATUS_S = 30 * 60  # AGENTS.md: a status file is updated every 30 minutes


def age(seconds):
    from rang.watch import duration

    return duration(seconds)


def lock():
    import heavy_lock

    print("## heavy lock")
    heavy_lock.status(heavy_lock.lock_dir())


def gpu(now, home=None):
    folder = (home or Path.home()) / ".gpu"
    log, reservations = folder / "log.txt", folder / "reservations.json"
    if not log.is_file() and not reservations.is_file():
        return
    print("## GPU bookings (~/.gpu)")
    if log.is_file():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-2:]:
            print(f"  {line[:200]}")
    if reservations.is_file():
        try:
            booked = json.loads(reservations.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"  reservations.json: {exc}")
            return
        today = datetime.fromtimestamp(now).isoformat()
        for r in booked.get("once", []):
            if str(r.get("end", "")) >= today:
                print(
                    f"  booked {r.get('start')} to {r.get('end')} by {r.get('owner')}:"
                    f" {r.get('note', '')}"
                )


def status_files(folders, now, limit):
    files = []
    for folder in folders:
        files += [p for p in Path(folder).glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"## status files ({len(files)}; newest {min(limit, len(files))})")
    for path in files[:limit]:
        seconds = now - path.stat().st_mtime
        first = ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip() and not line.startswith("#"):
                first = line.strip()
                break
        late = " LATE" if seconds > STALE_STATUS_S else ""
        print(f"  {path.stem:22s} {age(seconds):>12s} ago{late}  {first[:110]}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("paths", nargs="*", help="directories for rang-core watch --once")
    p.add_argument(
        "--status",
        action="append",
        metavar="DIR",
        help="a status directory (repeatable; default: outputs/status of this "
        "checkout and of its worktrees under ~/Worktrees)",
    )
    p.add_argument("--limit", type=int, default=8, help="status files shown (8)")
    p.add_argument("--no-lock", action="store_true", help="skip the heavy lock")
    args = p.parse_args(argv)
    now = time.time()
    if not args.no_lock:
        lock()
    gpu(now)
    default = [ROOT / "outputs" / "status"]
    default += sorted((Path.home() / "Worktrees" / "rang").glob("*/outputs/status"))
    status_files(args.status or default, now, args.limit)
    if args.paths:
        from rang import watch

        print("## directories")
        sys.stdout.flush()
        watch.main(["--once", *args.paths])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
