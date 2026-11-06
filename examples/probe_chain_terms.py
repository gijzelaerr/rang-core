"""Task C2c (research/c2c-bandpass.md), post hoc after run -18 (the chain).
Hypotheses, written here before this probe ran:

1. The per-term G and B differences against CASA are K's difference passed
   on: B absorbs the residual linear phase of K across the band and G its
   phase at the band centre, so the partial composites `K G` and `K B` agree
   with CASA's much better than G and B alone.
2. The twins' composite misses the truth by up to 0.017 only because G is
   applied with `linear` time interpolation between per-scan solutions while
   A1's G steps from scan to scan; with `nearest` for G (and K) the composite
   meets the 1e-5 gate.

Rang only (CASA's tables are run -18's); nothing is gated.

    python examples/probe_chain_terms.py <run> <run-18>
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_bandpass as cb
import check_gain as cg
from rang import cal_apply
from rang.formats import caltable


def composite(msp, fid, tables, interp):
    c = cg.columns(msp, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "FLAG"])
    rows = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"])
    nchan = c["FLAG"].shape[1]
    ones = np.zeros((rows.sum(), nchan, 4), np.complex64)
    ones[..., 0] = ones[..., 3] = 1
    v, f = cal_apply.apply(ones, np.zeros(ones.shape, bool), c["TIME"][rows],
                           c["ANTENNA1"][rows], c["ANTENNA2"][rows], cg.chan_freq(msp),
                           tables, interp=interp, field_id=fid, direction="corrupt")  # fmt: skip
    return v[..., (0, 3)], f[..., (0, 3)]


def rel(a, fa, b, fb):
    ok = ~fa & ~fb
    r = (np.abs(a - b) / np.abs(b))[ok]
    return {"median_rel": float(np.median(r)), "p95_rel": float(np.percentile(r, 95)),
            "max_rel": float(r.max())}  # fmt: skip


def main(argv):
    run, r18 = Path(argv[1]), Path(argv[2])
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    p = cb.paths(argv)
    out = {"terms": {}, "twins": {}}
    for case in cb.CHAIN_CASES:
        name, ms, fid = case[0], case[1], case[2]
        msp = r18 / "casa" / f"{ms}.ms"
        r = {t: caltable.read(r18 / "casa" / f"{name}.rang.{t}") for t in "KGB"}
        c = {t: caltable.read(r18 / "casa" / f"{name}.{t}") for t in "KGB"}
        res = {}
        for label, terms in (
            ("G", "G"),
            ("B", "B"),
            ("KG", "KG"),
            ("KB", "KB"),
            ("KGB", "KGB"),
        ):
            a, fa = composite(msp, fid, [r[t] for t in terms], "linear")
            b, fb = composite(msp, fid, [c[t] for t in terms], "linear")
            res[label] = rel(a, fa, b, fb)
        out["terms"][name] = res
        print(name, json.dumps(res), flush=True)
    src = cb.sources(p)
    for key in ("a1twin", "d50twin"):
        ms, _, _, ktab, btab, gtab = src[key]
        case = (f"T-C-{key}-f0", key, 0, ("inf", "inf", "inf"), "scan", 4, 70, "")
        _, model = cb.truth_ms(p, key, 0)
        rang = cb.rang_chain(ms, case, model=model, **cb.TWIN)
        truth = [caltable.read(t) for t in (ktab, gtab, btab)]
        res = {}
        for interp in ("linear", "nearest"):
            a, fa = composite(ms, 0, [rang[t][0] for t in "KGB"], interp)
            b, fb = composite(ms, 0, truth, interp)
            ok = ~fa & ~fb
            res[interp] = {"max_abs": float(np.abs(a - b)[ok].max())}
        out["twins"][key] = res
        print(key, json.dumps(res), flush=True)
    out["seconds"] = time.perf_counter() - started
    cg.write(run / "probe.json", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
