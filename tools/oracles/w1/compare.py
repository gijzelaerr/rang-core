"""Compare a W1 oracle run against the frozen tolerances of
research/w1-writeback.md and write `<run>/summary.json`.

    python tools/oracles/w1/compare.py <run>
"""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

WRITTEN = {"MODEL_DATA", "CORRECTED_DATA", "FLAG", "FLAG_ROW", "WEIGHT_SPECTRUM"}


def load(path):
    return json.loads(Path(path).read_text())


def image(run, name):
    with fits.open(run / "wsclean" / f"{name}-dirty.fits") as h:
        return np.asarray(h[0].data, np.float64).squeeze()


def compare(run):
    run = Path(run)
    out = {"run": str(run), "ms": {}, "pass": {}}
    for m in ("m1", "m2"):
        rec = load(run / "out" / f"{m}-writes.npz.json")
        r = {}
        before, after = rec["before"], rec["after"]
        written = {c for c in WRITTEN if c in after}
        if rec.get("weights_written"):
            written.add("WEIGHT")
        r["added"] = rec["added"]
        r["unwritten_unchanged_rang"] = all(
            before[c] == after[c] for c in before if c not in written
        )
        for tool in ("casacore381", "casacore371", "daskms"):
            got = load(run / "out" / f"{m}-{tool}.json")
            hashes = got["hashes"]
            common = [
                c
                for c in hashes
                if c in after
                and not hashes[c].startswith("unreadable")
                and not after[c].startswith("unreadable")
            ]
            r[f"{tool}_columns_compared"] = len(common)
            r[f"{tool}_hash_mismatch"] = [c for c in common if hashes[c] != after[c]]
            r[f"{tool}_checks"] = got["checks"]
            r[f"{tool}_unreadable"] = sorted(
                c for c, h in hashes.items() if h.startswith("unreadable")
            )
            if tool.startswith("casacore"):
                r[f"{tool}_unwritten_equal_pristine"] = all(
                    hashes[c] == before[c]
                    for c in hashes
                    if c in before
                    and c not in written
                    and not before[c].startswith("unreadable")
                )
                r[f"{tool}_columns"] = {
                    c: {
                        k: v["desc"].get(k)
                        for k in (
                            "valueType",
                            "dataManagerType",
                            "dataManagerGroup",
                            "ndim",
                            "shape",
                            "option",
                            "comment",
                        )
                    }
                    | {
                        "keywords": v["keywords"],
                        "dminfo_type": v["dminfo"]["TYPE"],
                        "dminfo_name": v["dminfo"]["NAME"],
                    }
                    for c, v in got["columns"].items()
                }
        for name in ("casarestore", "casasave"):
            h = load(run / "out" / f"{m}-{name}-hashes.json")
            r[f"{name}_flags_equal_pristine"] = (
                h["FLAG"] == before["FLAG"] and h["FLAG_ROW"] == before["FLAG_ROW"]
            )
        listed = load(run / "out" / f"{m}-casa-list.json")["flagmanager_list"]
        r["casa_lists_rang_original"] = "rang_original" in json.dumps(listed)
        r["casa_list"] = listed
        for col in ("corrected", "model"):
            r[f"split_{col}"] = load(run / "out" / f"{m}-split-compare-{col}.json")
        r["applycal"] = load(run / "out" / f"{m}-applycal-compare.json")
        d, c, mo = (
            image(run, f"{m}-{x}") for x in ("DATA", "CORRECTED_DATA", "MODEL_DATA")
        )
        peak = float(np.abs(d).max())
        r["wsclean"] = {
            "peak_DATA": peak,
            "max_abs_CORRECTED_minus_DATA": float(np.abs(c - d).max()),
            "rel_CORRECTED": float(np.abs(c - d).max() / peak),
            "max_abs_MODEL_minus_2DATA": float(np.abs(mo - 2 * d).max()),
            "rel_MODEL": float(np.abs(mo - 2 * d).max() / (2 * peak)),
        }
        qc = run / "out" / f"{m}-qc-gains.json"
        r["quartical_reported_not_gated"] = load(qc) if qc.exists() else "no gains"
        out["ms"][m] = r
        p = out["pass"]
        p[f"{m} casacore"] = all(
            not r[f"{t}_hash_mismatch"]
            and all(r[f"{t}_checks"].values())
            and r[f"{t}_unwritten_equal_pristine"]
            for t in ("casacore381", "casacore371")
        )
        p[f"{m} daskms"] = not r["daskms_hash_mismatch"] and all(
            r["daskms_checks"].values()
        )
        p[f"{m} flag round trip"] = (
            r["casarestore_flags_equal_pristine"]
            and r["casasave_flags_equal_pristine"]
            and r["casa_lists_rang_original"]
        )
        p[f"{m} CASA split"] = all(
            all(v for k, v in r[f"split_{col}"].items() if k != "rows")
            for col in ("corrected", "model")
        )
        p[f"{m} CASA applycal"] = r["applycal"]["cells_failing_class_C"] == 0
        p[f"{m} WSClean"] = (
            r["wsclean"]["rel_CORRECTED"] <= 1e-6 and r["wsclean"]["rel_MODEL"] <= 1e-6
        )
    u = image(run, "m1u-MODEL_DATA")
    centre = tuple(s // 2 for s in u.shape)
    at = np.unravel_index(np.argmax(u), u.shape)
    out["m1u"] = {
        "peak": float(u.max()),
        "peak_pixel": [int(i) for i in at],
        "centre_pixel": list(centre),
        "centre_value": float(u[centre]),
    }
    # Post hoc, not gated (the frozen criterion assumed a PSF that peaks
    # at one pixel): the unit model's image against the PSF of the same
    # weights and flags.
    psf_path = run / "wsclean" / "m1u-DATA-psf.fits"
    if psf_path.exists():
        with fits.open(psf_path) as h:
            psf = np.asarray(h[0].data, np.float64).squeeze()
        out["m1u"]["posthoc_max_abs_MODEL_minus_PSF"] = float(np.abs(u - psf).max())
        out["m1u"]["posthoc_psf_peak"] = float(psf.max())
        out["m1u"]["posthoc_psf_peak_pixel"] = [
            int(i) for i in np.unravel_index(np.argmax(psf), psf.shape)
        ]
        ring = psf[centre[0] - 8 : centre[0] + 9, centre[1] - 8 : centre[1] + 9]
        out["m1u"]["posthoc_psf_min_within_8_pixels"] = float(ring.min())
    out["pass"]["m1u WSClean point"] = (
        tuple(at) == centre and abs(float(u.max()) - 1) <= 1e-3
    )
    m0 = run / "out" / "m0-writes.npz.json"
    if m0.exists():
        rec = load(m0)
        r = {"added": rec["added"], "weights_written": rec.get("weights_written")}
        for tool in ("casacore381", "casacore371", "daskms"):
            got = load(run / "out" / f"m0-{tool}.json")
            common = [
                c
                for c in got["hashes"]
                if c in rec["after"]
                and not got["hashes"][c].startswith("unreadable")
                and not rec["after"][c].startswith("unreadable")
            ]
            r[f"{tool}_columns_compared"] = len(common)
            r[f"{tool}_hash_mismatch"] = [
                c for c in common if got["hashes"][c] != rec["after"][c]
            ]
            r[f"{tool}_checks"] = got["checks"]
        if "columns" in load(run / "out" / "m0-casacore381.json"):
            cols = load(run / "out" / "m0-casacore381.json")["columns"]
            r["casacore381_WEIGHT_SPECTRUM"] = {
                k: cols["WEIGHT_SPECTRUM"]["desc"].get(k)
                for k in (
                    "valueType",
                    "dataManagerType",
                    "dataManagerGroup",
                    "shape",
                    "comment",
                )
            }
        out["m0"] = r
        out["pass"]["m0 casacore and dask-ms"] = all(
            not r[f"{t}_hash_mismatch"] and all(r[f"{t}_checks"].values())
            for t in ("casacore381", "casacore371", "daskms")
        )
    out["pass"]["all"] = all(out["pass"].values())
    (run / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["pass"], indent=1))
    return out


if __name__ == "__main__":
    compare(sys.argv[1])
