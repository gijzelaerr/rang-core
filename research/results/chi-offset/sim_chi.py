"""The chi-offset simulation (research/chi-offset.md 4.1): poldx's noiseless
twin under three truths, E2-B's polcal chain in rang and CASA 6.7.6.14, chi
per 3C286-SIM scan against the parallactic angle.

    python sim_chi.py gen TRUTH OUT            TRUTH: control | feed0 | revpsi
    python sim_chi.py rang OUT TRUTH ARM             ARM: m90 | null | gpol_noparang
    python sim_chi.py casa OUT TRUTH ARM             ARM: m90 | feedms (FEED as written)
    python sim_chi.py score OUT ARM_DIR        chi per scan -> ARM_DIR/chi.json

Truths (the corruption's P; workers get q from the parent, so the parent's
q is shifted, not the module constant):
- control: a = psi + (-90 deg), FEED -90 deg (poldx as C6 and C6w).
- feed0:   a = psi + 0, FEED 0 (LUNO-like: H3 of the note).
- revpsi:  a = -psi + (-90 deg), FEED -90 deg (H1: P's sense reversed).
OUT/truth-<TRUTH>/a1-poldx-twin.ms. Arms copy that MS to OUT/<side>-<ARM>/.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

FCAL, XCAL = "J1939-6342", "3C286-SIM"
UVRANGE = ">150"
CASA_IMAGE = "rang-o-casa:6.7.6.14"
RANG_CORE = os.environ.get(
    "CHI_RANG_CORE", str(Path(sys.executable).parent / "rang-core")
)

CONFIG = """\
version: 1
fields: {{fcal: [J1939-6342], bpcal: [J1939-6342], xcal: [3C286-SIM]}}
data: {{weights: uniform{scans}}}
calibrate:
  model: {{source: setjy, standard: Stevens-Reynolds 2016}}
  refant: m000
  uvrange: "{uv}"
  average_time: {avg}
  primary:
    field: [fcal]
    terms:
      - {{type: K, name: K, solint: inf}}
      - {{type: G, name: G, solint: inf, calmode: ap, preapply: [K], interp: [linear]}}
      - {{type: B, name: B, solint: inf, preapply: [K, G], interp: [linear, linear]}}
  polcal:
    field: [xcal]
    model: {{source: nrao, name: 3C286}}
    feed_angle_rotation: {far}
    terms:
      - {{type: Gpol, name: Gpol, solint: 60s, calmode: p, parang: {gpol_parang},
         preapply: [K, G, B], interp: [linear, linear, linear]}}
      - {{type: KCROSS, name: Kcross, solint: inf, parang: true,
         preapply: [K, G, B, Gpol], interp: [linear, linear, linear, linear]}}
      - {{type: Xf, name: Xf, solint: inf, combine: scan, parang: true,
         preapply: [K, G, B, Gpol, Kcross], interp: [linear, linear, linear, linear, nearest]}}
      - {{type: Df, name: Df, field: [fcal], solint: inf, combine: scan, parang: true,
         clip: [-0.6, 0.6], preapply: [K, G, B, Kcross, Xf],
         interp: [linear, linear, linear, nearest, nearest]}}
apply:
  calwt: false
  parang: true
  targets:
    - field: [fcal, xcal]
      tables: [K, G, B, Gpol, Kcross, Xf, Df]
      interp: [linear, linear, linear, linear, nearest, nearest, nearest]
run:
  stages: [{stages}]
"""

RANG_ARMS = {
    "m90": {"far": "-90", "gpol_parang": "true"},
    "null": {"far": "null", "gpol_parang": "true"},
    "gpol_noparang": {"far": "-90", "gpol_parang": "false"},
    # Added 2026-11-13 after the control gate failed (post hoc): no time pre-averaging.
    "m90_noavg": {"far": "-90", "gpol_parang": "true", "avg": "false"},
    "null_noavg": {"far": "null", "gpol_parang": "true", "avg": "false"},
}


def wsl(p):
    p = str(Path(p).resolve()).replace("\\", "/")
    return f"/mnt/{p[0].lower()}{p[2:]}"


def log(out, msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(Path(out) / "sim_chi.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def gen(truth, out):
    from rang import simtruth as st
    from rang import simtruth_ms

    out = Path(out)
    (out / f"truth-{truth}").mkdir(parents=True, exist_ok=True)
    orig = st.geometry

    def geometry(d, times, fields):
        uvw, q, elev = orig(d, times, fields)
        if truth == "feed0":
            q = q + math.pi / 2  # worker adds RECEPTOR_ANGLE (-pi/2): a = psi + 0
        elif truth == "revpsi":
            q = -q
        return uvw, q, elev

    if truth == "feed0":
        st.RECEPTOR_ANGLE = 0.0  # FEED written by the parent
    elif truth not in ("control", "revpsi"):
        raise SystemExit(f"unknown truth {truth}")
    st.geometry = geometry
    t0 = time.perf_counter()
    simtruth_ms.main(["generate", "poldx", str(out / f"truth-{truth}"), "--noiseless",
                      "--workers", "4"])  # fmt: skip
    log(out, f"gen {truth} {time.perf_counter() - t0:.1f}s")


def src_ms(out, truth):
    return Path(out) / f"truth-{truth}" / "a1-poldx-twin.ms"


def rang_arm(out, truth, arm):
    d = Path(out) / f"rang-{truth}-{arm}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    ms = d / "sim.ms"
    shutil.copytree(src_ms(out, truth), ms)
    cfg = d / "config.yaml"
    a = RANG_ARMS[arm]
    cfg.write_text(CONFIG.format(scans="", uv=UVRANGE, far=a["far"],
                                 gpol_parang=a["gpol_parang"], avg=a.get("avg", "true"),
                                 stages="calibrate, apply"), encoding="utf-8")  # fmt: skip
    t0 = time.perf_counter()
    with open(d / "rang.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run([RANG_CORE, "run", str(cfg), str(ms)], stdout=fh,
                            stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
    log(out, f"rang {truth} {arm} rc={rc} {time.perf_counter() - t0:.1f}s")
    if rc == 0:
        score(d / "sim.ms", "CORRECTED_DATA", "FLAG", d)
    return rc


def casa_calls(ms, t, FCAL=FCAL, XCAL=XCAL, refant="m000"):
    common = {"vis": ms, "refant": refant, "minsnr": 3.0, "minblperant": 4}
    mode = {"refantmode": "flex"}
    x286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
            "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
            "rotmeas": 0.0}  # fmt: skip
    cc = [f"{t}/K", f"{t}/G", f"{t}/B"]
    LIN, NEAR = "linear", "nearest"
    calls = [
        {"task": "setjy", "args": {"vis": ms, "field": FCAL, "standard": "Stevens-Reynolds 2016",
         "scalebychan": True, "usescratch": True}},
        {"task": "setjy", "args": {"vis": ms, "field": XCAL, "standard": "manual", **x286,
         "scalebychan": True, "usescratch": True}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/K", "field": FCAL,
         "gaintype": "K", "solint": "inf", "combine": "", "parang": False}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/G", "field": FCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "gaintable": [f"{t}/K"], "interp": [LIN]}},
        {"task": "bandpass", "args": {**common, "caltable": f"{t}/B", "field": FCAL,
         "bandtype": "B", "solint": "inf", "combine": "", "solnorm": False,
         "parang": False, "uvrange": UVRANGE,
         "gaintable": [f"{t}/K", f"{t}/G"], "interp": [LIN, LIN]}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gpol", "field": XCAL,
         "gaintype": "G", "calmode": "p", "solint": "60s", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc, "interp": [LIN] * 3}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Kcross", "field": XCAL,
         "gaintype": "KCROSS", "solint": "inf", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc + [f"{t}/Gpol"], "interp": [LIN] * 4}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Xf", "field": XCAL,
         "poltype": "Xf", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Gpol", f"{t}/Kcross"], "interp": [LIN] * 4 + [NEAR]}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Df.raw", "field": FCAL,
         "poltype": "Df", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Kcross", f"{t}/Xf"], "interp": [LIN] * 3 + [NEAR] * 2}},
        {"task": "copytree", "args": {"src": f"{t}/Df.raw", "dst": f"{t}/Df"}},
        {"task": "flagdata", "args": {"vis": f"{t}/Df", "mode": "clip",
         "clipminmax": [-0.6, 0.6], "datacolumn": "CPARAM", "flagbackup": False}},
        {"task": "applycal", "args": {"vis": ms, "field": f"{FCAL},{XCAL}",
         "gaintable": [f"{t}/{n}" for n in ("K", "G", "B", "Gpol", "Kcross", "Xf", "Df")],
         "interp": [LIN] * 4 + [NEAR] * 3, "calwt": [False] * 7, "parang": True,
         "applymode": "calflag", "flagbackup": False}},
    ]  # fmt: skip
    return calls


SET_FEED = """\
import sys
from casatools import table
tb = table(); tb.open(sys.argv[1] + "/FEED", nomodify=False)
a = tb.getcol("RECEPTOR_ANGLE"); a[:] = float(sys.argv[2]); tb.putcol("RECEPTOR_ANGLE", a)
tb.close(); print("RECEPTOR_ANGLE set", sys.argv[2])
"""


def casa_docker(d, set_feed_rad):
    """CASA's chain on d/sim.ms with d/spec.json; FEED set first unless None."""
    (d / "set_feed.py").write_text(SET_FEED, encoding="utf-8")
    steps = []
    if set_feed_rad is not None:
        steps.append(
            f"/opt/casa/bin/python -I /r/set_feed.py /r/sim.ms {set_feed_rad!r}"
        )
    steps.append(
        "/opt/casa/bin/python -I /ex/oracle_pol.py tasks /r/spec.json /r/tasks.json"
    )
    script = " && ".join(steps)
    inner = " ".join(["docker", "run", "--rm", "--network", "none", "--user",
                      "$(id -u):$(id -g)", "--tmpfs", "/tmp", "-e", "HOME=/tmp",
                      "-e", "OMP_NUM_THREADS=4", "-v", f"'{wsl(d)}:/r:rw'", "-v",
                      f"'{wsl(ROOT / 'examples')}:/ex:ro'", "-w", "/tmp", CASA_IMAGE,
                      "sh", "-c", f'"{script}"'])  # fmt: skip
    with open(d / "casa.out", "w", encoding="utf-8") as fh:
        return subprocess.run(["wsl", "-e", "bash", "-lc", inner], stdout=fh,
                              stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip


def casa_arm(out, truth, arm):
    d = Path(out) / f"casa-{truth}-{arm}"
    if d.exists():
        shutil.rmtree(d)
    (d / "tables").mkdir(parents=True)
    ms = d / "sim.ms"
    shutil.copytree(src_ms(out, truth), ms)
    (d / "spec.json").write_text(
        json.dumps(casa_calls("/r/sim.ms", "/r/tables"), indent=1)
    )
    t0 = time.perf_counter()
    rc = casa_docker(d, -math.pi / 2 if arm == "m90" else None)
    log(out, f"casa {truth} {arm} rc={rc} {time.perf_counter() - t0:.1f}s")
    if rc == 0:
        score(ms, "CORRECTED_DATA", "FLAG", d)
    return rc


def score(ms, col, flag, d, xcal=XCAL, band=("0.8e9", "1.8e9"), rdeg=None, tag=""):
    import chi_vs_psi
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(xcal)
    with core_ms.open_table(ms) as t:
        scans = np.unique(
            np.asarray(t.getcol("SCAN_NUMBER"))[np.asarray(t.getcol("FIELD_ID")) == fid]
        )
    if rdeg is None:
        with core_ms.open_table(Path(ms) / "FEED") as t:
            rdeg = float(np.degrees(np.asarray(t.getcol("RECEPTOR_ANGLE"))[0, 0]))
        cfg = Path(d) / "config.yaml"
        if cfg.exists() and "feed_angle_rotation: -90" in cfg.read_text(
            encoding="utf-8"
        ):
            rdeg = -90.0
    summary = []
    for s in scans:
        o = Path(d) / f"chi{tag}-scan{s}.json"
        chi_vs_psi.main([str(ms), col, flag, xcal, str(s), str(rdeg), str(o), *band])
        rows = json.loads(o.read_text())["integrations"]
        z = np.mean([r["q"] + 1j * r["u"] for r in rows])
        zf = np.mean([r["q_f"] + 1j * r["u_f"] for r in rows])
        summary.append({"scan": int(s), "psi_deg": float(np.mean([r["psi_deg"] for r in rows])),
                        "p": float(abs(z)), "chi_deg": float(np.degrees(np.angle(z) / 2)),
                        "q_f": float(zf.real), "u_f": float(zf.imag),
                        "receptor_deg_used": rdeg})  # fmt: skip
    (Path(d) / f"chi{tag}.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8"
    )
    for r in summary:
        print(
            f"scan {r['scan']:3d} psi {r['psi_deg']:8.2f} p {r['p']:.4f} chi {r['chi_deg']:7.2f}"
            f" q_f {r['q_f']:+.4f}"
        )
    return summary


def main(argv):
    cmd = argv[0]
    if cmd == "gen":
        gen(argv[1], argv[2])
    elif cmd == "rang":
        return rang_arm(argv[1], argv[2], argv[3])
    elif cmd == "casa":
        return casa_arm(argv[1], argv[2], argv[3])
    elif cmd == "score":
        score(argv[2], "CORRECTED_DATA", "FLAG", argv[1])
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
