"""The LUNO rerun (research/chi-offset.md 4.3) on this task's own small MS:
LUNO scans 1 (3C 286), 2 (1934-638), 17 (3C 286), 18 (1934-638), the first
ROWS rows of each (whole integrations), all 4,096 channels. Never touches
E2's MSs or run directories.

    python luno_rerun.py build OUT             e2_convert build + rang's flag stage
    python luno_rerun.py rang OUT ARM          ARM: m90 | null (FEED's 0) | null_own | m90_own, each with _noavg
    python luno_rerun.py casa OUT ARM          ARM: m90 | feed0
    python luno_rerun.py score OUT ARM_DIR

The chain is e2b.yaml's calibrate and apply (the dry run's `b` config) with
data.scans [1, 2, 17, 18]: K, G, B on 1934-638 (both scans), Gpol p 60 s,
KCROSS inf per scan, Xf combine scan (one Xf from both 3C 286 scans, 44 deg
of psi apart), Df on 1934-638, apply with parang. CASA: the same calls
(sim_chi.casa_calls) with rang's refants m022, m023, m024 (flex), on a copy
carrying rang's flag-stage FLAG.
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import sim_chi as S

STORE = r"D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr"
GROUPS = ["MAIN_0", "MAIN_1", "MAIN_16", "MAIN_17"]
ROWS = 9576  # 6 integrations of 1,596 rows (56 antennas with autos)
STRATEGY = (
    ROOT
    / "research/results/e2-acceptance-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)
FCAL, XCAL = "J1939-6342", "J1331+3030"
REFANT = "m022,m023,m024"
BANDS = [(1.0e9, 1.1e9), (1.1e9, 1.2e9), (1.2e9, 1.3e9), (1.3e9, 1.4e9), (1.4e9, 1.5e9),
         (1.5e9, 1.6e9), (1.6e9, 1.65e9), (1.3e9, 1.5e9)]  # fmt: skip

FLAG_CONFIG = """\
version: 1
fields: {fcal: [J1939-6342], bpcal: [J1939-6342], xcal: [J1331+3030]}
data: {weights: uniform, scans: [1, 2, 17, 18]}
flag:
  strategy: mk_rfi_flagging_calibrator_fields_firstpass.yaml
run:
  stages: [flag]
"""


def chain_config(far, xf_own=False, average=True):
    """The dry run's b config (e2b.yaml's shape), scans 1, 2, 17, 18, calibrate and apply.
    xf_own: Xf solved per scan (combine '') so each 3C 286 scan gets its own Xf
    (added 2026-11-13 post hoc, for rule (iii)'s "Xf from either scan").
    average False: calibrate.average_time off (added 2026-11-13 post hoc: with
    it on, Xf combine scan is solved on rows averaged across both 3C 286
    scans, which the sim's control truth showed breaks Xf by 78 deg)."""
    src = (Path(r"D:\rang\outputs\e2-20261111-12-dryrun\b\config.yaml")).read_text(
        encoding="utf-8"
    )
    src = src.replace("  scans: [1, 2]\n", "  scans: [1, 2, 17, 18]\n")
    src = src.replace(
        "    feed_angle_rotation: -90\n", f"    feed_angle_rotation: {far}\n"
    )
    src = src.replace(
        "  stages: [flag, calibrate, apply, image]\n", "  stages: [calibrate, apply]\n"
    )
    assert "scans: [1, 2, 17, 18]" in src and f"feed_angle_rotation: {far}" in src
    assert "stages: [calibrate, apply]" in src
    if xf_own:
        old = "      - {type: Xf, name: Xf, solint: inf, combine: scan, parang: true,"
        assert old in src
        src = src.replace(old, old.replace("combine: scan", "combine: ''"))
    if not average:
        assert "  average_time: true\n" in src
        src = src.replace("  average_time: true\n", "  average_time: false\n")
    return src


def run(cmd, logfile):
    t0 = time.perf_counter()
    with open(logfile, "w", encoding="utf-8") as fh:
        rc = subprocess.run([str(c) for c in cmd], stdout=fh, stderr=subprocess.STDOUT,
                            check=False).returncode  # fmt: skip
    return rc, time.perf_counter() - t0


def build(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    base = out / "base" / "luno4.ms"
    base.parent.mkdir(exist_ok=True)
    conv = ROOT / "research/results/e2-acceptance-scripts/e2_convert.py"
    rc, s = run([sys.executable, conv, "build", base, *[f"{STORE}:{g}" for g in GROUPS],
                 "--rows", ROWS], out / "build.log")  # fmt: skip
    S.log(out, f"build rc={rc} {s:.1f}s")
    if rc:
        return rc
    (base.parent / "config.yaml").write_text(FLAG_CONFIG, encoding="utf-8")
    shutil.copy(STRATEGY, base.parent / STRATEGY.name)
    rc, s = run(
        [S.RANG_CORE, "run", base.parent / "config.yaml", base], out / "flag.log"
    )
    S.log(out, f"flag rc={rc} {s:.1f}s")
    return rc


def copy_base(out, d):
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copytree(Path(out) / "base" / "luno4.ms", d / "sim.ms")
    shutil.copy(STRATEGY, d / STRATEGY.name)


def rang_arm(out, arm):
    d = Path(out) / f"rang-{arm}"
    copy_base(out, d)
    far = "-90" if arm.startswith("m90") else "null"
    (d / "config.yaml").write_text(chain_config(far, "_own" in arm, "_noavg" not in arm),
                                   encoding="utf-8")  # fmt: skip
    rc, s = run([S.RANG_CORE, "run", d / "config.yaml", d / "sim.ms"], d / "rang.log")
    S.log(out, f"rang {arm} rc={rc} {s:.1f}s")
    if rc == 0:
        score(d, -90.0 if arm.startswith("m90") else 0.0)
    return rc


def casa_arm(out, arm):
    d = Path(out) / f"casa-{arm}"
    copy_base(out, d)
    (d / "tables").mkdir()
    calls = S.casa_calls("/r/sim.ms", "/r/tables", FCAL=FCAL, XCAL=XCAL, refant=REFANT)
    for c in calls:  # rang's B is per scan solint inf with combine '' as e2b.yaml
        c["args"].pop("fillgaps", None)
    (d / "spec.json").write_text(json.dumps(calls, indent=1))
    t0 = time.perf_counter()
    rc = S.casa_docker(d, -1.5707963267948966 if arm == "m90" else None)
    S.log(out, f"casa {arm} rc={rc} {time.perf_counter() - t0:.1f}s")
    if rc == 0:
        score(d, -90.0 if arm == "m90" else 0.0)
    return rc


def score(d, rdeg):
    d = Path(d)
    res = {}
    for col in ("CORRECTED_DATA", "MODEL_DATA"):
        for lo, hi in BANDS:
            tag = f"-{col}-{lo / 1e9:.2f}-{hi / 1e9:.2f}"
            res[tag] = S.score(d / "sim.ms", col, "FLAG", d, xcal=XCAL,
                               band=(str(lo), str(hi)), rdeg=rdeg, tag=tag)  # fmt: skip
    (d / "chi-all.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")


def main(argv):
    cmd, out = argv[0], argv[1]
    if cmd == "build":
        return build(out)
    if cmd == "rang":
        return rang_arm(out, argv[2])
    if cmd == "casa":
        return casa_arm(out, argv[2])
    if cmd == "score":
        score(argv[2], float(argv[3]))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
