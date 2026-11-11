"""F-SIM: simulated MeerKAT L-band scans with RFI of known mask (task F2,
research/f2-flagger.md, section 4).

Built from `rang.simtruth` (Jones, sky, corruption, noise law, A1's RFI
events and their baseline geometry), on LUNO's window: 2,048 channels of
208.984 kHz over 1070-1498 MHz, 8 s dumps. Scans F (J1939-6342), G (gain
calibrator) and T (target, two scans); the polcal field is not simulated.
F2's extra RFI morphologies (narrowband carriers, antenna-local and
single-baseline carriers, a pulsed comb and, in test observations only,
drifting carriers) come from their own seed. Every cell whose RFI amplitude
`A = max_c |RFI_c| / sigma` is under 0.1 gets RFI 0 exactly; the truth mask
is `A > 0`.
"""

import dataclasses
import json
import math
from pathlib import Path

import numpy as np

from . import simtruth as st

CHAN_WIDTH = 208984.375
FMIN = 856e6 + 1024 * CHAN_WIDTH  # 1070.0 MHz, channel 1024 of the 4k L-band
FMAX = 856e6 + 3072 * CHAN_WIDTH  # 1498.0 MHz
NCHAN = 2048
SEQUENCE = "FGTGT"
LENGTHS = {"F": 32, "G": 16, "T": 32, "X": 0}
FIELD_OF = {"F": 0, "G": 2, "T": 3}
CORR_TYPE = np.array([9, 10, 11, 12], np.int32)
CHUNK_DUMPS = 4
FLOOR = 0.1  # RFI below FLOOR * sigma (max over correlations) is set to 0

# Frozen in research/f2-flagger.md, section 4. Seeds are registered in
# rang.simtruth.SEEDS.
OBSERVATIONS = {
    "f2sim-1": {"seed0": 20262101, "start": "2024-08-18T15:00:00", "odd": False},
    "f2sim-2": {"seed0": 20262111, "start": "2024-08-18T19:00:00", "odd": False},
    "f2sim-3": {"seed0": 20262121, "start": "2024-08-18T23:00:00", "odd": False},
    "f2sim-v": {"seed0": 20262131, "start": "2024-08-19T17:00:00", "odd": False},
    "f2sim-t1": {"seed0": 20262141, "start": "2024-08-19T21:00:00", "odd": False},
    "f2sim-t2": {
        "seed0": 20262151,
        "start": "2024-08-20T01:00:00",
        "odd": True,
        "gcal_flux": 2.0,
    },
    # Task F3 (research/f3-flagger.md, section 4): its held-out simulation test.
    "f3sim-t": {"seed0": 20263101, "start": "2024-08-21T05:00:00", "odd": True},
    # Task F4 (research/f4-flagger.md, section 4): its held-out simulation test.
    "f4sim-t": {"seed0": 20264101, "start": "2024-08-22T05:00:00", "odd": True},
}
ROLE = {
    "f2sim-1": "train",
    "f2sim-2": "train",
    "f2sim-3": "train",
    "f2sim-v": "validation",
    "f2sim-t1": "test",
    "f2sim-t2": "test",
    "f3sim-t": "test",
    "f4sim-t": "test",
}


def seeds(name):
    """The observation's seeds, as registered in `simtruth.SEEDS`."""
    s = dict(st.SEEDS[name])
    if s["jones"] != OBSERVATIONS[name]["seed0"]:
        raise ValueError(f"{name}: simtruth.SEEDS disagrees with OBSERVATIONS")
    return s


def design(name):
    obs = OBSERVATIONS[name]
    s = seeds(name)
    rng = np.random.default_rng(s["sky"] + 1000)
    flux = obs.get("gcal_flux") or float(np.exp(rng.uniform(math.log(2), math.log(10))))
    antennas = list(range(1 if obs["odd"] else 0, 64, 2))
    return st.Design(
        name,
        antennas,
        NCHAN,
        dict(LENGTHS),
        {k: s[k] for k in ("jones", "sky", "rfi", "noise")},
        fmin=FMIN,
        fmax=FMAX,
        extra={"gcal": {"fluxdensity": flux, "reffreq_hz": 1.4e9, "spix": (-0.6,)}},
    )


def schedule(d, start_utc):
    """TIME (MJD s), scan (1-based), field and index within scan per dump,
    for SEQUENCE with simtruth's slew."""
    from astropy.time import Time

    t0 = Time(start_utc, scale="utc").mjd * st.MJD_S
    times, scans, fields, within = [], [], [], []
    start = t0
    for k, code in enumerate(SEQUENCE):
        for i in range(d.lengths[code]):
            times.append(start + d.dt * (i + 0.5))
            scans.append(k + 1)
            fields.append(FIELD_OF[code])
            within.append(i)
        start += d.lengths[code] * d.dt + st.SLEW_S
    return (
        np.array(times),
        np.array(scans, np.int32),
        np.array(fields, np.int32),
        np.array(within, np.int32),
    )


def _pol(rng):
    beta = rng.uniform(0, math.pi / 2)
    gamma = rng.uniform(-math.pi, math.pi)
    return [
        math.cos(beta),
        math.sin(beta) * math.cos(gamma),
        math.sin(beta) * math.sin(gamma),
    ]


def _level(rng, sigma, lo=1.0, hi=1000.0):
    return sigma * float(np.exp(rng.uniform(math.log(lo), math.log(hi))))


def _span(rng, ntime, scans):
    """A random run of dumps within one scan: (first, last+1)."""
    s = int(rng.choice(np.unique(scans)))
    idx = np.flatnonzero(scans == s)
    n = int(rng.integers(1, len(idx) + 1))
    first = int(rng.integers(0, len(idx) - n + 1))
    return idx[first], idx[first] + n


def extra_events(d, scans, test):
    """F2's extra RFI, from the `rfi_extra` seed. Returns (geometric events
    for `simtruth.rfi_chunk`, local events, drifting events)."""
    rng = np.random.default_rng(seeds(d.name)["rfi_extra"])
    ntime = len(scans)
    sigma = d.sigma
    nant = len(d.antennas)
    geometric, local, drifting = [], [], []

    def geo(kind, ch, amp_t, name):
        lmax = float(rng.uniform(400.0, 4000.0))
        geometric.append(
            {
                "name": name,
                "kind": kind,
                "chans": [int(c) for c in ch],
                "amp_t": list(map(float, amp_t)),
                "lmax_m": lmax,
                "l0_m": lmax / 3.0,
                "az_deg": float(rng.uniform(0, 360)),
                "el_deg": float(rng.uniform(0, 5)),
                "phase0": float(rng.uniform(-math.pi, math.pi)),
                "pol": _pol(rng),
            }
        )

    for k in range(int(rng.integers(4, 13))):
        width = int(rng.integers(1, 5))
        c0 = int(rng.integers(0, NCHAN - width))
        amp = np.zeros(ntime)
        level = _level(rng, sigma)
        if rng.random() < 0.5:
            amp[:] = level
            kind = "carrier-persistent"
        else:
            t = 0
            while t < ntime:
                t += int(rng.integers(4, 40))
                run = int(rng.integers(1, 17))
                amp[t : t + run] = level
                t += run
            kind = "carrier-intermittent"
        geo(kind, range(c0, c0 + width), amp, f"carrier {k}")
    # Pulsed comb: every 5th channel in 1070-1150 MHz, alternate dumps.
    top = int(np.searchsorted(d.freq, 1150e6))
    a, b = _span(rng, ntime, scans)
    amp = np.zeros(ntime)
    amp[a:b:2] = _level(rng, sigma)
    geo("comb", range(int(rng.integers(0, 5)), top, 5), amp, "comb")

    def loc(kind, pairs):
        width = int(rng.integers(1, 9))
        c0 = int(rng.integers(0, NCHAN - width))
        first, last = _span(rng, ntime, scans)
        local.append(
            {
                "kind": kind,
                "pairs": pairs,
                "chans": list(range(c0, c0 + width)),
                "t0": int(first),
                "t1": int(last),
                "level": _level(rng, sigma),
                "phase0": float(rng.uniform(-math.pi, math.pi)),
                "tau_s": float(rng.uniform(-1e-6, 1e-6)),
                "pol": _pol(rng),
            }
        )

    for _ in range(int(rng.integers(2, 6))):
        ant = int(rng.integers(0, nant))
        loc("antenna-local", [[ant, -1]])
    for _ in range(int(rng.integers(5, 21))):
        p = int(rng.integers(0, nant - 1))
        q = int(rng.integers(p + 1, nant))
        loc("single-baseline", [[p, q]])
    if test:
        for k in range(int(rng.integers(2, 5))):
            first, last = _span(rng, ntime, scans)
            rate = int(rng.integers(1, 4)) * (1 if rng.random() < 0.5 else -1)
            n = last - first
            lo = max(0, -rate * (n - 1))
            hi = NCHAN - 4 - max(0, rate * (n - 1))
            c0 = int(rng.integers(lo, hi))
            lmax = float(rng.uniform(400.0, 4000.0))
            drifting.append(
                {
                    "kind": "drifting",
                    "t0": int(first),
                    "t1": int(last),
                    "c0": c0,
                    "rate": rate,
                    "level": _level(rng, sigma),
                    "lmax_m": lmax,
                    "l0_m": lmax / 3.0,
                    "az_deg": float(rng.uniform(0, 360)),
                    "el_deg": float(rng.uniform(0, 5)),
                    "phase0": float(rng.uniform(-math.pi, math.pi)),
                    "pol": _pol(rng),
                }
            )
    return geometric, local, drifting


def _coh(pol):
    ex = pol[0]
    ey = pol[1] + 1j * pol[2]
    return np.array([ex * ex, ex * np.conj(ey), ey * ex, abs(ey) ** 2])


def local_chunk(events, d, rows):
    """(row, chan, 4) antenna-local and single-baseline RFI (no decay)."""
    out = np.zeros((len(rows.tindex), d.nchan, 4), complex)
    nu = d.freq
    for e in events:
        sel = np.zeros(len(rows.tindex), bool)
        for p, q in e["pairs"]:
            if q < 0:
                sel |= (rows.a1 == p) | (rows.a2 == p)
            else:
                sel |= (rows.a1 == p) & (rows.a2 == q)
        sel &= (rows.tindex >= e["t0"]) & (rows.tindex < e["t1"])
        idx = np.flatnonzero(sel)
        if not len(idx):
            continue
        ch = np.asarray(e["chans"])
        # A per-baseline delay: tau scaled by the baseline's antenna pair.
        tau = e["tau_s"] * (1 + 0.1 * (rows.a1[idx] - rows.a2[idx]))
        phase = e["phase0"] + 2 * math.pi * tau[:, None] * nu[ch][None]
        val = e["level"] * np.exp(1j * phase)[..., None] * _coh(e["pol"])[None, None]
        out[np.ix_(idx, ch, np.arange(4))] += val
    return out


def drifting_chunk(events, d, rows, enu):
    """(row, chan, 4) drifting carriers with rfi_chunk's baseline geometry."""
    out = np.zeros((len(rows.tindex), d.nchan, 4), complex)
    nu = d.freq
    b = enu[rows.a1] - enu[rows.a2]
    length = np.linalg.norm(b, axis=1)
    for e in events:
        on = (rows.tindex >= e["t0"]) & (rows.tindex < e["t1"])
        w = np.where(length <= e["lmax_m"], np.exp(-length / e["l0_m"]), 0.0) * on
        az, el = e["az_deg"] * st.DEG, e["el_deg"] * st.DEG
        s = np.array(
            [math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)]
        )
        coh = _coh(e["pol"])
        for i in np.flatnonzero(w > 0):
            k = int(rows.tindex[i]) - e["t0"]
            ch = np.arange(4) + e["c0"] + e["rate"] * k
            delay = float(b[i] @ s) / st.C
            phase = 2 * math.pi * delay * nu[ch] + e["phase0"]
            out[i, ch] += e["level"] * w[i] * np.exp(1j * phase)[:, None] * coh[None]
    return out


CODES = {
    "persistent": 1,
    "intermittent": 2,
    "burst": 3,
    "carrier-persistent": 4,
    "carrier-intermittent": 4,
    "comb": 5,
    "antenna-local": 6,
    "single-baseline": 7,
    "drifting": 8,
}
MORPHOLOGIES = {
    1: "persistent",
    2: "intermittent",
    3: "burst",
    4: "carrier",
    5: "comb",
    6: "antenna-local",
    7: "single-baseline",
    8: "drifting",
}


def rfi_and_morphology(d, rows, enu, events, geometric, local, drifting):
    """(row, chan, 4) RFI and the (row, chan) int8 code of the strongest
    contributing morphology (`MORPHOLOGIES`; 0 none), event by event."""
    r = np.zeros((len(rows.tindex), d.nchan, 4), complex)
    best = np.zeros((len(rows.tindex), d.nchan))
    code = np.zeros((len(rows.tindex), d.nchan), np.int8)
    parts = [(e["kind"], lambda e=e: st.rfi_chunk([e], d, rows, enu)) for e in events]
    parts += [
        (e["kind"], lambda e=e: st.rfi_chunk([e], d, rows, enu)) for e in geometric
    ]
    parts += [(e["kind"], lambda e=e: local_chunk([e], d, rows)) for e in local]
    parts += [
        ("drifting", lambda e=e: drifting_chunk([e], d, rows, enu)) for e in drifting
    ]
    for kind, make in parts:
        c = make()
        a = np.abs(c).max(-1)
        if not a.any():
            continue
        r += c
        upd = a > best
        best[upd] = a[upd]
        code[upd] = CODES[kind]
    return r, code


def baseline_pairs(nant):
    a1, a2 = np.triu_indices(nant, 1)
    return a1.astype(np.int32), a2.astype(np.int32)


def build(name, out, variant=None, log=print):
    """Write one observation: per scan `data.npy`, `rfi.npy`, `model.npy`
    (complex64, (row, chan, 4), rows time-major then baseline), `morph.npy`
    (int8 (row, chan)) and `meta.json`. `variant` is a guard of section 5:
    "line" (G5: an unmodelled 5-channel line source, 20 sigma per cell, in
    the target scans) or "step" (G6: a 5 % and 0.1 rad gain step on antenna
    0 mid-scan, every scan)."""
    import time

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    d = design(name)
    obs = OBSERVATIONS[name]
    test = ROLE[name] == "test"
    times, scans, fields, within = schedule(d, obs["start"])
    uvw_ant, q, _ = st.geometry(d, times, fields)
    truth = st.jones(d, times, scans, fields, within)
    sky = st.target_sky(d)
    cal = st.calibrator_stokes(d)
    events = st.rfi_events(d, len(times))
    geometric, local, drifting = extra_events(d, scans, test)
    enu = st.enu_baselines(d)
    nant = len(d.antennas)
    a1, a2 = baseline_pairs(nant)
    xyz_all, _, names_all = st.antenna_table()
    sigma = d.sigma
    line = None
    if variant == "line":
        rng = np.random.default_rng(seeds(name)["sky"] + 2000)
        c0 = int(rng.integers(200, NCHAN - 200))
        line = {
            "l": float(rng.uniform(-0.2, 0.2) * st.DEG),
            "m": float(rng.uniform(-0.2, 0.2) * st.DEG),
            "chans": list(range(c0, c0 + 5)),
            "flux_jy": 20 * sigma,
        }
    summary = {"scans": []}
    for s in np.unique(scans):
        t0 = time.perf_counter()
        tidx = np.flatnonzero(scans == s)
        field = int(fields[tidx[0]])
        nrow = len(tidx) * len(a1)
        sdir = out / f"scan{int(s)}"
        sdir.mkdir()
        shape = (nrow, d.nchan, 4)
        open_mm = np.lib.format.open_memmap
        data = open_mm(sdir / "data.npy", "w+", np.complex64, shape)
        rfi = open_mm(sdir / "rfi.npy", "w+", np.complex64, shape)
        model = open_mm(sdir / "model.npy", "w+", np.complex64, shape)
        morph = open_mm(sdir / "morph.npy", "w+", np.int8, shape[:2])
        uvw_rows = np.zeros((nrow, 3))
        err = scale = 0.0
        for c in range(0, len(tidx), CHUNK_DUMPS):
            ti = tidx[c : c + CHUNK_DUMPS]
            rs = slice(c * len(a1), (c + len(ti)) * len(a1))
            rows = st.chunk_rows(ti, a1, a2)
            m, uvw = st.sky_coherency(d, rows, uvw_ant, fields, sky, cal)
            uvw_rows[rs] = uvw
            v = st.corrupt(m, truth, d, rows, q)
            ap = q[rows.tindex, rows.a1] + st.RECEPTOR_ANGLE
            aq = q[rows.tindex, rows.a2] + st.RECEPTOR_ANGLE
            model[rs] = st.rotate(m, ap, aq)
            del m
            if line is not None and field == 3:
                comp = {
                    "kind": "point",
                    "l": line["l"],
                    "m": line["m"],
                    "flux": line["flux_jy"],
                    "alpha": 0.0,
                    "ref_freq_hz": 1.284e9,
                    "fwhm_arcsec": 0.0,
                    "p": 0.0,
                }
                ml = st.target_coherency(uvw, d.freq, [comp])
                keep = np.zeros(d.nchan, bool)
                keep[line["chans"]] = True
                ml[:, ~keep] = 0
                # Through the same chain as the sky, not into the model.
                v = v + st.corrupt(ml, truth, d, rows, q)
            if variant == "step":
                g = 1.05 * np.exp(0.1j)
                after = rows.tindex >= tidx[len(tidx) // 2]
                v[after & (rows.a1 == 0)] *= g
                v[after & (rows.a2 == 0)] *= np.conj(g)
            r, code = rfi_and_morphology(
                d, rows, enu, events, geometric, local, drifting
            )
            weak = np.abs(r).max(-1) / sigma < FLOOR
            r[weak] = 0
            code[weak] = 0
            n = np.concatenate([st.noise_integration(d, t, len(a1)) for t in ti])
            clean = v + n
            del v, n
            dc = (clean + r).astype(np.complex64)
            rc = r.astype(np.complex64)
            # Check: DATA minus the stored RFI equals the RFI-free DATA.
            err = max(err, float(np.abs(dc.astype(complex) - rc - clean).max()))
            scale = max(scale, float(np.abs(clean).max()))
            data[rs], rfi[rs], morph[rs] = dc, rc, code
            del clean, r, dc, rc
        for a in (data, rfi, model, morph):
            a.flush()
        uvw = uvw_rows
        a = np.abs(rfi).max(-1) / sigma
        meta = {
            "observation": name,
            "variant": variant,
            "scan": int(s),
            "field": field,
            "class": "target" if field == 3 else "calibrator",
            "field_name": st.FIELDS[field][0],
            "ntime": len(tidx),
            "nbl": len(a1),
            "nant": nant,
            "antennas": d.antennas,
            "antenna_names": [names_all[i] for i in d.antennas],
            "antenna_position": xyz_all[d.antennas].tolist(),
            "antenna1": np.tile(a1, len(tidx)).tolist(),
            "antenna2": np.tile(a2, len(tidx)).tolist(),
            "times": np.repeat(times[tidx], len(a1)).tolist(),
            "uvw": uvw.tolist(),
            "chan_freq": d.freq.tolist(),
            "chan_width": [d.chan_width] * d.nchan,
            "corr_type": CORR_TYPE.tolist(),
            "sigma": sigma,
            "rfi_check_max_abs": float(err),
            "rfi_check_scale": float(scale),
            "truth_fraction": float((a > 0).mean()),
            "fraction_ge3": float((a >= 3).mean()),
            "fraction_ge10": float((a >= 10).mean()),
            "seconds": time.perf_counter() - t0,
        }
        (sdir / "meta.json").write_text(
            json.dumps(meta), encoding="utf-8", newline="\n"
        )
        summary["scans"].append(
            {
                k: meta[k]
                for k in (
                    "scan",
                    "field",
                    "class",
                    "ntime",
                    "truth_fraction",
                    "fraction_ge3",
                    "fraction_ge10",
                    "rfi_check_max_abs",
                    "rfi_check_scale",
                    "seconds",
                )
            }
        )
        log(json.dumps(summary["scans"][-1]))
    summary.update(
        {
            "observation": name,
            "role": ROLE[name],
            "variant": variant,
            "design": d.as_json(),
            "seeds": seeds(name),
            "start_utc": obs["start"],
            "sequence": SEQUENCE,
            "extra_events": {
                "geometric": [
                    {k: e[k] for k in ("name", "kind", "chans")} for e in geometric
                ],
                "local": local,
                "drifting": drifting,
            },
            "line": line,
        }
    )
    st.write_json(out / "observation.json", summary)
    return summary


@dataclasses.dataclass
class Scan:
    """One stored scan, memory-mapped."""

    path: Path
    meta: dict

    @classmethod
    def from_dir(cls, path):
        path = Path(path)
        return cls(path, json.loads((path / "meta.json").read_text(encoding="utf-8")))

    def array(self, name, mmap=True):
        return np.load(self.path / f"{name}.npy", mmap_mode="r" if mmap else None)


def scans_of(obs_dir, klass=None):
    out = []
    for p in sorted(Path(obs_dir).glob("scan*")):
        s = Scan.from_dir(p)
        if klass is None or s.meta["class"] == klass:
            out.append(s)
    return out
