"""Compact archive of the gemclean held-out test (research/gemclean-heldout.md).

Usage: gemclean_heldout_archive.py ROOT OUT.json, with ROOT the run tree on D:
(ROOT/sim, ROOT/real). Reads scores and reports only, evaluates the
pre-registered bar, and writes research/results/gemclean-heldout.json.
"""

import json
import re
import sys
from pathlib import Path

SKIES = {
    "h1": "dec -75, 60 points",
    "h2": "dec +10, 300 points, blended",
    "h3": "dec -30, 4096 x 1.5 arcsec, 120 points",
    "h4": "dec -45, 30 points, 6 Gaussians, 25-Gaussian tail",
}
FALSE_RATIO_BAR = 1.6
Q_BAR = 0.002
RECOVERY_BAR = 0.005
MAX_CYCLES = 5


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def wsclean_majors(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"(\d+) major iterations were performed", text)
    total = re.findall(r"Performed (\d+) iterations in total", text)
    last = re.findall(r"Iteration (\d+):", text)
    return {
        "majors": int(m[-1]) if m else None,
        "components": int(total[-1]) if total else None,
        "components_at_least": int(last[-1]) if last else None,
    }


def cycles(report):
    return [
        {
            "components": c["components"],
            "peak_start": c["peak_start"],
            "stop": c["stop"],
            "stale_linf": c["stale_linf"],
            "gap_relative": c["gap_relative"],
            "abs_flux": c["abs_flux"],
        }
        for c in report["run"]["cycles"]
    ]


def sim_job(rec):
    keep = (
        "q_over_q_truth",
        "q_over_q0",
        "exact_residual_inner_peak_abs",
        "exact_residual_inner_rms",
        "false_pixels",
        "false_flux_abs",
        "false_flux_positive",
        "false_flux_negative",
        "total_flux_error",
        "model_pixels",
        "model_flux_total",
        "model_flux_negative",
        "recovery_all",
        "recovery_by_decade",
        "extended",
        "model_fits_sha256",
        "residual_fits_sha256",
        "command",
    )
    return {k: rec[k] for k in keep if k in rec}


def sims(root):
    out = {}
    for ds, sky in SKIES.items():
        ws = read(root / "scores" / f"wsclean-{ds}.json")
        ge = read(root / "scores" / f"gemclean-{ds}.json")
        fast = ws["jobs"][f"{ds}-abs-nominres-fast-j16"]
        plain = ws["jobs"][f"{ds}-abs-nominres-hogbom-j16"]
        gem = ge["jobs"][f"{ds}-abs-nominres-fast-j16"]
        report = gem["report"]
        cat = read(root / "data" / f"{ds}.json")
        meta = read(root / "prep" / ds / "meta.json")
        comparison = next(iter(meta["comparisons"].values()))
        log_fast = wsclean_majors(root / "wsclean" / f"{ds}-abs-nominres-fast-j16.log")
        log_plain = wsclean_majors(
            root / "wsclean" / f"{ds}-abs-nominres-hogbom-j16.log"
        )
        majors = report["run"]["major_cycles"]
        low = min(fast["false_flux_abs"], plain["false_flux_abs"])
        ratio = gem["false_flux_abs"] / low
        q = gem["q_over_q_truth"] / plain["q_over_q_truth"] - 1.0
        rec = (
            gem["recovery_all"]["flux_weighted"]
            - plain["recovery_all"]["flux_weighted"]
        )
        plain_peak = plain["exact_residual_inner_peak_abs"]
        to_plain = next(
            (
                i
                for i, c in enumerate(report["run"]["cycles"])
                if c["peak_start"] <= plain_peak
            ),
            majors,
        )
        out[ds] = {
            "sky": sky,
            "image": cat.get("image"),
            "seeds": {k: cat.get(k) for k in ("sky_seed", "noise_seed") if k in cat},
            "noise_briggs_jy": ge.get("briggs_noise"),
            "beam_arcsec": ge.get("beam_arcsec"),
            "dirty_vs_wsclean_linf_over_peak": comparison["dirty_linf_over_peak"],
            "psf_fit_arcsec": [
                comparison["psf_bmaj_arcsec"],
                comparison["psf_bmin_arcsec"],
            ],
            "gemclean": {
                **sim_job(gem),
                "majors": majors,
                "components": report["run"]["components"],
                "ascending_major_cycles": report["run"]["ascending_major_cycles"],
                "max_abs_gap_relative": report["run"]["max_abs_gap_relative"],
                "cycles": cycles(report),
            },
            "wsclean_fast": {**sim_job(fast), **log_fast},
            "wsclean_plain": {**sim_job(plain), **log_plain},
            "bar": {
                "cycles_at_most_5": majors <= MAX_CYCLES,
                "cycles_at_most_fast": majors <= log_fast["majors"],
                "false_ratio_to_lower_wsclean": ratio,
                "false_ratio_passes": ratio <= FALSE_RATIO_BAR,
                "q_excess_over_plain": q,
                "q_passes": q <= Q_BAR,
                "recovery_flux_weighted_minus_plain": rec,
                "recovery_passes": rec >= -RECOVERY_BAR,
            },
            "post_hoc_cycles_until_peak_at_or_below_plains_stop": to_plain,
        }
        out[ds]["bar"]["survives"] = all(
            v for k, v in out[ds]["bar"].items() if isinstance(v, bool)
        )
    return out


def real_set(root, scores, compare, jobs, run):
    s = read(root / scores)["jobs"]
    c = read(root / compare)
    out = {
        "off_source_mask": {
            k: c[k]
            for k in (
                "beam_arcsec",
                "mask_sigma",
                "sigma_used_jy",
                "source_mask_fraction_inner",
            )
        },
        "compact_sources": c["compact_sources"],
        "compact_agreement": c["compact_agreement"],
        "brightest_compact": [
            {k: x[k] for k in ("y", "x", "peak", "radius_deg", "flux")}
            for x in c["brightest_compact"][:5]
        ],
        "jobs": {},
    }
    for job, kind in jobs.items():
        rec = {**s[job], **c["jobs"][job], "imager": kind}
        rec.pop("score_seconds", None)
        if kind == "gemclean":
            report = read(run / f"{job}-report.json")
            rec.update(
                majors=report["run"]["major_cycles"],
                components=report["run"]["components"],
                ascending_major_cycles=report["run"]["ascending_major_cycles"],
                max_abs_gap_relative=report["run"]["max_abs_gap_relative"],
                peak_memory_bytes=report.get("peak_memory_bytes"),
                restoring_beam=report.get("beam"),
                cycles=cycles(report),
            )
        else:
            rec.update(wsclean_majors(run / f"{job}.log"))
        out["jobs"][job] = rec
    return out


def main(argv):
    root, out = Path(argv[1]), Path(argv[2])
    real = root / "real"
    run = real / "run"
    verify = read(real / "verify.json")
    verify.pop("spot_visibilities", None)
    result = {
        "note": "research/gemclean-heldout.md",
        "code": "gemclean binary built at f0ca931, core/src/gemclean* unchanged on this branch",
        "wsclean": "WSClean 3.7 in rang-o-casa:6.7.6.14, -gridder wgridder "
        "-no-min-grid-resolution -wgridder-accuracy 1e-6",
        "wall_times": "not results: contended host, the speed run is postponed",
        "bar": {
            "max_cycles": MAX_CYCLES,
            "false_ratio": FALSE_RATIO_BAR,
            "q_excess": Q_BAR,
            "recovery": RECOVERY_BAR,
            "written_before_runs_in_commit": "00387b2",
        },
        "simulations": sims(root / "sim"),
        "pilot": {
            "ms_verify": verify,
            "casacore_read_beyond_2gib": read(real / "casacore-compare.json"),
            "gains_manifest_bytes": read(
                "/mnt/d/rang/data/eso137-pilot/gains/manifest.json"
            )["bytes"],
            "gain_load": read(real / "gains.npz.json"),
            "gain_check": read(real / "gaincheck.json"),
            "dirty_raw_vs_calibrated": read(real / "dirty-stats.json"),
            "scorer_vs_wsclean_native": read(real / "dirtycheck.json"),
            "scorer_vs_wsclean_averaged": read(real / "dirtycheck2.json"),
            "averaged_ms": read(real / "cal2.ms.json"),
            "calibrated_ms": read(real / "cal.ms.json"),
            "extra_flags": {
                k: v for k, v in read(real / "badbaselines.json").items() if k != "list"
            },
            "extra_flag_baselines": [
                [b["a1"], b["a2"], round(b["length_m"])]
                for b in read(real / "badbaselines.json")["list"]
            ],
            "flagged_ms": read(real / "cal3.ms.json"),
            "prep_a": read(real / "prep2" / "meta.json"),
            "prep_b": read(real / "prep3" / "meta.json"),
        },
        "real_A_received_flags_3mJy": real_set(
            real,
            "scores.json",
            "compare-003.json",
            {
                "cal2-003-gem": "gemclean",
                "cal2-003-fast": "wsclean fast",
                "cal2-003-plain": "wsclean plain",
            },
            run,
        ),
        "real_A_received_flags_1mJy": real_set(
            real,
            "scores.json",
            "compare-001.json",
            {
                "cal2-001-gem": "gemclean",
                "cal-001-fast": "wsclean fast, on the native 512 channels",
            },
            run,
        ),
        "real_B_extra_flags_3mJy": real_set(
            real,
            "scores3.json",
            "compare3-003.json",
            {
                "cal3-003-gem": "gemclean",
                "cal3-003-fast": "wsclean fast",
                "cal3-003-plain": "wsclean plain",
            },
            run,
        ),
    }
    out.write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    for ds, rec in result["simulations"].items():
        print(ds, rec["bar"], rec["post_hoc_cycles_until_peak_at_or_below_plains_stop"])


if __name__ == "__main__":
    main(sys.argv)
