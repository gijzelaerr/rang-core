# SPDX-License-Identifier: MIT
"""`rang-core watch`: what a run directory, or any output directory, shows of
a job in progress (research/live-view-scope.md, owner decision 6).

It only reads, and creates nothing. For a run directory (one with
`state.json`, or a Measurement Set whose `<ms>.rang-run` exists) it reports
each stage's status and time, whether the process that marked a stage
`running` is still there, the receipts, and the last line of the newest log. For any directory it
reports the newest file and how long ago it changed, and for a spool
directory (`data.spool`) its tasks and worker heartbeats.

That is liveness, not progress: until the stages write a record of their own
(the same note, section 2), a long stage shows a clock and the time since its
last file change, and nothing of how far it has got.
"""

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import mcp_tools
from .core_spool import LEASE_S

SCHEMA = "rang.watch"
# A walk stops after this many directory entries, and says so.
MAX_ENTRIES = 50_000
MAX_LINE = 200
# Measurement Sets and other tables inside an output directory are counted by
# their top level only: their thousands of files say nothing a stage log does not.
_TABLE_MARK = "table.dat"


def _now():
    return time.time()


def _iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")


def _parse(stamp):
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except (TypeError, ValueError):
        return None


def duration(seconds):
    """`3 s`, `4 min 05 s`, `2 h 07 min`, `3 d 04 h`; `-` for None."""
    if seconds is None:
        return "-"
    s = int(max(seconds, 0))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    if s < 86400:
        return f"{s // 3600} h {s % 3600 // 60:02d} min"
    return f"{s // 86400} d {s % 86400 // 3600:02d} h"


def walk(path):
    """Newest file under `path`, the number of files and their bytes; logs
    (`*.log`) newest first. Tables are not entered; `truncated` when the walk
    stopped at MAX_ENTRIES."""
    newest, files, size, logs, seen, truncated = None, 0, 0, [], 0, False
    stack = [Path(path)]
    while stack and not truncated:
        here = stack.pop()
        try:
            entries = list(os.scandir(here))
        except OSError:
            continue
        table = any(e.name == _TABLE_MARK for e in entries)
        for entry in entries:
            seen += 1
            if seen > MAX_ENTRIES:
                truncated = True
                break
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not table:
                        stack.append(Path(entry.path))
                    continue
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            files += 1
            size += st.st_size
            if newest is None or st.st_mtime > newest[0]:
                newest = (st.st_mtime, entry.path)
            if entry.name.endswith(".log"):
                logs.append((st.st_mtime, entry.path))
    logs.sort(reverse=True)
    return {
        "newest": newest,
        "files": files,
        "bytes": size,
        "logs": logs,
        "truncated": truncated,
    }


def last_line(path, limit=MAX_LINE):
    """The last non-empty line of a text file, read from its end."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(fh.tell() - 8192, 0))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:limit]
    return None


def _relative(path, root):
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return str(path)


def spool(root, now):
    """Tasks and workers of a spool directory (`core_spool`'s layout), or None."""
    root = Path(root)
    if not (root / "tasks").is_dir() or not (root / "workers").is_dir():
        return None

    def count(name, pattern="*"):
        folder = root / name
        return len(list(folder.glob(pattern))) if folder.is_dir() else 0

    workers = []
    for beat in sorted((root / "workers").glob("*.beat")):
        try:
            age = now - beat.stat().st_mtime
        except OSError:
            continue
        workers.append(
            {"worker": beat.stem, "beat_age_s": round(age, 1), "live": age < LEASE_S}
        )
    return {
        "path": str(root),
        "waiting": count("tasks", "*.json"),
        "claimed": count("claimed"),
        "done": count("done", "*.pkl"),
        "failed": count("done", "*.err"),
        "stop": (root / "stop").exists(),
        "workers": workers,
    }


def _stage(name, entry, now):
    status = entry.get("status")
    started, finished = _parse(entry.get("started")), _parse(entry.get("finished"))
    out = {
        "stage": name,
        "status": status,
        "attempts": entry.get("attempts"),
        "host": entry.get("host"),
        "pid": entry.get("pid"),
        "started": entry.get("started"),
        "finished": entry.get("finished"),
        "seconds": entry.get("seconds"),
    }
    if status == "running":
        out["elapsed_s"] = None if started is None else round(now - started, 1)
        # Only this host can say whether the pid is still there.
        if entry.get("host") == socket.gethostname():
            out["process"] = (
                "alive" if mcp_tools._pid_alive(entry.get("pid")) else "gone"
            )
        else:
            out["process"] = "unknown (other host)"
    elif out["seconds"] is None and started is not None and finished is not None:
        out["seconds"] = round(finished - started, 1)
    return out


def resolve(path):
    """The directory to watch: a Measurement Set's run directory when it
    exists (`<ms>.rang-run`, the default of `rang-core run`), else `path`."""
    path = Path(path)
    beside = path.with_name(path.name + ".rang-run")
    if (path / _TABLE_MARK).is_file() and (beside / "state.json").is_file():
        return beside
    return path


def snapshot(path, now=None):
    """What `path` shows now, as a JSON-safe dict."""
    now = _now() if now is None else now
    path = resolve(path)
    out = {"schema": SCHEMA, "path": str(path), "time": _iso(now), "kind": "missing"}
    if not path.is_dir():
        return out
    seen = walk(path)
    out.update(
        kind="directory",
        files=seen["files"],
        bytes=seen["bytes"],
        truncated=seen["truncated"],
        newest=None,
        log=None,
        spools=[found] if (found := spool(path, now)) else [],
    )
    if seen["newest"]:
        mtime, name = seen["newest"]
        out["newest"] = {
            "file": _relative(name, path),
            "changed": _iso(mtime),
            "age_s": round(now - mtime, 1),
        }
    if seen["logs"]:
        mtime, name = seen["logs"][0]
        out["log"] = {
            "file": _relative(name, path),
            "age_s": round(now - mtime, 1),
            "last_line": last_line(name),
        }
    state_path = path / "state.json"
    if not state_path.is_file():
        return out
    try:
        state = mcp_tools._read_json(state_path)
    except (OSError, ValueError) as exc:
        out.update(kind="run", error=f"state.json: {exc}", stages=[])
        return out
    stages = state.get("stages") or {}
    receipts = path / "receipts"
    out.update(
        kind="run",
        ms=state.get("ms"),
        created=state.get("created"),
        updated=state.get("updated"),
        # In the order they started; state.json keeps them by name.
        stages=sorted(
            (_stage(name, entry or {}, now) for name, entry in stages.items()),
            key=lambda s: (s["started"] is None, s["started"] or "", s["stage"]),
        ),
        receipts=len(list(receipts.glob("*.rang-receipt.json")))
        if receipts.is_dir()
        else 0,
    )
    return out


def render(snap):
    """The lines of one snapshot, plain text."""
    path = snap["path"]
    if snap["kind"] == "missing":
        return [f"{path}: no such directory"]
    lines = []
    if snap["kind"] == "run":
        lines.append(f"{path}: run of {snap.get('ms') or '?'}")
        if snap.get("error"):
            lines.append(f"  {snap['error']}")
        for s in snap["stages"]:
            if s["status"] == "running":
                text = f"running {duration(s.get('elapsed_s'))}"
                text += f", pid {s['pid']} on {s['host']}: process {s['process']}"
            else:
                text = f"{s['status']}"
                if s.get("seconds") is not None:
                    text += f" in {duration(s['seconds'])}"
            if (s.get("attempts") or 1) > 1:
                text += f" (attempt {s['attempts']})"
            lines.append(f"  {s['stage']:10s} {text}")
        if not snap["stages"]:
            lines.append("  no stage has started")
        lines.append(f"  receipts: {snap['receipts']}")
    else:
        lines.append(f"{path}: {snap['files']} files, {snap['bytes'] / 1e6:.1f} MB")
    for sp in snap["spools"]:
        live = sum(w["live"] for w in sp["workers"])
        lines.append(
            f"  spool: {sp['waiting']} waiting, {sp['claimed']} claimed, "
            f"{sp['done']} done, {sp['failed']} failed; "
            f"{live} of {len(sp['workers'])} workers live"
            + ("; stop requested" if sp["stop"] else "")
        )
    if snap.get("truncated"):
        lines.append(f"  (stopped counting at {MAX_ENTRIES} entries)")
    if snap.get("newest"):
        n = snap["newest"]
        lines.append(f"  last change {duration(n['age_s'])} ago: {n['file']}")
    else:
        lines.append("  no files")
    if snap.get("log") and snap["log"]["last_line"]:
        log = snap["log"]
        lines.append(
            f"  {log['file']} ({duration(log['age_s'])} ago): {log['last_line']}"
        )
    return lines


def _stable(snap):
    """A snapshot without its clocks, to tell a change from the passing of time."""

    def strip(value):
        if isinstance(value, dict):
            return {
                k: strip(v)
                for k, v in value.items()
                if k not in ("time", "age_s", "elapsed_s", "beat_age_s")
            }
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return strip(snap)


def _brief(snap):
    """One line for a tick on which nothing but the clocks moved."""
    if snap["kind"] == "missing":
        return f"{snap['path']}: no such directory"
    parts = []
    for s in snap.get("stages", []):
        if s["status"] == "running":
            parts.append(
                f"{s['stage']} running {duration(s.get('elapsed_s'))}"
                f" (process {s['process']})"
            )
    if snap.get("newest"):
        parts.append(f"last change {duration(snap['newest']['age_s'])} ago")
    return f"{snap['path']}: " + ("; ".join(parts) or "no change")


def main(argv=None, out=None, sleep=time.sleep, ticks=None):
    """`rang-core watch PATH [PATH ...]`. `ticks` bounds the loop (tests)."""
    out = sys.stdout if out is None else out
    parser = argparse.ArgumentParser(
        prog="rang-core watch",
        description="Follow run directories or output directories without "
        "touching them. Reports each stage's status and time, whether its "
        "process is still there, spool tasks and worker heartbeats, receipts, "
        "the newest file and the last log line. This is liveness, not progress: "
        "it cannot say how far a running stage has got.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="a run directory, a Measurement Set that has one beside it "
        "(<ms>.rang-run), a spool directory (data.spool), or any directory a "
        "job writes into",
    )
    parser.add_argument("--once", action="store_true", help="report once and exit")
    parser.add_argument(
        "--json", action="store_true", help="one JSON object per report, on one line"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        metavar="S",
        help="seconds between reports (default 30)",
    )
    args = parser.parse_args(argv)
    if args.interval <= 0:
        parser.error("--interval must be positive")
    before, tick = {}, 0
    try:
        while True:
            now = _now()
            for path in args.paths:
                snap = snapshot(path, now)
                if args.json:
                    out.write(json.dumps(snap, sort_keys=True) + "\n")
                else:
                    stamp = datetime.fromtimestamp(now).strftime("%H:%M:%S")
                    stable = _stable(snap)
                    if before.get(path) != stable:
                        lines = render(snap)
                        out.write(f"{stamp} {lines[0]}\n")
                        out.writelines(f"{line}\n" for line in lines[1:])
                    else:
                        out.write(f"{stamp} {_brief(snap)}\n")
                    before[path] = stable
            out.flush()
            tick += 1
            if args.once or (ticks is not None and tick >= ticks):
                return 0
            sleep(args.interval)
    except KeyboardInterrupt:
        return 0
