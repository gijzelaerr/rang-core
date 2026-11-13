"""E2-B's 1934-638 leakage row (research/e2-acceptance.md 6.5, 7.1; A0 6.3):
dirty IQUV MFS images of one column of J1939-6342 (scan 18, the field's only
scan) with WSClean 3.7 at gate 3c's settings (2048 x 2", Briggs 0, 8 joined
channels, joined polarisations, wgridder 1e-4, MS weights), then per Stokes
Q, U, V the peak |P| within 3 beams of the I peak over that I peak. Gate:
each <= 0.3 %. Images to OUT_DIR/<label>-*.

    python e2_leakage.py MS_DIR MS_NAME COLUMN OUT_DIR LABEL
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

IMAGE = "rang-wsclean-native:3.7"
FIELD = "J1939-6342"


def wsl(path):
    p = str(Path(path).resolve()).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def main(ms_dir, ms_name, column, out_dir, label):
    from astropy.io import fits
    from rang import core_ms

    out = Path(out_dir)
    (out / "tmp").mkdir(parents=True, exist_ok=True)
    with core_ms.open_table(Path(ms_dir) / ms_name / "FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(
            FIELD
        )  # WSClean -field takes an index
    cmd = (f"wsclean -name /o/{label} -size 2048 2048 -scale 2asec -weight briggs 0.0 "
           "-make-psf -channels-out 8 -join-channels -pol IQUV -join-polarizations "
           f"-data-column {column} -gridder wgridder -wgridder-accuracy 0.0001 -niter 0 "
           f"-no-update-model-required -j 8 -temp-dir /o/tmp -field {fid} /m/{ms_name}")  # fmt: skip
    inner = ("docker run --rm --network none --user $(id -u):$(id -g) --tmpfs /tmp "
             f"-e HOME=/tmp -v '{wsl(ms_dir)}:/m:rw' -v '{wsl(out)}:/o:rw' -w /tmp {IMAGE} "
             f"sh -c '{cmd}'")  # fmt: skip
    with open(out / f"{label}-wsclean.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(["wsl", "-e", "bash", "-lc", inner], stdout=fh,
                            stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
    rec = {
        "label": label,
        "column": column,
        "field_id": fid,
        "wsclean_exit": rc,
        "command": cmd,
    }
    if rc == 0:
        img = {p: np.asarray(fits.getdata(out / f"{label}-MFS-{p}-image.fits"), float).squeeze()
               for p in "IQUV"}  # fmt: skip
        h = fits.getheader(out / f"{label}-MFS-I-image.fits")
        assert str(h.get("OBJECT")) == FIELD, h.get("OBJECT")
        psf = out / f"{label}-MFS-psf.fits"  # WSClean names one PSF per channel group
        hp = fits.getheader(psf if psf.exists() else out / f"{label}-MFS-I-psf.fits")
        bmaj = max(float(h["BMAJ"]), float(hp.get("BMAJ", 0.0))) / abs(h["CDELT2"])
        assert bmaj > 0, "no beam in the image or PSF header"
        py, px = np.unravel_index(int(np.argmax(img["I"])), img["I"].shape)
        yy, xx = np.mgrid[: img["I"].shape[0], : img["I"].shape[1]]
        near = np.hypot(xx - px, yy - py) <= 3 * bmaj
        peak = float(img["I"][py, px])
        rec.update(i_peak_jy=peak, i_peak_pix=[int(px), int(py)], beam_major_pix=bmaj)
        for p in "QUV":
            v = float(np.max(np.abs(img[p][near])))
            rec[f"{p}_over_I"] = v / peak
            rec[f"{p}_at_peak_over_I"] = float(img[p][py, px]) / peak
        rec["met"] = all(rec[f"{p}_over_I"] <= 0.003 for p in "QUV")
        rec["max_over_I"] = max(rec[f"{p}_over_I"] for p in "QUV")
        assert math.isfinite(rec["max_over_I"])
    (out / f"{label}.json").write_text(
        json.dumps(rec, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(rec, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
