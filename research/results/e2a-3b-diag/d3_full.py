"""D3 of research/e2a-3b-diag.md (post hoc, section 11): the fix at full scale
on E2-A's primary. B1 re-solved by this branch on a field-0 copy of `e2a.ms`
(all antennas, FLAG after rang's calibrate), with E2-A's archived K1 and G1
pre-applied, `average_time` on, `model_divided` off and on; scored against
E2-A's archived rang and CASA tables.

    python d3_full.py build D      CASA deep copy of field 0, FLAG from rang_apply_20261115T144017Z
    python d3_full.py solve D      B1 off and on -> D/B1-off, D/B1-on
    python d3_full.py score D      -> D/d3.json

The model is rang's SR2016 MODEL_DATA of the D1 subset (`rang-tt.ms`), which
is the same in every row (real, XX = YY, cross hands 0), broadcast to every row.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d1_run as R

RUN = Path(r"D:\rang\outputs\e2a-20261115")
SUBSET = Path(r"D:\rang\outputs\e2a-3b-diag-20261117\d1\rang-tt.ms")
AFTER = "flags.rang_apply_20261115T144017Z"


def build(d):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    if (d / "fcal.ms").exists():
        raise SystemExit("fcal.ms exists")
    ants = ",".join(str(a) for a in range(61))
    rc, _ = R.docker(d, f"/opt/casa/bin/python -I /s/d1_casa.py base /src/e2a.ms /d1/fcal.ms "
                     f"/d1/fcal-base.json {ants}", "fcal-base", 4, src_ro=True)  # fmt: skip
    if rc:
        return rc
    calls = [
        {"task": "putflags", "args": {"vis": "/d1/fcal.ms", "rows": "/d1/fcal-base.json",
         "version": f"/src/e2a.ms.flagversions/{AFTER}"}},
        {"task": "flaghash", "args": {"vis": "/d1/fcal.ms"}},
    ]  # fmt: skip
    return R.tasks(d, "fcal-flags", calls, 4, src_ro=True)


def model_row():
    from rang import core_ms

    with core_ms.open_table(SUBSET) as t:
        m = np.asarray(t.getcol("MODEL_DATA", 0, 1))[0]
    return m


def solve(d):
    from rang import cal_bandpass, core_chunks
    from rang.formats import caltable

    d = Path(d)
    ms = d / "fcal.ms"
    m0 = model_row()

    def model(pos):
        return np.broadcast_to(m0[None], (len(pos), *m0.shape))

    rk = RUN / "rang-run" / "calibrate"
    tables = [caltable.read(rk / "K1"), caltable.read(rk / "G1")]
    budget = core_chunks.ChainBudget(chunk_bytes=int(6e9))
    kw = {"field_id": 0, "refant": ["m022", "m023", "m024"], "refantmode": "flex",
          "solint": "inf", "combine": "scan", "minsnr": 3.0, "minblperant": 4,
          "fillgaps": 70, "uvrange": ">150", "gaintable": tables,
          "interp": ["linear", "linear"], "weight_column": None, "model": model,
          "budget": budget, "average_time": True}  # fmt: skip
    secs = {}
    for div in (False, True):
        t0 = time.perf_counter()
        table = cal_bandpass.bandpass(ms, model_divided=div, **kw)[0]
        caltable.write(table, d / ("B1-on" if div else "B1-off"))
        secs["on" if div else "off"] = time.perf_counter() - t0
    (d / "d3-solve.json").write_text(json.dumps(secs, indent=1) + "\n")
    print(secs)
    return 0


def score(d):
    import d1_score as S

    C = S.C
    d = Path(d)
    ms = d / "fcal.ms"
    fid = C.field_id(ms, S.FCAL)
    r = {n: C.table(RUN / "rang-run" / "calibrate" / n) for n in ("K1", "G1", "B1")}
    c = [C.table(RUN / "casa" / "tables" / n) for n in ("K1", "G1", "B1")]
    off, on = C.table(d / "B1-off"), C.table(d / "B1-on")
    out = {
        "control: off vs archived rang B1 (rang K1, G1)": S.composite_rel(
            ms, fid, [r["K1"], r["G1"], off], [r["K1"], r["G1"], r["B1"]]
        ),
        "archived rang vs CASA (the booked 3b, on the copy)": S.composite_rel(
            ms, fid, [r["K1"], r["G1"], r["B1"]], c
        ),
        "on (the fix) vs CASA": S.composite_rel(ms, fid, [r["K1"], r["G1"], on], c),
        "on vs off": S.composite_rel(ms, fid, [r["K1"], r["G1"], on], [r["K1"], r["G1"], off]),
        "B1 on vs CASA B1 (term)": {
            k: v for k, v in C.term_diff(on, c[2], "complex").items() if k != "rows"
        },
        "B1 archived vs CASA B1 (term)": {
            k: v for k, v in C.term_diff(r["B1"], c[2], "complex").items() if k != "rows"
        },
    }
    C.write(d / "d3.json", out)
    print(json.dumps({k: [v.get("median"), v.get("p95"), v.get("class_b")] for k, v in out.items()
                      if "median" in v}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    step, d = sys.argv[1:3]
    sys.exit({"build": build, "solve": solve, "score": score}[step](d))
