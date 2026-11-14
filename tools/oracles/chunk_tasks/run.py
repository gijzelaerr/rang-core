# SPDX-License-Identifier: GPL-3.0-or-later
"""The identity runs of research/chunk-task-api.md (sections 2 and 3).

    python run.py arm RUN CASE ARM      # one arm: fresh MS copy, stages, hashes
    python run.py verdict RUN           # every arm against U, criteria 1-5

Cases F, S, O, W, C, P and arms U, P1, P4, P2T as section 2 freezes them.
U runs main 30d9412's Python (`RANG_CTA_ORACLE`, a detached worktree whose
`python/rang` holds the same `_core` extension as this checkout); the other
arms run this checkout's. Columns and flag versions are hashed with rang's
own reader in row chunks (casacure is not in the Windows venv). Each arm's MS
copy is deleted after its hashes are written.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
CHECKOUT = HERE.parents[3]
INPUTS = Path(r"D:\rang\outputs\cta-20261113-inputs")
STRATEGY = INPUTS / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
SOURCES = {
    "F": INPUTS / "fixture" / "outer_scans" / "1672727931_sdp_l0_scan_9.ms",
    "S": Path(r"D:\rang\outputs\fp-a1-20261106-simtruth\small\a1-small.ms"),
    "O": INPUTS / "o-casa-work.ms",
    "W": Path(r"D:\rang\outputs\w3\data\w3.ms"),
    "C": Path(r"D:\rang\outputs\fp-a1-20261106-simtruth\small\a1-small.ms"),
    "P": Path(r"D:\rang\outputs\c6w-20261106-01\prepared.ms"),
}
STAGES = {
    "F": ("flag", "calibrate", "apply"),
    "S": ("flag", "calibrate", "apply"),
    "O": ("flag", "calibrate", "apply"),
    "W": ("flag", "calibrate", "apply"),
    "C": ("calibrate", "apply"),
    "P": ("calibrate", "apply"),
}
ARMS = {
    "U": [],
    "P1": [],
    "P4": ["processes: 4", "threads: 4"],
    "P2T": ["processes: 2", "threads: 2", "chunk_rows: 7"],
}
ARMS_OF = {c: ("U", "P1", "P4", "P2T") for c in STAGES}
ARMS_OF["W"] = ("U", "P1", "P4")
# U and P1 run one process at this many rayon threads (section 2).
SERIAL_THREADS = 4
CHUNK_BYTES = 128 << 20

# W3's complex configuration (tools/oracles/w3/compare.py, amendment 1 there).
COMPLEX_TERMS = """\
calibrate:
  model: {source: setjy}
  primary:
    terms:
      - {type: complex, name: Gint, solint: int, freqint: 16}
      - {type: complex, name: G2, solint: 2, freqint: 512}
      - {type: complex, name: Gchan, solint: inf, freqint: 1}
"""
FIELDS = {
    "F": "fields: {fcal: [J1939-6342]}\n",
    "O": "fields: {fcal: [J1939-6342]}\n",
    "S": "fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], target: [SIM-TARGET]}\n",
    "W": "fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], target: [SIM-TARGET]}\n",
}
# W3b's cases C and P (tools/oracles/w3b/compare.py, templates A1 and POL).
A1 = """\
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], target: [SIM-TARGET]}
data: {weights: uniform, scans: %(scans)s%(data_inline)s}
flag: {strategy: %(strategy)s}
calibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: m000
  uvrange: ">150"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}
      - {type: A, name: A}
  secondary:
    terms:
      - {type: G, name: Gsec, solint: 60s, preapply: [K, B], interp: [linear, linear]}
      - {type: A, name: Asec}
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
apply:
  targets:
    - {field: [fcal], tables: [K, G, B]}
    - {field: [gcal, target], tables: [K, F, B],
       gainfield: [J1939-6342, nearest, J1939-6342]}
"""
POL = """\
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], xcal: [3C286-SIM],
         target: [SIM-TARGET]}
%(data)scalibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: m000
  uvrange: ">150"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}
  secondary:
    terms:
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
  polcal:
    model: {source: nrao, name: 3C286}
    feed_angle_rotation: -90.0
    terms:
      - {type: Gpol, name: Gpol, solint: 60s, preapply: [K, G, B]}
      - {type: KCROSS, name: Kcross, solint: inf, preapply: [K, G, B, Gpol]}
      - {type: Xf, name: Xf, solint: inf, combine: scan,
         preapply: [K, G, B, Gpol, Kcross]}
      - {type: Df, name: Df, field: [fcal], solint: inf, combine: scan,
         clip: [-0.6, 0.6], preapply: [K, G, B, Kcross, Xf]}
apply:
  parang: true
  targets:
    - {field: [xcal], tables: [K, G, B, Gpol, Kcross, Xf, Df],
       interp: [linear, linear, linear, linear, nearest, nearest, nearest]}
    - {field: [fcal], tables: [K, G, B, Kcross, Xf, Df],
       interp: [linear, linear, linear, nearest, nearest, nearest]}
    - {field: [gcal, target], tables: [K, F, B, Kcross, Xf, Df],
       gainfield: [J1939-6342, nearest, J1939-6342, "", "", ""],
       interp: [linear, linear, linear, nearest, nearest, nearest]}
"""


def config_text(case, arm, ms):
    lines = ARMS[arm]
    strategy = STRATEGY.as_posix()
    if case == "C":
        from rang import core_ms

        with core_ms.open_table(ms) as t:
            scans = sorted({int(s) for s in t.getcol("SCAN_NUMBER")})[:-1]
        inline = "".join(f", {d}" for d in lines)
        return A1 % {
            "scans": json.dumps(scans),
            "data_inline": inline,
            "strategy": strategy,
        }
    block = ("data:\n" + "".join(f"  {d}\n" for d in lines)) if lines else ""
    if case == "P":
        return POL % {"data": block}
    return (
        "version: 1\n"
        + FIELDS[case]
        + block
        + f"flag: {{strategy: {strategy}}}\n"
        + COMPLEX_TERMS
    )


# -- hashes ---------------------------------------------------------------------------


def _column_hash(t, name):
    first = t.getcol(name, 0, 1)
    step = max(1, CHUNK_BYTES // max(1, first.nbytes))
    digest = hashlib.sha256()
    for start in range(0, t.nrows, step):
        n = min(step, t.nrows - start)
        digest.update(np.ascontiguousarray(t.getcol(name, start, n)).tobytes())
    return digest.hexdigest()


def table_hashes(path, names=None):
    from rang import core_ms

    out = {}
    with core_ms.open_table(path) as t:
        for name in names or t.colnames():
            try:
                out[name] = _column_hash(t, name)
            except (OSError, ValueError, RuntimeError) as exc:  # undefined cells
                out[name] = f"unreadable: {type(exc).__name__}"
    return out


def hashes(ms):
    ms = Path(ms)
    record = {"columns": table_hashes(ms), "flag_versions": []}
    root = ms.with_name(ms.name + ".flagversions")
    listing = root / "FLAG_VERSION_LIST"
    if listing.is_file():
        for line in listing.read_text(encoding="utf-8").splitlines():
            name = line.split(" : ")[0].strip()
            if not name:
                continue
            record["flag_versions"].append(
                {
                    "key": re.sub(r"_\d{8}T\d{6}Z(_\d+)?$", "", name),
                    "columns": table_hashes(
                        root / f"flags.{name}", ["FLAG", "FLAG_ROW"]
                    ),
                }
            )
    return record


# -- one arm --------------------------------------------------------------------------


def arm(run, case, arm_name):
    run = Path(run)
    d = run / f"{case}-{arm_name}"
    if (d / "done.json").is_file():
        print(f"{case}-{arm_name}: done already")
        return
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    ms = d / "work.ms"
    shutil.copytree(SOURCES[case], ms)
    (d / "config.yaml").write_text(config_text(case, arm_name, ms), encoding="utf-8")
    if arm_name == "U":
        code = Path(os.environ["RANG_CTA_ORACLE"]) / "python"
    else:
        code = CHECKOUT / "python"
    env = dict(os.environ, PYTHONPATH=str(code), RAYON_NUM_THREADS=str(SERIAL_THREADS))
    record = {"case": case, "arm": arm_name, "code": str(code), "stages": {}}
    for stage in STAGES[case]:
        t0 = time.time()
        with open(d / f"{stage}.log", "w", encoding="utf-8") as log:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "rang.core_cli",
                    stage,
                    "config.yaml",
                    "work.ms",
                ],
                check=False,
                cwd=d,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        wall = time.time() - t0
        record["stages"][stage] = {"exit": proc.returncode, "wall_s": round(wall, 1)}
        print(
            f"{case}-{arm_name} {stage}: exit {proc.returncode}, {wall:.1f} s",
            flush=True,
        )
        if proc.returncode:
            break
        (d / f"hashes-{stage}.json").write_text(
            json.dumps(hashes(ms), indent=1) + "\n", encoding="utf-8"
        )
    shutil.rmtree(ms)
    flagversions = d / "work.ms.flagversions"
    if flagversions.exists():
        shutil.rmtree(flagversions)
    (d / "done.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


# -- the verdict ----------------------------------------------------------------------

VOLATILE = re.compile(
    r"(seconds|started|finished|updated|created|flag_version|store|strategy$|"
    r"receipt|ms$|path|chunking|rang_original_saved_now|restored_before|"
    r"append_table)"
)


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if not VOLATILE.search(str(k))}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _files(root):
    if not root.is_dir():
        return {}
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "summary.json"
    }


def _summary(d, stage):
    path = d / "work.ms.rang-run" / stage / "summary.json"
    if not path.is_file():
        return None
    return _clean(json.loads(path.read_text(encoding="utf-8")))


def verdict(run):
    run = Path(run)
    report = {"cases": {}, "pass": True}
    for case, stages in STAGES.items():
        u = run / f"{case}-U"
        if not (u / "done.json").is_file():
            continue
        out = {}
        for name in ARMS_OF[case][1:]:
            d = run / f"{case}-{name}"
            if not (d / "done.json").is_file():
                out[name] = "not run"
                continue
            diffs = []
            done_u = json.loads((u / "done.json").read_text())
            done_a = json.loads((d / "done.json").read_text())
            for stage in stages:
                eu = done_u["stages"].get(stage, {}).get("exit")
                ea = done_a["stages"].get(stage, {}).get("exit")
                if eu != 0 or ea != 0:
                    diffs.append(f"5: {stage} exit U {eu}, {name} {ea}")
                    continue
                hu = json.loads((u / f"hashes-{stage}.json").read_text())
                ha = json.loads((d / f"hashes-{stage}.json").read_text())
                for col in sorted(set(hu["columns"]) | set(ha["columns"])):
                    if hu["columns"].get(col) != ha["columns"].get(col):
                        diffs.append(f"1: {stage} column {col}")
                if stage == stages[-1] and hu["flag_versions"] != ha["flag_versions"]:
                    diffs.append("2: flag versions")
                if _summary(u, stage) != _summary(d, stage):
                    diffs.append(f"4: {stage} summary")
            fu = _files(u / "work.ms.rang-run" / "calibrate")
            fa = _files(d / "work.ms.rang-run" / "calibrate")
            if fu != fa:
                diffs.append(
                    "3: tables "
                    + ", ".join(
                        sorted(k for k in set(fu) | set(fa) if fu.get(k) != fa.get(k))
                    )
                )
            out[name] = {
                "pass": not diffs,
                "differences": diffs,
                "files_compared": len(fu),
                "walls_s": {s: v["wall_s"] for s, v in done_a["stages"].items()},
            }
            report["pass"] &= not diffs
        out["U_walls_s"] = {
            s: v["wall_s"]
            for s, v in json.loads((u / "done.json").read_text())["stages"].items()
        }
        report["cases"][case] = out
    text = json.dumps(report, indent=1) + "\n"
    (run / "verdict.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    if sys.argv[1] == "arm":
        arm(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "verdict":
        verdict(sys.argv[2])
    else:
        raise SystemExit(__doc__)
