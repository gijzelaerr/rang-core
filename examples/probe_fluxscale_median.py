"""Post-hoc probe of task C2d (research/c2d-fluxscale.md, section 8): which
amplitude and median rules reproduce CASA's `fluxd` exactly?

    python examples/probe_fluxscale_median.py <run> <out.json>

For each P case without edits on a CASA input table of run `<run>`, the
per-(hand, antenna) ratios are recomputed in NumPy from CASA's own table
(unweighted means over time) with three amplitude rules: `hypot` (float32
`|z|`, what rang uses), `sqrt32` (`sqrt(re*re + im*im)` in float32) and
`f64` (`|z|` in float64). For each, CASA's `fluxd` is compared with the
square of the lower middle value, the upper middle value and their mean.
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang.formats import caltable

CASES = {"P-a1": ("a1", 0), "P-a1x4": ("a1x4", 0), "P-full64": ("full64", 0),
         "P-slice2": ("slice2", 1)}  # fmt: skip


def amplitudes(p, rule):
    if rule == "hypot":
        return np.abs(p).astype(np.float32).astype(float)
    re, im = p.real.astype(np.float32), p.imag.astype(np.float32)
    if rule == "sqrt32":
        return np.sqrt(re * re + im * im).astype(np.float32).astype(float)
    if rule in ("fma-re", "fma-im"):
        # fmaf(a, a, b*b): the product a*a is exact in float64, one rounding.
        a, b = (re, im) if rule == "fma-re" else (im, re)
        s = (a.astype(float) ** 2 + (b * b).astype(float)).astype(np.float32)
        return np.sqrt(s).astype(np.float32).astype(float)
    if rule == "sqrt64":
        s = re.astype(float) ** 2 + im.astype(float) ** 2
        return np.sqrt(s).astype(np.float32).astype(float)
    return np.abs(p.astype(np.complex128))


def ratios(t, ref, tran, w, rule):
    amp = amplitudes(t.params[:, 0, :], rule)
    flag = t.flags[:, 0, :]
    f, s, a = (t.column(c) for c in ("FIELD_ID", "SPECTRAL_WINDOW_ID", "ANTENNA1"))
    nant = len(t.subtables["ANTENNA"]["NAME"])

    def means(field):
        m = np.full((nant, 2), np.nan)
        for ant in range(nant):
            for h in range(2):
                sel = (f == field) & (s == w) & (a == ant) & ~flag[:, h]
                if sel.any():
                    acc = 0.0
                    for v in amp[sel, h]:
                        acc += v
                    m[ant, h] = acc / sel.sum()
        return m

    r = means(tran) / means(ref)
    return r[np.isfinite(r)].ravel()


def main(run, out):
    run = Path(run)
    res = json.loads((run / "casa" / "result.json").read_text())
    by = {s["label"]: s for s in res}
    report = {}
    for case, (ds, ref) in CASES.items():
        t = caltable.read(run / "casa" / f"{ds}.Gapp")
        ret = by[f"{case} fluxscale"]["return"]
        for fk in (k for k in ret if k.isdigit()):
            for w in (k for k in ret[fk] if k.isdigit()):
                fd = ret[fk][w]["fluxd"][0]
                if fd <= 0:
                    continue
                entry = {"casa_fd": fd}
                for rule in ("hypot", "sqrt32", "f64", "fma-re", "fma-im", "sqrt64"):
                    r = np.sort(ratios(t, ref, int(fk), int(w), rule))
                    n = len(r)
                    lo, hi = r[(n - 1) // 2], r[n // 2]
                    entry["n"] = n
                    for name, v in (
                        ("lower", lo),
                        ("upper", hi),
                        ("mean", 0.5 * (lo + hi)),
                    ):
                        entry[f"{rule}-{name}"] = abs(v * v / fd - 1)
                report[f"{case} field {fk} spw {w}"] = entry
    Path(out).write_text(json.dumps(report, indent=1) + "\n")
    for k, v in report.items():
        best = sorted((x, y) for y, x in v.items() if "-" in y)[:3]
        print(k, v["n"], [(y, f"{x:.2e}") for x, y in best])


if __name__ == "__main__":
    main(*sys.argv[1:3])
