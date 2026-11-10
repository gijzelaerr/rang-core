"""compare.py SCORES.json OUT.json : the class B bounds of research/g7-defaults.md, section 4.

From g7_score.py's output (exact Q, inner peak, model flux; LABEL-exact-residual.npy beside it)
and the models: the common-beam restored image (exact residual + model convolved with GD's
fitted beam, from GD's image header) of each arm against GD's, on the inner field (central 2N/3);
sigma = 1.4826 x MAD of GD's exact inner residual. Bounds: rms of the difference <= 0.1 sigma,
largest <= 3 mJy, |dQ/Q| <= 1e-3, inner peak change <= 0.3 mJy, |dS/S| <= 1e-3. The oracle pairs
GD - WN and GC - WM are reported with the same measures.
"""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
from identity_check import kernel

RUNS = Path("D:/rang/outputs/g7-20261109-01/runs")
MODEL = {"WN": "WN-j16-r1/w", "WM": "WM-j16-r1/w"}


def model_path(label):
    return RUNS / (MODEL.get(label, f"{label}-j16-r1/g") + "-model.fits")


def inner(a):
    n = a.shape[0]
    lo, hi = n // 2 - n // 3, n // 2 + n // 3
    return a[lo:hi, lo:hi]


def main():
    scores = Path(sys.argv[1])
    sc = json.loads(scores.read_text())
    h = fits.getheader(RUNS / "GD-j16-r1" / "g-image.fits")
    n = sc["size"]
    k = kernel(n, h, abs(h["CDELT1"]))
    restored = {}
    for label in sc["models"]:
        m = np.squeeze(fits.getdata(model_path(label))).astype(np.float64)
        r = np.load(scores.parent / f"{label}-exact-residual.npy").astype(np.float64)
        restored[label] = inner(r + fftconvolve(m, k, mode="same"))
    gd = sc["models"]["GD"]
    sigma = gd["inner_mad_sigma"]
    out = {
        "sigma_jy": sigma,
        "beam_asec_deg": [h["BMAJ"] * 3600, h["BMIN"] * 3600, h["BPA"]],
        "pairs": {},
    }

    def pair(a, b):
        d = restored[a] - restored[b]
        A, B = sc["models"][a], sc["models"][b]
        row = {
            "restored_rms_over_sigma": float(np.sqrt(np.mean(d**2)) / sigma),
            "restored_largest_jy": float(np.abs(d).max()),
            "dq_over_q": (A["q"] - B["q"]) / B["q"],
            "inner_peak_change_jy": A["inner_peak"] - B["inner_peak"],
            "flux_change_rel": (A["model_flux"] - B["model_flux"]) / B["model_flux"],
        }
        row["class_b_pass"] = (
            row["restored_rms_over_sigma"] <= 0.1
            and row["restored_largest_jy"] <= 3e-3
            and abs(row["dq_over_q"]) <= 1e-3
            and abs(row["inner_peak_change_jy"]) <= 3e-4
            and abs(row["flux_change_rel"]) <= 1e-3
        )
        return row

    print(f"sigma {sigma * 1e3:.4f} mJy")
    print(
        "| pair | restored rms / σ | largest, mJy | ΔQ/Q | Δ inner peak, mJy | ΔS/S | class B |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for a, b in [(x, "GD") for x in sc["models"] if x != "GD"] + [
        ("GD", "WN"),
        ("GC", "WM"),
        ("GC", "WN"),
    ]:
        if a not in restored or b not in restored:
            continue
        row = pair(a, b)
        out["pairs"][f"{a}-{b}"] = row
        print(
            f"| {a} − {b} | {row['restored_rms_over_sigma']:.4f} | {1e3 * row['restored_largest_jy']:.3f} "
            f"| {row['dq_over_q']:.2e} | {1e3 * row['inner_peak_change_jy']:+.3f} | {row['flux_change_rel']:.2e} "
            f"| {'pass' if row['class_b_pass'] else 'FAIL'} |"
        )
    print()
    print(
        "| arm | Q/Q0 | inner rms, mJy | inner MAD σ, mJy | inner peak, mJy | model flux, Jy | negative, Jy | pixels |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for label, m in sc["models"].items():
        print(
            f"| {label} | {m['q_over_q0']:.6e} | {1e3 * m['inner_rms']:.4f} | {1e3 * m['inner_mad_sigma']:.4f} "
            f"| {1e3 * m['inner_peak']:.3f} | {m['model_flux']:.4f} | {m['model_negative']:.4f} | {m['components']} |"
        )
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
