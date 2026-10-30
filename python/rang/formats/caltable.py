"""CASA calibration tables (DF-IO-CT; research/dfio-formats.md, F1).

`read(path)` turns a CASA `NewCalTable` (G, B, K, T, Df Jones, CASA >= 3.4)
into a `CalTable`: every MAIN and subtable cell as the core reads it
(undefined cells are None, as CASA leaves WEIGHT), the keywords and
`table.info`, plus the VisCal semantics: the type from `VisCal`, the
parameter layout, the solution frequencies of the caltable's
SPECTRAL_WINDOW, the K reference frequency and the reference antenna
(ANTENNA2). `write(table, path)` writes one through the core writer
(`rang.core_ms_write.create_caltable`, CASA's write sequence; E4).
`from_gains(...)` builds a table from the core's gain arrays, and
`correct(...)` applies tables to visibilities as CASA `applycal` does, the
model frozen in the protocol from CASA's sources:

- VisCal order B, K, G, D, T (`VisCal::Type`); the diagonal terms commute,
  so corrected = D_p^-1 (diag_p^-1 V diag_q^-H) D_q^-H;
- K: phase 2 pi tau[ns] (nu - nu_ref)[GHz], nu_ref = CHAN_FREQ[nchan // 2]
  of the caltable window (`KJones::setApply`, CASA >= 5.3);
- Df: [[1, d0], [d1, 1]] (`DJones::calcOneJones`);
- time interpolation `linear` per (antenna, window): amplitude and tracked
  phase (`RIorAPArray::f(true)`) or the float parameters, in float32 with
  times relative to floor(t0 - 1) (`CTTimeInterp1`), the nearest slot
  outside the solution range, exact slots as they are; either bracketing
  slot's flag flags the result.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import core_ms, core_ms_write
from ._aipsio import table_info, table_keywords

SUBTABLES = core_ms_write.CAL_SUBTABLES
TYPES = ("B", "K", "G", "D", "T")  # VisCal::Type order of the supported terms
NPAR = {"G": 2, "B": 2, "K": 2, "T": 1, "Df": 2}


def _cells(path):
    """Every cell of every column of a table (None where undefined)."""
    with core_ms.open_table(path) as reader:
        nrows, names = reader.nrows, list(reader.columns)
    return {
        name: (core_ms_write.read_cells(path, name, 0, nrows) if nrows else [])
        for name in names
    }


@dataclass
class CalTable:
    """A CASA calibration table: cells, keywords, info and semantics."""

    vis_cal: str
    main: dict
    subtables: dict
    keywords: dict = field(default_factory=dict)
    info: list = field(default_factory=lambda: ["Calibration", "", ""])

    # -- identity ---------------------------------------------------------
    @property
    def kind(self):
        """`G`, `B`, `K`, `T` or `Df` (the first word of VisCal)."""
        return self.vis_cal.split()[0]

    @property
    def term(self):
        """The VisCal type letter used for ordering (`Df` is a D term)."""
        return "D" if self.kind.startswith("D") else self.kind

    @property
    def float_param(self):
        return self.keywords.get("ParType", "Complex") == "Float"

    @property
    def nrows(self):
        return len(self.main["TIME"])

    # -- the per-row arrays -----------------------------------------------
    def column(self, name):
        return np.asarray(self.main[name])

    @property
    def params(self):
        """(row, chan, par) complex64 (CPARAM) or float32 (FPARAM)."""
        name = "FPARAM" if self.float_param else "CPARAM"
        return np.stack([np.asarray(c) for c in self.main[name]])

    @property
    def flags(self):
        return np.stack([np.asarray(c, bool) for c in self.main["FLAG"]])

    @property
    def snr(self):
        return np.stack([np.asarray(c) for c in self.main["SNR"]])

    @property
    def reference_antenna(self):
        """The reference antennas of the solutions (ANTENNA2; -1: none)."""
        return sorted({int(a) for a in self.main["ANTENNA2"]})

    def solution_frequencies(self, spw):
        """CHAN_FREQ of window `spw` of the caltable's SPECTRAL_WINDOW."""
        return np.asarray(self.subtables["SPECTRAL_WINDOW"]["CHAN_FREQ"][spw], float)

    def k_reference_frequency(self, spw):
        """The K delay pivot (Hz): the caltable window's middle channel."""
        f = self.solution_frequencies(spw)
        return float(f[len(f) // 2])

    def summary(self):
        p = self.params
        return {
            "vis_cal": self.vis_cal,
            "rows": self.nrows,
            "antennas": sorted({int(a) for a in self.main["ANTENNA1"]}),
            "reference_antenna": self.reference_antenna,
            "times": len({float(t) for t in self.main["TIME"]}),
            "spws": sorted({int(s) for s in self.main["SPECTRAL_WINDOW_ID"]}),
            "param_shape": list(p.shape[1:]),
            "par_type": self.keywords.get("ParType"),
            "flagged_fraction": float(self.flags.mean()),
        }


def read(path):
    """A CASA calibration table at `path` as a `CalTable`."""
    path = Path(path)
    keywords = table_keywords(path)
    if "VisCal" not in keywords:
        raise ValueError(f"{path} is not a CASA calibration table (no VisCal)")
    subtables = {
        name: _cells(path / name) for name in SUBTABLES if (path / name).is_dir()
    }
    return CalTable(
        vis_cal=keywords["VisCal"],
        main=_cells(path),
        subtables=subtables,
        keywords=keywords,
        info=table_info(path),
    )


def write(table, path):
    """Write `table` as CASA writes a calibration table (E4's sequence)."""
    kw = table.keywords
    core_ms_write.create_caltable(
        path,
        table.vis_cal,
        table.main,
        table.subtables,
        kw.get("MSName", ""),
        kw.get("PolBasis", "unknown"),
        kw.get("CASA_Version", "6.7.6-14"),
        float_param=table.float_param,
    )
    return Path(path)


# -- building tables from the core's gains --------------------------------------


def _keep(values, name):
    return {k: v for k, v in values.items() if k in core_ms_write.CAL_COLUMNS[name]}


def subtables_from_ms(ms, single_channel=True):
    """ANTENNA, FIELD, SPECTRAL_WINDOW and OBSERVATION of an MS for a
    caltable; one solution channel per window (mean frequency, summed
    width) when `single_channel`, as gaincal writes G, K, T and Df."""
    ms = Path(ms)
    out = {}
    for name in ("ANTENNA", "FIELD", "SPECTRAL_WINDOW", "OBSERVATION"):
        out[name] = _keep(_cells(ms / name), name)
    if single_channel:
        spw = dict(out["SPECTRAL_WINDOW"])
        spw["CHAN_FREQ"] = [np.array([np.mean(c)]) for c in spw["CHAN_FREQ"]]
        for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
            spw[col] = [np.array([np.sum(c)]) for c in spw[col]]
        spw["NUM_CHAN"] = [np.int32(1) for _ in spw["NUM_CHAN"]]
        out["SPECTRAL_WINDOW"] = spw
    return out


def from_gains(
    kind,
    times,
    antennas,
    values,
    flags=None,
    *,
    subtables,
    field_id=0,
    spw=0,
    refant=0,
    interval=0.0,
    scan=-1,
    snr=100.0,
    ms_name="rang.ms",
):
    """A `CalTable` of type `kind` (G, B, K, T, Df) from gain arrays:
    `values[t, a]` is the (chan, par) parameter cell for time `times[t]` and
    antenna `antennas[a]` (complex; K: delays in ns, float), `flags` the
    same shape (bool)."""
    if kind not in NPAR:
        raise ValueError(f"unsupported calibration type {kind!r}")
    values = np.asarray(values)
    if values.ndim != 4 or values.shape[:2] != (len(times), len(antennas)):
        raise ValueError("values must be (time, antenna, chan, par)")
    if values.shape[3] != NPAR[kind]:
        raise ValueError(f"{kind} has {NPAR[kind]} parameters per channel")
    is_float = kind == "K"
    values = values.astype(np.float32 if is_float else np.complex64)
    flags = np.zeros(values.shape, bool) if flags is None else np.asarray(flags, bool)
    rows = [(t, a) for t in range(len(times)) for a in range(len(antennas))]
    n = len(rows)
    cell = values.shape[2:]
    main = {
        "TIME": [float(times[t]) for t, _ in rows],
        "FIELD_ID": [int(field_id)] * n,
        "SPECTRAL_WINDOW_ID": [int(spw)] * n,
        "ANTENNA1": [int(antennas[a]) for _, a in rows],
        "ANTENNA2": [int(refant)] * n,
        "INTERVAL": [float(interval)] * n,
        "SCAN_NUMBER": [int(scan)] * n,
        "OBSERVATION_ID": [0] * n,
        ("FPARAM" if is_float else "CPARAM"): [values[t, a] for t, a in rows],
        "PARAMERR": [np.zeros(cell, np.float32)] * n,
        "FLAG": [flags[t, a] for t, a in rows],
        "SNR": [np.full(cell, snr, np.float32)] * n,
        "WEIGHT": [None] * n,
    }
    vis_cal = {"Df": "Df Jones"}.get(kind, f"{kind} Jones")
    keywords = {
        "ParType": "Float" if is_float else "Complex",
        "MSName": ms_name,
        "VisCal": vis_cal,
        "PolBasis": "unknown",
        "CASA_Version": "6.7.6-14",
    }
    return CalTable(
        vis_cal, main, dict(subtables), keywords, ["Calibration", vis_cal, ""]
    )


# -- applying tables (the VisCal semantics) -------------------------------------


def _track_phase(phase):
    """CASA's phase tracking along rows (axis 0): each phase moved by whole
    turns to within pi of the previous row's, in float32."""
    out = phase.astype(np.float32).copy()
    two_pi = np.float32(2 * np.pi)
    for i in range(1, len(out)):
        d = out[i] - out[i - 1]
        out[i] -= two_pi * np.round(d / two_pi).astype(np.float32)
    return out


def _interpolate(times, values, flags, at):
    """CTTimeInterp1 `linear` for one (antenna, window) series: `values`
    (slot, ...) float32 (amp/phase stacked for complex), `times` sorted
    float64; returns the values and flags at each time of `at`."""
    ref = np.floor(times[0] - 1.0)
    tl = (times - ref).astype(np.float32)
    ft = (np.asarray(at, float) - ref).astype(np.float32)
    out = np.empty((len(ft),) + values.shape[1:], np.float32)
    fout = np.empty((len(ft),) + flags.shape[1:], bool)
    n = len(tl)
    for k, x in enumerate(ft):
        if n == 1 or x <= tl[0]:
            i, exact = 0, True
        elif x >= tl[-1]:
            i, exact = n - 1, True
        else:
            i = int(np.searchsorted(tl, x, side="right") - 1)
            exact = bool(tl[i] == x)
        if exact:
            out[k], fout[k] = values[i], flags[i]
        else:
            x0, x1 = tl[i], tl[i + 1]
            y0, y1 = values[i], values[i + 1]
            out[k] = y0 + (x - x0) * (y1 - y0) / (x1 - x0)
            fout[k] = flags[i] | flags[i + 1]
    return out, fout


def _series(table, antenna, spw, field_id):
    """Rows of one antenna and window (the nearest field: the table's own
    when it has a single one), sorted by time."""
    ant = table.column("ANTENNA1")
    spws = table.column("SPECTRAL_WINDOW_ID")
    fields = table.column("FIELD_ID")
    pick = (ant == antenna) & (spws == spw)
    if np.any(pick & (fields == field_id)):
        pick &= fields == field_id
    rows = np.flatnonzero(pick)
    t = table.column("TIME")[rows]
    order = np.argsort(t, kind="stable")
    return rows[order], t[order]


def _resample_freq(values, flags, fin, fout, complex_par):
    """CTPatchedInterp::resampleInFreq with interp 'linear' (no 'flag'
    suffix): per float parameter, the unflagged solution channels only;
    the same grid is copied; the phase unwrapped over them; nearest beyond
    the first and last unflagged channel, linear between (float values,
    GHz abscissae); flagged channels are bridged, not flagged; a parameter
    with every channel flagged is flagged (value 0).
    `values` is (nsol, npar, 2) amp/phase (complex) or (nsol, npar) float."""
    nsol, npar = flags.shape
    fin = np.asarray(fin, float) / 1e9
    fout = np.asarray(fout, float) / 1e9
    nf = len(fout)
    nfpar = 2 if complex_par else 1
    out = np.zeros((nf, npar, nfpar), np.float32)
    oflag = np.zeros((nf, npar), bool)
    vals = values.reshape(nsol, npar, nfpar)
    for p in range(npar):
        good = ~flags[:, p]
        if not good.any():
            oflag[:, p] = True
            continue
        mfin = fin[good]
        for q in range(nfpar):
            y = vals[good, p, q].astype(np.float32)
            if len(fout) == len(mfin) and np.allclose(fout, mfin, rtol=0, atol=1e-10):
                out[:, p, q] = y
                continue
            if complex_par and q == 1:
                y = y.astype(np.float64)
                for i in range(1, len(y)):
                    while y[i] - y[i - 1] > np.pi:
                        y[i] -= 2 * np.pi
                    while y[i] - y[i - 1] < -np.pi:
                        y[i] += 2 * np.pi
                y = y.astype(np.float32)
            res = np.empty(nf, np.float32)
            lo_v, hi_v = y[0], y[-1]
            inner = (fout > mfin[0]) & (fout < mfin[-1])
            res[fout <= mfin[0]] = lo_v
            res[fout >= mfin[-1]] = hi_v
            if inner.any():
                x = fout[inner]
                i = np.searchsorted(mfin, x, side="right") - 1
                i = np.clip(i, 0, len(mfin) - 2)
                x0, x1 = mfin[i], mfin[i + 1]
                y0, y1 = y[i].astype(np.float64), y[i + 1].astype(np.float64)
                res[inner] = (y0 + (x - x0) * (y1 - y0) / (x1 - x0)).astype(np.float32)
            out[:, p, q] = res
    return out, oflag


def jones_terms(table, antenna, spw, field_id, row_times, frequencies):
    """The table's per-receptor parameters for `antenna` at each time and
    channel: (time, chan, 2) complex128 values and (time, chan, 2) flags.
    G, B, T: the diagonal gains; K: exp(i phase); Df: the leakages d0, d1
    (each flag set when either is flagged)."""
    rows, t = _series(table, antenna, spw, field_id)
    nt, nf = len(row_times), len(frequencies)
    if not len(rows):
        return np.ones((nt, nf, 2), complex), np.ones((nt, nf, 2), bool)
    params = table.params[rows]
    flags = table.flags[rows]
    complex_par = not table.float_param
    if complex_par:
        amp = np.abs(params).astype(np.float32)
        ph = _track_phase(np.angle(params).astype(np.float32))
        vals, fl = _interpolate(t, np.stack([amp, ph], -1), flags, row_times)
    else:
        vals, fl = _interpolate(t, params.astype(np.float32), flags, row_times)
    fin = table.solution_frequencies(spw)
    npar = params.shape[2]
    p = np.empty((nt, nf, npar), complex)
    pf = np.empty((nt, nf, npar), bool)
    for k in range(nt):
        r, rf = _resample_freq(vals[k], fl[k], fin, frequencies, complex_par)
        if complex_par:
            a, f = r[..., 0], r[..., 1]
            p[k] = (a * np.cos(f) + 1j * (a * np.sin(f))).astype(np.complex64)
        else:
            p[k] = r[..., 0]
        pf[k] = rf
    kind = table.kind
    if kind == "K":
        nu = np.asarray(frequencies, float) / 1e9
        ref = table.k_reference_frequency(spw) / 1e9
        values = np.exp(1j * 2 * np.pi * p.real * (nu[None, :, None] - ref))
        return values, pf
    if kind == "T":
        return np.repeat(p[..., :1], 2, -1), np.repeat(pf[..., :1], 2, -1)
    if kind.startswith("D"):
        bad = pf[..., 0] | pf[..., 1]
        return p, np.stack([bad, bad], -1)
    return p, pf


def correct(
    data, flag, time, antenna1, antenna2, frequencies, tables, field_id=0, spw=0
):
    """Apply `tables` (CalTable list) to `data` (row, chan, 4) linear
    correlations XX, XY, YX, YY as `applycal(applymode='calflag',
    interp='linear')`; returns (corrected complex128, flags). Diagonal
    terms divide V_pq,ab by g_p,a conj(g_q,b) and flag the correlations of
    a flagged receptor; Df is CASA's linear approximation (`JonesGenLin`):
    XY -= d0_p YY + conj(d1_q) XX, YX -= d1_p XX + conj(d0_q) YY, parallel
    hands unchanged, a flagged term flags all four correlations."""
    data = np.asarray(data)
    nrow, nchan, _ = data.shape
    v = data.astype(np.complex128).copy()
    out_flag = np.array(flag, bool).copy()
    order = sorted(tables, key=lambda t: TYPES.index(t.term))
    antennas = np.union1d(antenna1, antenna2)
    times = np.unique(time)
    tindex = np.searchsorted(times, time)
    pols = ((0, 0), (0, 1), (1, 0), (1, 1))
    for table in order:
        gp = np.empty((nrow, nchan, 2), complex)
        gq = np.empty_like(gp)
        fp = np.empty((nrow, nchan, 2), bool)
        fq = np.empty_like(fp)
        for a in antennas:
            g, f = jones_terms(table, int(a), spw, field_id, times, frequencies)
            for sel, gg, ff in ((antenna1 == a, gp, fp), (antenna2 == a, gq, fq)):
                gg[sel] = g[tindex[sel]]
                ff[sel] = f[tindex[sel]]
        if table.term == "D":
            xx, yy = v[..., 0].copy(), v[..., 3].copy()
            v[..., 1] -= gp[..., 0] * yy + np.conj(gq[..., 1]) * xx
            v[..., 2] -= gp[..., 1] * xx + np.conj(gq[..., 0]) * yy
            bad = fp[..., 0] | fq[..., 0]
            out_flag |= bad[..., None]
            continue
        for c, (a, b) in enumerate(pols):
            bad = fp[..., a] | fq[..., b]
            denom = np.where(bad, 1, gp[..., a] * np.conj(gq[..., b]))
            v[..., c] /= denom
            out_flag[..., c] |= bad
    return v, out_flag


__all__ = [
    "CalTable",
    "correct",
    "from_gains",
    "jones_terms",
    "read",
    "subtables_from_ms",
    "write",
]
