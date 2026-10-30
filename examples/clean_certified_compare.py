"""Compare the certified CLEAN runs with the WSClean 3.7 CLEAN references.

Research note: research/clean-certified-imaging.md. Reads the Rust example's
`clean-certified.json` and `<config>-{model,residual}.npy` (gridder layout,
transposed here to WSClean's FITS order), the WSClean `c-*-{model,residual}.fits`
and logs of `examples/clean_certified_wsclean.sh`, and the export inputs.
Every model, rang's and WSClean's, is also scored through the same exact
measurement (core `dirty2vis`/`vis2dirty`, epsilon 1e-9, w-gridding as
WSClean): `Q = 1/2 sum w |V - A m|^2 / sum w`, the exact residual image and
its rms and peak, so that the comparison does not depend on which imager
produced the residual.

Usage:
    .venv/bin/python examples/clean_certified_compare.py INPUTS RUN WSCLEAN OUT_JSON
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
from rang import core_wgridder
from rang.core_imaging import read_fits

ARCSEC = np.pi / (180.0 * 3600.0)
SIZE = 512
SCALE_ARCSEC = 8.0
CENTRAL = 32
EDGE = 8


class Exact:
    """The measurement of the Rust example, through the Python bindings."""

    def __init__(self, inputs):
        meta = json.loads((inputs / "meta.json").read_text())
        nrow, nchan = meta["nrow"], meta["nchan"]
        self.uvw = np.fromfile(inputs / "uvw.f64").reshape(nrow, 3)
        self.freq = np.fromfile(inputs / "freq.f64")
        self.vis = np.fromfile(inputs / "vis.c128", dtype=np.complex128).reshape(
            nrow, nchan
        )
        wgt = np.fromfile(inputs / "wgt.f64").reshape(nrow, nchan)
        self.wgt = wgt / wgt.sum()
        self.kw = {
            "pixsize_x": SCALE_ARCSEC * ARCSEC,
            "pixsize_y": SCALE_ARCSEC * ARCSEC,
            "epsilon": 1e-9,
            "flip_v": True,
            "flip_w": True,
        }

    def score(self, model_fits_order):
        """Q and the exact residual (FITS order) of a FITS-order model."""
        model = np.ascontiguousarray(model_fits_order.T, np.float64)
        predicted = core_wgridder.dirty2vis(
            uvw=self.uvw, freq=self.freq, dirty=model, **self.kw
        )
        e = self.vis - predicted
        q = 0.5 * float(np.sum(self.wgt * np.abs(e) ** 2))
        residual = core_wgridder.vis2dirty(
            uvw=self.uvw,
            freq=self.freq,
            vis=e,
            wgt=self.wgt,
            npix_x=SIZE,
            npix_y=SIZE,
            **self.kw,
        )
        return q, residual.T


def model_stats(model):
    h = SIZE // 2
    box = model[h - CENTRAL : h + CENTRAL + 1, h - CENTRAL : h + CENTRAL + 1]
    edge = np.ones_like(model, bool)
    edge[EDGE:-EDGE, EDGE:-EDGE] = False
    return {
        "model_pixels_within_8px_of_edge": int(np.count_nonzero(model[edge])),
        "model_flux_within_8px_of_edge": float(model[edge].sum()),
        "model_pixels": int(np.count_nonzero(model)),
        "model_flux_total": float(model.sum()),
        "model_flux_positive": float(model[model > 0].sum()),
        "model_flux_negative": float(model[model < 0].sum()),
        "model_flux_central_65px": float(box.sum()),
        "model_peak": float(model.max()),
        "model_peak_yx": [
            int(i) for i in np.unravel_index(np.argmax(model), model.shape)
        ],
    }


def residual_stats(residual, prefix):
    return {
        f"{prefix}_rms": float(np.sqrt(np.mean(residual**2))),
        f"{prefix}_peak_abs": float(np.abs(residual).max()),
    }


def wsclean_log(path):
    text = path.read_text()
    # The sub-minor loop prints its total; the plain loop only every 10th or
    # 100th iteration, so its count is a lower bound.
    iters = [int(x) for x in re.findall(r"Performed (\d+) iterations in total", text)]
    logged = [int(x) for x in re.findall(r"^Iteration (\d+):", text, re.MULTILINE)]
    majors = re.findall(r"(\d+) major iterations were performed", text)
    return {
        "components": iters[-1] if iters else None,
        "last_logged_iteration": max(logged) if logged else None,
        "major_cycles": int(majors[-1]) if majors else None,
        "diverged": "divergence" in text,
        "divergence_line": next(
            (line.strip() for line in text.splitlines() if "increased to" in line), None
        ),
        "inversion_prediction_deconvolution": next(
            (
                line.strip()
                for line in text.splitlines()
                if line.startswith("Inversion:")
            ),
            None,
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs")
    parser.add_argument("run")
    parser.add_argument("wsclean")
    parser.add_argument("out_json")
    args = parser.parse_args(argv)
    inputs, run, wsc = Path(args.inputs), Path(args.run), Path(args.wsclean)
    exact = Exact(inputs)
    q0, _dirty = exact.score(np.zeros((SIZE, SIZE)))
    result = {"q0": q0, "rang": {}, "wsclean": {}}
    summary = json.loads((run / "clean-certified.json").read_text())
    for cfg in summary["runs"]:
        name = cfg["name"]
        model = np.load(run / f"{name}-model.npy").T
        residual = np.load(run / f"{name}-residual.npy").T
        q, exact_residual = exact.score(model)
        entry = {
            "components": cfg["components"],
            "major_cycles": cfg["major_cycles"],
            "stop": cfg["stop"],
            "q_rust": cfg["q_final"],
            "q_python": q,
            "q_over_q0": q / q0,
            "residual_python_vs_rust_linf": float(
                np.abs(exact_residual - residual).max()
            ),
            "erc_k": cfg["erc"]["k"],
            "erc_eta": cfg["erc"]["eta"],
            "max_abs_gap_relative": cfg["max_abs_gap_relative"],
            "ascending_steps": cfg["ascending_steps"],
            "seconds": cfg["seconds"],
        }
        entry.update(model_stats(model))
        entry.update(residual_stats(residual, "residual"))
        result["rang"][name] = entry
    for model_path in sorted(wsc.glob("c-*-model.fits")):
        name = model_path.name[: -len("-model.fits")]
        model, _ = read_fits(model_path)
        residual, _ = read_fits(wsc / f"{name}-residual.fits")
        q, exact_residual = exact.score(model)
        entry = {"q_exact": q, "q_over_q0": q / q0}
        entry.update(wsclean_log(wsc / f"{name}.log"))
        entry.update(model_stats(model))
        entry.update(residual_stats(residual, "residual_wsclean"))
        entry.update(residual_stats(exact_residual, "residual_exact"))
        entry["residual_wsclean_vs_exact_linf"] = float(
            np.abs(exact_residual - residual).max()
        )
        timing = (wsc / "timing" / f"{name}.txt").read_text().split()
        entry["wall_s"] = float(timing[0])
        entry["max_rss_kb"] = int(timing[1])
        result["wsclean"][name] = entry
    # Model agreement of the matched pairs.
    pairs = {
        "exact-mgain_vs_c-nominres-hogbom": ("exact-mgain", "c-nominres-hogbom"),
        "image-mgain_vs_c-nominres-hogbom": ("image-mgain", "c-nominres-hogbom"),
        "wsclean-nominres-mgain_vs_c-nominres-hogbom": (
            "wsclean-nominres-mgain",
            "c-nominres-hogbom",
        ),
        "wsclean-recorded-mgain_vs_c-recorded-hogbom": (
            "wsclean-recorded-mgain",
            "c-recorded-hogbom",
        ),
    }
    result["pairs"] = {}
    for key, (a, b) in pairs.items():
        if a in result["rang"] and b in result["wsclean"]:
            ma = np.load(run / f"{a}-model.npy").T
            mb, _ = read_fits(wsc / f"{b}-model.fits")
            ra = np.load(run / f"{a}-residual.npy").T
            rb, _ = read_fits(wsc / f"{b}-residual.fits")
            result["pairs"][key] = {
                "model_linf": float(np.abs(ma - mb).max()),
                "model_flux_difference": float(ma.sum() - mb.sum()),
                "same_support": bool(
                    np.array_equal(np.flatnonzero(ma), np.flatnonzero(mb))
                ),
                "residual_linf": float(np.abs(ra - rb).max()),
            }
    Path(args.out_json).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(
        f"{'run':<28} {'comps':>7} {'cyc':>4} {'Q/Q0':>10} {'rms':>8} {'peak':>8} {'flux':>9} {'central':>9}  stop"
    )
    for name, e in result["rang"].items():
        print(
            f"rang {name:<23} {e['components']:>7} {e['major_cycles']:>4} {e['q_over_q0']:>10.3e} "
            f"{e['residual_rms']:>8.4f} {e['residual_peak_abs']:>8.4f} {e['model_flux_total']:>9.4f} "
            f"{e['model_flux_central_65px']:>9.4f}  {e['stop']}"
        )
    for name, e in result["wsclean"].items():
        print(
            f"wsc  {name:<23} {e['components'] or e['last_logged_iteration']:>7} "
            f"{e['major_cycles'] or 0:>4} {e['q_over_q0']:>10.3e} "
            f"{e['residual_wsclean_rms']:>8.4f} {e['residual_wsclean_peak_abs']:>8.4f} "
            f"{e['model_flux_total']:>9.4f} {e['model_flux_central_65px']:>9.4f}  "
            f"{'diverged' if e['diverged'] else 'ok'} (exact rms {e['residual_exact_rms']:.4f})"
        )
    print(json.dumps(result["pairs"], indent=1))


if __name__ == "__main__":
    main()
