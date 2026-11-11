"""Simulated truth for E1 and C2 to C7 (task A1, research/a1-simtruth.md).

A MeerKAT L-band observation in full polarisation with known sky, Jones
terms, RFI and thermal noise, written through rang's casacore table writer
(`rang.core_ms_write`).

The measurement equation is C1's (research/c1-calibration-chain.md, 1.1),
with the terms in CASA's type order and KCROSS in the K slot:

    V_pq = J_p M_pq J_q^H,   J_p = B_p K_p Kc G_p S_p D_p X P_p

- M is the sky-frame coherency: XX = I+Q, XY = U+iV, YX = U-iV, YY = I-Q.
- P_p = [[cos a, sin a], [-sin a, cos a]], a = q_p(t) + RECEPTOR_ANGLE, with
  q_p the geodetic parallactic angle at antenna p (`rang.measures`) and
  RECEPTOR_ANGLE = -pi/2 on both receptors (written to FEED, as CARACal
  sets it).
- X = diag(x(nu), 1) (Xf) and Kc = diag(exp(2 pi i tau_c (nu - nu0)), 1)
  (KCROSS) are one value for the array.
- D is CASA's linearised Df operator, not a matrix product: at D's place,
  XY += d_x,p YY + conj(d_y,q) XX and YX += d_y,p XX + conj(d_x,q) YY,
  parallel hands unchanged. Second-order leakage is absent by construction,
  so CASA's Df apply inverts it exactly.
- G_p = diag(g_x, g_y)(t) (`calmode='ap'`), S_p a scalar (both hands) on the
  target only: the residual that self-calibration should find. Scalars
  commute, so S's place does not matter.
- K_p = diag(exp(2 pi i tau (nu - nu0))), nu0 = the band centre (the
  frequency of CASA's one-channel K table window); B_p
  = diag(b_x(nu), b_y(nu)).

Thermal noise is added to DATA after corruption: complex Gaussian with
sigma per real and per imaginary part on every correlation, sigma =
SEFD / sqrt(2 dnu dt) exactly (SIGMA = sigma, WEIGHT = 1 / sigma^2). RFI is
added to DATA after corruption too, from a list of events drawn from its own
seed; its cells are saved as bit masks. Noise is drawn per integration from
(noise seed, integration index), so any subset of integrations reproduces
the same noise.

No primary beam, no time or bandwidth smearing (point evaluation at the
channel and integration centres), no autocorrelations. UVW are computed in
the ICRS (GCRS axes, astropy), uvw = uvw(ANTENNA1) - uvw(ANTENNA2), and the
visibility phase is positive, as the gemclean simulator and rang's imaging.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

C = 299_792_458.0
MJD_S = 86400.0
DEG = math.pi / 180.0
ARCSEC = DEG / 3600.0
ROOT = Path(__file__).resolve().parents[2]
ITRF = ROOT / "data" / "meerkat.itrf.txt"
RECEPTOR_ANGLE = -math.pi / 2
SEFD_JY = 420.0
CORR = ("XX", "XY", "YX", "YY")

# Fields: name, RA (deg), Dec (deg), role, MeerKAT-style intent.
FIELDS = (
    ("J1939-6342", 294.854275, -63.712675, "fcal", "CALIBRATE_BANDPASS,CALIBRATE_FLUX"),
    ("3C286-SIM", 301.25, -20.0, "xcal", "CALIBRATE_POLARIZATION"),
    ("SIM-GCAL", 298.0, -33.0, "gcal", "CALIBRATE_AMPLI,CALIBRATE_PHASE"),
    ("SIM-TARGET", 300.0, -36.0, "target", "TARGET"),
)
# The scan sequence (field index) and each scan's integrations in the full
# version; the small version keeps every scan's start time and truncates it.
SEQUENCE = "FXGTGTGXGTGTGXGTGTGTGXF"
FULL_LENGTH = {"F": 45, "X": 30, "G": 15, "T": 150}
SMALL_LENGTH = {"F": 6, "X": 4, "G": 2, "T": 8}
# Task W3 (research/w3-chunking.md): the whole array at 4096 channels, short scans.
W3_LENGTH = {"F": 6, "X": 1, "G": 2, "T": 4}
FIELD_OF = {"F": 0, "X": 1, "G": 2, "T": 3}
SLEW_S = 24.0
START_UTC = "2024-08-18T19:09:00"
SELFCAL_BLOCK = 8  # integrations per constant S block, from each target scan start

# Polarised calibrator: CARACal's nrao_xcal.yml 3C 286 Stokes I, A0's p and chi.
XCAL = {
    "fluxdensity": 14.7172,
    "reffreq_hz": 1.47e9,
    "spix": (-0.4507, -0.1798, 0.0357),
    "p": 0.095,
    "chi_deg": 33.0,
    "rm": 0.0,
}
GCAL = {"fluxdensity": 4.0, "reffreq_hz": 1.4e9, "spix": (-0.6,)}

SEEDS = {
    "full": {"jones": 20261106, "sky": 20261107, "rfi": 20261108, "noise": 20261109},
    "small": {"jones": 20261116, "sky": 20261117, "rfi": 20261118, "noise": 20261119},
    # Task C2b (research/c2b-delay.md): delays up to 50 ns.
    "delay50": {"jones": 20261126, "sky": 20261127, "rfi": 20261128, "noise": 20261129},
    # Task C2c (research/c2c-bandpass.md): the held-out set, new seeds.
    "holdout256": {
        "jones": 20261136,
        "sky": 20261137,
        "rfi": 20261138,
        "noise": 20261139,
    },
    # Task C6 (research/c6-polterms.md): the polarisation truth (CASA's
    # parallactic frame, a leaking refant) and its held-out twin, new seeds.
    "poldx": {"jones": 20261146, "sky": 20261147, "rfi": 20261148, "noise": 20261149},
    "polholdout": {
        "jones": 20261156,
        "sky": 20261157,
        "rfi": 20261158,
        "noise": 20261159,
    },
    # Task C2e (research/c2e-calibrate.md): its held-out set, new seeds.
    "holdout128": {
        "jones": 20261146,
        "sky": 20261147,
        "rfi": 20261148,
        "noise": 20261149,
    },
    # Task W3 (research/w3-chunking.md): 64 antennas at 4096 channels. Its
    # seeds equal holdout256's (both chosen the same day); the designs differ.
    "w3": {"jones": 20261136, "sky": 20261137, "rfi": 20261138, "noise": 20261139},
    # Task C5 (research/c5-selfcal.md): the self-calibration truths, built by
    # examples/c5_selfcal_sim.py (target only, 32 antennas, 64 channels), not
    # designs of this module; the held-out two were frozen before they ran.
    **{
        name: {"jones": s0, "sky": s0 + 1, "rfi": s0 + 2, "noise": s0 + 3}
        for name, s0 in (
            ("c5pa", 20261301),
            ("c5delay", 20261311),
            ("c5pa-held", 20261321),
            ("c5delay-held", 20261331),
            # Task C5b (research/c5b-selfcal-masks.md): its own held-out pair,
            # frozen in that note before they ran.
            ("c5pa-held2", 20261501),
            ("c5delay-held2", 20261511),
        )
    },
    # Task F2 (research/f2-flagger.md): F-SIM's six observations, built by
    # rang.f2flag_sim, not designs of this module; `rfi_extra` seeds F2's
    # added RFI morphologies.
    **{
        name: {
            "jones": s0,
            "sky": s0 + 1,
            "rfi": s0 + 2,
            "noise": s0 + 3,
            "rfi_extra": s0 + 4,
        }
        for name, s0 in (
            ("f2sim-1", 20262101),
            ("f2sim-2", 20262111),
            ("f2sim-3", 20262121),
            ("f2sim-v", 20262131),
            ("f2sim-t1", 20262141),
            ("f2sim-t2", 20262151),
            # Task F3 (research/f3-flagger.md): its held-out simulation test.
            ("f3sim-t", 20263101),
        )
    },
}

# Task C6: the versions whose parallactic angle is CASA's frame and whose
# refant leaks (`extra["parang_frame"] == "casa"`, `extra["refant_leakage"]`).
POL_EXTRA = {"parang_frame": "casa", "refant_leakage": True}


@dataclass
class Design:
    """What one version is: antennas, band, sampling, schedule and seeds."""

    name: str
    antennas: list
    nchan: int
    lengths: dict
    seeds: dict
    dt: float = 8.0
    fmin: float = 856e6
    fmax: float = 1712e6
    refant: int = 0
    sefd: float = SEFD_JY
    tau_c_ns: float = 3.0
    extra: dict = field(default_factory=dict)

    @property
    def freq(self):
        width = (self.fmax - self.fmin) / self.nchan
        return self.fmin + width * (np.arange(self.nchan) + 0.5)

    @property
    def chan_width(self):
        return (self.fmax - self.fmin) / self.nchan

    @property
    def nu0(self):
        """The K and KCROSS pivot: CASA's K table window is one channel at
        the mean frequency of the solved channels (1284.0 MHz here), not the
        MS's CHAN_FREQ[nchan // 2] (measured, research/a1-simtruth.md 7.1)."""
        return float(self.freq.mean())

    @property
    def sigma(self):
        """Noise per real and per imaginary part of each correlation (Jy)."""
        return self.sefd / math.sqrt(2.0 * self.chan_width * self.dt)

    def as_json(self):
        return {
            "name": self.name,
            "antennas": list(self.antennas),
            "nchan": self.nchan,
            "fmin_hz": self.fmin,
            "fmax_hz": self.fmax,
            "chan_width_hz": self.chan_width,
            "nu0_hz": self.nu0,
            "dt_s": self.dt,
            "scan_lengths": dict(self.lengths),
            "sequence": SEQUENCE,
            "slew_s": SLEW_S,
            "start_utc": START_UTC,
            "seeds": dict(self.seeds),
            "refant": self.refant,
            "sefd_jy": self.sefd,
            "sigma_jy": self.sigma,
            "tau_c_ns": self.tau_c_ns,
            **({"extra": dict(self.extra)} if self.extra else {}),
        }


def design(name):
    """The `full` (64 antennas, 256 channels) or `small` (16, 64) version, or
    `delay50` (C2b: small's antennas and schedule, 256 channels, delays of
    1-50 ns, `extra["tau_range_ns"]`), or `holdout256` (C2c's held-out set:
    as delay50 with new seeds and delays of 1-30 ns), or `holdout128` (C2e's
    held-out set: as holdout256 with 128 channels and its own seeds), or
    `w3` (W3: all 64 antennas, 4096 channels, scans of `W3_LENGTH`
    integrations)."""
    if name == "full":
        return Design("full", list(range(64)), 256, FULL_LENGTH, SEEDS["full"])
    if name == "small":
        return Design("small", list(range(0, 64, 4)), 64, SMALL_LENGTH, SEEDS["small"])
    if name == "delay50":
        return Design(
            "delay50",
            list(range(0, 64, 4)),
            256,
            SMALL_LENGTH,
            SEEDS["delay50"],
            extra={"tau_range_ns": (1.0, 50.0)},
        )
    if name == "holdout256":
        return Design(
            "holdout256",
            list(range(0, 64, 4)),
            256,
            SMALL_LENGTH,
            SEEDS["holdout256"],
            extra={"tau_range_ns": (1.0, 30.0)},
        )
    if name == "holdout128":
        return Design(
            "holdout128",
            list(range(0, 64, 4)),
            128,
            SMALL_LENGTH,
            SEEDS["holdout128"],
            extra={"tau_range_ns": (1.0, 30.0)},
        )
    if name in ("poldx", "polholdout"):
        # Task C6 (research/c6-polterms.md): small's antennas and schedule, 256
        # channels, P in CASA's frame (`parallactic_angle_casa`) and d_x of the
        # refant not zero (A1's two open owner decisions, chosen provisionally).
        return Design(
            name,
            list(range(0, 64, 4)),
            256,
            SMALL_LENGTH,
            SEEDS[name],
            tau_c_ns=2.2 if name == "poldx" else -3.7,
            extra={"tau_range_ns": (1.0, 10.0), **POL_EXTRA},
        )
    if name == "w3":
        return Design("w3", list(range(64)), 4096, W3_LENGTH, SEEDS["w3"])
    raise ValueError(
        f"unknown version {name!r}: full, small, delay50, holdout256, holdout128, "
        "poldx, polholdout or w3"
    )


# -- geometry ---------------------------------------------------------------------


def antenna_table():
    rows = [line.split() for line in ITRF.read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r and not r[0].startswith("#")]
    xyz = np.array([[float(v) for v in r[:3]] for r in rows])
    diameter = np.array([float(r[3]) for r in rows])
    names = [r[4].lower() for r in rows]
    return xyz, diameter, names


def schedule(d):
    """Per integration: TIME (MJD s, centre), scan number (1-based), field,
    and the index of the integration within its scan. Scan k starts at the
    same time in every version (full lengths plus slews)."""
    from astropy.time import Time

    t0 = Time(START_UTC, scale="utc").mjd * MJD_S
    times, scans, fields, within = [], [], [], []
    start = t0
    for k, code in enumerate(SEQUENCE):
        n = d.lengths[code]
        for i in range(n):
            times.append(start + d.dt * (i + 0.5))
            scans.append(k + 1)
            fields.append(FIELD_OF[code])
            within.append(i)
        start += FULL_LENGTH[code] * d.dt + SLEW_S
    return (
        np.array(times),
        np.array(scans, np.int32),
        np.array(fields, np.int32),
        np.array(within, np.int32),
    )


def _direction(ra, dec):
    ca, sa, cd, sd = math.cos(ra), math.sin(ra), math.cos(dec), math.sin(dec)
    u = np.array([-sa, ca, 0.0])
    v = np.array([-sd * ca, -sd * sa, cd])
    w = np.array([cd * ca, cd * sa, sd])
    return np.stack([u, v, w])


def geometry(d, times, fields):
    """Per-antenna UVW (ntime, nant, 3) in the ICRS axes, the parallactic
    angle q (ntime, nant) and the elevation at the array centre (ntime)."""
    from astropy import units
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    from . import measures

    iers.conf.auto_download = False
    xyz_all, _, _ = antenna_table()
    xyz = xyz_all[d.antennas]
    when = Time(times / MJD_S, format="mjd", scale="utc")
    ntime, nant = len(times), len(xyz)
    pos = np.empty((ntime, nant, 3))
    for a in range(nant):
        loc = EarthLocation.from_geocentric(*xyz[a], unit=units.m)
        p, _ = loc.get_gcrs_posvel(when)
        pos[:, a] = p.xyz.to_value(units.m).T
    centre = pos.mean(axis=1, keepdims=True)
    uvw = np.empty((ntime, nant, 3))
    q = np.empty((ntime, nant))
    elev = np.empty(ntime)
    site = measures.location(xyz_all.mean(axis=0))
    for f, (_, ra, dec, _, _) in enumerate(FIELDS):
        sel = fields == f
        if not sel.any():
            continue
        basis = _direction(ra * DEG, dec * DEG)
        uvw[sel] = np.einsum("tak,jk->taj", pos[sel] - centre[sel], basis)
        for a in range(nant):
            q[sel, a] = measures.parallactic_angle(
                times[sel], ra * DEG, dec * DEG, xyz[a]
            )
        src = SkyCoord(ra * units.deg, dec * units.deg, frame="icrs")
        elev[sel] = src.transform_to(AltAz(obstime=when[sel], location=site)).alt.deg
    if d.extra.get("parang_frame") == "casa":
        # Task C6: the truth's P in CASA's frame (provisional owner decision).
        q = parallactic_angle_casa(d, times, fields)
    return uvw, q, elev


def parallactic_angle_casa(d, times, fields):
    """(ntime, nant) the angle CASA 6.7.6.14's `applycal(parang=True)` was
    measured to use (research/a1-simtruth.md 7.1): the hour-angle formula
    on the apparent (TETE) place with apparent sidereal time and the
    **geocentric** latitude of each antenna, from apparent north (no
    rotation to ICRS north). Not the truth's convention; saved for C6."""
    from astropy import units
    from astropy.coordinates import TETE, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    xyz_all, _, _ = antenna_table()
    xyz = xyz_all[d.antennas]
    out = np.empty((len(times), len(xyz)))
    for f, (_, ra, dec, _, _) in enumerate(FIELDS):
        sel = fields == f
        if not sel.any():
            continue
        when = Time(times[sel] / MJD_S, format="mjd", scale="utc")
        for a, pos in enumerate(xyz):
            loc = EarthLocation.from_geocentric(*pos, unit=units.m)
            app = SkyCoord(ra * units.deg, dec * units.deg, frame="icrs").transform_to(
                TETE(obstime=when, location=loc)
            )
            h = when.sidereal_time("apparent", longitude=loc.lon).rad - app.ra.rad
            phi = math.atan2(pos[2], math.hypot(pos[0], pos[1]))
            dd = app.dec.rad
            out[sel, a] = np.arctan2(
                np.sin(h), np.tan(phi) * np.cos(dd) - np.sin(dd) * np.cos(h)
            )
    return out


# -- the Jones terms ----------------------------------------------------------------


def _smooth(rng, x, nterm=3, scale=1.0):
    """A smooth random function of x in [-1, 1]: a few low-order sines."""
    out = np.zeros_like(x)
    for k in range(1, nterm + 1):
        out += rng.normal(0.0, scale / k) * np.sin(
            math.pi * k * (x + 1) / 2 * rng.uniform(0.6, 1.4)
            + rng.uniform(0, 2 * math.pi)
        )
    return out


def jones(d, times, scans, fields, within):
    """The true Jones terms (raw, before any gauge), from the jones seed.

    Construction choices that make refant `d.refant`'s CASA gauge clean
    (research/a1-simtruth.md, "Gauge"): its B and G phases are equal in X and
    Y, so referencing moves only its X-Y delay into KCROSS; its d_x is zero,
    so CASA's subtractive Df reference is the identity."""
    rng = np.random.default_rng(d.seeds["jones"])
    nant, nchan, ntime = len(d.antennas), d.nchan, len(times)
    nu = d.freq
    x = (nu - 0.5 * (d.fmin + d.fmax)) / (0.5 * (d.fmax - d.fmin))
    r = d.refant

    # K: |tau| uniform 1-10 ns (delay50: 1-50 ns), random sign, per antenna
    # and hand.
    lo, hi = d.extra.get("tau_range_ns", (1.0, 10.0))
    tau = rng.uniform(lo, hi, (nant, 2)) * rng.choice([-1.0, 1.0], (nant, 2))
    # The refant's X-Y delay is moved into KCROSS by referencing: keep the
    # effective KCROSS (tau_c + tau_x,r - tau_y,r) at a few ns.
    delta = rng.uniform(-1.5, 1.5)
    tau[r, 1] = tau[r, 0] - delta
    if not lo <= abs(tau[r, 1]) <= hi:
        tau[r, 1] = math.copysign(min(max(abs(tau[r, 1]), lo), hi), tau[r, 1])
    # CASA stores delays as float32 (FPARAM) and turns them into phases of up
    # to 2 pi 10 ns 428 MHz = 27 rad: a float64 delay would differ from its
    # table by up to 11 float32 epsilons of phase per antenna. So the truth's
    # delays are float32 values (research/a1-simtruth.md 7.1).
    tau = tau.astype(np.float32).astype(np.float64)
    k_phase = 2 * math.pi * tau[:, None, :] * 1e-9 * (nu - d.nu0)[None, :, None]

    # B: amplitude with a slope, ripples and band-edge roll-off; phase ripples.
    edge = 1.0 / (1.0 + np.exp(-(nu - d.fmin - 12e6) / 4e6))
    edge *= 1.0 / (1.0 + np.exp((nu - d.fmax + 30e6) / 6e6))
    b_amp = np.empty((nant, nchan, 2))
    b_ph = np.empty((nant, nchan, 2))
    for a in range(nant):
        for h in range(2):
            level = rng.uniform(0.85, 1.15)
            slope = rng.uniform(-0.15, 0.15) * x
            period = rng.uniform(25e6, 60e6)
            ripple = rng.uniform(0.01, 0.04) * np.sin(
                2 * math.pi * nu / period + rng.uniform(0, 2 * math.pi)
            )
            b_amp[a, :, h] = (
                level
                * (1 + slope + ripple + 0.05 * _smooth(rng, x))
                * (0.3 + 0.7 * edge)
            )
            b_ph[a, :, h] = DEG * (
                rng.uniform(-60, 60)
                + 6.0 * _smooth(rng, x, 4)
                + rng.uniform(1, 4) * np.sin(2 * math.pi * nu / rng.uniform(15e6, 40e6))
            )
    b_ph[r, :, 1] = b_ph[r, :, 0]
    bandpass = b_amp * np.exp(1j * b_ph)

    # G: constant amplitude per antenna and hand; phase constant within each
    # calibrator scan (a random walk from scan to scan), linear in time
    # between the gain calibrator's scans on the target (CASA's `linear`),
    # nearest outside them.
    g_amp = rng.uniform(0.8, 1.25, (nant, 2))
    nscan = int(scans.max())
    scan_field = np.array([fields[scans == s][0] for s in range(1, nscan + 1)])
    common = np.cumsum(rng.normal(0.0, 25.0, (nscan, nant)), axis=0)
    hand = rng.uniform(-180, 180, (1, nant, 2)) + np.cumsum(
        rng.normal(0.0, 5.0, (nscan, nant, 2)), axis=0
    )
    phase_scan = DEG * (common[..., None] + hand)  # (scan, ant, hand)
    phase_scan[:, r, 1] = phase_scan[:, r, 0]
    scan_time = np.array([times[scans == s].mean() for s in range(1, nscan + 1)])
    g_phase = np.empty((ntime, nant, 2))
    gcal_scans = np.flatnonzero(scan_field == 2)
    for i in range(ntime):
        s = scans[i] - 1
        if fields[i] != 3:
            g_phase[i] = phase_scan[s]
            continue
        t = times[i]
        before = gcal_scans[scan_time[gcal_scans] <= t]
        after = gcal_scans[scan_time[gcal_scans] > t]
        if not len(before):
            g_phase[i] = phase_scan[after[0]]
        elif not len(after):
            g_phase[i] = phase_scan[before[-1]]
        else:
            s0, s1 = before[-1], after[0]
            w = (t - scan_time[s0]) / (scan_time[s1] - scan_time[s0])
            g_phase[i] = phase_scan[s0] + w * (phase_scan[s1] - phase_scan[s0])
    gain = g_amp[None] * np.exp(1j * g_phase)

    # S: scalar residual on the target, constant per SELFCAL_BLOCK
    # integrations from each target scan start.
    s_amp_a = rng.uniform(0.005, 0.02, nant)
    s_ph_a = rng.uniform(5.0, 15.0, (nant, 2))
    s_period = rng.uniform([1200.0, 300.0], [3600.0, 900.0], (nant, 2))
    s_off = rng.uniform(0, 2 * math.pi, (nant, 3))
    selfcal = np.ones((ntime, nant), complex)
    block = np.full(ntime, -1, np.int32)
    tgt = np.flatnonzero(fields == 3)
    if len(tgt):
        bid = 0
        for s in np.unique(scans[tgt]):
            idx = np.flatnonzero(scans == s)
            for start in range(0, len(idx), SELFCAL_BLOCK):
                block[idx[start : start + SELFCAL_BLOCK]] = bid
                bid += 1
        for b in range(bid):
            idx = np.flatnonzero(block == b)
            tc = times[idx].mean() - times[0]
            ph = DEG * (
                s_ph_a[:, 0] * np.sin(2 * math.pi * tc / s_period[:, 0] + s_off[:, 0])
                + s_ph_a[:, 1] * np.sin(2 * math.pi * tc / s_period[:, 1] + s_off[:, 1])
            )
            amp = 1.0 + s_amp_a * np.sin(2 * math.pi * tc / 2400.0 + s_off[:, 2])
            selfcal[idx] = (amp * np.exp(1j * ph))[None]

    # KCROSS and Xf (array values).
    kcross = np.exp(2j * math.pi * d.tau_c_ns * 1e-9 * (nu - d.nu0))
    xf_deg = 35.0 + 20.0 * np.sin(1.2 * x + 0.4) + 8.0 * x**2 + 2.0 * _smooth(rng, x, 3)
    xf = np.exp(1j * DEG * xf_deg)

    # Df: |d| 1-3 % per antenna and hand, smooth in frequency.
    leak = np.empty((nant, nchan, 2), complex)
    for a in range(nant):
        for h in range(2):
            amp0 = rng.uniform(0.012, 0.028)
            amp = amp0 * (1 + 0.15 * _smooth(rng, x, 2))
            ph = rng.uniform(-math.pi, math.pi) + DEG * 40.0 * _smooth(rng, x, 2)
            leak[a, :, h] = np.clip(amp, 0.01, 0.03) * np.exp(1j * ph)
    if not d.extra.get("refant_leakage"):
        # Task C6's versions keep the refant's d_x (A1 owner decision 2).
        leak[r, :, 0] = 0.0

    return {
        "tau_ns": tau,
        "k": np.exp(1j * k_phase),
        "bandpass": bandpass,
        "gain": gain,
        "gain_phase_scan": phase_scan,
        "scan_time": scan_time,
        "selfcal": selfcal,
        "selfcal_block": block,
        "kcross": kcross,
        "xf": xf,
        "leakage": leak,
    }


def casa_gauge(truth, refant, nu, nu0):
    """The truth in CASA's gauge for reference antenna `refant`.

    K, G, B are referenced per hand (tau_r = 0; phases divided by the
    refant's). The removed common factor diag(u_x, u_y) is moved right
    through D (d_x -> e d_x, d_y -> conj(e) d_y, e = u_x conj(u_y)) into
    the cross-hand terms; its linear-in-frequency K part goes to KCROSS
    (tau_c' = tau_c + tau_x,r - tau_y,r) and the rest (the refant's B and G
    X-Y phase, which the construction makes zero for d.refant) to Xf. Then
    CASA's subtractive Df reference: d_x,p -= d_x,r, d_y,p += conj(d_x,r).
    This split of the cross-hand phase between KCROSS (before D) and Xf
    (after D) is an assumption: D in this gauge depends on it.
    G is returned per integration (ntime, nant, 2), including S."""
    tau = truth["tau_ns"] - truth["tau_ns"][refant][None]
    k = np.exp(2j * math.pi * tau[:, None, :] * 1e-9 * (nu - nu0)[None, :, None])
    b = truth["bandpass"]
    b_ref = b * (np.abs(b[refant]) / b[refant])[None]
    g = truth["gain"] * truth["selfcal"][..., None]
    g_ref = g * (np.abs(g[:, refant]) / g[:, refant])[:, None]
    # The refant's per-hand phases removed by referencing, per channel and
    # time: K, B (frequency) and G (time). e = u_x conj(u_y).
    dtau = truth["tau_ns"][refant, 0] - truth["tau_ns"][refant, 1]
    kc = truth["kcross"] * np.exp(2j * math.pi * dtau * 1e-9 * (nu - nu0))
    phb = np.angle(b[refant, :, 0] * np.conj(b[refant, :, 1]))
    phg = np.angle(g[:, refant, 0] * np.conj(g[:, refant, 1]))
    if np.ptp(phg) > 1e-12:
        raise ValueError("the refant's G X-Y phase varies in time: no constant Xf")
    e2 = np.exp(1j * (phb + phg[0]))
    xf = truth["xf"] * e2
    leak = truth["leakage"].copy()
    leak[..., 0] *= e2[None]
    leak[..., 1] *= np.conj(e2)[None]
    zx = leak[refant, :, 0].copy()
    leak[..., 0] -= zx[None]
    leak[..., 1] += np.conj(zx)[None]
    return {
        "refant": int(refant),
        "tau_ns": tau,
        "k": k,
        "bandpass": b_ref,
        "gain": g_ref,
        "tau_c_ns": None,
        "kcross": kc,
        "xf": xf,
        "leakage": leak,
        "tau_c_eff_ns_from_k": float(dtau),
    }


# -- the sky -----------------------------------------------------------------------


def radec(l, m, ra0, dec0):
    """Inverse SIN projection (radians)."""
    n = math.sqrt(1.0 - l * l - m * m)
    dec = math.asin(m * math.cos(dec0) + n * math.sin(dec0))
    ra = ra0 + math.atan2(l, n * math.cos(dec0) - m * math.sin(dec0))
    return ra % (2 * math.pi), dec


def target_sky(d):
    """Target components (dicts): points, Gaussians and an arc of Gaussians;
    some polarised with a rotation measure. Stokes I = flux (nu/1.284 GHz)
    ** alpha; Q + iU = p I exp(2i (chi0 + rm lambda^2)); V = 0."""
    rng = np.random.default_rng(d.seeds["sky"])
    ref = 1.284e9
    comps = []
    radius = 0.4 * DEG
    pos = []
    while len(pos) < 40:
        r = radius * math.sqrt(rng.uniform())
        a = rng.uniform(0, 2 * math.pi)
        lm = (r * math.sin(a), r * math.cos(a))
        if any(math.hypot(lm[0] - p[0], lm[1] - p[1]) < 60 * ARCSEC for p in pos):
            continue
        pos.append(lm)
    flux = np.exp(rng.uniform(math.log(1e-3), math.log(0.2), 40))
    flux[0] = 0.5
    alpha = rng.normal(-0.7, 0.2, 40)
    for i, (l, m) in enumerate(pos):
        comps.append(
            {
                "kind": "point",
                "l": l,
                "m": m,
                "flux": float(flux[i]),
                "alpha": float(alpha[i]),
                "fwhm_arcsec": 0.0,
            }
        )
    for _ in range(5):
        r = 0.3 * DEG * math.sqrt(rng.uniform())
        a = rng.uniform(0, 2 * math.pi)
        comps.append(
            {
                "kind": "gaussian",
                "l": r * math.sin(a),
                "m": r * math.cos(a),
                "flux": float(np.exp(rng.uniform(math.log(0.02), math.log(0.2)))),
                "alpha": float(rng.normal(-0.8, 0.1)),
                "fwhm_arcsec": float(np.exp(rng.uniform(math.log(20), math.log(120)))),
            }
        )
    # An arc of 10 overlapping Gaussians holding 0.3 Jy.
    l0, m0 = rng.uniform(-0.1 * DEG, 0.1 * DEG, 2)
    arc_r = 600 * ARCSEC
    angles = np.linspace(0, 0.6 * math.pi, 10) + rng.uniform(0, 2 * math.pi)
    along = np.exp(-np.linspace(0, 1.5, 10))
    along = 0.3 * along / along.sum()
    for a, f in zip(angles, along, strict=True):
        comps.append(
            {
                "kind": "gaussian",
                "l": float(l0 + arc_r * math.sin(a)),
                "m": float(m0 + arc_r * math.cos(a)),
                "flux": float(f),
                "alpha": -1.0,
                "fwhm_arcsec": float(rng.uniform(40, 80)),
            }
        )
    # Polarisation: five points (the brightest and four others) and one Gaussian.
    pol_idx = [0, *rng.choice(np.arange(1, 40), 4, replace=False).tolist(), 40]
    for i in range(len(comps)):
        comps[i].update({"p": 0.0, "chi0_deg": 0.0, "rm": 0.0})
    for i in pol_idx:
        comps[i]["p"] = float(rng.uniform(0.02, 0.15))
        comps[i]["chi0_deg"] = float(rng.uniform(-90, 90))
        comps[i]["rm"] = float(rng.uniform(-60, 60))
    _, ra0, dec0, _, _ = FIELDS[3]
    for c in comps:
        c["ref_freq_hz"] = ref
        ra, dec = radec(c["l"], c["m"], ra0 * DEG, dec0 * DEG)
        c["ra_deg"], c["dec_deg"] = ra / DEG, dec / DEG
    return comps


def calibrator_stokes(d):
    """(field, chan, 4) Stokes I, Q, U, V of the three point calibrators at
    their phase centres (the target row is zero)."""
    from . import fluxstd

    nu = d.freq
    out = np.zeros((4, len(nu), 4))
    out[0] = fluxstd.flux("J1939-6342", nu, "Stevens-Reynolds 2016", extrapolate=True)
    i_x = fluxstd.manual(nu, XCAL["fluxdensity"], XCAL["reffreq_hz"], XCAL["spix"])
    chi = XCAL["chi_deg"] * DEG + XCAL["rm"] * (C / nu) ** 2
    out[1, :, 0] = i_x
    out[1, :, 1] = XCAL["p"] * i_x * np.cos(2 * chi)
    out[1, :, 2] = XCAL["p"] * i_x * np.sin(2 * chi)
    # `extra["gcal"]` replaces the gain calibrator's model (task C2d's
    # held-out version); the default versions use GCAL.
    gcal = d.extra.get("gcal", GCAL)
    out[2, :, 0] = fluxstd.manual(
        nu, gcal["fluxdensity"], gcal["reffreq_hz"], gcal["spix"]
    )
    return out


def _component_arrays(comps):
    n = len(comps)
    return {
        "lm": np.array([[c["l"], c["m"]] for c in comps]).reshape(n, 2),
        "kind": np.array([1 if c["kind"] == "gaussian" else 0 for c in comps]),
        "flux": np.array([c["flux"] for c in comps]),
        "coeffs": np.array([[c["alpha"]] for c in comps]).reshape(n, 1),
        "log_poly": np.ones(n, bool),
        "ref_freq": np.array([c["ref_freq_hz"] for c in comps]),
        "gauss_shape": np.array(
            [[c["fwhm_arcsec"] * ARCSEC, c["fwhm_arcsec"] * ARCSEC, 0.0] for c in comps]
        ).reshape(n, 3),
    }


def _predict(uvw, nu, arrays):
    from . import core

    return core.predict_components(
        uvw,
        nu,
        arrays["lm"],
        arrays["kind"],
        arrays["flux"],
        arrays["coeffs"],
        arrays["log_poly"],
        arrays["ref_freq"],
        arrays["gauss_shape"],
    )


def target_coherency(uvw, nu, comps):
    """(row, chan, 4) sky-frame XX, XY, YX, YY of the target components."""
    unpol = [c for c in comps if c["p"] == 0.0]
    pol = [c for c in comps if c["p"] != 0.0]
    vi = _predict(uvw, nu, _component_arrays(unpol))
    vq = np.zeros_like(vi)
    vu = np.zeros_like(vi)
    lam2 = (C / nu) ** 2
    for c in pol:
        v = _predict(uvw, nu, _component_arrays([c]))
        vi += v
        chi = c["chi0_deg"] * DEG + c["rm"] * lam2
        vq += v * (c["p"] * np.cos(2 * chi))[None]
        vu += v * (c["p"] * np.sin(2 * chi))[None]
    return np.stack([vi + vq, vu, vu, vi - vq], axis=-1)


def stokes_coherency(stokes):
    """(..., 4) I, Q, U, V to sky-frame XX, XY, YX, YY."""
    i, q, u, v = (stokes[..., k] for k in range(4))
    return np.stack([i + q, u + 1j * v, u - 1j * v, i - q], axis=-1)


# -- corruption ---------------------------------------------------------------------


def rotate(m, ap, aq, inverse=False):
    """P_p M P_q^T (or P_p^T M P_q) for P = [[c, s], [-s, c]]; m (row, chan,
    4), ap, aq (row,) angles."""
    sgn = -1.0 if inverse else 1.0
    cp, sp = np.cos(ap)[:, None], sgn * np.sin(ap)[:, None]
    cq, sq = np.cos(aq)[:, None], sgn * np.sin(aq)[:, None]
    p = ((cp, sp), (-sp, cp))
    q = ((cq, sq), (-sq, cq))
    mm = ((m[..., 0], m[..., 1]), (m[..., 2], m[..., 3]))
    out = np.empty_like(m)
    for k, (a, b) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        acc = 0.0
        for i in range(2):
            for j in range(2):
                acc = acc + p[a][i] * mm[i][j] * q[b][j]
        out[..., k] = acc
    return out


@dataclass
class Rows:
    """Row axes of a chunk: integration index (global), antenna indices
    (into the design's antenna list) of ANTENNA1 and ANTENNA2."""

    tindex: np.ndarray
    a1: np.ndarray
    a2: np.ndarray


def diagonal(truth, d, rows):
    """(row, chan, 2) per-hand diagonal of B K Kc G S for ANTENNA1 and 2."""
    static = truth["bandpass"] * truth["k"]
    static = static.copy()
    static[..., 0] *= truth["kcross"][None]
    tg = truth["gain"] * truth["selfcal"][..., None]
    gp = static[rows.a1] * tg[rows.tindex, rows.a1][:, None, :]
    gq = static[rows.a2] * tg[rows.tindex, rows.a2][:, None, :]
    return gp, gq


def corrupt(m, truth, d, rows, q):
    """DATA (row, chan, 4) from the sky-frame coherency m by the chain."""
    ap = q[rows.tindex, rows.a1] + RECEPTOR_ANGLE
    aq = q[rows.tindex, rows.a2] + RECEPTOR_ANGLE
    w = rotate(m, ap, aq)
    x = truth["xf"][None]
    w[..., 1] *= x
    w[..., 2] *= np.conj(x)
    dp = truth["leakage"][rows.a1]
    dq = truth["leakage"][rows.a2]
    xx, yy = w[..., 0].copy(), w[..., 3]
    w[..., 1] += dp[..., 0] * yy + np.conj(dq[..., 1]) * xx
    w[..., 2] += dp[..., 1] * xx + np.conj(dq[..., 0]) * yy
    gp, gq = diagonal(truth, d, rows)
    for k, (a, b) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        w[..., k] *= gp[..., a] * np.conj(gq[..., b])
    return w


def correct(v, truth, d, rows, q, parang=True):
    """The exact inverse of `corrupt` (the NumPy self-check); with
    parang=False it stops before P, giving P M P^H."""
    w = np.array(v, np.complex128)
    gp, gq = diagonal(truth, d, rows)
    for k, (a, b) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        w[..., k] /= gp[..., a] * np.conj(gq[..., b])
    dp = truth["leakage"][rows.a1]
    dq = truth["leakage"][rows.a2]
    xx, yy = w[..., 0].copy(), w[..., 3]
    w[..., 1] -= dp[..., 0] * yy + np.conj(dq[..., 1]) * xx
    w[..., 2] -= dp[..., 1] * xx + np.conj(dq[..., 0]) * yy
    x = truth["xf"][None]
    w[..., 1] /= x
    w[..., 2] /= np.conj(x)
    if not parang:
        return w
    ap = q[rows.tindex, rows.a1] + RECEPTOR_ANGLE
    aq = q[rows.tindex, rows.a2] + RECEPTOR_ANGLE
    return rotate(w, ap, aq, inverse=True)


def corrupt_matrix(m, truth, d, rows, q):
    """The chain as explicit 2x2 products with the full D matrix (a second,
    independent reading for the self-check; equal to `corrupt` to first
    order in d, and exactly when d = 0)."""
    n, nchan, _ = m.shape
    mm = m.reshape(n, nchan, 2, 2)

    def pmat(a):
        c, s = np.cos(a), np.sin(a)
        return np.stack([np.stack([c, s], -1), np.stack([-s, c], -1)], -2)[:, None]

    ap = q[rows.tindex, rows.a1] + RECEPTOR_ANGLE
    aq = q[rows.tindex, rows.a2] + RECEPTOR_ANGLE
    gp, gq = diagonal(truth, d, rows)

    def jones_of(g, leak, a):
        dmat = np.zeros((len(a), nchan, 2, 2), complex)
        dmat[..., 0, 0] = 1
        dmat[..., 1, 1] = 1
        dmat[..., 0, 1] = leak[..., 0]
        dmat[..., 1, 0] = leak[..., 1]
        xmat = np.zeros((1, nchan, 2, 2), complex)
        xmat[..., 0, 0] = truth["xf"]
        xmat[..., 1, 1] = 1
        gmat = np.zeros((len(a), nchan, 2, 2), complex)
        gmat[..., 0, 0] = g[..., 0]
        gmat[..., 1, 1] = g[..., 1]
        return gmat @ dmat @ xmat @ pmat(a)

    jp = jones_of(gp, truth["leakage"][rows.a1], ap)
    jq = jones_of(gq, truth["leakage"][rows.a2], aq)
    return (jp @ mm @ np.conj(np.swapaxes(jq, -1, -2))).reshape(n, nchan, 4)


def chunk_rows(tindex, a1, a2):
    """Rows of whole integrations `tindex`, baselines (a1, a2) in MS order."""
    tindex = np.asarray(tindex, np.int64)
    nbl = len(a1)
    return Rows(
        np.repeat(tindex, nbl), np.tile(a1, len(tindex)), np.tile(a2, len(tindex))
    )


def sky_coherency(d, rows, uvw_ant, fields, sky, cal):
    """(row, chan, 4) sky-frame M and the rows' UVW: the calibrators' point
    Stokes at the phase centre, the target's components by the core DFT."""
    uvw = uvw_ant[rows.tindex, rows.a1] - uvw_ant[rows.tindex, rows.a2]
    rf = fields[rows.tindex]
    m = np.zeros((len(rows.tindex), d.nchan, 4), complex)
    for f in np.unique(rf):
        sel = rf == f
        if f == 3:
            m[sel] = target_coherency(uvw[sel], d.freq, sky)
        else:
            m[sel] = stokes_coherency(cal[f])[None]
    return m, uvw


# -- RFI and noise ----------------------------------------------------------------


def rfi_events(d, ntime):
    """RFI events drawn from the rfi seed: persistent and intermittent
    narrowband transmitters and broadband bursts. Each has channels, a
    per-integration amplitude (Jy, 0 when off), a baseline-length cut-off
    and decay, a fixed local direction (az, el) for the geometric phase and
    a polarisation vector."""
    rng = np.random.default_rng(d.seeds["rfi"])
    nu = d.freq
    sigma = d.sigma
    width = d.chan_width
    events = []

    def chans(f_lo, f_hi):
        idx = np.flatnonzero((nu + width / 2 > f_lo) & (nu - width / 2 < f_hi))
        return idx

    def add(kind, ch, amp_t, name):
        if not len(ch):
            return
        beta = rng.uniform(0, math.pi / 2)
        gamma = rng.uniform(-math.pi, math.pi)
        lmax = float(rng.uniform(400.0, 4000.0))
        events.append(
            {
                "name": name,
                "kind": kind,
                "chans": [int(c) for c in ch],
                "amp_t": amp_t,
                "lmax_m": lmax,
                "l0_m": lmax / 3.0,
                "az_deg": float(rng.uniform(0, 360)),
                "el_deg": float(rng.uniform(0, 5)),
                "phase0": float(rng.uniform(-math.pi, math.pi)),
                "pol": [
                    math.cos(beta),
                    math.sin(beta) * math.cos(gamma),
                    math.sin(beta) * math.sin(gamma),
                ],
            }
        )

    persistent = [
        ("GSM downlink", 935e6, 960e6),
        ("GPS L5 / Galileo E5", 1166e6, 1186e6),
        ("GPS L2", 1222e6, 1232e6),
        ("Inmarsat", 1537e6, 1545e6),
        ("GPS L1", 1570e6, 1580e6),
        ("Iridium", 1618e6, 1626e6),
    ]
    for name, lo, hi in persistent:
        level = sigma * float(np.exp(rng.uniform(math.log(3.0), math.log(300.0))))
        mod = 1.0 + 0.3 * np.sin(2 * math.pi * np.arange(ntime) / rng.uniform(50, 400))
        add("persistent", chans(lo, hi), (level * mod).tolist(), name)
    # Intermittent: aircraft DME / ADS-B (on in random runs of integrations).
    for name, lo, hi in (("DME", 1025e6, 1150e6), ("ADS-B", 1088e6, 1092e6)):
        ch = chans(lo, hi)
        ch = ch[rng.random(len(ch)) < (0.35 if name == "DME" else 1.0)]
        on = np.zeros(ntime)
        t = 0
        while t < ntime:
            t += int(rng.integers(5, 60))
            run = int(rng.integers(1, 6))
            on[t : t + run] = sigma * float(
                np.exp(rng.uniform(math.log(2.0), math.log(500.0)))
            )
            t += run
        add("intermittent", ch, on.tolist(), name)
    # Broadband bursts: one or two integrations, 40-200 contiguous MHz.
    nburst = max(3, ntime // 60)
    for k in range(nburst):
        t = int(rng.integers(0, ntime))
        span = rng.uniform(40e6, 200e6)
        lo = rng.uniform(d.fmin, d.fmax - span)
        amp = np.zeros(ntime)
        amp[t : t + int(rng.integers(1, 3))] = sigma * float(
            np.exp(rng.uniform(math.log(2.0), math.log(100.0)))
        )
        add("burst", chans(lo, lo + span), amp.tolist(), f"burst {k}")
    return events


def enu_baselines(d):
    """(nant, 3) antenna positions in the local east-north-up frame (m)."""
    xyz_all, _, _ = antenna_table()
    xyz = xyz_all[d.antennas]
    c = xyz_all.mean(axis=0)
    lon = math.atan2(c[1], c[0])
    lat = math.atan2(c[2], math.hypot(c[0], c[1]))
    rot = np.array(
        [
            [-math.sin(lon), math.cos(lon), 0.0],
            [
                -math.sin(lat) * math.cos(lon),
                -math.sin(lat) * math.sin(lon),
                math.cos(lat),
            ],
            [
                math.cos(lat) * math.cos(lon),
                math.cos(lat) * math.sin(lon),
                math.sin(lat),
            ],
        ]
    )
    return (xyz - c) @ rot.T


def rfi_chunk(events, d, rows, enu):
    """(row, chan, 4) RFI added to DATA for the chunk's rows."""
    nu = d.freq
    n = len(rows.tindex)
    out = np.zeros((n, len(nu), 4), complex)
    b = enu[rows.a1] - enu[rows.a2]
    length = np.linalg.norm(b, axis=1)
    for e in events:
        amp_t = np.asarray(e["amp_t"])[rows.tindex]
        w = np.where(length <= e["lmax_m"], np.exp(-length / e["l0_m"]), 0.0) * amp_t
        sel = np.flatnonzero(w > 0)
        if not len(sel):
            continue
        az, el = e["az_deg"] * DEG, e["el_deg"] * DEG
        s = np.array(
            [math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)]
        )
        delay = (b[sel] @ s) / C
        ch = np.asarray(e["chans"])
        phase = 2 * math.pi * delay[:, None] * nu[ch][None] + e["phase0"]
        ex = e["pol"][0]
        ey = e["pol"][1] + 1j * e["pol"][2]
        coh = np.array([ex * ex, ex * np.conj(ey), ey * ex, abs(ey) ** 2])
        val = w[sel][:, None, None] * np.exp(1j * phase)[..., None] * coh[None, None]
        out[np.ix_(sel, ch, np.arange(4))] += val
    return out


def noise_integration(d, tindex, nbl):
    """(nbl, chan, 4) complex noise of one integration: N(0, sigma^2) per
    real and imaginary part, from (noise seed, integration index)."""
    rng = np.random.default_rng([d.seeds["noise"], int(tindex)])
    g = rng.standard_normal((nbl, d.nchan, 4, 2))
    return (g[..., 0] + 1j * g[..., 1]) * d.sigma


# -- files ------------------------------------------------------------------------


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=1, default=_jsonable) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _jsonable(v):
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.generic):
        return v.item()
    raise TypeError(type(v))


__all__ = [
    "CORR",
    "FIELDS",
    "RECEPTOR_ANGLE",
    "Design",
    "Rows",
    "antenna_table",
    "calibrator_stokes",
    "casa_gauge",
    "correct",
    "corrupt",
    "corrupt_matrix",
    "design",
    "enu_baselines",
    "geometry",
    "jones",
    "noise_integration",
    "rfi_chunk",
    "rfi_events",
    "rotate",
    "schedule",
    "stokes_coherency",
    "target_coherency",
    "target_sky",
]
