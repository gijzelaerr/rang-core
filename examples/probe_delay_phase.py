"""Task C2b (research/c2b-delay.md), post hoc after run -02: why rang's K
misses CASA's on the slice and on A1 without a pre-apply.

Hypothesis (written before this probe ran): QuartiCal's `delay` model has
no phase offset (zero phase at the band's mid frequency), while CASA's FFT
peak ignores a constant phase. An unmodelled antenna phase then biases the
least-squares delay wherever the weights are not symmetric about mid-band
(flagged channels, RFI). If so, corrupting the model with the antenna phases
(a G table pre-applied) brings rang to CASA's delays; CASA's own delays
change little when the same G is pre-applied.

Host only, no new CASA run: CASA's tables are run -02's.

    python examples/probe_delay_phase.py <run> <run-02>
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_delay as cd
import check_gain as cg
from rang import cal_delay
from rang.formats import caltable


def compare(sol, info, msp, fid, ctab, ref):
    cols = cg.columns(msp, ["TIME", "FIELD_ID"])
    info["row_time"] = cols["TIME"][cols["FIELD_ID"] == fid]
    nant = sol.delays.shape[2]
    ctimes, d, f, _ = cd.k_table(ctab, nant)
    rtimes = np.array([info["row_time"][info["time_bin"] == t].mean()
                       for t in range(sol.delays.shape[0])])  # fmt: skip
    bins, index = cg.match_intervals(ctimes, info, rtimes)
    out = {"intervals": bins}
    if bins["all_matched_once"]:
        out["delays"] = cd.delay_compare(
            sol.delays[index][:, 0], sol.flags[index][:, 0], d, f, ref
        )
    return out


def main(argv):
    run, r02 = Path(argv[1]), Path(argv[2])
    run.mkdir(parents=True, exist_ok=False)
    p = cd.paths(argv)
    started = time.perf_counter()
    out = {}
    # (a) The slice's antenna phases in O-CASA's c.G0.
    g0 = caltable.read(p["slice"].parent / "c.G0")
    ph = np.degrees(np.angle(g0.params[:, 0, :]))
    out["slice_c.G0_phase_deg"] = {
        "min": float(ph.min()),
        "max": float(ph.max()),
        "median_abs": float(np.median(np.abs(ph))),
    }
    # (b) The slice with c.G0 corrupting the model, against run -02's CASA K.
    msp = r02 / "casa" / "slice.ms"
    for solint in ("inf", "120s", "int"):
        ctab = caltable.read(r02 / "casa" / f"B-slice-{solint}.K")
        for label, tabs in (("no-apply", []), ("G-applied", [g0])):
            _, sol, info = cal_delay.gaincal(
                msp, field_id=1, solint=solint, refant="m000", gaintable=tabs
            )
            out[f"slice-{solint}-{label}"] = compare(sol, info, msp, 1, ctab, 0)
    # (c) A1 without B: truth G alone, against CASA's no-apply table; and
    # CASA's no-apply against CASA's B and G applied.
    msa = r02 / "casa" / "a1.ms"
    c_none = caltable.read(r02 / "casa" / "B-a1-noapply-inf-f0.K")
    c_both = caltable.read(r02 / "casa" / "B-a1-inf-f0.K")
    for label, tabs in (("G-only", [caltable.read(p["a1g"])]),):
        _, sol, info = cal_delay.gaincal(
            msa, field_id=0, solint="inf", refant="m000", gaintable=tabs
        )
        out[f"a1-inf-f0-{label}-vs-casa-noapply"] = compare(
            sol, info, msa, 0, c_none, 0
        )
    _, dn, fn, _ = cd.k_table(c_none, 16)
    _, db, fb, _ = cd.k_table(c_both, 16)
    out["casa-noapply-vs-casa-applied"] = cd.delay_compare(dn, fn, db, fb, 0)
    out["seconds"] = time.perf_counter() - started
    cg.write(run / "probe.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
