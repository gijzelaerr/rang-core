"""identity_check.py OUT.json : gate A of research/g7-defaults.md, section 2.

Compares identity/beam against identity/refkeep (both with the FITS files kept), file by file:
the sha256 of every file of `refkeep` equals that of `ref` (the same binary, rerun); every file
but `*image.fits` has a byte-identical data unit and a header identical except BMAJ, BMIN and BPA,
which every GeMClean file carries (amendment, post hoc: section 2 said "byte-identical files");
each image equals residual + model convolved with the new beam (BMAJ, BMIN, BPA of its own
header, unit peak, linear convolution) to 1e-6 of its peak.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy.signal import fftconvolve

O = Path("D:/rang/outputs/g7-20261109-01/identity")


def hashes(tag, name):
    p = O / tag / "img" / f"{name}.sha256"
    out = {}
    for ln in p.read_text().splitlines():
        h, f = ln.split()
        out[f] = h
    return out


def kernel(n, h, scale):
    major = h["BMAJ"] / scale
    minor = h["BMIN"] / scale
    pa = math.radians(h["BPA"])
    ax = np.arange(-(n - 1), n)
    yy, xx = np.meshgrid(ax, ax, indexing="ij")  # array [Y, X]
    # PA from +Y (north) towards -X (east): major axis direction (-sin PA, cos PA) in (X, Y).
    dmaj = -math.sin(pa) * xx + math.cos(pa) * yy
    dmin = math.cos(pa) * xx + math.sin(pa) * yy
    return np.exp(-4.0 * math.log(2.0) * (dmaj**2 / major**2 + dmin**2 / minor**2))


def check_image(img_path):
    stem = str(img_path)[: -len("image.fits")]
    with fits.open(img_path) as f:
        h = f[0].header
        image = np.squeeze(f[0].data).astype(np.float64)
    model = np.squeeze(fits.getdata(stem + "model.fits")).astype(np.float64)
    residual = np.squeeze(fits.getdata(stem + "residual.fits")).astype(np.float64)
    n = image.shape[0]
    k = kernel(n, h, abs(h["CDELT1"]))
    smooth = fftconvolve(model, k, mode="same")
    diff = np.abs(residual + smooth - image).max() / np.abs(image).max()
    return float(diff), [h["BMAJ"] * 3600, h["BMIN"] * 3600, float(h["BPA"])]


BEAM_CARDS = {"BMAJ", "BMIN", "BPA"}


def same_but_beam(fa, fb):
    """Data units byte-identical, headers equal but for the beam cards."""
    with fits.open(fa) as a, fits.open(fb) as b:
        if len(a) != len(b):
            return False
        for ha, hb in zip(a, b):
            if ha.data is None or hb.data is None:
                if (ha.data is None) != (hb.data is None):
                    return False
            elif ha.data.tobytes() != hb.data.tobytes():
                return False
            ka = [(k, v) for k, v in ha.header.items() if k not in BEAM_CARDS]
            kb = [(k, v) for k, v in hb.header.items() if k not in BEAM_CARDS]
            if ka != kb:
                return False
    return True


def main():
    out = sys.argv[1]
    names = sorted(p.stem for p in (O / "ref" / "img").glob("*.sha256"))
    res = {}
    ok = True
    for name in names:
        r, a, b = hashes("ref", name), hashes("refkeep", name), hashes("beam", name)
        rerun_same = r == a
        changed = sorted(f for f in a if a[f] != b.get(f))
        bad = [
            f
            for f in changed
            if not f.endswith("image.fits")
            and not same_but_beam(O / "refkeep" / "img" / f, O / "beam" / "img" / f)
        ]
        checks = {}
        for f in changed:
            if f.endswith("image.fits"):
                checks[f] = check_image(O / "beam" / "img" / f)
        good = (
            rerun_same
            and not bad
            and set(a) == set(b)
            and all(v[0] <= 1e-6 for v in checks.values())
        )
        ok &= good
        res[name] = {
            "files": len(a), "rerun_identical": rerun_same, "changed": changed,
            "non_image_data_or_header_changed": bad, "restore_check": checks, "pass": good,
        }  # fmt: skip
        worst = max((v[0] for v in checks.values()), default=0.0)
        print(
            f"{name}: {len(a)} files, rerun same {rerun_same}, {len(changed)} changed, {len(bad)} with data or other cards changed, restore residual {worst:.2e} -> {'pass' if good else 'FAIL'}"
        )
    Path(out).write_text(json.dumps({"runs": res, "all_pass": ok}, indent=1) + "\n")
    print("ALL PASS" if ok else "GATE A FAILS")


if __name__ == "__main__":
    main()
