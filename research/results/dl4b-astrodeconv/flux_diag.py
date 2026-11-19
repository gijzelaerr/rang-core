"""Pilot diagnostic (amendment 2): the flux-test source of seeds 0-9,
flux1000, imaged by run B from (a) all sources noise-free and (b) in-image
sources only noise-free. If (b) is within a few % and (a) is not, the
pilot's flux bias is CLEAN absorbing out-of-field sidelobes, not prediction.

    python research/results/dl4b-astrodeconv/flux_diag.py OUT_JSON [seeds...]
"""

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "examples"))
import astrodeconv_sim as a


def run(seed, f=1000):
    p = a.randomize(seed, f)
    text = a.skymodel_text(seed, p)
    ra0, dec0 = math.radians(a.JOB["ra"]), math.radians(p["dec"])
    a.FIELD_DEC[0] = dec0
    xyz = np.array([q[1:] for q in a.SPIEL_ANTENNAS])
    names = [q[0] for q in a.SPIEL_ANTENNAS]
    nd = math.floor(p["synthesis"] * 3600 / a.JOB["dtime"])
    times, uvw, _ = a.track(xyz, ra0, dec0, nd, a.JOB["dtime"])
    a1, a2 = np.triu_indices(16, 1)
    rows = (uvw[:, a2] - uvw[:, a1]).reshape(-1, 3)
    outside = a.outside_only(text, rows, ra0, dec0)
    full = np.zeros_like(outside)
    full[:, 0, 0] = full[:, 0, 3] = a.predict(text, rows, ra0, dec0)
    inside = full - outside
    sigma = a.JOB["sefd"] / math.sqrt(2 * a.JOB["dtime"] * p["dfreq"])
    work = Path(tempfile.mkdtemp(prefix=f"diag{seed}-", dir="/dev/shm"))
    out = {"seed": seed}
    try:
        ms = work / "d.ms"
        a.write_ms(ms, xyz, names, times, rows, np.tile(a1, nd).astype(np.int32),
                   np.tile(a2, nd).astype(np.int32), {"DATA_ALL": full, "DATA_IN": inside},
                   sigma, a.JOB["freq0"], float(p["dfreq"]))  # fmt: skip
        base = ["-size", "256", "256", "-scale", "1.6asec", "-weight", "uniform",
                "-niter", "100000000", "-auto-threshold", "0.125", "-auto-mask", "5",
                "-temp-dir", str(work), "-no-update-model-required", "-reorder", "-mgain", "0.8"]  # fmt: skip
        hdr = None
        for col in ("DATA_ALL", "DATA_IN"):
            a.wsclean(
                base + ["-data-column", col, "-name", str(work / col), str(ms)],
                work / f"{col}.log",
                work,
            )
            model, hdr = a.read_image(work / f"{col}-model.fits")
            out[col] = model
        _, comps, ins = a.truth_image(text, hdr)
        k = int(np.flatnonzero(ins)[np.argmax(comps[ins, 2])])
        x, y = (int(np.floor(c + 0.5)) for c in comps[k, 4:6])
        res = {"seed": seed, "I": float(comps[k, 2])}
        for col in ("DATA_ALL", "DATA_IN"):
            m = out[col][max(y - 1, 0) : y + 2, max(x - 1, 0) : x + 2].sum()
            res[f"rel_err_{col.lower()}"] = float(m / comps[k, 2] - 1)
        return res
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    seeds = [int(s) for s in sys.argv[2:]] or list(range(10))
    rows = [run(s) for s in seeds]
    for r in rows:
        print(r)
    Path(sys.argv[1]).write_text(json.dumps(rows, indent=1))
