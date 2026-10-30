"""B1-3 Part 1: the identifiability survey rerun (research/b1-3-pointing-selfcal.md).

B1-2's five sets with two changes only: gains per antenna x hand x channel
x 2-dump interval (a per-channel bandpass nuisance), and per-antenna
holography beams by the B1-3 rule. Everything else (sets, models, noise
calibration, primary and strict sky arms, measures, the frozen rule) is
B1-2's.

    python examples/b1_survey_rerun.py survey S3 outputs/b1-3-<date>-NN [--nproc 4]
    python examples/b1_survey_rerun.py survey S4 OUT --pilot outputs/b1-2-20261030-01-pilot \\
        --field outputs/b1-2-20261030-04-fieldmodel
    python examples/b1_survey_rerun.py archive OUT_JSON RUN...

Inputs: B1-2's loaders and noise records (`examples/b1_identifiability.py`,
`outputs/b1-2-20261030-*`), the B1-0 holography product (CC BY-NC 4.0, de
Villiers 2023, DOI 10.48479/wdb0-h061), the ESO137 fetches (CC BY 4.0,
Ramatsoku et al. 2020) and the antenna names of
`outputs/b1-3-20261030-00-probe-names` (opcode scan, nothing unpickled).
"""

import argparse
import json
import math
import platform
import re
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b1_identifiability as b12
from rang import beam_holography, core, rusage
from rang import beam_identifiability as bi
from rang import pointing_selfcal as ps

ROOT = b12.ROOT
NAMES = ROOT / "outputs/b1-3-20261030-00-probe-names/names.json"
LUNO_NAMES = ROOT / "outputs/luno-solve-20261029-02/inputs/ANTENNA/ANTENNA_0/NAME"
B12_RUNS = {
    "S1": ROOT / "outputs/b1-2-20261030-06-S1",
    "S2": ROOT / "outputs/b1-2-20261030-07-S2",
    "S3": ROOT / "outputs/b1-2-20261030-09-S3",
    "S4": ROOT / "outputs/b1-2-20261030-12-S4",
    "S5": ROOT / "outputs/b1-2-20261030-13-S5",
}
VERDICT = "antenna"
CONVERGENCE = 0.05
G3A_RHO = 1e-6


def log(*args):
    print(time.strftime("%H:%M:%S"), *args, flush=True)


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=_json_default) + "\n")


def _json_default(x):
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, np.bool_):
        return bool(x)
    raise TypeError(type(x))


# --------------------------------------------------------------------------
# Antenna names -> holography antennas


def luno_names():
    raw = core.blosc_decode((LUNO_NAMES / "0").read_bytes())
    names = json.loads(raw.decode())
    return [n for n in names if isinstance(n, str) and re.fullmatch(r"m\d{3}", n)]


def eso_names():
    strings = json.loads(NAMES.read_text())["strings"]
    return [s for s in strings if re.fullmatch(r"m\d{3}", s)]


def holography_index(product, names):
    return [product.antnames.index(n) for n in names]


def names_for(name, nant):
    names = luno_names() if name in ("S1", "S2", "S3") else eso_names()
    if len(names) != nant:
        raise ValueError(f"{name}: {len(names)} names for {nant} antennas")
    return names


# --------------------------------------------------------------------------
# Sets


def load_set(name, pilot=None, track=None, field=None):
    if name in ("S1", "S2"):
        d = b12.load_luno("MAIN/MAIN_1", None if name == "S2" else [0, 1, 2, 3])
        sky = b12.sky_from_sources(b12.sky_lsm(), d["phase_dir"])
        scans = [d]
    elif name == "S3":
        d = b12.load_luno("MAIN/MAIN_2", None)
        p = b12.S3_POINT
        sky = b12.sky_point(p["i0_jy"], p["alpha"], p["nu0_hz"])
        scans = [d]
    elif name == "S4":
        d = b12.load_eso_pilot(pilot)
        comps = np.load(Path(field) / "components.npz")
        sky = b12.sky_components(comps["lm"], comps["flux"])
        scans = [d]
    elif name == "S5":
        scans = b12.load_eso_track(track)
        comps = np.load(Path(field) / "components.npz")
        sky = b12.sky_components(comps["lm"], comps["flux"])
    else:
        raise ValueError(name)
    return scans, sky


def b12_noise(name):
    """B1-2's noise and amplitude records of the set's verdict run."""
    rec = json.loads((B12_RUNS[name] / "survey.json").read_text())
    return rec["noise"]


def calibration(name, scans):
    """s^2 recomputed (B1-2's `noise_for`) and checked against B1-2's
    records; c taken from B1-2's records (the same procedures); kappa =
    c^2 / s^2 per (scan, hand), as B1-2."""
    records = b12_noise(name)
    kappa, out = {}, []
    for s, d in enumerate(scans):
        noise = b12.noise_for(d)
        rec = records[s]
        c = {h: float(rec["c"][str(h)]) for h in range(2)}
        s2 = [noise[h]["s2"] for h in range(2)]
        ref = [rec["noise"][str(h)]["s2"] for h in range(2)]
        dev = max(abs(a / b - 1) for a, b in zip(s2, ref, strict=True))
        for h in range(2):
            kappa[(s, h)] = c[h] ** 2 / s2[h]
        out.append(
            {
                "scan": s,
                "s2": s2,
                "s2_b12": ref,
                "s2_relative_difference": dev,
                "c": [c[0], c[1]],
            }
        )
    return kappa, out


def component_radius_deg(sky):
    r = np.degrees(np.hypot(sky["lm"][:, 0], sky["lm"][:, 1]))
    return float(max(r.max() + 0.12, 0.3))


# --------------------------------------------------------------------------
# The survey of one set


def info_labels(acc, kappa):
    info = acc.information(kappa)
    lab = acc.label_transform()
    return {k: lab.T @ v @ lab for k, v in info.items()}


def per_scan_common(info, labels, nant, nscan, variants):
    """The per-scan array-common pointing (delta_p = c_s for every antenna of
    scan s): u^T F u from the per-antenna blocks (S5's derived direction)."""
    out = []
    raw_d = np.diag(info["raw"])
    for v, vname in enumerate(variants):
        for s in range(nscan):
            for j, axis in enumerate(("x", "y")):
                u = np.zeros(len(labels))
                for i, lab in enumerate(labels):
                    if (
                        lab["family"] == "antenna"
                        and lab["variant"] == vname
                        and lab["scan"] == s
                        and lab["direction"] == f"pointing_{axis}"
                        and raw_d[i] > 0
                    ):
                        u[i] = 1.0
                if not u.any():
                    continue
                rec = {
                    "variant": vname,
                    "scan": s,
                    "direction": f"scan-common pointing_{axis}",
                }
                fr = float(u @ info["raw"] @ u)
                for arm in ("primary", "strict"):
                    fp = float(u @ info[f"both_{arm}"] @ u)
                    rec[f"sigma_{arm}"] = 1 / math.sqrt(fp) if fp > 0 else math.inf
                    rec[f"rho_{arm}"] = math.sqrt(max(fp, 0) / fr) if fr > 0 else 0.0
                rec["constrainable"] = bool(
                    rec["sigma_primary"] <= bi.SIGMA_ARCMIN
                    and rec["rho_primary"] >= bi.RHO_MIN
                )
                out.append(rec)
    return out


def candidates_from(rows, scan_common, variant):
    """Families that pass the rerun (width never): the candidates for R."""
    fam = set()
    for r in rows:
        if r["variant"] != variant or not r["constrainable"]:
            continue
        d = r["direction"]
        if d.startswith("antenna"):
            fam.add("antenna")
        elif d in ("pointing_x", "pointing_y"):
            fam.add("common_pointing")
        elif d.startswith("squint"):
            fam.add("squint")
        elif d == "ellipticity":
            fam.add("ellipticity")
    if any(r["constrainable"] for r in scan_common if r["variant"] == variant):
        fam.add("interval_common")
    return sorted(fam)


def survey_set(name, out, pilot=None, track=None, field=None, nproc=4):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    stages = {}
    scans, sky = load_set(name, pilot, track, field)
    stages["load"] = time.perf_counter() - started
    nant = len(scans[0]["positions"])
    names = names_for(name, nant)
    product = beam_holography.HolographyBeam(b12.HOLOGRAPHY)
    holo = holography_index(product, names)
    radius = component_radius_deg(sky)
    variants = [
        ("antenna", "antenna", False, ps.SUB),
        ("average", "average", False, ps.SUB),
    ]
    if name == "S1":
        variants.append(("antenna8", "antenna", False, 8))
    if name == "S3":
        variants.append(("copolar", "antenna", True, ps.SUB))
    beam_objs = [
        (
            ps.AntennaBeams(product, holo, mode=mode, copolar=cop, radius_deg=radius),
            width,
        )
        for _n, mode, cop, width in variants
    ]
    vnames = [v[0] for v in variants]
    log(
        "loaded",
        name,
        [len(s["a1"]) for s in scans],
        "components",
        len(sky["flux"]),
        "variants",
        vnames,
    )
    mark = time.perf_counter()
    kappa, noise = calibration(name, scans)
    stages["noise"] = time.perf_counter() - mark
    log("noise", noise)
    mark = time.perf_counter()
    prepared = [ps.prepare_scan(d, [1.0, 1.0]) for d in scans]
    nu0 = float(np.mean(np.concatenate([s["freqs"] for s in scans])))
    base = [bi.spectra(sky, d["freqs"]) for d in scans]
    psky = {
        "lm": np.asarray(sky["lm"], float),
        "kind": np.asarray(sky["kind"]),
        "gauss_shape": np.asarray(sky["gauss_shape"], float),
        "base": base,
        "beamed": np.ones(len(sky["flux"]), bool),
    }
    stages["prepare"] = time.perf_counter() - mark
    prob = ps.Problem(
        prepared, psky, beam_objs[0][0], nu0, nproc=nproc, average=beam_objs[1][0]
    )
    mark = time.perf_counter()
    acc, cost = prob.survey(beam_objs)
    stages["survey"] = time.perf_counter() - mark
    log("survey", f"{stages['survey']:.1f} s", "bins", acc.bins, "samples", acc.samples)
    mark = time.perf_counter()
    nscan = len(scans)
    info = info_labels(acc, kappa)
    info_raw = info_labels(acc, {k: 1.0 for k in kappa})
    labels = bi.direction_labels(nant, nscan, len(variants), vnames)
    duration = float(sum(np.ptp(s["time"]) + 8.0 for s in scans))
    m = bi.measures_from(info, labels, nant, nscan, len(variants), duration)
    m_raw = bi.measures_from(info_raw, labels, nant, nscan, len(variants), duration)
    for rec, rr in zip(m["directions"], m_raw["directions"], strict=True):
        rec["sigma_primary_raw_weights"] = rr["sigma_primary"]
    rows = bi.summarise(m["directions"], nant)
    scan_common = per_scan_common(info, labels, nant, nscan, vnames)
    stages["measures"] = time.perf_counter() - mark
    record = {
        "set": name,
        "protocol": "research/b1-3-pointing-selfcal.md",
        "git_head": b12.git_head(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "nproc": nproc,
        "gain_nuisance": "per antenna x hand x channel x 2-dump interval",
        "variants": [list(v) for v in variants],
        "verdict_variant": VERDICT,
        "antenna_names": names,
        "holography_index": holo,
        "beam_crop_radius_deg": radius,
        "scans": [
            {
                "label": s["label"],
                "rows": len(s["a1"]),
                "channels": len(s["freqs"]),
                "freq_mhz": [float(s["freqs"][0] / 1e6), float(s["freqs"][-1] / 1e6)],
            }
            for s in scans
        ],
        "antennas": nant,
        "components": len(sky["flux"]),
        "noise": noise,
        "kappa": {f"{s},{h}": v for (s, h), v in kappa.items()},
        "gain_bins": acc.bins,
        "samples": acc.samples,
        "nu0_hz": nu0,
        "duration_s": duration,
        "directions": m["directions"],
        "verdict_rows": rows,
        "scan_common": scan_common,
    }
    # the frozen checks
    if name == "S3":
        bad = [
            d
            for d in m["directions"]
            if d["variant"] == "copolar"
            and d["raw_information"] > 0
            and (d["rho_primary"] or 0) > G3A_RHO
        ]
        rho_max = max(
            (d["rho_primary"] or 0)
            for d in m["directions"]
            if d["variant"] == "copolar" and d["raw_information"] > 0
        )
        rho_full = max(
            (d["rho_primary"] or 0)
            for d in m["directions"]
            if d["variant"] == "antenna" and d["raw_information"] > 0
        )
        record["g3a"] = {
            "rho_max_copolar": rho_max,
            "rho_max_full_jones": rho_full,
            "threshold": G3A_RHO,
            "pass": not bad,
        }
        log("G3a", record["g3a"])
    if name == "S1":
        change = {}
        for d8 in m["directions"]:
            if d8["variant"] != "antenna8" or d8["family"] != "common":
                continue
            d16 = next(
                x
                for x in m["directions"]
                if x["variant"] == "antenna"
                and x["family"] == "common"
                and x["direction"] == d8["direction"]
            )
            change[d8["direction"]] = d8["sigma_primary"] / d16["sigma_primary"] - 1
        med = {}
        for v in ("antenna", "antenna8"):
            sig = [
                x["sigma_primary"]
                for x in m["directions"]
                if x["variant"] == v
                and x["family"] == "antenna"
                and x["raw_information"] > 0
            ]
            med[v] = float(np.median(sig))
        change["per_antenna_median"] = med["antenna8"] / med["antenna"] - 1
        fired = any(abs(v) > CONVERGENCE for v in change.values() if np.isfinite(v))
        record["convergence_check"] = {
            "relative_change": change,
            "limit": CONVERGENCE,
            "fired": bool(fired),
        }
        log("convergence", record["convergence_check"])
    record["candidates"] = candidates_from(rows, scan_common, VERDICT)
    record["stages_seconds"] = stages
    record["survey_cost"] = cost
    record["wall_seconds"] = time.perf_counter() - started
    record["peak_rss_mb"] = rusage.peak_rss_mb()
    record["peak_rss_children_mb"] = (
        resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    )
    write_json(out / "survey.json", record)
    for r in rows:
        if r["variant"] in (VERDICT, "average"):
            log(
                json.dumps(
                    {
                        k: r[k]
                        for k in r
                        if k
                        in (
                            "variant",
                            "direction",
                            "sigma_primary",
                            "rho_primary",
                            "constrainable",
                            "passing",
                            "antennas",
                            "sigma_primary_median",
                            "rho_primary_median",
                            "labels",
                            "scan",
                        )
                    },
                    default=float,
                )
            )
    for r in scan_common:
        if r["variant"] == VERDICT:
            log(json.dumps(r, default=float))
    log("candidates", record["candidates"], f"{record['wall_seconds']:.0f} s")
    return record


# --------------------------------------------------------------------------
# Archive (derived numbers only)


def archive(out_json, runs):
    payload = {
        "protocol": "research/b1-3-pointing-selfcal.md",
        "part": "survey rerun",
        "note": "derived numbers only; holography beam CC BY-NC 4.0 (de Villiers 2023, "
        "doi:10.48479/wdb0-h061); ESO137 CC BY 4.0 (Ramatsoku et al. 2020)",
        "runs": {},
    }
    for run in runs:
        run = Path(run)
        rec = json.loads((run / "survey.json").read_text())
        common = [
            {
                k: d[k]
                for k in (
                    "variant",
                    "direction",
                    "sigma_primary",
                    "rho_primary",
                    "sigma_strict",
                    "rho_strict",
                    "sigma_family_marginal",
                    "sigma_primary_raw_weights",
                    "constrainable",
                    "labels",
                )
            }
            for d in rec["directions"]
            if d["family"] == "common"
        ]
        payload["runs"][run.name] = _rounded(
            {
                "set": rec["set"],
                "variants": rec["variants"],
                "noise": rec["noise"],
                "gain_bins": rec["gain_bins"],
                "samples": rec["samples"],
                "verdict_rows": rec["verdict_rows"],
                "common_directions": common,
                "scan_common": rec["scan_common"],
                "candidates": rec["candidates"],
                "g3a": rec.get("g3a"),
                "convergence_check": rec.get("convergence_check"),
                "wall_seconds": rec["wall_seconds"],
                "peak_rss_mb": rec["peak_rss_mb"],
                "peak_rss_children_mb": rec.get("peak_rss_children_mb"),
                "run": str(run.relative_to(ROOT))
                if run.is_relative_to(ROOT)
                else str(run),
            }
        )
    write_json(out_json, payload)


def _rounded(x):
    if isinstance(x, float):
        return float(f"{x:.6g}") if math.isfinite(x) else str(x)
    if isinstance(x, dict):
        return {k: _rounded(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_rounded(v) for v in x]
    return x


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("survey")
    p.add_argument("set", choices=("S1", "S2", "S3", "S4", "S5"))
    p.add_argument("out")
    p.add_argument("--pilot", default=str(ROOT / "outputs/b1-2-20261030-01-pilot"))
    p.add_argument("--track", default=str(ROOT / "outputs/b1-2-20261030-02-track"))
    p.add_argument("--field", default=str(ROOT / "outputs/b1-2-20261030-04-fieldmodel"))
    p.add_argument("--nproc", type=int, default=4)
    p = sub.add_parser("archive")
    p.add_argument("out_json")
    p.add_argument("runs", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "survey":
        survey_set(args.set, args.out, args.pilot, args.track, args.field, args.nproc)
    else:
        archive(args.out_json, args.runs)


if __name__ == "__main__":
    sys.exit(main())
