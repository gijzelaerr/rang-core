"""E1's runs (research/e1-chain.md, section 5): prepare a run directory, check
m32 against A1 full, write the control column and image it.

    python e1_run.py snapshot RUN
    python e1_run.py prepare RUN SRC_MS [--twin]
    python e1_run.py verify-m32 M32_MS FULL_MS OUT_JSON
    python e1_run.py control RUN

RUN holds `config.yaml`, the strategy file, `ms/<name>.ms` (a copy) and
`.code/` (the commit, the working-tree diff, the scripts and python/rang).
The chain itself runs as `rang-core run RUN/config.yaml RUN/ms/<name>.ms`
through `e1_job.ps1` (heavy lock, START/END lines in the log).
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rang import core_ms, core_pipeline, core_writeback, simtruth

A1 = Path(r"D:\rang\outputs\fp-a1-20261106-simtruth")
TRUTH = A1 / "full" / "truth.npz"
STRATEGY = Path(
    r"\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs"
    r"\caracal-strategy-inputs-8f7bb363\mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)
TARGET = "SIM-TARGET"
CONTROL_COLUMN = "CORRECTED_TRUTH"


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=1, default=_default) + "\n", encoding="utf-8"
    )


def _default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


def snapshot(run):
    code = Path(run) / ".code"
    if code.exists():
        shutil.rmtree(code)
    code.mkdir(parents=True)

    def git(*a):
        return subprocess.run(
            ["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True
        ).stdout

    (code / "commit.txt").write_text(git("rev-parse", "HEAD"), encoding="utf-8")
    (code / "status.txt").write_text(git("status", "--porcelain"), encoding="utf-8")
    (code / "diff.patch").write_text(git("diff", "HEAD"), encoding="utf-8")
    shutil.copytree(HERE, code / "e1-chain-scripts")
    shutil.copytree(
        ROOT / "python" / "rang",
        code / "rang",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyd", "*.so"),
    )


def prepare(run, src, twin=False):
    run = Path(run)
    (run / "ms").mkdir(parents=True, exist_ok=True)
    dst = run / "ms" / Path(src).name
    if dst.exists():
        raise SystemExit(f"{dst} exists")
    shutil.copytree(src, dst)
    shutil.copy2(STRATEGY, run / STRATEGY.name)
    text = (HERE / "e1_config.yaml").read_text(encoding="utf-8")
    if twin:
        # Section 4.1, the noise-free tier: no flag stage and no A step.
        text = text.replace("      - {type: A, name: Asec}\n", "")
        text = text.replace(
            "  stages: [flag, calibrate, apply, selfcal]",
            "  stages: [calibrate, apply]",
        )
        assert "Asec" not in text and "[calibrate, apply]" in text
    (run / "config.yaml").write_text(text, encoding="utf-8")
    snapshot(run)
    print(dst)


def truth_index(times, truth_times):
    """Integration index of every row time (exact float64 match)."""
    idx = np.searchsorted(truth_times, times)
    idx = np.clip(idx, 0, len(truth_times) - 1)
    if not np.array_equal(truth_times[idx], times):
        bad = int((truth_times[idx] != times).sum())
        raise ValueError(f"{bad} row times are not truth integration times")
    return idx


def verify_m32(m32, full, out):
    """Section 5 item 2: m32's DATA equals A1 full's on three integrations."""
    npz = np.load(TRUTH)
    tt = npz["time"]
    scans = npz["scan"]
    picks = {
        "scan 1, first": (1, 0),
        "scan 4, 32nd": (4, 31),
        "scan 21, 15th": (21, 14),
    }
    report = {"m32": str(m32), "full": str(full), "checks": {}}
    nbl = 64 * 63 // 2
    with core_ms.open_table(m32) as a, core_ms.open_table(full) as b:
        ta = a.getcol("TIME")
        for label, (scan, k) in picks.items():
            gi = int(np.flatnonzero(scans == scan)[k])
            t = tt[gi]
            ra = np.flatnonzero(ta == t)
            assert len(ra) == nbl, (label, len(ra))
            rb0 = gi * nbl
            tb = b.getcol("TIME", rb0, nbl)
            assert np.all(tb == t), label
            da = a.getcol("DATA", int(ra[0]), nbl)
            db = b.getcol("DATA", rb0, nbl)
            for col in ("ANTENNA1", "ANTENNA2"):
                assert np.array_equal(
                    a.getcol(col, int(ra[0]), nbl), b.getcol(col, rb0, nbl)
                )
            diff = float(np.abs(da.astype(np.complex128) - db).max())
            report["checks"][label] = {"integration": gi, "max_abs_diff": diff}
    report["pass"] = all(c["max_abs_diff"] == 0.0 for c in report["checks"].values())
    write_json(out, report)
    print(json.dumps(report, indent=1))


def load_truth(version="full"):
    npz = np.load(A1 / version / "truth.npz")
    truth = {k[4:]: npz[k] for k in npz.files if k.startswith("raw_")}
    return npz, truth


def ms_of(run):
    found = sorted((Path(run) / "ms").glob("*.ms"))
    assert len(found) == 1, found
    return found[0]


def field_id(ms, name):
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        names = list(t.getcol("NAME"))
    return names.index(name)


def control(run, version="full", chunk_rows=40320):
    """Section 4.4: CORRECTED_TRUTH on the target's rows, then its image."""
    run = Path(run)
    ms = ms_of(run)
    out = run / "control"
    out.mkdir(exist_ok=True)
    npz, truth = load_truth(version)
    d = simtruth.design(version)
    q = npz["parallactic_angle"]
    fid = field_id(ms, TARGET)
    started = time.perf_counter()
    with core_ms.open_table(ms) as t:
        fields = t.getcol("FIELD_ID")
    rows = np.flatnonzero(fields == fid)
    lo, hi = int(rows[0]), int(rows[-1]) + 1
    record = {"field_id": fid, "rows": len(rows), "version": version}
    with core_writeback.WriteBack(
        ms, flag_backup="e1_control", stage="e1-control", comment="E1 control"
    ) as w:
        w.ensure_column(CONTROL_COLUMN, init="zero")
        for start in range(lo, hi, chunk_rows):
            n = min(chunk_rows, hi - start)
            tm = np.asarray(w.read("TIME", start, n))
            f = np.asarray(w.read("FIELD_ID", start, n))
            a1 = np.asarray(w.read("ANTENNA1", start, n)).astype(np.int64)
            a2 = np.asarray(w.read("ANTENNA2", start, n)).astype(np.int64)
            v = np.asarray(w.read("DATA", start, n))
            sel = f == fid
            r = simtruth.Rows(truth_index(tm, npz["time"]), a1, a2)
            c = simtruth.correct(v, truth, d, r, q, parang=True)
            out_v = np.zeros(v.shape, np.complex64)
            out_v[sel] = c[sel].astype(np.complex64)
            w.write(CONTROL_COLUMN, start, out_v)
    record["write_seconds"] = time.perf_counter() - started
    config = json.loads(
        (run / "ms" / f"{ms.name}.rang-run" / "config.resolved.json").read_text(
            encoding="utf-8"
        )
    )
    img = config["image"]
    binary = core_pipeline.find_gemclean(img["gemclean"])
    where = out / "image"
    where.mkdir()
    argv = [
        str(binary),
        *core_pipeline.gemclean_arguments(
            img,
            CONTROL_COLUMN,
            fid,
            where / img["name"],
            ms,
            config["data"]["scans"] or (),
            config["data"]["weights"] == "uniform",
        ),
    ]
    record["argv"] = argv
    record["image_seconds"] = core_pipeline.run_gemclean(
        binary, argv, where / "gemclean.log"
    )
    write_json(out / "control.json", record)
    print(json.dumps(record, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("run")
    s = sub.add_parser("prepare")
    s.add_argument("run")
    s.add_argument("src")
    s.add_argument("--twin", action="store_true")
    s = sub.add_parser("verify-m32")
    s.add_argument("m32")
    s.add_argument("full")
    s.add_argument("out")
    s = sub.add_parser("control")
    s.add_argument("run")
    s.add_argument("--version", default="full")
    a = p.parse_args(argv)
    if a.cmd == "snapshot":
        snapshot(a.run)
    elif a.cmd == "prepare":
        prepare(a.run, a.src, a.twin)
    elif a.cmd == "verify-m32":
        verify_m32(a.m32, a.full, a.out)
    else:
        control(a.run, a.version)


if __name__ == "__main__":
    main()
