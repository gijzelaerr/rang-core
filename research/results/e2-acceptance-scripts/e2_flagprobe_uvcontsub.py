"""E2 flag probe: the uvcontsub_flagger steps on the probed baseline, cycle by
cycle, with Tricolour's smooth fit (complex64 pocketfft round trip) and with
rang's (the truncated series as an exact DFT in float64, rounded to
complex64; core/src/sumthreshold.rs `lowpass_fit`). Runs inside
rang-tricolour:0.2.1-e1 (NumPy 2.0.2, Tricolour's own):

    python e2_flagprobe_uvcontsub.py TRI.npz RANG.npz STRATEGY.yaml OUT.json

TRI.npz and RANG.npz are e2_flagprobe_tricolour.py / e2_flagprobe_rang.py
outputs (`vis` from TRI; the intensity is bit-identical in both). For each
uvcontsub step it starts from the flags before that step, checks that the
instrumented copy with `fit="pocketfft"` reproduces tricolour.flagging's
function, and reports, per cycle, the MAD threshold and every cell whose
flag differs between the two fits with its relative margin
|residual / threshold - 1|.
"""

import json
import sys

import numpy as np
import yaml
from tricolour.flagging import uvcontsub_flagger


def fit(avgvis, lb, how):
    if how == "pocketfft":
        f = np.fft.fft(avgvis, axis=0)
        f[np.arange(lb, f.shape[0])] = 0
        return np.fft.ifft(f)
    n = avgvis.shape[0]
    x = avgvis.astype(np.complex128)
    k = np.arange(min(lb, n))
    m = np.arange(n)
    spec = np.exp(-2j * np.pi * np.outer(k, m) / n) @ x
    out = np.exp(2j * np.pi * np.outer(m, k) / n) @ spec / n
    return out.astype(np.complex64)


def run(
    vis, flags, major_cycles, or_original_from_cycle, taylor_degrees, sigma, how, log
):
    """tricolour.flagging.uvcontsub_flagger for one plane, instrumented."""
    result = flags.copy()
    for mi in range(major_cycles):
        if result.sum() == result.size:
            continue
        scratch = vis.copy()
        scratch[result] = np.nan
        avgvis = np.nanmean(scratch, axis=0)
        avgvis[np.isnan(avgvis)] = 0.0
        smooth = fit(avgvis, taylor_degrees, how)
        absres = np.abs(vis - smooth[None, :]).real
        fr = absres.copy()
        fr[result] = np.nan
        diff = np.abs(np.abs(fr) - np.nanmedian(np.abs(fr)))
        mad = np.nanmedian(np.abs(diff))
        thr = sigma * mad
        new = absres > thr
        log.append(
            {
                "cycle": mi,
                "absres": absres,
                "thr": thr,
                "new": new,
                "dtype": str(absres.dtype),
                "thr_dtype": str(np.asarray(thr).dtype),
            }
        )
        result = (result | new) if mi >= or_original_from_cycle else new
    return result


def main():
    tri, rang, strategy, out = sys.argv[1:5]
    t, r = np.load(tri), np.load(rang)
    vis = t["vis"]
    with open(strategy) as fh:
        steps = yaml.safe_load(fh)["strategies"]
    report = []
    for i, s in enumerate(steps):
        if s["task"] != "uvcontsub_flagger":
            continue
        kw = s["kwargs"]
        entry = {"step": i, "kwargs": kw}
        for src_name, src in (("tricolour", t), ("rang", r)):
            before = src["stages"][i - 1].astype(bool)
            real = uvcontsub_flagger(
                vis[None, None].copy(), before[None, None].copy(), **kw
            )[0, 0]
            logs = {}
            res = {}
            for how in ("pocketfft", "dft64"):
                logs[how] = []
                res[how] = run(
                    vis,
                    before,
                    kw["major_cycles"],
                    kw["or_original_from_cycle"],
                    kw["taylor_degrees"],
                    kw["sigma"],
                    how,
                    logs[how],
                )
            cycles = []
            for a, b in zip(logs["pocketfft"], logs["dft64"]):
                d = np.argwhere(a["new"] != b["new"])
                rel_a = np.abs(a["absres"] / a["thr"] - 1)
                cycles.append(
                    {
                        "cycle": a["cycle"],
                        "thr_pocketfft": float(a["thr"]),
                        "thr_dft64": float(b["thr"]),
                        "thr_rel_diff": float(abs(b["thr"] / a["thr"] - 1)),
                        "absres_max_rel_diff": float(
                            np.nanmax(np.abs(b["absres"] / a["absres"] - 1))
                        ),
                        "min_margin_pocketfft": float(np.nanmin(rel_a)),
                        "cells_new_differ": [
                            {
                                "time": int(x),
                                "chan": int(y),
                                "absres_pocketfft": float(a["absres"][x, y]),
                                "absres_dft64": float(b["absres"][x, y]),
                                "thr_pocketfft": float(a["thr"]),
                                "thr_dft64": float(b["thr"]),
                                "margin_pocketfft": float(
                                    a["absres"][x, y] / a["thr"] - 1
                                ),
                                "margin_dft64": float(b["absres"][x, y] / b["thr"] - 1),
                                "pocketfft": bool(a["new"][x, y]),
                                "dft64": bool(b["new"][x, y]),
                            }
                            for x, y in d[:20]
                        ],
                        "n_new_differ": len(d),
                    }
                )
            entry[f"from_{src_name}_flags"] = {
                "dtype": logs["pocketfft"][0]["dtype"],
                "thr_dtype": logs["pocketfft"][0]["thr_dtype"],
                "real_vs_pocketfft_copy": int((real != res["pocketfft"]).sum()),
                "flagged_real": int(real.sum()),
                "flagged_pocketfft": int(res["pocketfft"].sum()),
                "flagged_dft64": int(res["dft64"].sum()),
                "pocketfft_vs_tricolour_stage": int(
                    (res["pocketfft"] != t["stages"][i]).sum()
                ),
                "dft64_vs_rang_stage": int((res["dft64"] != r["stages"][i]).sum()),
                "dft64_vs_tricolour_stage": int((res["dft64"] != t["stages"][i]).sum()),
                "pocketfft_vs_rang_stage": int(
                    (res["pocketfft"] != r["stages"][i]).sum()
                ),
                "cycles": cycles,
            }
        report.append(entry)
    print(json.dumps(report, indent=1)[:6000])
    with open(out, "w") as fh:
        json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
