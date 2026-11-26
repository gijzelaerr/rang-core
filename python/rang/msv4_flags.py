# SPDX-License-Identifier: MIT
"""Flag versions and the write-back journal of an MSv4 store
(research/msv4-cli.md).

The MSv2 path keeps CASA flag versions and a journal in `<ms>.flagversions/`
(`rang.formats.flagversions`, `rang.core_writeback`). A store keeps the same
in a sibling `<store>.flagversions/`, laid out the same way, so the
pipeline's version names, lost-version test and journal rules apply to both:

- `FLAG_VERSION_LIST`: one `name : comment` line per version;
- `flags.<name>/`: per partition, a byte copy of the flag variable's
  directory (`<partition>/<variable>/`, its `zarr.json` and chunk files),
  and `manifest.json` (every file's size and sha256). Saved under
  `flags.<name>.rang-partial`, read back by sha256, renamed, then listed, so
  a killed save leaves no listed version;
- `rang-writeback.json`: the journal, with the MSv2 journal's keys. `FLAG`
  is recorded as written before the first write, so a session killed after
  it makes the next one refuse until the flags are restored
  (`restore_flags`), or the run directory that saved the version reruns.

Nothing is written into the store except by `restore_flags` and a
`WriteSession`'s caller; the versions never add a variable or attribute to
it (the store's files and schema check stay as the writer left them).
"""

import hashlib
import json
import os
import shutil
import socket
from pathlib import Path

from . import core_writeback
from .formats import flagversions

DEFAULT_BACKUP = core_writeback.DEFAULT_BACKUP
MANIFEST = "manifest.json"
PARTIAL = flagversions.PARTIAL
TMP = ".rang-restore-tmp"


class InterruptedWriteBack(core_writeback.InterruptedWriteBack):
    """An earlier write-back session on this store did not finish."""


def root(store):
    return flagversions.root(store)


def versions(store):
    return flagversions.versions(store)


def exists(store, name):
    return flagversions.exists(store, name)


def read_journal(store):
    return core_writeback.read_journal(store)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def flag_variables(store):
    """[(partition, flag variable)] of every visibility partition of the
    store, in the reader's order, for every data group's flag."""
    from . import msv4

    ps = msv4.open_processing_set(store)
    if ps.refused:
        raise ValueError(f"{store}: partitions refused: {ps.refused}")
    out = []
    for name in ps.names:
        groups = ps.tree[name].attrs["data_groups"]
        seen = []
        for group in groups.values():
            var = group.get("flag")
            if var and var not in seen:
                seen.append(var)
        out.extend((name, var) for var in seen)
    if not out:
        raise ValueError(f"{store}: no visibility partition with a flag variable")
    return out


def _files(top):
    """{relative posix path: absolute path} of every file under `top`."""
    top = Path(top)
    if not top.is_dir():
        return {}
    return {
        p.relative_to(top).as_posix(): p for p in sorted(top.rglob("*")) if p.is_file()
    }


def _record(store, pairs):
    """The manifest entries of the store's flag variables as they are now."""
    out = []
    for part, var in pairs:
        files = _files(Path(store) / part / var)
        if "zarr.json" not in files and ".zarray" not in files:
            raise ValueError(f"{store}: {part}/{var} is not a zarr array")
        out.append(
            {
                "partition": part,
                "variable": var,
                "files": {
                    rel: {"bytes": p.stat().st_size, "sha256": _sha256(p)}
                    for rel, p in files.items()
                },
            }
        )
    return out


def _metadata_name(entry):
    return "zarr.json" if "zarr.json" in entry["files"] else ".zarray"


def _fsync(path):
    with open(path, "rb+") as fh:
        os.fsync(fh.fileno())


def _differs(version_dir, entries):
    """Why the files of `version_dir` do not hold `entries`, or ''."""
    for e in entries:
        here = _files(Path(version_dir) / e["partition"] / e["variable"])
        if set(here) != set(e["files"]):
            return f"{e['partition']}/{e['variable']}: other files"
        for rel, want in e["files"].items():
            if _sha256(here[rel]) != want["sha256"]:
                return f"{e['partition']}/{e['variable']}/{rel} reads back differently"
    return ""


def save(store, name, comment=""):
    """Save the flag variables of every partition as flag version `name`
    (refused if it exists). Returns the version's directory."""
    store = Path(store)
    if exists(store, name):
        raise ValueError(f"flag version {name!r} exists")
    if (
        any(c in name for c in '/\\:*?"<>|')
        or " : " in name
        or name.endswith(PARTIAL)
        or not name.strip()
    ):
        raise ValueError(f"flag version name {name!r} is not allowed")
    pairs = flag_variables(store)
    top = root(store)
    top.mkdir(exist_ok=True)
    final = top / f"flags.{name}"
    partial = top / f"flags.{name}{PARTIAL}"
    entries = _record(store, pairs)
    if final.exists():
        # Killed between the rename and the list line: list it if it holds
        # exactly the store's flags now.
        if partial.exists() or _differs(final, entries):
            raise ValueError(f"{final} exists but is not listed; remove it first")
        flagversions._list(top, name, comment)
        return final
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir()
    for e in entries:
        src = store / e["partition"] / e["variable"]
        for rel in e["files"]:
            dst = partial / e["partition"] / e["variable"] / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / rel, dst)
            _fsync(dst)
    manifest = {
        "schema": "rang.msv4-flag-version",
        "version": 1,
        "name": name,
        "comment": comment,
        "store": str(store.resolve()),
        "partitions": entries,
    }
    (partial / MANIFEST).write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _fsync(partial / MANIFEST)
    # The copy is read back against what was read from the store.
    differs = _differs(partial, entries)
    if differs:
        raise RuntimeError(f"flag version {name}: {differs}")
    if _differs(store, entries):
        raise RuntimeError(f"{store}: its flags changed while version {name} was saved")
    os.replace(partial, final)
    flagversions._fsync_dir(top)
    flagversions._list(top, name, comment)
    return final


def manifest(store, name):
    path = root(store) / f"flags.{name}" / MANIFEST
    return json.loads(path.read_text(encoding="utf-8"))


def backup_flags(store, name=DEFAULT_BACKUP, comment=""):
    """Save flag version `name` unless it exists; True when saved now."""
    if exists(store, name):
        return False
    save(store, name, comment)
    return True


def restore(store, name):
    """Write flag version `name` back into the store's flag variables, file
    by file (temporary file in `<store>.flagversions`, then `os.replace`);
    chunk files the store has and the version has not are removed. Refused
    when a partition or a variable's metadata differs from the version's.
    Returns the number of files written. A killed restore is repeated by
    calling it again."""
    store = Path(store)
    if not exists(store, name):
        raise ValueError(f"flag version {name!r} of {store} does not exist")
    version = root(store) / f"flags.{name}"
    entries = manifest(store, name)["partitions"]
    bad = _differs(version, entries)
    if bad:
        raise ValueError(f"flag version {name!r} is damaged: {bad}")
    for e in entries:
        meta = _metadata_name(e)
        here = store / e["partition"] / e["variable"] / meta
        if not here.is_file() or _sha256(here) != e["files"][meta]["sha256"]:
            raise ValueError(
                f"{store}: {e['partition']}/{e['variable']} is not the array flag "
                f"version {name!r} was saved from (its {meta} differs)"
            )
    tmp_dir = root(store) / TMP
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir()
    written = 0
    try:
        for e in entries:
            target = store / e["partition"] / e["variable"]
            for rel, want in e["files"].items():
                dst = target / rel
                if dst.is_file() and _sha256(dst) == want["sha256"]:
                    continue
                tmp = tmp_dir / f"{written}.tmp"
                shutil.copyfile(version / e["partition"] / e["variable"] / rel, tmp)
                _fsync(tmp)
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp, dst)
                written += 1
            for rel, path in _files(target).items():
                if rel not in e["files"]:
                    path.unlink()
                    written += 1
            # Directories left empty by removed chunks (zarr 3 nests them).
            for d in sorted(
                (p for p in target.rglob("*") if p.is_dir()),
                key=lambda p: len(p.parts),
                reverse=True,
            ):
                if not any(d.iterdir()):
                    d.rmdir()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    bad = _differs(store, entries)
    if bad:
        raise RuntimeError(f"{store} reads back differently from {name!r}: {bad}")
    return written


def restore_flags(store, name=DEFAULT_BACKUP):
    """Restore flag version `name` and mark an interrupted session's journal
    as restored (as `core_writeback.restore_flags` on an MSv2)."""
    n = restore(store, name)
    journal = read_journal(store)
    if journal and journal.get("state") in ("open", "failed"):
        journal["state"] = "restored"
        journal["restored"] = core_writeback._now()
        journal["restored_from"] = name
        core_writeback._write_journal(store, journal)
    return n


def check_writable(store):
    """Refuse a store whose flag variables this process cannot write."""
    for part, var in flag_variables(store):
        for path in [
            Path(store) / part / var,
            *_files(Path(store) / part / var).values(),
        ]:
            if not os.access(path, os.W_OK):
                raise PermissionError(
                    f"{store} is not writable ({part}/{var}: permission denied); "
                    "make it writable (or work on a copy) and run again. Nothing "
                    "was written."
                )


class WriteSession:
    """A write-back session on a store, as `core_writeback.WriteBack` on an
    MSv2: `begin` refuses after an unfinished session that may have written
    FLAG (unless `on_interrupted` is "restore" or "continue"), saves
    `flag_backup` if absent and writes the journal `open`; `mark_flag_write`
    records FLAG as written before the caller's first write; `close` marks
    the journal `closed`, or `failed` on an exception."""

    def __init__(self, store, flag_backup=DEFAULT_BACKUP, stage="", comment=None,
                 on_interrupted="refuse"):  # fmt: skip
        if on_interrupted not in ("refuse", "restore", "continue"):
            raise ValueError("on_interrupted is 'refuse', 'restore' or 'continue'")
        self.store = Path(store)
        self.flag_backup = flag_backup
        self.stage = stage
        self.comment = comment
        self.on_interrupted = on_interrupted
        self._journal = None

    def begin(self):
        if self._journal is not None:
            return self
        check_writable(self.store)
        prior = read_journal(self.store)
        if core_writeback.flags_unfinished(prior):
            what = (
                f"an earlier write-back on {self.store} (stage {prior.get('stage')!r}, "
                f"pid {prior.get('pid')}, started {prior.get('started')}) is "
                f"{prior['state']}"
            )
            if self.on_interrupted == "refuse":
                raise InterruptedWriteBack(
                    f"{what}; FLAG may be partly written. Call "
                    f"rang.msv4_flags.restore_flags({str(self.store)!r}, "
                    f"{prior.get('flag_backup')!r}) to go back to the flags saved "
                    "before it, or pass on_interrupted='restore' or 'continue'."
                )
            if self.on_interrupted == "restore":
                restore_flags(self.store, prior["flag_backup"])
            if prior.get("flag_backup") and prior["flag_backup"] != self.flag_backup:
                self.flag_backup = prior["flag_backup"]
        backup_flags(
            self.store,
            self.flag_backup,
            self.comment
            or f"rang write-back: flags before {self.stage or 'the first write'}",
        )
        self._journal = {
            "state": "open",
            "ms": str(self.store.resolve()),
            "flag_backup": self.flag_backup,
            "stage": self.stage,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started": core_writeback._now(),
            "initialising": [],
            "written": [],
            "written_before_put": True,
        }
        core_writeback._write_journal(self.store, self._journal)
        return self

    def mark_flag_write(self, *_):
        """Record FLAG as written, before the first write (idempotent)."""
        if self._journal is None:
            raise ValueError("the write-back session is not open")
        if "FLAG" not in self._journal["written"]:
            self._journal["written"].append("FLAG")
            core_writeback._write_journal(self.store, self._journal)

    def close(self, error=None):
        if self._journal is None or self._journal["state"] != "open":
            return
        self._journal["state"] = "failed" if error is not None else "closed"
        self._journal["finished"] = core_writeback._now()
        if error is not None:
            self._journal["error"] = f"{type(error).__name__}: {error}"
        core_writeback._write_journal(self.store, self._journal)

    def __enter__(self):
        return self.begin()

    def __exit__(self, kind, value, tb):
        self.close(error=value)


__all__ = [
    "DEFAULT_BACKUP",
    "InterruptedWriteBack",
    "WriteSession",
    "backup_flags",
    "exists",
    "flag_variables",
    "manifest",
    "read_journal",
    "restore",
    "restore_flags",
    "root",
    "save",
    "versions",
]
