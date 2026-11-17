"""E2-A's gate 3c scorer (research/results/e2-acceptance-scripts/e2_score3c_a.py;
research/e2-acceptance.md 9.10 and the coordinator's decisions) on small
synthetic image sets in rang's and WSClean's Stokes I file names: dirty L-inf
over the full image with the inner two-thirds beside, compact-source ratios
within 0.7 deg (gated) and over the inner two-thirds and the full image
(reported), and the dirty-only reading for the nosi run."""

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

fits = pytest.importorskip("astropy.io.fits")

HERE = Path(__file__).resolve().parents[1] / "research/results/e2-acceptance-scripts"
spec = importlib.util.spec_from_file_location("e2_score3c_a", HERE / "e2_score3c_a.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

N, CEN, PIX_DEG, SIG = 160, 80, 0.7 / 40, 1.5  # 0.7 deg = 40 pixels
FREQS = (1.0e9, 1.4e9)
# (x, y, flux at 1 GHz, WSClean's flux over rang's): four within 0.7 deg, one
# beyond it inside the inner two-thirds, one outside both, one at the edge
SOURCES = [(90, 80, 0.20, 1 / 1.002), (60, 85, 0.15, 1 / 1.002), (85, 55, 0.30, 1 / 1.002),
           (110, 95, 0.12, 1 / 1.002), (130, 80, 0.25, 1 / 0.95), (140, 20, 0.2, 1.0),
           (155, 150, 0.2, 1.0)]  # fmt: skip
TAG = "ESO137m001"


def header(freq, bmaj_deg=None):
    h = fits.Header()
    for k, v in (("CTYPE1", "RA---SIN"), ("CTYPE2", "DEC--SIN"), ("CRPIX1", CEN + 1),
                 ("CRPIX2", CEN + 1), ("CRVAL1", 250.0), ("CRVAL2", -60.0),
                 ("CDELT1", -PIX_DEG), ("CDELT2", PIX_DEG), ("CUNIT1", "deg"), ("CUNIT2", "deg"),
                 ("CTYPE3", "FREQ"), ("CRPIX3", 1), ("CRVAL3", freq), ("CDELT3", 1e6),
                 ("CTYPE4", "STOKES"), ("CRPIX4", 1), ("CRVAL4", 1), ("CDELT4", 1)):  # fmt: skip
        h[k] = v
    if bmaj_deg:
        h["BMAJ"], h["BMIN"], h["BPA"] = bmaj_deg, bmaj_deg, 0.0
    return h


def put(path, img, h):
    fits.PrimaryHDU(np.asarray(img, np.float32)[None, None], h).writeto(path)


def gauss(x0, y0):
    yy, xx = np.mgrid[:N, :N]
    return np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * SIG**2))


def write_arm(where, stem, arm, rng_seed, dirty_extra=None, clean=True):
    where.mkdir(parents=True, exist_ok=True)
    bmaj = 2 * math.sqrt(2 * math.log(2)) * SIG * PIX_DEG
    noise = np.random.default_rng(rng_seed).normal(0, 1e-3, (len(FREQS), N, N))
    mfs = {"image": 0, "model": 0, "residual": 0, "dirty": 0}
    for i, f in enumerate(FREQS):
        h = header(f, bmaj)
        model = np.zeros((N, N))
        for x, y, s, w in SOURCES:
            model[y, x] = s * (f / 1e9) ** -0.7 * (w if arm == "wsclean" else 1.0)
        image = sum(model[y, x] * gauss(x, y) for x, y, *_ in SOURCES) + noise[i]
        # both arms' dirty images from the same sky: they differ only by `dirty_extra`
        dirty = (
            sum(s * (f / 1e9) ** -0.7 * gauss(x, y) for x, y, s, _ in SOURCES)
            + noise[i]
        )
        if dirty_extra is not None:
            dirty = dirty + dirty_extra(np.max(np.abs(image)))
        c = f"{i:04d}"
        put(where / stem("dirty", c, "dirty"), dirty, h)
        if clean:
            put(where / stem("clean", c, "image"), image, h)
            put(where / stem("clean", c, "model"), model, h)
            put(where / stem("clean", c, "residual"), noise[i], h)
            put(where / stem("clean", c, "psf"), gauss(CEN, CEN), h)
        for k, v in (
            ("image", image),
            ("model", model),
            ("residual", noise[i]),
            ("dirty", dirty),
        ):
            mfs[k] = mfs[k] + v / len(FREQS)
    h = header(1.2e9, bmaj)
    put(where / stem("dirty", "MFS", "dirty"), mfs["dirty"], h)
    if clean:
        for k in ("image", "model", "residual"):
            put(where / stem("clean", "MFS", k), mfs[k], h)


def make(tmp_path, rang_dirty_extra=None, oracle="wsclean3c-a", clean=True):
    r = tmp_path / "R"
    base = r / "rang-run"
    (base / "image").mkdir(parents=True)
    (base / "config.resolved.json").write_text(
        json.dumps({"image": {"channels_out": 2}})
    )
    (base / "image" / "summary.json").write_text(json.dumps({"images": [{
        "field": "ESO137-001", "field_id": 1,
        "argv": ["py", "-m", "rang.gemclean", "-name",
                 "D:\\rang\\outputs\\e2a\\e2a.ms.rang-run\\image\\ESO137-001\\image", "ms"]}]}))  # fmt: skip
    write_arm(base / "image" / "ESO137-001", lambda kind, c, what: f"image-{c}-{what}.fits",
              "rang", 1, rang_dirty_extra)  # fmt: skip
    write_arm(r / oracle, lambda kind, c, what: f"{TAG}-{kind}-{c}-{what}.fits", "wsclean", 1,
              clean=clean)  # fmt: skip
    return r


def run(r, oracle="wsclean3c-a", *flags):
    out = r / "g.json"
    assert score.main(r, r / oracle, out, *flags) == 0
    return json.loads(out.read_text())


def test_compact_sets_and_dirty(tmp_path):
    def edge_spike(peak):
        d = np.zeros((N, N))
        d[3, 3] = 1e-7 * peak  # in the 5 % border, outside the inner two-thirds
        return d

    res = run(make(tmp_path, edge_spike))
    dirty = res["dirty"]
    assert dirty["met"] and 5e-8 < dirty["max_over_peak"] < 2e-7
    assert dirty["reported"]["inner_two_thirds"] == 0.0
    assert (
        dirty["reported"]["border5"] == 0.0
        and dirty["reported"]["within_0p7deg"] == 0.0
    )
    comp = res["compact"]
    assert comp["too_near_edge"] == 1 and len(comp["sources"]) == 6
    gated = comp["gated"]
    assert gated["n"] == 4 and gated["met"]
    assert gated["median"] == pytest.approx(1.002, abs=2e-4)
    rep = comp["reported"]
    assert rep["inner_two_thirds"]["n"] == 5 and rep["full_image"]["n"] == 6
    out = [s for s in comp["sources"] if s["x"] == 130]
    assert out[0]["ratio"] == pytest.approx(0.95, abs=2e-3) and not out[0]["in_0p7deg"]
    assert comp["radial"][0]["n"] + comp["radial"][1]["n"] == 4
    assert comp["spectral_index_reported"]["median_abs_dalpha"] < 1e-3
    assert res["gates"] == {"dirty_linf": True, "compact_ratio": True,
                            "q_over_q0": "not checked", "model_data_predict": "not checked"}  # fmt: skip
    assert res["met_where_checked"]


def test_dirty_edge_term_fails_the_full_image_only(tmp_path):
    def corner(peak):
        d = np.zeros((N, N))
        d[2, 150] = 3e-5 * peak  # the kind of edge term small inversion leaves
        return d

    res = run(make(tmp_path, corner))
    assert (
        not res["dirty"]["met"] and res["dirty"]["reported"]["inner_two_thirds"] == 0.0
    )
    assert not res["met_where_checked"]


def test_dirty_only_reading_for_nosi(tmp_path):
    r = make(tmp_path, oracle="wsclean3c-a-nosi", clean=False)
    res = run(r, "wsclean3c-a-nosi", "--dirty-only")
    assert res["dirty_only"] and "compact" not in res and res["dirty"]["met"]
    assert set(res["gates"]) == {"dirty_linf", "q_over_q0", "model_data_predict"}


def test_grids_must_match(tmp_path):
    r = make(tmp_path)
    p = r / "wsclean3c-a" / f"{TAG}-dirty-0000-dirty.fits"
    with fits.open(p, mode="update") as f:
        f[0].header["CRPIX1"] = CEN + 2
    with pytest.raises(SystemExit, match="CRPIX1"):
        score.main(r, r / "wsclean3c-a", r / "g.json")
