# SPDX-License-Identifier: GPL-3.0-or-later
"""A spool executor for the chunk tasks: workers on any number of nodes that
share a filesystem (multi-node stage 2, research/multinode-executor.md).

The parent (the stage, the single MS writer) writes each `ChunkSpec` as JSON
into a spool directory; workers started by any launcher (a process on this
host, ssh, srun, a Slurm or PBS job array of pilot workers) claim specs by
creating a claim file exclusively (`O_CREAT | O_EXCL`), run them with `core_tasks.run` and write the pickled partial
under a temporary name renamed into place. The parent consumes the partials in
plan order, so results equal the inline path bit for bit, as stage 1's pool.

    python -m rang.core_spool worker SPOOL [--threads T] [--idle-exit S]
    python -m rang.core_spool stop SPOOL

Layout of SPOOL:

- `tasks/<tag>.json`: specs waiting for a worker (`<tag>` sorts in plan order);
- `claimed/<tag>`: the claim of the worker running it (its name is the
  content). A rename is not a safe claim: on Windows two processes can both
  rename the same file, the second moving it again;
- `done/<tag>.pkl`, `done/<tag>.err`: partials and tracebacks;
- `workers/<worker>.json`, `workers/<worker>.beat`: a worker's build and its
  heartbeat (touched every `BEAT_S`);
- `stop`: workers exit when it exists (`stop` subcommand).

A claim whose worker's heartbeat is older than `LEASE_S` is removed, so the
task can be claimed again (at most `ATTEMPTS` runs per task); `run` never writes the MS, so a
re-run is safe and gives the same partial. Each task carries the parent's
build (rang version and the `_core` extension's SHA-256), and a worker of
another build refuses it, which the parent raises. Partials are pickles, so
the spool must be private: the parent creates it 0700 and, on POSIX, refuses
one that is not its own or is open to others.
"""

import argparse
import functools
import hashlib
import json
import os
import pickle
import socket
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

BEAT_S = 2.0
LEASE_S = 60.0
ATTEMPTS = 3
POLL_S = (0.01, 0.2)  # first and longest sleep between polls
SUBDIRS = ("tasks", "claimed", "done", "workers")


class SpoolError(RuntimeError):
    """A spool that cannot run: unsafe, no live worker, a lost task."""


@functools.lru_cache(maxsize=1)
def build():
    """{'version', 'core_sha256'}: what a parent and its workers must share."""
    from . import __version__, _core

    digest = hashlib.sha256(Path(_core.__file__).read_bytes()).hexdigest()
    return {"version": __version__, "core_sha256": digest}


def prepare(spool):
    """Create `spool` (0700) and its subdirectories; refuse an unsafe one."""
    spool = Path(spool)
    spool.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        st = spool.stat()
        if st.st_uid != os.getuid():
            raise SpoolError(f"spool {spool} is not owned by this user")
        if st.st_mode & 0o077:
            raise SpoolError(
                f"spool {spool} is open to other users (mode "
                f"{st.st_mode & 0o777:o}); partials are pickles, chmod 700 it"
            )
    for sub in SUBDIRS:
        (spool / sub).mkdir(mode=0o700, exist_ok=True)
    return spool


def _retry(fn, *args, **kwargs):
    """`fn(*args)`, retried while Windows reports a sharing violation (another
    process has the file open for a moment: PermissionError)."""
    for delay in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0):
        try:
            return fn(*args, **kwargs)
        except PermissionError:
            if os.name != "nt":
                raise
            time.sleep(delay)
    return fn(*args, **kwargs)


def _unlink(path):
    _retry(Path(path).unlink, missing_ok=True)


def _write(path, data):
    """Write bytes under a temporary name and rename them into place."""
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    with open(tmp, "wb") as f:
        f.write(data)
    _retry(os.replace, tmp, path)


def _sleeper():
    delay = POLL_S[0]
    while True:
        time.sleep(delay)
        delay = min(POLL_S[1], delay * 1.5)
        yield


# -- the parent's side --------------------------------------------------------------


class Spool:
    """The parent's view of a spool: `submit(spec)`, `result(spec)` (blocks,
    re-queues lost claims, raises a task's error), `discard()`."""

    def __init__(self, spool, wait_s=600.0, log=None):
        self.root = prepare(spool)
        self.wait_s = float(wait_s)
        self.session = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.maps = 0
        self.attempts = {}
        self.mine = set()
        self.log = log
        self.counts = {"tasks": 0, "spec_bytes": 0, "partial_bytes": 0, "requeued": 0}
        self.plan_digest = hashlib.sha256()  # every map's specs, in order

    def new_map(self):
        self.maps += 1
        self.plan_digest.update(b"map")
        return self.maps

    def record(self):
        """Counts and the digest of the specs this parent sent: equal digests
        mean equal plans (research/multinode-executor.md, section 4)."""
        return dict(
            self.counts, maps=self.maps, plan_sha256=self.plan_digest.hexdigest()
        )

    def tag(self, spec, map_id):
        return f"{self.session}-{map_id:04d}-{spec.index:08d}"

    def submit(self, spec, map_id):
        tag = self.tag(spec, map_id)
        text = spec.to_json()
        # The plan, not where the MS is: the digest leaves `ms` out.
        self.plan_digest.update(text.replace(json.dumps(spec.ms), '""', 1).encode())
        body = json.dumps({"build": build(), "spec": text}, sort_keys=True).encode(
            "utf-8"
        )
        _write(self.root / "tasks" / f"{tag}.json", body)
        self.attempts[tag] = 1
        self.mine.add(tag)
        self.counts["tasks"] += 1
        self.counts["spec_bytes"] += len(body)
        return tag

    def _live_workers(self, now):
        live = set()
        for beat in (self.root / "workers").glob("*.beat"):
            try:
                if now - beat.stat().st_mtime <= LEASE_S:
                    live.add(beat.stem)
            except FileNotFoundError:
                pass
        return live

    def _requeue_lost(self, now):
        live = self._live_workers(now)
        for claim in (self.root / "claimed").glob(f"{self.session}-*"):
            tag = claim.name
            try:
                worker = _retry(claim.read_text, encoding="utf-8").strip()
                made = claim.stat().st_mtime
            except FileNotFoundError:
                continue  # finished meanwhile
            if worker in live or (not worker and now - made <= LEASE_S):
                continue  # running, or a claim being written
            beat = self.root / "workers" / f"{worker}.beat"
            try:
                age = now - beat.stat().st_mtime
            except (FileNotFoundError, OSError):
                age = float("inf")
            if age <= LEASE_S:
                continue
            if self.attempts.get(tag, 1) >= ATTEMPTS:
                raise SpoolError(
                    f"task {tag} lost {ATTEMPTS} times (worker {worker} last "
                    f"seen {age:.0f} s ago)"
                )
            if not (self.root / "tasks" / f"{tag}.json").is_file():
                continue  # the worker finished after all
            _unlink(claim)
            self.attempts[tag] = self.attempts.get(tag, 1) + 1
            self.counts["requeued"] += 1
            if self.log:
                self.log(f"spool: re-queued {tag} (worker {worker} lost)")
        return live

    def result(self, tag):
        done = self.root / "done"
        pkl, err = done / f"{tag}.pkl", done / f"{tag}.err"
        alone_since = None
        last_check = 0.0
        for _ in _sleeper():
            if pkl.is_file():
                data = _retry(pkl.read_bytes)
                _unlink(pkl)
                self.mine.discard(tag)
                self.counts["partial_bytes"] += len(data)
                return pickle.loads(data)
            if err.is_file():
                text = _retry(err.read_text, encoding="utf-8")
                _unlink(err)
                self.mine.discard(tag)
                raise SpoolError(f"task {tag} failed on a spool worker:\n{text}")
            now = time.time()
            if now - last_check < BEAT_S:
                continue
            last_check = now
            live = self._requeue_lost(now)
            if live:
                alone_since = None
            elif alone_since is None:
                alone_since = now
            elif now - alone_since > self.wait_s:
                raise SpoolError(
                    f"no live worker on spool {self.root} for {self.wait_s:.0f} s "
                    "(start one: python -m rang.core_spool worker SPOOL)"
                )

    def discard(self):
        """Remove this session's specs, claims and results left over."""
        for sub in ("tasks", "done", "claimed"):
            for p in (self.root / sub).glob(f"{self.session}-*"):
                _unlink(p)
        self.mine.clear()


# -- the worker ------------------------------------------------------------------------


class _Beat(threading.Thread):
    def __init__(self, path):
        super().__init__(daemon=True)
        self.path = path
        self.halt = threading.Event()

    def run(self):
        while not self.halt.is_set():
            try:
                self.path.touch()
            except OSError:
                pass
            self.halt.wait(BEAT_S)


def _claim(root, worker):
    """(tag, claim file, task file) of the first unclaimed task, or None."""
    claimed = root / "claimed"
    for path in sorted((root / "tasks").glob("*.json")):
        tag = path.name[: -len(".json")]
        claim = claimed / tag
        if claim.exists():
            continue
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except (FileExistsError, PermissionError):
            continue  # another worker took it
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(worker)
        if not path.is_file():  # finished or discarded meanwhile
            _unlink(claim)
            continue
        return tag, claim, path
    return None


def serve(spool, threads=None, idle_exit=None, log=print, max_tasks=None):
    """Run tasks from `spool` until its `stop` file exists, `idle_exit`
    seconds pass with nothing to do, or `max_tasks` have run."""
    if threads:
        # Before the core loads: its rayon pool is built at first use.
        os.environ["RAYON_NUM_THREADS"] = str(int(threads))
    root = prepare(spool)
    from . import core_tasks

    mine = build()
    worker = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    info = dict(mine, host=socket.gethostname(), pid=os.getpid(), threads=threads)
    (root / "workers" / f"{worker}.json").write_text(json.dumps(info) + "\n")
    beat = _Beat(root / "workers" / f"{worker}.beat")
    beat.path.touch()
    beat.start()
    log(f"spool worker {worker}: serving {root}")
    ran = 0
    idle = time.time()
    try:
        while not (root / "stop").exists():
            got = _claim(root, worker)
            if got is None:
                if idle_exit is not None and time.time() - idle > idle_exit:
                    break
                time.sleep(POLL_S[1])
                continue
            tag, claim, task = got
            try:
                try:
                    text = _retry(task.read_text, encoding="utf-8")
                except FileNotFoundError:
                    _unlink(claim)
                    continue  # discarded by the parent
                body = json.loads(text)
                if body["build"] != mine:
                    raise SpoolError(
                        f"build mismatch: the parent runs {body['build']}, this "
                        f"worker {mine}"
                    )
                spec = core_tasks.ChunkSpec.from_json(body["spec"])
                partial = core_tasks.run(spec)
                data = pickle.dumps(partial, protocol=5)
                _write(root / "done" / f"{tag}.pkl", data)
            except Exception:  # noqa: BLE001  (any failure goes to the parent)
                _write(
                    root / "done" / f"{tag}.err",
                    f"worker {worker}\n{traceback.format_exc()}".encode(),
                )
            _unlink(task)  # before the claim, so no one re-runs it
            _unlink(claim)
            ran += 1
            idle = time.time()
            if max_tasks is not None and ran >= max_tasks:
                break
    finally:
        beat.halt.set()
        for suffix in (".beat", ".json"):
            _unlink(root / "workers" / f"{worker}{suffix}")
    log(f"spool worker {worker}: {ran} tasks, exiting")
    return ran


def stop(spool):
    Path(spool, "stop").touch()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m rang.core_spool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker", help="serve chunk tasks from a spool directory")
    w.add_argument("spool")
    w.add_argument("--threads", type=int, default=None, help="RAYON_NUM_THREADS")
    w.add_argument("--idle-exit", type=float, default=None, help="seconds idle")
    w.add_argument("--max-tasks", type=int, default=None)
    s = sub.add_parser("stop", help="ask every worker of a spool to exit")
    s.add_argument("spool")
    args = ap.parse_args(argv)
    if args.cmd == "worker":
        serve(
            args.spool,
            args.threads,
            args.idle_exit,
            log=lambda m: print(m, flush=True),
            max_tasks=args.max_tasks,
        )
    else:
        stop(args.spool)
    return 0


if __name__ == "__main__":
    sys.exit(main())
