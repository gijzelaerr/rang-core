"""D2 of research/e2a-3b-diag.md (post hoc, section 8): B1 alone on the D1
subset with this branch's `rang.cal_bandpass.bandpass`, T-T's K1 and G1
pre-applied (linear), with and without `average_time` and `model_divided`.
The KGB1 composites use T-T's K1 and G1 with each B1.

    python d2_divided.py D     -> D/d2-divided.json
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d1_score as S

from rang import cal_bandpass

C = S.C


def main(d):
    d = Path(d)
    ms = d / "rang-tt.ms"  # FLAG after T-T's calibrate, rang's MODEL_DATA
    fid = C.field_id(ms, S.FCAL)
    tt = S.load(d, "tt")
    tk2 = S.load(d, "tk2")
    kw = dict(field_id=fid, refant=["m022", "m023", "m024"], refantmode="flex", solint="inf",
              combine="scan", minsnr=3.0, minblperant=4, fillgaps=70, uvrange=">150",
              gaintable=[tt["K1"], tt["G1"]], interp=["linear", "linear"],
              weight_column=None)  # fmt: skip
    b, secs = {}, {}
    for avg in (False, True):
        for div in (False, True):
            t0 = time.perf_counter()
            b[(avg, div)] = cal_bandpass.bandpass(ms, average_time=avg, model_divided=div, **kw)[0]
            secs[f"avg={avg} div={div}"] = time.perf_counter() - t0
    K, G = tt["K1"], tt["G1"]
    out = {"seconds": secs, "composites": {}, "terms": {}}

    def comp(label, b1, ref):
        out["composites"][label] = S.composite_rel(ms, fid, [K, G, b1], ref)

    comp("unavg_undivided vs T-T (control: this branch = frozen wheel)", b[(False, False)],
         [K, G, tt["B1"]])  # fmt: skip
    comp("avg_undivided vs unavg_undivided (the frozen averaging)", b[(True, False)],
         [K, G, b[(False, False)]])  # fmt: skip
    comp("avg_divided vs unavg_undivided (the fix)", b[(True, True)], [K, G, b[(False, False)]])
    comp("unavg_divided vs unavg_undivided", b[(False, True)], [K, G, b[(False, False)]])
    tk2_set = [tk2["K1"], tk2["G1"], tk2["B1"]]
    for (avg, div), bb in b.items():
        out["composites"][f"avg={avg} div={div} vs T-K2 (CASA, rang's K)"] = S.composite_rel(
            ms, fid, [K, G, bb], tk2_set
        )
        out["terms"][f"avg={avg} div={div} B1 vs T-T B1"] = {
            k: v for k, v in C.term_diff(bb, tt["B1"], "complex").items() if k != "rows"
        }
    C.write(d / "d2-divided.json", out)
    print(json.dumps({k: [v["median"], v["p95"], v["class_b"]] for k, v in out["composites"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
