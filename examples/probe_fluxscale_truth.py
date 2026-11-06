"""Post-hoc probe of task C2d (research/c2d-fluxscale.md, section 8): class T
with noise failed against the frozen expected flux `E_k` (one weighted mean
over all of SIM-GCAL's cells). Is the difference the per-antenna effective
spectrum under uneven RFI flags?

    python examples/probe_fluxscale_truth.py <run> <out.json>

For each class T dataset of run `<run>` and window `k`: `E_a,h` is the same
weighted mean of `Re(P_p M P_q^T)` over the cells of antenna `a`'s baselines
and hand `h`; the per-antenna expectation `E_med` is the square of CASA's
median (casacore's rule) of `sqrt(E_a,h)`, as `fluxscale` takes the median
of amplitude ratios. Reported against rang's `fluxd`, with the frozen `E_k`.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_fluxscale as cfx
from check_gain import a1_model
from rang.cal_fluxscale import _extension

DATA = {"a1": ("a1", 1), "a1-twin": ("a1-twin", 1), "a1x4": ("a1", 4),
        "a1x4-twin": ("a1-twin", 4), "h1": ("h1", 1), "hx4": ("h1", 4),
        "hx4-twin": ("h1-twin", 4)}  # fmt: skip


def per_antenna(ms1, truth, nspw):
    rows, values = a1_model(ms1, truth, [cfx.GCAL], parang=True)
    c = cfx.columns(ms1, ["FLAG", "WEIGHT_SPECTRUM", "ANTENNA1", "ANTENNA2"])
    flag, w = c["FLAG"][rows], c["WEIGHT_SPECTRUM"][rows].astype(float)
    a1, a2 = c["ANTENNA1"][rows], c["ANTENNA2"][rows]
    nant = int(max(a1.max(), a2.max())) + 1
    per = values.shape[1] // nspw
    out = []
    for k in range(nspw):
        sl = slice(k * per, (k + 1) * per)
        e = np.full((nant, 2), np.nan)
        for ant in range(nant):
            r = (a1 == ant) | (a2 == ant)
            for i, h in enumerate((0, 3)):
                ok = ~flag[r][:, sl, h]
                ww = w[r][:, sl, h]
                e[ant, i] = np.sum((ww * values[r][:, sl, h].real)[ok]) / np.sum(ww[ok])
        vals = np.sqrt(e.ravel())
        n = len(vals)
        s = np.sort(vals)
        med = (
            0.5 * (s[(n - 1) // 2] + s[n // 2])
            if n % 2 == 0 and n <= 100
            else s[(n - 1) // 2]
        )
        out.append(
            {"E_med": float(med**2), "E_spread": [float(np.min(e)), float(np.max(e))]}
        )
    return out


def main(run, out, argv):
    run = Path(run)
    p = cfx.paths(argv)
    rres = json.loads((run / "rang" / "result.json").read_text())
    report = {}
    for name, rec in rres["chains"].items():
        base = name.replace("-fit2", "")
        if base not in DATA:
            continue
        ms_name, nspw = DATA[base]
        d = cfx.datasets(base.startswith("h"))[base]
        truth = dict(np.load(p[d["truth"]]))
        ms1 = run / "ms" / f"{ms_name}.ms"
        per = per_antenna(ms1, truth, nspw)
        e = rec[str(cfx.GCAL)]
        fd = [float(e[str(k)]["fluxd"][0]) for k in range(nspw)]
        err = [float(e[str(k)]["fluxdErr"][0]) for k in range(nspw)]
        item = {"fd": fd, "E_med": [x["E_med"] for x in per],
                "E_ant_range": [x["E_spread"] for x in per]}  # fmt: skip
        item["fd_rel_E_med"] = [abs(a / b - 1) for a, b in zip(fd, item["E_med"])]
        if nspw > 1:
            order = 2 if name.endswith("-fit2") else 1
            fit = _extension().cal_fluxscale_fit(list(np.asarray(rec["freq"], float)),
                                                 item["E_med"], err, order)  # fmt: skip
            item["fit_flux_rel"] = abs(float(e["fitFluxd"]) / fit["flux"] - 1)
            item["alpha_abs"] = abs(float(np.asarray(e["spidx"])[1]) - fit["coeffs"][1])
        report[name] = item
        print(name, {k: v for k, v in item.items() if k != "E_ant_range"})
    Path(out).write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
