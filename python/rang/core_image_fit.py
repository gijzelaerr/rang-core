"""Pinned WSClean dirty-image evaluation of frozen MeerKAT gain controls.

Verbatim extract of the frozen `rangtoy.flagging_imaging` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_imaging.py at commit
2da566c (now history/python/flagging_imaging.py),
sha256 a57560ebe771e55bf1d224bda5f5d64722f715ed8ab81c1285b44020e8c86488.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np

SETTINGS = {
    "size": [512, 512],
    "scale_arcsec": 8.0,
    "robust": 0.5,
    "polarization": "I",
    "channels": [1024, 3072],
    "gridder": "wstacking",
    "w_layers": 64,
    "threads": 1,
    "niter": 0,
    "small_inversion": False,
    "update_model_required": False,
    "memory_gib": 0.5,
}


IMAGE_CLOSURE_JY = 1e-6


def linear_image_fit(image, templates):
    """Joint unrestricted known-family dirty-template coefficients; no CI."""
    image, templates = np.asarray(image, float), np.asarray(templates, float)
    if (
        image.ndim != 2
        or templates.shape != (2, *image.shape)
        or not np.isfinite(image).all()
        or not np.isfinite(templates).all()
    ):
        raise ValueError("finite image and two matched dirty templates required")
    design, target = templates.reshape(2, -1).T, image.ravel()
    coefficients, _, rank, singular = np.linalg.lstsq(design, target, rcond=1e-10)
    condition = (
        float(singular[0] / singular[-1])
        if singular.size == 2 and singular[-1] > 0
        else None
    )
    available = rank == 2 and condition is not None and condition <= 1e8
    return {
        "available": bool(available),
        "rank": int(rank),
        "condition": condition,
        "coefficients_jy": coefficients.tolist() if available else None,
        "unweighted_pixel_MSE_proxy": float(
            np.mean((target - design @ coefficients) ** 2)
        ),
        "pixel_count": int(image.size),
        "confidence_intervals": "not claimed: correlated dirty pixels, shared DATA/gains, known family",
        "blind_flux_or_morphology_recovery": False,
    }


def image_diagnostics(image):
    """Fixed regions; dirty offsource RMS includes sidelobes, not thermal noise."""
    image = np.asarray(image, float)
    if image.shape != tuple(SETTINGS["size"]) or not np.isfinite(image).all():
        raise ValueError("finite frozen512x512 image required")
    y, x = np.indices(image.shape)
    l, m = (256 - x) * 8 / 60, (y - 256) * 8 / 60
    region = (
        (np.hypot(l, m) >= 25)
        & (np.hypot(l - 9, m + 6) >= 12)
        & (np.hypot(l + 12, m + 14) >= 12)
    )
    values = image[region]
    return {
        "fixed_offsource_pixels": int(region.sum()),
        "dirty_offsource_RMS_jy_per_beam": float(np.sqrt(np.mean(values**2))),
        "dirty_offsource_std_jy_per_beam": float(np.std(values)),
        "peak_abs_jy_per_beam": float(np.max(np.abs(image))),
        "RMS_role": "fixed-region dirty diagnostic; includes PSF sidelobes/real sky, not independent thermal noise",
    }


def image_geometry(header):
    """Require frozen pixel scale/axes and expose exact matched FITS WCS."""
    keys = (
        "CRPIX1",
        "CRPIX2",
        "CRVAL1",
        "CRVAL2",
        "CDELT1",
        "CDELT2",
        "CTYPE1",
        "CTYPE2",
    )
    if any(key not in header for key in keys):
        raise RuntimeError("missing image WCS geometry")
    if (
        not np.isclose(header["CDELT1"], -8 / 3600, rtol=0, atol=1e-12)
        or not np.isclose(header["CDELT2"], 8 / 3600, rtol=0, atol=1e-12)
        or header["CTYPE1"] != "RA---SIN"
        or header["CTYPE2"] != "DEC--SIN"
        or not np.isfinite([header[key] for key in keys[:6]]).all()
    ):
        raise RuntimeError("image violates frozen scale/axes")
    return {key: header[key] for key in keys}


def _read_images(prefix):
    from astropy.io import fits

    images, headers = {}, {}
    for kind in ("dirty", "psf"):
        with fits.open(f"{prefix}-{kind}.fits", memmap=False) as hdus:
            value = np.asarray(hdus[0].data, float).squeeze()
            header = hdus[0].header
            if value.shape != (512, 512) or not np.isfinite(value).all():
                raise RuntimeError("invalid/frozen-image shape or support")
            if "WSCDATAC" in header and header["WSCDATAC"] != "CORRECTED_DATA":
                raise RuntimeError("WSClean read unexpected DATA column")
            image_geometry(header)
            if kind == "dirty" and str(header.get("BUNIT", "")).lower() != "jy/beam":
                raise RuntimeError("dirty image unit must be Jy/beam")
            images[kind] = value
            headers[kind] = {
                key: header[key]
                for key in (
                    "BITPIX",
                    "BUNIT",
                    "CRPIX1",
                    "CRPIX2",
                    "CRVAL1",
                    "CRVAL2",
                    "CDELT1",
                    "CDELT2",
                    "CTYPE1",
                    "CTYPE2",
                    "BMAJ",
                    "BMIN",
                    "BPA",
                    "WSCVERSI",
                    "WSCNWLAY",
                    "WSCDATAC",
                    "WSCWEIGH",
                    "WSCNITER",
                    "WSCVWSUM",
                    "WSCNVIS",
                )
                if key in header
            }
    return images, headers
