# SPDX-License-Identifier: GPL-3.0-or-later
"""W2 comparisons (research/w2-commands.md, criteria 2 and 3).

    python compare.py flag PRISTINE_MS WORK_MS ORACLE.npz BEFORE.json AFTER.json
    python compare.py store RANG_STORE ORACLE_STORE

Prints one JSON line with every measure and `pass`.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from casacure.tables import table
from rang.formats import quartical_store


def _col(ms, name):
    with table(str(ms), readonly=True, ack=False) as t:
        return t.getcol(name)


def flag(pristine, work, oracle, before, after):
    want = np.load(oracle)["FLAG"]
    got = _col(work, "FLAG")
    hashes_before = json.loads(Path(before).read_text(encoding="utf-8"))
    hashes_after = json.loads(Path(after).read_text(encoding="utf-8"))
    changed = sorted(
        k for k in hashes_before if hashes_before[k] != hashes_after.get(k)
    )
    version = Path(str(work) + ".flagversions") / "flags.rang_original"
    saved_flag, saved_row = _col(version, "FLAG"), _col(version, "FLAG_ROW")
    out = {
        "cells": int(want.size),
        "cells_differing": int(np.count_nonzero(want != got)),
        "flagged_fraction_rang": float(got.mean()),
        "flagged_fraction_oracle": float(want.mean()),
        "input_flagged_fraction": float(_col(pristine, "FLAG").mean()),
        "columns_changed": changed,
        "rang_original_flag_equal": bool(
            np.array_equal(saved_flag, _col(pristine, "FLAG"))
        ),
        "rang_original_flag_row_equal": bool(
            np.array_equal(saved_row, _col(pristine, "FLAG_ROW"))
        ),
    }
    out["pass"] = (
        out["cells_differing"] == 0
        and changed in ([], ["FLAG"])
        and out["rang_original_flag_equal"]
        and out["rang_original_flag_row_equal"]
    )
    return out


def _files(root):
    root = Path(root)
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def store(rang_store, oracle_store):
    a, b = _files(rang_store), _files(oracle_store)
    differing = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    ta = quartical_store.read(rang_store)
    tb = quartical_store.read(oracle_store)
    gains_equal, flags_equal, parts = True, True, 0
    for term in ta:
        for pa, pb in zip(ta[term], tb[term], strict=True):
            parts += 1
            ga, gb = pa.variables["gains"].data, pb.variables["gains"].data
            fa, fb = pa.variables["gain_flags"].data, pb.variables["gain_flags"].data
            gains_equal &= ga.dtype == gb.dtype and ga.tobytes() == gb.tobytes()
            flags_equal &= np.array_equal(fa, fb)
    out = {
        "files": len(a),
        "files_differing": differing,
        "partitions": parts,
        "gains_bit_identical": bool(gains_equal),
        "gain_flags_equal": bool(flags_equal),
    }
    out["pass"] = not differing and gains_equal and flags_equal and parts > 0
    return out


def resume(out):
    """Criterion 4 from the files run.sh keeps in OUT."""
    out = Path(out)

    def text(name):
        return (out / name).read_text(encoding="utf-8")

    bad = json.loads(text("state-after-bad.json"))["stages"]
    good = json.loads(text("state-after-good.json"))["stages"]
    hb = json.loads(text("hashes-resume-bad.json"))
    hg = json.loads(text("hashes-resume-good.json"))
    result = {
        "after_bad": {s: e["status"] for s, e in bad.items()},
        "after_good": {s: e["status"] for s, e in good.items()},
        "flag_and_calibrate_not_rerun": all(
            good[s]["started"] == bad[s]["started"] and good[s]["attempts"] == 1
            for s in ("flag", "calibrate")
        ),
        "image_attempts": good["image"]["attempts"],
        "ms_columns_unchanged": hb == hg,
        "flag_versions_unchanged": text("versions-after-bad.txt")
        == text("versions-after-good.txt"),
        "flag_versions": len(text("versions-after-good.txt").splitlines()),
        "store_unchanged": text("store-after-bad.txt") == text("store-after-good.txt"),
    }
    result["pass"] = (
        result["after_bad"] == {"flag": "done", "calibrate": "done", "image": "failed"}
        and result["after_good"]
        == {"flag": "done", "calibrate": "done", "image": "done"}
        and result["flag_and_calibrate_not_rerun"]
        and result["ms_columns_unchanged"]
        and result["flag_versions_unchanged"]
        and result["store_unchanged"]
    )
    return result


def main(argv):
    action, *args = argv
    actions = {"flag": flag, "store": store, "resume": resume}
    print(json.dumps({action: actions[action](*args)}))


if __name__ == "__main__":
    main(sys.argv[1:])
