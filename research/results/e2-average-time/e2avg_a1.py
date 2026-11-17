"""Validation 1 of `calibrate.average_time` (task E2): A1 small with C2e's
I-a1 chain (K, G, B, A on the primary; Gsec 60s, Asec, F on the secondary;
`examples/check_c2e.py` A1_CONFIG, calibrate only), once without and once
with the key, on fresh copies; the tables and the fcal (K G B) and gcal
(K F B) composites compared.

    python e2avg_a1.py RUN
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import e2avg_common as C
from rang import cal_apply, core_ms

A1 = Path(r"D:\rang\outputs\fp-a1-20261106-simtruth\small\a1-small.ms")
STRATEGY = "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
CONFIG = """\
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], target: [SIM-TARGET]}
data: {weights: uniform, scans: %(scans)s}
flag: {strategy: %(strategy)s}
calibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: m000
  uvrange: ">150"%(extra)s
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
run: {stages: [calibrate]}
"""


def main(run):
    run = Path(run)
    with core_ms.open_table(A1) as t:
        scans = sorted({int(s) for s in t.getcol("SCAN_NUMBER")})[:-1]
    out = {"ms": str(A1), "scans": scans, "arms": {}}
    for arm, extra in (("off", ""), ("on", "\n  average_time: true")):
        d = run / f"a1-{arm}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        shutil.copy(run / STRATEGY, d / STRATEGY)
        ms = d / "a1-small.ms"
        shutil.copytree(A1, ms)
        (d / "config.yaml").write_text(
            CONFIG % {"scans": json.dumps(scans), "strategy": STRATEGY, "extra": extra},
            encoding="utf-8",
        )
        rc, wall = C.rang_core("run", d / "config.yaml", ms, log=d / "rang-core.log")
        out["arms"][arm] = {"exit": rc, "wall_s": round(wall, 1)}
        if rc:
            C.write(run / "a1.json", out)
            raise SystemExit(f"arm {arm} exit {rc}")
    cal = {
        a: run / f"a1-{a}" / "a1-small.ms.rang-run" / "calibrate" for a in ("off", "on")
    }
    t = {a: {n: C.table(cal[a] / n) for n in ("K", "G", "B", "Gsec", "F")} for a in cal}
    terms = {}
    for name, kind in (("K", "delay"), ("G", "complex"), ("B", "complex"),
                       ("Gsec", "complex"), ("F", "complex")):  # fmt: skip
        terms[name] = C.term_diff(t["on"][name], t["off"][name], kind)
    out["terms_on_vs_off"] = terms
    ms = run / "a1-off" / "a1-small.ms"
    fcal = C.field_id(ms, "J1939-6342")
    gcal = C.field_id(ms, "SIM-GCAL")
    pooled = [cal_apply.POOLED] * 3
    comp = {}
    a, fa = C.composite(ms, fcal, [t["on"][n] for n in ("K", "G", "B")], pooled)
    b, fb = C.composite(ms, fcal, [t["off"][n] for n in ("K", "G", "B")], pooled)
    comp["fcal_KGB"] = C.rel_stats(a, fa, b, fb)
    fields = [cal_apply.POOLED, gcal, cal_apply.POOLED]
    a, fa = C.composite(ms, gcal, [t["on"][n] for n in ("K", "F", "B")], fields)
    b, fb = C.composite(ms, gcal, [t["off"][n] for n in ("K", "F", "B")], fields)
    comp["gcal_KFB"] = C.rel_stats(a, fa, b, fb)
    out["composites_on_vs_off"] = comp
    for arm, cdir in cal.items():
        s = json.loads((cdir / "summary.json").read_text(encoding="utf-8"))
        f = next(x for x in s["steps"] if x["type"] == "F")["fluxscale"]
        out["arms"][arm]["fluxscale"] = f
        out["arms"][arm]["solutions"] = {
            x["name"]: x.get("solutions") for x in s["steps"] if x.get("solutions")
        }
    C.write(run / "a1.json", out)
    print(json.dumps({"terms": terms, "composites": comp}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
