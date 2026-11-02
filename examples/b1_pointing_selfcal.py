"""B1-3 Parts 2-4: pointing self-calibration and the rang method against both
baselines at matched cost (research/b1-3-pointing-selfcal.md).

Subcommands (each writes into a fresh OUT under outputs/):

- `fixture OUT`: F1 (B1-1's G1b design, seeds 1-200) and F1r (the real
  fixture) for (i) the SARAO/SKA Gaussian fit, (ii) the holography-beam
  raster fit of every axis, R (the same with selection), and the
  array-average controls;
- `simulate F2|F3 OUT`: the frozen simulated science fields (truth, model
  and noise per scan);
- `fit SET ARM OUT`: one arm (G, ii, R) on one set (F2, F2-free, F3, S1,
  S2, S4, S5) in its own process: the profiled LM solve, the held-out
  error on the seed-7 test cells, offsets against truth (simulations), the
  faint-source fit (F2), the cost;
- `compare OUT_JSON --set NAME RUN...`: the frozen calls and the archive.

Inputs: the B1-0 holography product (CC BY-NC 4.0, de Villiers 2023, DOI
10.48479/wdb0-h061), the ESO137 fetches (CC BY 4.0, Ramatsoku et al. 2020),
the LUNO tiles, the SKA fixture `outer_scans.zip` and the Part 1 reruns.
"""

import argparse
import json
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np
from scipy import optimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b1_baselines as b11
import b1_identifiability as b12
import b1_survey_rerun as rerun
from rang import beam_holography, measures, rusage
from rang import beam_identifiability as bi
from rang import pointing_selfcal as ps

ROOT = b12.ROOT
FIXTURE = ROOT / "outputs/ska-pointing/outer_scans.zip"
PILOT = ROOT / "outputs/b1-2-20261030-01-pilot"
TRACK = ROOT / "outputs/b1-2-20261030-02-track"
FIELD = ROOT / "outputs/b1-2-20261030-04-fieldmodel"
RERUNS = {
    "S1": ROOT / "outputs/b1-3-20261030-02-rerun-S1",
    "S2": ROOT / "outputs/b1-3-20261030-05-rerun-S2",
    "S4": ROOT / "outputs/b1-3-20261030-03-rerun-S4",
    "S5": ROOT / "outputs/b1-3-20261030-04-rerun-S5",
}
SIM_FROM = {"F2": "S5", "F2-free": "S5", "F3": "S4"}
# The simulations measured under amendment 1 (per-channel beam frequency).
SIM_DIRS = {
    "F2": "outputs/b1-3-20261030-34-sim-F2",
    "F2-free": "outputs/b1-3-20261030-34-sim-F2",
    "F3": "outputs/b1-3-20261030-33-sim-F3",
}
GROUP_CHANNELS = {"F2": 4, "F2-free": 4, "F3": 2}
REAL_GROUP_CHANNELS = 32
# Frozen simulation settings (Part 3).
F2_FREQS = 900e6 + (np.arange(16) + 0.5) * 46.875e6
F2_R = 46.875e6 / 0.208984375e6
F3_BLOCK = 20
SIM_S2 = 0.512
SIM_REF_HZ = 1.4e9
SIM_ALPHA = -0.7
SEED_POINTING = 2026
SEED_GAINS = 17
SEED_NOISE = 5
SEED_FAINT = 31
POINTING_SIGMA = 0.6
GAIN_AMP_SIGMA = 0.1
# Frozen decision margins (Part 4).
RMS_BETTER, RMS_WORSE = 0.9, 1.1
COST_FACTOR = 1.5
COST_MATERIAL = 0.5
FAINT_REL = 0.2
FAINT_FLUX_ABS = 1e-3
FAINT_ALPHA_ABS = 5e-3
F1_INJECTIONS = (
    [(0, 0)]
    + [(s * v, 0) for v in (0.5, 1, 2) for s in (1, -1)]
    + [(0, s * v) for v in (0.5, 1, 2) for s in (1, -1)]
)


def log(*args):
    print(time.strftime("%H:%M:%S"), *args, flush=True)


write_json = rerun.write_json


def cost_record():
    return {
        "peak_rss_mb": rusage.peak_rss_mb(),
        "peak_rss_children_mb": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        / 1024,
    }


# --------------------------------------------------------------------------
# F1 and F1r: the fixture


def fixture(out, seeds=200):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    product = beam_holography.HolographyBeam(b12.HOLOGRAPHY)
    record = {
        "protocol": "research/b1-3-pointing-selfcal.md",
        "git_head": b12.git_head(),
    }
    # ---- F1r: end to end on the real fixture -----------------------------
    t0 = time.perf_counter()
    scans, reference, _root = b11.load_fixture(FIXTURE, out / "fixture")
    read_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    base = b11.run_baseline(scans)
    baseline_s = time.perf_counter() - t1
    x, std, freq = base["x"], base["std"], base["frequency"]
    names = [str(n) for n in reference[:, 0]]
    holo = [product.antnames.index(n) for n in names]
    i_arcmin = np.degrees(base["rows"][:, [0, 2]]) * 60
    i_sigma = np.degrees(base["rows"][:, [1, 3]]) * 60
    t2 = time.perf_counter()
    gains_y, gains_std, _ = b11.gain_amplitudes(scans)
    gain_s = time.perf_counter() - t2
    f1r = {"antennas": names, "i": {"offset_arcmin": i_arcmin, "sigma_arcmin": i_sigma}}
    walls = {
        "read_s": read_s,
        "i_end_to_end_s": read_s + baseline_s,
        "gain_solve_s": gain_s,
    }
    for arm, select in (("ii", False), ("R", True)):
        t3 = time.perf_counter()
        fits = []
        for k, h in enumerate(holo):
            rb = ps.RasterBeam(product, h, freq)
            fits.append(
                ps.fit_raster(x[:, k], gains_y[k], gains_std[k], freq, rb, select)
            )
        fit_s = time.perf_counter() - t3
        walls[f"{arm}_fit_s"] = fit_s
        walls[f"{arm}_end_to_end_s"] = read_s + gain_s + fit_s
        off = np.array([f["offset"] for f in fits])
        sig = np.array([f["sigma"] for f in fits])
        comb = np.sqrt(np.where(np.isfinite(sig), sig, 0) ** 2 + i_sigma**2)
        f1r[arm] = {
            "offset_arcmin": off,
            "sigma_arcmin": sig,
            "selected": [f["selected"] for f in fits],
            "sigma_marginal_at_zero": [f["sigma_marginal_at_zero"] for f in fits],
            "rho_at_zero": [f["rho_at_zero"] for f in fits],
            "agrees_with_i_within_combined_sigma": (
                np.abs(off - i_arcmin) <= comb
            ).tolist(),
            "difference_from_i_arcmin": off - i_arcmin,
        }
    walls["R_over_i"] = walls["R_end_to_end_s"] / walls["i_end_to_end_s"]
    walls["ii_over_i"] = walls["ii_end_to_end_s"] / walls["i_end_to_end_s"]
    walls["R_over_ii"] = walls["R_end_to_end_s"] / walls["ii_end_to_end_s"]
    f1r["cost"] = walls
    f1r["bytes_read"] = int(
        sum(s["vis"].nbytes + s["weight"].nbytes + s["flags"].nbytes for s in scans)
    )
    record["F1r"] = f1r
    log("F1r", json.dumps(walls))
    # ---- F1: B1-1's G1b design -------------------------------------------
    t4 = time.perf_counter()
    clean = {}
    for inj in F1_INJECTIONS:
        inj_deg = np.asarray(inj, float) / 60.0
        cl = np.zeros((4, len(freq), x.shape[0]))
        for k in range(4):
            pos = x[:, k] - inj_deg
            for c, f in enumerate(freq):
                j = product.jones(k, pos[:, 0], pos[:, 1], f)
                cl[k, c] = 3.0 * 0.5 * (np.abs(j[:, 0, 0]) + np.abs(j[:, 1, 1]))
        clean[inj] = cl
    setup_s = time.perf_counter() - t4
    beams = {
        "ii": [ps.RasterBeam(product, k, freq) for k in range(4)],
        "R": None,
        "ii-average": [ps.RasterBeam(product, "array_average", freq)] * 4,
    }
    beams["R"] = beams["ii"]
    beams["R-average"] = beams["ii-average"]
    arms = ("i", "ii", "R", "ii-average", "R-average")
    err = {a: [] for a in arms}
    sel = {a: [] for a in arms}
    fit_time = dict.fromkeys(arms, 0.0)
    nfits = dict.fromkeys(arms, 0)
    for inj in F1_INJECTIONS:
        for seed in range(1, seeds + 1):
            rng = np.random.default_rng(seed)
            noisy = clean[inj] + rng.normal(size=clean[inj].shape) * std
            t = time.perf_counter()
            rows, _ = b11.fit_offsets(x, noisy, std, freq)
            fit_time["i"] += time.perf_counter() - t
            nfits["i"] += 1
            err["i"].append(np.degrees(rows[:, [0, 2]]) * 60 - np.asarray(inj))
            for arm in arms[1:]:
                t = time.perf_counter()
                offs, chosen = [], []
                for k in range(4):
                    f = ps.fit_raster(
                        x[:, k],
                        noisy[k],
                        std[k],
                        freq,
                        beams[arm][k],
                        arm.startswith("R"),
                    )
                    offs.append(f["offset"])
                    chosen.append(f["selected"])
                fit_time[arm] += time.perf_counter() - t
                nfits[arm] += 1
                err[arm].append(np.array(offs) - np.asarray(inj))
                sel[arm].append(chosen)
        log("F1 injection", inj, "done")
    f1 = {
        "injections_arcmin": F1_INJECTIONS,
        "seeds": seeds,
        "truth_setup_s": setup_s,
        "arms": {},
    }
    for arm in arms:
        e = np.array(err[arm])  # (inj * seeds, 4, 2)
        ok = np.isfinite(e)
        f1["arms"][arm] = {
            "rms_error_arcmin": float(np.sqrt(np.nanmean(e**2))),
            "bias_arcmin": float(np.nanmean(e)),
            "rms_per_antenna_axis": np.sqrt(np.nanmean(e**2, axis=0)).tolist(),
            "bias_per_antenna_axis": np.nanmean(e, axis=0).tolist(),
            "valid_fraction": float(ok.mean()),
            "rms_by_injection": [
                float(np.sqrt(np.nanmean(e[i * seeds : (i + 1) * seeds] ** 2)))
                for i in range(len(F1_INJECTIONS))
            ],
            "fit_wall_s_per_fit": fit_time[arm] / nfits[arm],
            "selected_fraction": float(np.mean(sel[arm])) if sel[arm] else None,
        }
    record["F1"] = f1
    record.update(cost_record())
    write_json(out / "fixture.json", record)
    log(
        "F1",
        json.dumps(
            {
                a: (
                    f1["arms"][a]["rms_error_arcmin"],
                    f1["arms"][a]["fit_wall_s_per_fit"],
                )
                for a in arms
            }
        ),
    )
    return record


# --------------------------------------------------------------------------
# Simulations


def _pilot_weights_and_q():
    d = b12.load_eso_pilot(PILOT)
    w = []
    for _h, c in ps.HANDS:
        e = b12.eligible(d, c)
        w.append(float(np.median(d["weight"][..., c][e])))
    centre = measures.array_centre(d["positions"])
    q = measures.parallactic_angle(
        np.array([d["time"].mean()]), *d["phase_dir"], centre
    )[0]
    return d, w, float(q)


def simulate(name, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    product = beam_holography.HolographyBeam(b12.HOLOGRAPHY)
    pilot, w_med, q_pilot = _pilot_weights_and_q()
    comps = np.load(FIELD / "components.npz")
    lm_b, flux_app = np.asarray(comps["lm"], float), np.asarray(comps["flux"], float)
    avg = ps.AntennaBeams(product, [None], mode="average", radius_deg=1.6)
    x, y = measures.sky_to_beam(lm_b[:, 0], lm_b[:, 1], q_pilot)
    ib = avg.average_power(SIM_REF_HZ, np.degrees(x), np.degrees(y))
    s0_b = flux_app / ib
    alpha_b = np.full(len(s0_b), SIM_ALPHA)
    if name == "F2":
        scans_t = b12.load_eso_track(TRACK)
        freqs = F2_FREQS
        r_factor = F2_R

        def eligibility(d):
            return np.stack(
                [b12.eligible(d, c)[:, 8 * np.arange(16)] for _h, c in ps.HANDS], -1
            )

        lobes = b12.first_null_radius(product, SIM_REF_HZ)
        rng = np.random.default_rng(SEED_FAINT)
        r_out = rng.uniform(lobes["r_half_power_deg"], lobes["r_first_null_deg"], 20)
        r_core = rng.uniform(0.3, lobes["r_half_power_deg"], 20)
        r = np.r_[r_out, r_core]
        pa = rng.uniform(0, 2 * np.pi, 40)
        lm_f = np.radians(np.stack((r * np.sin(pa), r * np.cos(pa)), 1))
        s0_f = 10 ** rng.uniform(-4, -3, 40)
        alpha_f = rng.normal(SIM_ALPHA, 0.2, 40)
    else:
        scans_t = [pilot]
        nb = len(pilot["freqs"]) // F3_BLOCK
        freqs = pilot["freqs"][: nb * F3_BLOCK].reshape(nb, F3_BLOCK).mean(1)
        r_factor = float(F3_BLOCK)
        lobes = None

        def eligibility(d):
            first = F3_BLOCK * np.arange(nb)
            return np.stack([b12.eligible(d, c)[:, first] for _h, c in ps.HANDS], -1)

        lm_f = np.zeros((0, 2))
        s0_f = np.zeros(0)
        alpha_f = np.zeros(0)
    nant = len(scans_t[0]["positions"])
    names = rerun.eso_names()
    holo = [product.antnames.index(n) for n in names]
    beams = ps.AntennaBeams(product, holo, radius_deg=1.6 if name == "F2" else 0.6)
    lm = np.r_[lm_b, lm_f]
    s0 = np.r_[s0_b, s0_f]
    alpha = np.r_[alpha_b, alpha_f]
    base = [s0[:, None] * (freqs[None] / SIM_REF_HZ) ** alpha[:, None] for _ in scans_t]
    rng_p = np.random.default_rng(SEED_POINTING)
    delta = rng_p.normal(0, POINTING_SIGMA, (len(scans_t), nant, 2))
    rng_g = np.random.default_rng(SEED_GAINS)
    shape = (len(scans_t), len(freqs), 2, nant)
    gains = np.exp(rng_g.normal(0, GAIN_AMP_SIGMA, shape)) * np.exp(
        1j * rng_g.uniform(0, 2 * np.pi, shape)
    )
    sims = []
    for d in scans_t:
        e = eligibility(d)
        sd = {
            "a1": d["a1"],
            "a2": d["a2"],
            "time": d["time"],
            "uvw": d["uvw"],
            "freqs": freqs,
            "positions": d["positions"],
            "phase_dir": d["phase_dir"],
            "data": np.zeros((len(d["a1"]), len(freqs), 4), np.complex64),
            "flag": np.ones((len(d["a1"]), len(freqs), 4), bool),
            "weight": np.zeros((len(d["a1"]), len(freqs), 4), np.float32),
        }
        for h, c in ps.HANDS:
            sd["flag"][..., c] = ~e[..., h]
            sd["weight"][..., c] = w_med[h] * r_factor
        sims.append(sd)
    prepared = [ps.prepare_scan(sd, [SIM_S2, SIM_S2]) for sd in sims]
    sky = {
        "lm": lm,
        "kind": np.zeros(len(lm), np.uint8),
        "gauss_shape": np.zeros((len(lm), 3)),
        "base": base,
        "beamed": np.ones(len(lm), bool),
    }
    prob = ps.Problem(
        prepared,
        sky,
        beams,
        float(np.mean(freqs)),
        nproc=4,
        extra={"truth_gains": list(gains)},
        beam_width=1,
    )
    jobs = [(s, f, {"delta": delta[s]}, None, "predict") for s, f in prob.tasks]
    t = time.perf_counter()
    results = prob.map(jobs)
    prob.close()
    predict_s = time.perf_counter() - t
    rng_n = np.random.default_rng(SEED_NOISE)
    for s, sd in enumerate(sims):
        model = np.zeros((len(sd["a1"]), len(freqs), 2), np.complex64)
        for r in results:
            if r["scan"] == s:
                ch = np.arange(
                    r["block"] * ps.BLOCK, r["block"] * ps.BLOCK + r["pred"].shape[1]
                )
                model[:, ch] = r["pred"]
        sig = np.sqrt(SIM_S2 / (np.asarray(w_med) * r_factor))
        noise = (
            rng_n.normal(size=model.shape) + 1j * rng_n.normal(size=model.shape)
        ) * sig[None, None, :]
        np.savez(
            out / f"scan{s}.npz",
            a1=sd["a1"],
            a2=sd["a2"],
            time=sd["time"],
            uvw=sd["uvw"],
            freqs=freqs,
            positions=sd["positions"],
            phase_dir=sd["phase_dir"],
            flag=sd["flag"],
            weight=sd["weight"],
            model=model,
            noise=noise.astype(np.complex64),
        )
    truth = {
        "set": name,
        "protocol": "research/b1-3-pointing-selfcal.md",
        "git_head": b12.git_head(),
        "scans": len(sims),
        "freqs_hz": freqs,
        "r_factor": r_factor,
        "s2": SIM_S2,
        "median_weight_s4": w_med,
        "q_pilot_rad": q_pilot,
        "lobes_1p4ghz": lobes,
        "seeds": {
            "pointing": SEED_POINTING,
            "gains": SEED_GAINS,
            "noise": SEED_NOISE,
            "faint": SEED_FAINT,
        },
        "delta_arcmin": delta,
        "bright": {"lm": lm_b, "s0_jy": s0_b, "alpha": alpha_b},
        "faint": {
            "lm": lm_f,
            "s0_jy": s0_f,
            "alpha": alpha_f,
            "group": ["outer"] * 20 + ["core"] * 20 if len(s0_f) else [],
        },
        "antenna_names": names,
        "predict_s": predict_s,
        "wall_s": time.perf_counter() - started,
        **cost_record(),
    }
    np.save(out / "gains.npy", gains)
    write_json(out / "truth.json", truth)
    log("simulated", name, f"{truth['wall_s']:.0f} s")


def load_sim(sim_dir, noisy=True):
    sim_dir = Path(sim_dir)
    truth = json.loads((sim_dir / "truth.json").read_text())
    scans = []
    for s in range(truth["scans"]):
        z = np.load(sim_dir / f"scan{s}.npz")
        data = np.zeros(z["flag"].shape, np.complex64)
        vis = z["model"] + (z["noise"] if noisy else 0)
        data[..., 0] = vis[..., 0]
        data[..., 3] = vis[..., 1]
        scans.append(
            {
                "label": f"{truth['set']} scan {s}",
                "a1": z["a1"],
                "a2": z["a2"],
                "time": z["time"],
                "uvw": z["uvw"],
                "freqs": z["freqs"],
                "positions": z["positions"],
                "phase_dir": z["phase_dir"],
                "data": data,
                "flag": z["flag"],
                "weight": z["weight"],
            }
        )
    return scans, truth


# --------------------------------------------------------------------------
# One arm on one set


def candidates_for(name):
    real = SIM_FROM.get(name, name)
    rec = json.loads((RERUNS[real] / "survey.json").read_text())
    cand = set(rec["candidates"])
    if "common_pointing" in cand:
        cand.add("interval_common")
    cand.discard("common_pointing")
    if real in ("S1", "S2"):
        cand &= {"antenna", "squint"}
    return sorted(cand), str(RERUNS[real].relative_to(ROOT))


def intrinsic_base(scans, sky, avg, q_mean):
    """Base spectra of the fit model: apparent spectrum / array-average I_b
    at the component (mean q), for components with I_b >= 0.01 at the
    set's lowest and highest frequency ("beamed"); apparent otherwise."""
    x, y = measures.sky_to_beam(sky["lm"][:, 0], sky["lm"][:, 1], q_mean)
    xd, yd = np.degrees(x), np.degrees(y)
    fmin = min(d["freqs"].min() for d in scans)
    fmax = max(d["freqs"].max() for d in scans)
    beamed = (avg.average_power(fmin, xd, yd) >= bi.IB_FLOOR) & (
        avg.average_power(fmax, xd, yd) >= bi.IB_FLOOR
    )
    bases = []
    for d in scans:
        app = bi.spectra(sky, d["freqs"])
        ib = np.array([avg.average_power(f, xd, yd) for f in d["freqs"]]).T
        bases.append(np.where(beamed[:, None], app / ib, app))
    return bases, beamed


def elevation(d):
    from astropy import units
    from astropy.coordinates import AltAz, SkyCoord
    from astropy.time import Time

    when = Time(np.mean(d["time"]) / 86400.0, format="mjd", scale="utc")
    site = measures.location(measures.array_centre(d["positions"]))
    src = SkyCoord(
        d["phase_dir"][0] * units.rad, d["phase_dir"][1] * units.rad, frame="icrs"
    )
    return float(src.transform_to(AltAz(obstime=when, location=site)).alt.deg)


def fit(name, arm, out, fit_beam="antenna", nproc=4, max_passes=ps.LM_MAX_PASSES):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    stages = {}
    truth = None
    product = beam_holography.HolographyBeam(b12.HOLOGRAPHY)
    if name.startswith("F"):
        sim_dir = ROOT / SIM_DIRS[name]
        scans, truth = load_sim(sim_dir, noisy=name != "F2-free")
        names = truth["antenna_names"]
        s2s = [[truth["s2"], truth["s2"]] for _ in scans]
        lm_b = np.asarray(truth["bright"]["lm"], float)
        sky = {
            "lm": lm_b,
            "kind": np.zeros(len(lm_b), np.uint8),
            "gauss_shape": np.zeros((len(lm_b), 3)),
        }
        s0 = np.asarray(truth["bright"]["s0_jy"])
        al = np.asarray(truth["bright"]["alpha"])
        bases = [
            s0[:, None] * (d["freqs"][None] / SIM_REF_HZ) ** al[:, None] for d in scans
        ]
        beamed = np.ones(len(lm_b), bool)
        gauge_flux = s0
        group = GROUP_CHANNELS[name]
    else:
        scans, sky_src = rerun.load_set(name, PILOT, TRACK, FIELD)
        names = rerun.names_for(name, len(scans[0]["positions"]))
        s2s = []
        for d in scans:
            nz = b12.noise_for(d)
            s2s.append([nz[0]["s2"], nz[1]["s2"]])
        sky = {
            k: sky_src[k]
            for k in ("lm", "kind", "gauss_shape", "flux", "coeffs", "ref_freq")
        }
        group = REAL_GROUP_CHANNELS
    stages["load"] = time.perf_counter() - started
    mark = time.perf_counter()
    holo = [product.antnames.index(n) for n in names]
    crop_lm = sky["lm"]
    if truth is not None and len(truth["faint"]["s0_jy"]):
        # the faint-source fit evaluates the fitted beams at the faint positions
        crop_lm = np.r_[crop_lm, np.asarray(truth["faint"]["lm"], float)]
    radius = rerun.component_radius_deg({"lm": crop_lm})
    beams = ps.AntennaBeams(product, holo, mode=fit_beam, radius_deg=radius)
    elig = [ps.eligible_both(d) for d in scans]
    bins = [ps.scan_bins(d) for d in scans]
    split = ps.split_cells(
        [(e, tb, bl) for e, (tb, bl) in zip(elig, bins, strict=True)], group
    )
    prepared = [
        ps.prepare_scan(d, s2, tr, te)
        for d, s2, (tr, _va, te) in zip(scans, s2s, split, strict=True)
    ]
    nu0 = float(np.mean(np.concatenate([d["freqs"] for d in scans])))
    if not name.startswith("F"):
        q_all = np.concatenate([p["q"] for p in prepared])
        q_mean = float(np.angle(np.mean(np.exp(1j * q_all))))
        bases, beamed = intrinsic_base(scans, sky, beams, q_mean)
        gauge_flux = bi.spectra(sky, np.array([nu0]))[:, 0]
    psky = {
        "lm": np.asarray(sky["lm"], float),
        "kind": np.asarray(sky["kind"]),
        "gauss_shape": np.asarray(sky["gauss_shape"], float),
        "base": bases,
        "beamed": beamed,
        "gauge_flux": gauge_flux,
    }
    extra = {}
    if name == "F2" or name == "F2-free":
        extra["faint_sky"] = {"lm": np.asarray(truth["faint"]["lm"], float)}
    prob = ps.Problem(
        prepared,
        psky,
        beams,
        nu0,
        nproc=nproc,
        extra=extra,
        beam_width=1 if name.startswith("F") else ps.SUB,
    )
    stages["prepare"] = time.perf_counter() - mark
    cand, cand_from = candidates_for(name) if arm == "R" else ([], None)
    log(
        "set",
        name,
        "arm",
        arm,
        "beam",
        fit_beam,
        "candidates",
        cand,
        "rows",
        [len(d["a1"]) for d in scans],
    )
    res = ps.solve(prob, arm, cand, log=log, max_passes=max_passes)
    log("solved", arm, f"{res['solver_wall_s']:.1f} s", "passes", res["passes"])
    mark = time.perf_counter()
    keys, vals = ps.heldout(prob, res)
    np.savez(out / "heldout.npz", keys=keys, values=vals.astype(np.float64))
    stages["heldout_eval"] = time.perf_counter() - mark
    record = {
        "set": name,
        "arm": arm,
        "fit_beam": fit_beam,
        "protocol": "research/b1-3-pointing-selfcal.md",
        "git_head": b12.git_head(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "nproc": nproc,
        "candidates": cand,
        "candidates_from": cand_from,
        "antennas": len(names),
        "components": len(psky["lm"]),
        "beamed": int(np.sum(beamed)),
        "rows": [len(d["a1"]) for d in scans],
        "channels": [len(d["freqs"]) for d in scans],
        "s2": s2s,
        "split_group_channels": group,
        "split_cells": {
            "train": int(sum(s[0].sum() for s in split)),
            "validation": int(sum(s[1].sum() for s in split)),
            "test": int(sum(s[2].sum() for s in split)),
        },
        "heldout": {"cells": len(vals), "mse": float(vals.mean())},
        "chi2_train": res["chi2"],
        "objective": res["objective"],
        "passes": res["passes"],
        "rejected_outside_beam_grid": res["rejected_outside_beam_grid"],
        "accepted": res["accepted"],
        "rejected": res["rejected"],
        "history": res["history"],
        "solver_wall_s": res["solver_wall_s"],
        "free_parameters": res["free_parameters"],
        "free_beam_parameters": res["free_beam_parameters"],
        "gain_bin_solves": res["solves"],
        "stefcal_iterations": res["stefcal_iterations"],
        "pass_walls_s": [p["wall_s"] for p in prob.passes],
        "bytes_data": int(
            sum(d["data"].nbytes + d["weight"].nbytes + d["flag"].nbytes for d in scans)
        ),
        "delta_arcmin": [dd.tolist() for dd in res["state"]["delta"]],
        "sigma_delta_arcmin": [],
        "squint_arcmin": res["state"]["squint"].tolist(),
        "ellipticity": res["state"]["ellip"],
        "active": [a.tolist() for a in res["active"]],
        "q_mean_rad_per_scan": [
            float(np.angle(np.mean(np.exp(1j * p["q"])))) for p in prepared
        ],
        "time_mean_per_scan": [float(np.mean(d["time"])) for d in scans],
    }
    nant = len(names)
    if res["arm"] != "G":
        st = res["sigma_theta"]
        n2 = 2 * nant
        record["sigma_delta_arcmin"] = [
            np.stack(
                (st[s * n2 : s * n2 + nant], st[s * n2 + nant : (s + 1) * n2]), 1
            ).tolist()
            for s in range(len(scans))
        ]
        if res["state"]["ncom"]:
            record["sigma_squint_ellipticity"] = st[len(scans) * n2 :].tolist()
    if res["selection"]:
        sel = res["selection"]
        record["selection"] = {
            "antenna_selected": int(sum(r["selected"] for r in sel["antenna"])),
            "antenna_candidates": len(sel["antenna"]),
            "antenna_records": sel["antenna"],
            "common_records": sel["common"],
        }
    try:
        record["elevation_deg_per_scan"] = [elevation(d) for d in scans]
    except ImportError as exc:  # pragma: no cover - astropy missing
        record["elevation_error"] = str(exc)
    if truth is not None:
        tdelta = np.asarray(truth["delta_arcmin"], float)
        err = []
        for s in range(len(scans)):
            act = res["active"][s]
            err.append((res["state"]["delta"][s] - tdelta[s])[act])
        err = np.concatenate(err)
        record["offsets"] = {
            "rms_error_arcmin": float(np.sqrt(np.mean(err**2))),
            "bias_arcmin": float(np.mean(err)),
            "bias_per_axis": err.mean(0).tolist(),
            "rms_per_axis": np.sqrt((err**2).mean(0)).tolist(),
            "n": int(err.size),
            "truth_rms_arcmin": float(np.sqrt(np.mean(tdelta**2))),
        }
        if name in ("F2", "F2-free"):
            mark = time.perf_counter()
            record["faint"] = faint_fit(prob, res, truth)
            stages["faint_eval"] = time.perf_counter() - mark
    prob.close()
    record["stages_seconds"] = stages
    record["wall_seconds"] = time.perf_counter() - started
    record.update(cost_record())
    write_json(out / "arm.json", record)
    log(
        "done",
        name,
        arm,
        "heldout mse",
        record["heldout"]["mse"],
        "offsets",
        record.get("offsets"),
    )
    return record


def faint_fit(prob, res, truth):
    """Linear per-channel fluxes of the 40 faint sources on the residual with
    the arm's beam and gains, then S0 and alpha by a weighted power-law fit."""
    results = prob.evaluate(res["state"], res["gains"], "faint")
    nchan = len(prob.scans[0]["freqs"])
    nf = len(truth["faint"]["s0_jy"])
    h = np.zeros((nchan, nf, nf))
    b = np.zeros((nchan, nf))
    for r in results:
        ch = np.arange(
            r["block"] * ps.BLOCK, r["block"] * ps.BLOCK + r["faint"]["h"].shape[0]
        )
        h[ch] += r["faint"]["h"]
        b[ch] += r["faint"]["b"]
    s = np.zeros((nchan, nf))
    sig = np.zeros((nchan, nf))
    for c in range(nchan):
        inv = bi.pinv_psd(h[c])
        s[c] = inv @ b[c]
        sig[c] = np.sqrt(np.clip(np.diag(inv), 0, None))
    freqs = prob.scans[0]["freqs"]
    s0_t = np.asarray(truth["faint"]["s0_jy"])
    al_t = np.asarray(truth["faint"]["alpha"])
    rec = []
    for j in range(nf):
        ok = np.isfinite(sig[:, j]) & (sig[:, j] > 0)

        def resid(p, j=j, ok=ok):
            return (s[ok, j] - p[0] * (freqs[ok] / SIM_REF_HZ) ** p[1]) / sig[ok, j]

        p = optimize.least_squares(resid, [max(np.median(s[ok, j]), 1e-6), SIM_ALPHA]).x
        rec.append(
            {
                "s0": float(p[0]),
                "alpha": float(p[1]),
                "ratio_minus_1": float(p[0] / s0_t[j] - 1),
                "alpha_error": float(p[1] - al_t[j]),
                "group": truth["faint"]["group"][j],
                "sigma_s_median": float(np.median(sig[ok, j])),
            }
        )
    out = {"sources": rec}
    for grp in ("all", "outer", "core"):
        sel = [r for r in rec if grp == "all" or r["group"] == grp]
        out[f"median_abs_ratio_minus_1_{grp}"] = float(
            np.median([abs(r["ratio_minus_1"]) for r in sel])
        )
        out[f"median_abs_alpha_error_{grp}"] = float(
            np.median([abs(r["alpha_error"]) for r in sel])
        )
    return out


# --------------------------------------------------------------------------
# Calls (Part 4)


def consistency(rec):
    """S5 self-consistency diagnostics (frozen, not in the call) from one
    arm's per-scan offsets: per antenna and axis the chi^2/dof of the seven
    offsets about their weighted mean in the antenna frame and, rotated to
    the sky frame, there; and regressions of the per-scan common mode on
    elevation and on (cos q, sin q)."""
    from scipy import stats

    delta = np.asarray(rec["delta_arcmin"], float)  # (scan, N, 2)
    sig = np.asarray(rec["sigma_delta_arcmin"], float)
    act = np.asarray(rec["active"], bool)
    q = np.asarray(rec["q_mean_rad_per_scan"], float)
    el = np.asarray(rec.get("elevation_deg_per_scan", [np.nan] * len(q)), float)
    c, s = np.cos(q)[:, None], np.sin(q)[:, None]
    sky = np.stack(
        (-c * delta[..., 0] + s * delta[..., 1], s * delta[..., 0] + c * delta[..., 1]),
        -1,
    )
    var = sig**2
    var_sky = np.stack(
        (
            c**2 * var[..., 0] + s**2 * var[..., 1],
            s**2 * var[..., 0] + c**2 * var[..., 1],
        ),
        -1,
    )

    def chi2(o, v, m):
        out = []
        for p in range(o.shape[1]):
            ok = m[:, p] & (v[:, p] > 0).all(-1)
            if ok.sum() < 3:
                out.append(np.nan)
                continue
            tot = 0.0
            for j in range(2):
                w = 1 / v[ok, p, j]
                mean = np.sum(w * o[ok, p, j]) / np.sum(w)
                tot += np.sum(w * (o[ok, p, j] - mean) ** 2)
            out.append(tot / (2 * (ok.sum() - 1)))
        return np.array(out)

    ca = chi2(delta, var, act)
    cs = chi2(sky, var_sky, act)
    good = np.isfinite(ca) & np.isfinite(cs)
    out = {
        "antennas": int(good.sum()),
        "chi2_dof_antenna_frame_median": float(np.median(ca[good])),
        "chi2_dof_sky_frame_median": float(np.median(cs[good])),
        "antennas_lower_in_sky_frame": int(np.sum(cs[good] < ca[good])),
        "chi2_dof_antenna_frame": ca.tolist(),
        "chi2_dof_sky_frame": cs.tolist(),
    }
    # per-scan common mode (mean over active antennas) and its sigma
    common, csig = [], []
    for k in range(len(q)):
        a = act[k]
        common.append(delta[k, a].mean(0))
        csig.append(np.sqrt((sig[k, a] ** 2).sum(0)) / a.sum())
    common, csig = np.array(common), np.array(csig)
    out["common_mode_arcmin"] = common.tolist()
    out["common_mode_sigma_arcmin"] = csig.tolist()
    regs = {}
    for j, axis in enumerate(("x", "y")):
        y = common[:, j]
        w = 1 / np.maximum(csig[:, j], 1e-12) ** 2
        designs = {
            "constant": np.ones((len(q), 1)),
            "elevation": np.stack((np.ones(len(q)), el), 1),
            "sky_frame": np.stack((np.ones(len(q)), np.cos(q), np.sin(q)), 1),
        }
        res = {}
        for name, a in designs.items():
            if not np.all(np.isfinite(a)):
                continue
            sw = np.sqrt(w)
            coef = np.linalg.lstsq(a * sw[:, None], y * sw, rcond=None)[0]
            res[name] = {
                "coefficients": coef.tolist(),
                "chi2": float(np.sum(w * (y - a @ coef) ** 2)),
                "dof": len(q) - a.shape[1],
            }
        c0 = res["constant"]
        for name in ("elevation", "sky_frame"):
            if name in res:
                r = res[name]
                dk = c0["dof"] - r["dof"]
                fstat = ((c0["chi2"] - r["chi2"]) / dk) / max(
                    r["chi2"] / r["dof"], 1e-300
                )
                r["f_test_p"] = float(stats.f.sf(fstat, dk, r["dof"]))
        regs[axis] = res
    out["common_mode_regressions"] = regs
    return out


def load_arm(run):
    run = Path(run)
    rec = json.loads((run / "arm.json").read_text())
    z = np.load(run / "heldout.npz")
    rec["_keys"], rec["_vals"] = z["keys"], z["values"]
    rec["_run"] = str(run.relative_to(ROOT)) if run.is_relative_to(ROOT) else str(run)
    return rec


def heldout_call(a, b):
    if not np.array_equal(a["_keys"], b["_keys"]):
        common, ia, ib = np.intersect1d(a["_keys"], b["_keys"], return_indices=True)
        out = ps.paired(a["_vals"][ia], b["_vals"][ib])
        out["matched_cells"] = len(common)
        return out
    return ps.paired(a["_vals"], b["_vals"])


def rms_call(a, b):
    ra, rb = a["offsets"]["rms_error_arcmin"], b["offsets"]["rms_error_arcmin"]
    r = ra / rb
    return {
        "ratio": r,
        "rms_R": ra,
        "rms_B": rb,
        "call": "better"
        if r < RMS_BETTER
        else ("worse" if r > RMS_WORSE else "within"),
    }


def faint_call(a, b):
    out = {"call": "within"}
    worse = better = False
    for key, floor in (
        ("median_abs_ratio_minus_1_all", FAINT_FLUX_ABS),
        ("median_abs_alpha_error_all", FAINT_ALPHA_ABS),
    ):
        va, vb = a["faint"][key], b["faint"][key]
        out[key] = [va, vb]
        if va <= (1 - FAINT_REL) * vb and vb - va >= floor:
            better = True
        if va >= (1 + FAINT_REL) * vb and va - vb >= floor:
            worse = True
    out["call"] = "worse" if worse else ("better" if better else "within")
    return out


def set_call(metrics, cost_ratio):
    """The frozen per-set label: "worse" if any applicable metric is worse
    or the wall ratio exceeds 1.5; "beats" if held-out and offsets (where
    applicable) are better, metric 3 (F2) being a veto only (not worse);
    "matches" otherwise."""
    calls = {k: m["call"] for k, m in metrics.items()}
    if cost_ratio > COST_FACTOR or "worse" in calls.values():
        return "worse"
    required = [c for k, c in calls.items() if k != "faint"]
    if required and all(c == "better" for c in required):
        return "beats"
    return "matches"


def compare(out_json, sets, rerun_runs=()):
    """sets: {set name: {arm: run dir}}; plus the fixture run under "F1".
    `rerun_runs`: the Part 1 rerun directories, archived alongside."""
    payload = {
        "protocol": "research/b1-3-pointing-selfcal.md",
        "note": "derived numbers only; holography beam CC BY-NC 4.0 (de Villiers 2023, doi:10.48479/wdb0-h061); ESO137 CC BY 4.0 (Ramatsoku et al. 2020)",
        "sets": {},
    }
    for name, runs in sets.items():
        if name == "F1":
            fx = json.loads((Path(runs) / "fixture.json").read_text())
            arms = fx["F1"]["arms"]
            cost = fx["F1r"]["cost"]
            entry = {
                "F1": {
                    a: {
                        k: arms[a][k]
                        for k in (
                            "rms_error_arcmin",
                            "bias_arcmin",
                            "valid_fraction",
                            "fit_wall_s_per_fit",
                            "selected_fraction",
                            "rms_by_injection",
                        )
                    }
                    for a in arms
                },
                "F1r": {k: fx["F1r"][k] for k in ("antennas", "cost", "bytes_read")}
                | {
                    a: {kk: fx["F1r"][a][kk] for kk in fx["F1r"][a]}
                    for a in ("i", "ii", "R")
                },
            }
            calls = {}
            for base in ("i", "ii"):
                r = arms["R"]["rms_error_arcmin"] / arms[base]["rms_error_arcmin"]
                m = {
                    "offsets": {
                        "ratio": r,
                        "call": "better"
                        if r < RMS_BETTER
                        else ("worse" if r > RMS_WORSE else "within"),
                    }
                }
                cr = cost["R_end_to_end_s"] / cost[f"{base}_end_to_end_s"]
                calls[base] = {"metrics": m, "cost_ratio": cr, "call": set_call(m, cr)}
            entry["calls"] = calls
            payload["sets"]["F1"] = entry
            continue
        arms = {a: load_arm(r) for a, r in runs.items()}
        entry = {"arms": {}}
        for a, rec in arms.items():
            entry["arms"][a] = {
                k: rec[k]
                for k in (
                    "solver_wall_s",
                    "passes",
                    "accepted",
                    "rejected",
                    "free_parameters",
                    "free_beam_parameters",
                    "gain_bin_solves",
                    "stefcal_iterations",
                    "peak_rss_mb",
                    "peak_rss_children_mb",
                    "heldout",
                    "chi2_train",
                    "bytes_data",
                    "candidates",
                )
                if k in rec
            }
            entry["arms"][a]["run"] = rec["_run"]
            for k in ("offsets", "selection", "squint_arcmin", "ellipticity"):
                if k in rec:
                    entry["arms"][a][k] = (
                        rec[k]
                        if k != "selection"
                        else {
                            kk: rec[k][kk]
                            for kk in ("antenna_selected", "antenna_candidates")
                        }
                        | {
                            "common": [
                                c for c in rec[k]["common_records"] if c["selected"]
                            ]
                        }
                    )
            if "faint" in rec:
                entry["arms"][a]["faint"] = {
                    k: v for k, v in rec["faint"].items() if k != "sources"
                }
                entry["arms"][a]["faint_sources"] = rec["faint"]["sources"]
            if name in ("S5", "F2") and a in ("ii", "R"):
                entry["arms"][a]["self_consistency"] = consistency(rec)
        calls = {}
        for base in ("ii", "G"):
            if base not in arms or "R" not in arms:
                continue
            m = {"heldout": heldout_call(arms["R"], arms[base])}
            if "offsets" in arms["R"] and base == "ii":
                m["offsets"] = rms_call(arms["R"], arms[base])
            cr = arms["R"]["solver_wall_s"] / arms[base]["solver_wall_s"]
            calls[base] = {"metrics": m, "cost_ratio": cr, "call": set_call(m, cr)}
        if "ii" in arms and "G" in arms:
            m = {"heldout": heldout_call(arms["ii"], arms["G"])}
            calls["ii_vs_G"] = {"metrics": m}
        entry["calls"] = calls
        payload["sets"][name] = entry
    # metric 3 is called on the noise-free twin and belongs to F2's call
    if "F2" in payload["sets"] and "F2-free" in payload["sets"]:
        free = {a: load_arm(r) for a, r in sets["F2-free"].items()}
        f2 = payload["sets"]["F2"]["calls"]
        for base in ("ii", "G"):
            if base in f2 and base in free and "R" in free:
                f2[base]["metrics"]["faint"] = faint_call(free["R"], free[base])
                f2[base]["call"] = set_call(f2[base]["metrics"], f2[base]["cost_ratio"])
        payload["sets"]["F2-free"]["role"] = (
            "noise-free twin of F2 (metric 3); not a separate call"
        )
    payload["overall"] = overall(payload["sets"])
    if rerun_runs:
        tmp = Path(out_json).with_suffix(".rerun.json")
        rerun.archive(tmp, rerun_runs)
        payload["survey_rerun"] = json.loads(tmp.read_text())
        tmp.unlink()
    write_json(out_json, rerun._rounded(payload))
    log("overall", payload["overall"])
    return payload


def overall(sets):
    """The frozen overall rule (Part 4)."""
    eso = [s for s in ("F2", "F3", "S4", "S5") if s in sets]
    vs_ii = {
        s: sets[s]["calls"].get("ii")
        for s in sets
        if s not in ("F1", "F2-free")
        and not s.endswith("-average")
        and "ii" in sets[s]["calls"]
    }
    improves = any(
        any(
            vs_ii[s]["metrics"][m]["call"] == "better"
            for m in ("heldout", "faint")
            if m in vs_ii[s]["metrics"]
        )
        for s in eso
        if s in vs_ii
    )
    worse23 = any(
        any(
            c["metrics"][m]["call"] == "worse"
            for m in ("heldout", "faint")
            if m in c["metrics"]
        )
        for c in vs_ii.values()
    )
    m1_ok = all(
        c["metrics"]["offsets"]["call"] != "worse"
        for c in vs_ii.values()
        if "offsets" in c["metrics"]
    )
    cost_ok = all(c["cost_ratio"] <= COST_FACTOR for c in vs_ii.values())
    f1 = sets.get("F1", {}).get("calls", {})
    f1_ii_ok = (
        f1.get("ii", {}).get("metrics", {}).get("offsets", {}).get("call") != "worse"
    )
    f1_i_ok = (
        f1.get("i", {}).get("metrics", {}).get("offsets", {}).get("call") != "worse"
    )
    rule1 = improves and not worse23 and m1_ok and f1_ii_ok and cost_ok
    positive = rule1 and f1_i_ok
    labels = {s: c["call"] for s, c in vs_ii.items()}
    cost_branch = all(lab == "matches" for lab in labels.values()) and all(
        c["cost_ratio"] <= COST_MATERIAL for c in vs_ii.values()
    )
    negative = any(labels.get(s) == "worse" for s in eso)
    result = (
        "positive"
        if positive
        else (
            "positive (cost)"
            if cost_branch
            else ("negative" if negative else "matched")
        )
    )
    return {
        "result": result,
        "b1_closes_null": result not in ("positive", "positive (cost)"),
        "per_set_vs_ii": labels,
        "per_set_vs_G": {
            s: sets[s]["calls"]["G"]["call"]
            for s in sets
            if s not in ("F1", "F2-free")
            and not s.endswith("-average")
            and "G" in sets[s]["calls"]
        },
        "F1": {b: f1.get(b, {}).get("call") for b in ("i", "ii")},
        "clauses": {
            "metric_2_or_3_better_on_an_eso137_set": improves,
            "metric_2_or_3_worse_anywhere": worse23,
            "metric_1_no_worse_on_simulations": m1_ok and f1_ii_ok,
            "cost_within_1p5_everywhere": cost_ok,
            "metric_1_no_worse_than_i_on_F1": f1_i_ok,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fixture")
    p.add_argument("out")
    p.add_argument("--seeds", type=int, default=200)
    p = sub.add_parser("simulate")
    p.add_argument("set", choices=("F2", "F3"))
    p.add_argument("out")
    p = sub.add_parser("fit")
    p.add_argument("set", choices=("F2", "F2-free", "F3", "S1", "S2", "S4", "S5"))
    p.add_argument("arm", choices=("G", "ii", "R"))
    p.add_argument("out")
    p.add_argument("--fit-beam", choices=("antenna", "average"), default="antenna")
    p.add_argument("--nproc", type=int, default=4)
    p.add_argument(
        "--max-passes", type=int, default=ps.LM_MAX_PASSES, help="smoke runs only"
    )
    p = sub.add_parser("compare")
    p.add_argument("out_json")
    p.add_argument("spec", help="JSON file {set: {arm: run dir}} (and F1: fixture run)")
    args = parser.parse_args(argv)
    if args.command == "fixture":
        fixture(args.out, args.seeds)
    elif args.command == "simulate":
        simulate(args.set, args.out)
    elif args.command == "fit":
        fit(args.set, args.arm, args.out, args.fit_beam, args.nproc, args.max_passes)
    else:
        spec = json.loads(Path(args.spec).read_text())
        rerun_runs = [ROOT / r for r in spec.pop("rerun", [])]
        sets = {
            k: (
                {a: ROOT / r for a, r in v.items()} if isinstance(v, dict) else ROOT / v
            )
            for k, v in spec.items()
        }
        compare(args.out_json, sets, rerun_runs)


if __name__ == "__main__":
    sys.exit(main())
