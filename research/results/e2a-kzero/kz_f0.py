# SPDX-License-Identifier: MIT
"""research/e2a-kzero.md, gate 3b's CASA arms per rang arm, on nash: step F
of research/e2a-3b-k.md (`k_run.f0casa`, unchanged) on a copy of its `f0.ms`
(E2-A's field-0 rows, all 61 antennas) carrying the rang arm's own flags and
K tables.

    python kz_f0.py flags ARM     the arm's flag-stage and after-A FLAG at f0.ms's
                                  source rows -> O/ARM/f0/f0win/f0-{stage,after}-flags.npz
    python kz_f0.py prep ARM      f0.ms copied from e2a-3b-k's outputs (read only),
                                  the arm's six tables -> O/ARM/f0/f0win/rang-run/calibrate
    python kz_f0.py casa ARM CASE CASE tf (CASA's own K) or k (CASA on the arm's K0, K1)

ARM is zs, zsd or off. The flag-stage FLAG is the version saved before the
calibrate stage (state.json `stages.calibrate.flag_version`); the after-A FLAG
is the version saved before apply (`stages.apply.flag_version`) or, for an
arm without apply (off), the MS's FLAG when calibrate has finished and no
later stage has run. Every export is compared with e2a-3b-k's archived
export of E2-A's run (bitwise for the flag stage; counted for after-A).
"""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

# The pinned wheel's rang, imported before any script below puts the
# checkout's python/ (no extension built there) on sys.path; its submodules
# then resolve through the installed package.
import rang

if "site-packages" not in rang.__file__:
    raise SystemExit(f"rang from {rang.__file__}, not the installed wheel")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
O = Path.home() / "rang-data" / "outputs" / "e2a-kzero-20261117"
K = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"  # read only
NAMES = ("K0", "G0", "B0", "K1", "G1", "B1")


def log(text):
    with open(O / "kz.log", "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")


def arm_paths(arm):
    ms = O / arm / "e2a.ms"
    return ms, Path(str(ms) + ".rang-run"), O / arm / "f0"


def _versions(arm):
    _ms, rd, _ = arm_paths(arm)
    if not (rd / "state.json").exists():  # restore moved it; flux-run makes another
        rd = O / arm / "R" / "rang-run"  # the archive step's copy
    st = json.loads((rd / "state.json").read_text())["stages"]
    if st.get("calibrate", {}).get("status") != "done":
        raise SystemExit(f"{arm}: calibrate is not done")
    stage = st["calibrate"]["flag_version"]
    apply = st.get("apply", {})
    if apply.get("flag_version"):
        after = ("version", apply["flag_version"])
    else:
        later = [s for s in ("apply", "image", "selfcal") if s in st]
        if later:
            raise SystemExit(f"{arm}: {later} ran without an apply flag version")
        after = ("main", None)
    return stage, after


def _read(table_path, runs, col):
    from rang import core_ms

    parts = []
    with core_ms.open_table(table_path) as t:
        for r in runs:
            for s in range(0, len(r), 20000):
                k = min(20000, len(r) - s)
                parts.append(np.asarray(t.getcol(col, int(r[s]), k), bool))
    return np.concatenate(parts)


def _archived(name):
    z = np.load(K / "f0win" / f"f0-{name}-flags.npz")
    shape = tuple(int(x) for x in z["shape"])
    return np.unpackbits(z["flag"])[: np.prod(shape)].reshape(shape).astype(bool)


def flags(arm):
    from rang import core_ms

    ms, _rd, d = arm_paths(arm)
    out = d / "f0win"
    out.mkdir(parents=True, exist_ok=True)
    base = json.loads((K / "f0-base.json").read_text())
    rows = np.asarray(base["source_rows"], np.int64)
    runs = np.split(rows, np.flatnonzero(np.diff(rows) != 1) + 1)
    stage, (kind, after) = _versions(arm)
    fv = Path(str(ms) + ".flagversions")
    # row metadata from e2a-3b-k's idle f0.ms (the same source rows, checked by
    # npzflags), not from the arm's main table, which later stages write
    with core_ms.open_table(K / "f0.ms") as t:
        meta = {c: np.asarray(t.getcol(c)) for c in ("TIME", "ANTENNA1", "ANTENNA2")}
    if len(meta["TIME"]) != len(rows):
        raise SystemExit("f0.ms rows differ from f0-base.json's source rows")
    rec = {"arm": arm, "source_rows": len(rows), "runs": len(runs)}
    for name, src in (("stage", fv / f"flags.{stage}"),
                      ("after", fv / f"flags.{after}" if kind == "version" else ms)):  # fmt: skip
        t0 = time.perf_counter()
        f = np.ascontiguousarray(_read(src, runs, "FLAG"))
        fr = _read(src, runs, "FLAG_ROW")
        np.savez_compressed(out / f"f0-{name}-flags.npz", shape=np.array(f.shape),
                            flag=np.packbits(f.ravel()), FLAG_ROW=fr, **meta)  # fmt: skip
        ref = _archived(name)
        rec[name] = {"source": str(src), "shape": list(f.shape), "flagged": int(f.sum()),
                     "sha256": hashlib.sha256(f.tobytes()).hexdigest(),
                     "archived_flagged": int(ref.sum()),
                     "differ_from_archived": int((f != ref).sum()),
                     "seconds": time.perf_counter() - t0}  # fmt: skip
    (out / "flags.json").write_text(json.dumps(rec, indent=1) + "\n")
    log(f"flags {arm}: {json.dumps(rec)}")
    print(json.dumps(rec, indent=1))
    return 0


def prep(arm):
    _ms, rd, d = arm_paths(arm)
    if (d / "f0.ms").exists():
        raise SystemExit(f"{d / 'f0.ms'} exists")
    t0 = time.perf_counter()
    shutil.copytree(K / "f0.ms", d / "f0.ms", symlinks=True)
    shutil.copy(K / "f0-base.json", d / "f0-base.json")
    cal = d / "f0win" / "rang-run" / "calibrate"
    cal.mkdir(parents=True, exist_ok=True)
    if not (rd / "state.json").exists():
        rd = O / arm / "R" / "rang-run"  # the archive step's copy (see _versions)
    for n in NAMES:
        shutil.copytree(rd / "calibrate" / n, cal / n)
    log(f"prep {arm}: f0.ms and tables {time.perf_counter() - t0:.1f}s")
    return 0


def casa(arm, case):
    _, _, d = arm_paths(arm)
    os.environ.setdefault("K_THREADS", "4")
    sys.path.insert(0, str(ROOT / "research" / "results" / "e2a-3b-k"))
    import k_run  # step F's runner, unchanged; its outputs go to d

    k_run.O = d
    t0 = time.perf_counter()
    rc = k_run.f0casa(case)
    log(f"casa {arm} {case} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    fn = {"flags": flags, "prep": prep, "casa": casa}.get(step)
    if not fn:
        sys.exit(__doc__)
    sys.exit(fn(*args))
