"""DL4c (#43), research/dl4c-mask.md sections 2-3: the masks of arms P and T.

    python dl4c_mask.py posterior A_DIR OUT.fits OUT.json
    python dl4c_mask.py truth A_DIR TRUTH_MODEL.fits NOISE_JY OUT.fits OUT.json

posterior: pixels where arm A's restored MFS image exceeds 5 x the MAD-sigma
of A's final MFS residual, dilated by one restoring-beam FWHM (BMAJ).
truth: the pixelised truth (the bench scorer's `truth` model, Jy/pixel)
convolved with A's restoring beam (peak 1, so Jy/beam), pixels above
5 x NOISE_JY (the simulator's image noise), dilated by one FWHM.
The mask is written with A's MFS header, 1 inside, 0 outside, float32.
"""

import hashlib
import json
import sys

import numpy as np
from astropy.io import fits
from scipy import ndimage, signal

K = 5.0


def mad_sigma(x):
    x = x[np.isfinite(x)]
    return 1.4826 * float(np.median(np.abs(x - np.median(x))))


def beam(header):
    cell = abs(float(header["CDELT2"]))
    return (
        float(header["BMAJ"]) / cell,
        float(header["BMIN"]) / cell,
        float(header.get("BPA", 0.0)),
    )


def disk(radius):
    r = int(np.ceil(radius))
    y, x = np.mgrid[-r : r + 1, -r : r + 1]
    return x * x + y * y <= radius * radius


def gaussian_kernel(bmaj, bmin, bpa_deg):
    s_maj, s_min = bmaj / 2.3548, bmin / 2.3548
    half = int(np.ceil(4 * s_maj))
    y, x = np.mgrid[-half : half + 1, -half : half + 1].astype(float)
    t = np.radians(bpa_deg)
    # position angle from north (+y) towards east (-x in the image's RA axis)
    u = -x * np.sin(t) + y * np.cos(t)
    v = x * np.cos(t) + y * np.sin(t)
    return np.exp(-0.5 * ((u / s_maj) ** 2 + (v / s_min) ** 2))


def write(out_fits, out_json, header, shape, mask, extra):
    data = mask.astype(np.float32).reshape(shape)
    fits.PrimaryHDU(data=data, header=header).writeto(out_fits, overwrite=True)
    digest = hashlib.sha256(open(out_fits, "rb").read()).hexdigest()
    rec = {"mask": out_fits, "sha256": digest, "pixels": int(mask.sum()),
           "fraction": float(mask.mean()), **extra}
    json.dump(rec, open(out_json, "w"), indent=1)
    print(json.dumps(rec))


def main(argv):
    mode, a_dir = argv[0], argv[1]
    with fits.open(f"{a_dir}/image-MFS-image.fits") as h:
        header, shape = h[0].header.copy(), h[0].data.shape
        image = np.squeeze(h[0].data).astype(float)
    bmaj, bmin, bpa = beam(header)
    if mode == "posterior":
        out_fits, out_json = argv[2], argv[3]
        with fits.open(f"{a_dir}/image-MFS-residual.fits") as h:
            sigma = mad_sigma(np.squeeze(h[0].data).astype(float))
        core = image > K * sigma
        extra = {"mode": mode, "sigma_jy": sigma, "level_jy": K * sigma}
    elif mode == "truth":
        truth_fits, noise, out_fits, out_json = argv[2], float(argv[3]), argv[4], argv[5]
        with fits.open(truth_fits) as h:
            truth = np.squeeze(h[0].data).astype(float)
        smooth = signal.fftconvolve(truth, gaussian_kernel(bmaj, bmin, bpa), mode="same")
        core = smooth > K * noise
        extra = {"mode": mode, "noise_jy": noise, "level_jy": K * noise}
    else:
        raise SystemExit(f"unknown mode {mode}")
    mask = ndimage.binary_dilation(core, structure=disk(bmaj))
    extra.update({"core_pixels": int(core.sum()), "dilation_px": bmaj,
                  "beam_px": [bmaj, bmin, bpa], "a_dir": a_dir})
    write(out_fits, out_json, header, shape, mask, extra)


if __name__ == "__main__":
    main(sys.argv[1:])
