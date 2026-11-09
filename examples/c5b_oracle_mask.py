"""Task C5b, post hoc (research/c5b-selfcal-masks.md, section 5): a truth
(oracle) clean mask for one of C5's cases, to test whether any mask can stop
the model absorbing the gains. Images MODEL_TRUE (the uncorrupted,
noiseless sky) of a copy of the case with Högbom CLEAN and the loop's grid,
then writes the model's nonzero pixels dilated by DILATE pixels as a FITS
mask beside it. Uses nothing the loop produced.

    python examples/c5b_oracle_mask.py RUN CASE
"""

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_c5b as b

DILATE = 3


def main(run, case):
    out = Path(run) / "oracle" / case
    out.mkdir(parents=True, exist_ok=True)
    ms = out / f"{case}.ms"
    if not ms.exists():
        shutil.copytree(b.base_ms(run, case), ms)
    prefix = out / "truth"
    argv = [*b.LOCK, str(b.GEMCLEAN), "-name", str(prefix), "-size", "2048", "2048",
            "-scale", "2asec", "-weight", "briggs", "0.0", "-niter", "1000000",
            "-mgain", "0.9", "-threshold", "0.0001", "-data-column", "MODEL_TRUE",
            "-field", "3", "-no-update-model-required", str(ms)]  # fmt: skip
    with (out / "gemclean.log").open("w", encoding="utf-8") as log:
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True)
    with fits.open(f"{prefix}-model.fits") as h:
        model = np.asarray(h[0].data, float)
        header = h[0].header.copy()
    support = np.abs(model) > 0
    plane = support.reshape(support.shape[-2:])
    mask = ndimage.binary_dilation(plane, iterations=DILATE)
    data = mask.astype(np.float32).reshape(model.shape)
    path = out / "oracle-mask.fits"
    fits.writeto(path, data, header, overwrite=True)
    print(f"{path}: {int(plane.sum())} model pixels, {int(mask.sum())} in the mask")


if __name__ == "__main__":
    main(*sys.argv[1:3])
