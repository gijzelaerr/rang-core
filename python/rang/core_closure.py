"""Closure quantities as a gauge-free flagging statistic (research/c1-closure-arm.md).

The Rust kernel `core/src/closure.rs` computes, for every sample of every
baseline, the median normalised closure residual against the model, the
median closure TV and the closure count of one family:

- `"trace"`: closure traces `tr(V_ab V_sb^-1 V_sd V_ad^-1) / 2` (Broderick and
  Pesce 2020), invariant under any per-antenna 2x2 gains, on the cyclic
  quadrangles (baseline (a, b) leads one per station s, d the next station
  after s in the cycle, re-routed up to `reroute` times around a missing
  edge);
- `"phase"`: parallel-hand closure phases on all triangles;
- `"logamp"`: parallel-hand log closure amplitudes on the cyclic quadrangles.

Only `usable` samples (the campaign passes its training cells) enter a
closure. This module loads the kernel, holds an independent NumPy reference
for the tests and the in-run gate, and turns the per-sample scores into the
protocol's gain-grid maps, the robust outlier score and the Q1 statistics.

Until `core/src/lib.rs` lists `closure` and `ffi_closure` (a coordinator
edit), the files are built with `jones.rs` as a standalone cdylib in
`core/target/c1-standalone` and loaded through ctypes; `RANG_C1_LIB` selects
a prebuilt library.
"""

import ctypes
import os
import subprocess
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import core

FAMILIES = {"trace": 0, "phase": 1, "logamp": 2}
MIN_CLOSURES = 5
REROUTE = 3
MAD_FLOOR = 0.05
SOURCES = ("jones.rs", "closure.rs", "ffi_closure.rs")
SYMBOLS = ("rang_core_closure_scores", "rang_core_closure_last_error")
CORR_LINEAR = (9, 10, 11, 12)


# --- loading -----------------------------------------------------------------


class ClosureInputs(ctypes.Structure):
    _fields_ = [
        ("nrow", ctypes.c_size_t),
        ("nchan", ctypes.c_size_t),
        ("nant", ctypes.c_size_t),
        ("ntime", ctypes.c_size_t),
        ("nstation", ctypes.c_size_t),
        ("data", ctypes.c_void_p),
        ("model", ctypes.c_void_p),
        ("weights", ctypes.c_void_p),
        ("usable", ctypes.c_void_p),
        ("antenna1", ctypes.c_void_p),
        ("antenna2", ctypes.c_void_p),
        ("time_index", ctypes.c_void_p),
        ("stations", ctypes.c_void_p),
        ("family", ctypes.c_uint32),
        ("min_closures", ctypes.c_uint32),
        ("reroute", ctypes.c_uint32),
    ]


def standalone_dir():
    return core.core_root() / "target" / "c1-standalone"


def _write_if_changed(path, text):
    """Write only on change, so that cargo's fingerprints stay valid."""
    path = Path(path)
    if not path.is_file() or path.read_text() != text:
        path.write_text(text)


def write_standalone():
    """The standalone crate (`rang_c1_core`) whose root includes the C1 files
    and `jones.rs` by path; rayon comes from the core's lock."""
    root = core.core_root()
    out = standalone_dir()
    out.mkdir(parents=True, exist_ok=True)
    _write_if_changed(
        out / "Cargo.toml",
        "[package]\n"
        'name = "rang-c1-core"\n'
        'version = "0.1.0"\n'
        'edition = "2024"\n'
        'license = "GPL-3.0-or-later"\n'
        "publish = false\n\n"
        "[lib]\n"
        'name = "rang_c1_core"\n'
        'path = "root.rs"\n'
        'crate-type = ["rlib", "cdylib"]\n\n'
        "[dependencies]\n"
        'rayon = "1.12.0"\n\n'
        "[profile.release]\n"
        'lto = "thin"\n'
        "codegen-units = 1\n\n"
        "[workspace]\n",
    )
    modules = "".join(
        f'#[path = "{(root / "src" / name).as_posix()}"]\npub mod {name.removesuffix(".rs")};\n'
        for name in SOURCES
    )
    _write_if_changed(
        out / "root.rs",
        "//! Standalone build of the C1 closure kernel until core/src/lib.rs lists it.\n"
        + modules,
    )
    _write_if_changed(out / "Cargo.lock", (root / "Cargo.lock").read_text())
    return out


def build_standalone():
    out = write_standalone()
    subprocess.run(
        [
            "cargo",
            "build",
            "--offline",
            "--release",
            "-q",
            "--manifest-path",
            str(out / "Cargo.toml"),
        ],
        cwd=out,
        check=True,
    )
    return out / "target" / "release" / "librang_c1_core.so"


def _declare(lib):
    lib.rang_core_closure_scores.argtypes = [
        ctypes.POINTER(ClosureInputs),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    lib.rang_core_closure_scores.restype = ctypes.c_int
    lib.rang_core_closure_last_error.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.rang_core_closure_last_error.restype = ctypes.c_size_t
    return lib


@lru_cache(maxsize=1)
def library():
    """A ctypes handle exporting the C1 symbols: `RANG_C1_LIB` if set, else
    the standalone build."""
    configured = os.environ.get("RANG_C1_LIB")
    if configured:
        return _declare(ctypes.CDLL(str(Path(configured).resolve())))
    return _declare(ctypes.CDLL(str(build_standalone())))


def library_path():
    return Path(library()._name).resolve()


def _last_error(lib):
    buf = ctypes.create_string_buffer(512)
    n = lib.rang_core_closure_last_error(buf, len(buf))
    return buf.value[:n].decode(errors="replace")


# --- the kernel --------------------------------------------------------------


def scores(
    data,
    model,
    weights,
    usable,
    antenna1,
    antenna2,
    time_index,
    stations,
    family,
    *,
    nant=None,
    min_closures=MIN_CLOSURES,
    reroute=REROUTE,
):
    """Per-sample closure scores of one family: `residual` and `tv` (float32,
    NaN without a score) and `count` (uint16), each `(nrow, nchan)`."""
    data = np.require(data, np.complex64, ["C", "A"])
    model = np.require(model, np.complex64, ["C", "A"])
    weights = np.require(weights, np.float32, ["C", "A"])
    nrow, nchan = data.shape[:2]
    if data.shape != (nrow, nchan, 4) or model.shape != data.shape:
        raise ValueError("data and model must be (row, chan, 4)")
    if weights.shape != data.shape:
        raise ValueError("weights must be (row, chan, 4)")
    usable = np.require(usable, np.uint8, ["C", "A"])
    if usable.shape != (nrow, nchan):
        raise ValueError("usable must be (row, chan)")
    a1 = np.require(antenna1, np.uint32, ["C", "A"])
    a2 = np.require(antenna2, np.uint32, ["C", "A"])
    ti = np.require(time_index, np.uint32, ["C", "A"])
    st = np.require(stations, np.uint32, ["C", "A"])
    if not (len(a1) == len(a2) == len(ti) == nrow):
        raise ValueError("row columns must have one entry per row")
    nant = int(max(a1.max(initial=0), a2.max(initial=0)) + 1) if nant is None else nant
    ntime = int(ti.max(initial=0)) + 1 if nrow else 0
    inputs = ClosureInputs(
        nrow,
        nchan,
        nant,
        ntime,
        len(st),
        data.ctypes.data,
        model.ctypes.data,
        weights.ctypes.data,
        usable.ctypes.data,
        a1.ctypes.data,
        a2.ctypes.data,
        ti.ctypes.data,
        st.ctypes.data,
        FAMILIES[family],
        int(min_closures),
        int(reroute),
    )
    residual = np.empty((nrow, nchan), np.float32)
    tv = np.empty((nrow, nchan), np.float32)
    count = np.empty((nrow, nchan), np.uint16)
    lib = library()
    status = lib.rang_core_closure_scores(
        ctypes.byref(inputs), residual.ctypes.data, tv.ctypes.data, count.ctypes.data
    )
    if status:
        raise ValueError(f"closure kernel failed ({status}): {_last_error(lib)}")
    return {"residual": residual, "tv": tv, "count": count}


# --- an independent NumPy reference ------------------------------------------


class Reference:
    """Direct enumeration of the protocol's closures with NumPy's matrix
    inverse and trace, for small subsets (tests and the in-run gate)."""

    def __init__(
        self,
        data,
        model,
        weights,
        usable,
        antenna1,
        antenna2,
        time_index,
        stations,
        reroute=REROUTE,
    ):
        self.data, self.model, self.weights = data, model, weights
        self.usable = np.asarray(usable, bool)
        self.stations = [int(s) for s in stations]
        self.reroute = reroute
        self.rows = {}
        for row, (a, b, t) in enumerate(
            zip(
                np.asarray(antenna1).tolist(),
                np.asarray(antenna2).tolist(),
                np.asarray(time_index).tolist(),
            )
        ):
            if a != b:
                self.rows[(t, a, b)] = row

    def edge(self, t, i, j, c):
        """(data 2x2, model 2x2, (w_XX, w_YY)) oriented i -> j, or None."""
        if (t, i, j) in self.rows:
            row, flip = self.rows[(t, i, j)], False
        elif (t, j, i) in self.rows:
            row, flip = self.rows[(t, j, i)], True
        else:
            return None
        if not self.usable[row, c]:
            return None
        d = self.data[row, c].astype(np.complex128).reshape(2, 2)
        m = self.model[row, c].astype(np.complex128).reshape(2, 2)
        if flip:
            d, m = d.conj().T, m.conj().T
        w = self.weights[row, c].astype(np.float64)
        return d, m, (w[0], w[3])

    def next(self, x, excluded):
        n = len(self.stations)
        k = self.stations.index(x)
        while True:
            k = (k + 1) % n
            if self.stations[k] not in excluded:
                return self.stations[k]

    @staticmethod
    def _trace(ab, sb, sd, ad):
        try:
            x = ab @ np.linalg.inv(sb) @ sd @ np.linalg.inv(ad)
        except np.linalg.LinAlgError:
            return None
        return 0.5 * np.trace(x)

    @staticmethod
    def _inv_snr2(e, h):
        v = e[0][h, h]
        with np.errstate(divide="ignore"):
            x = 1.0 / (e[2][h] * abs(v) ** 2)
        return x if np.isfinite(x) and x > 0 else np.inf

    def closure(self, family, t, c, a, b, s):
        """(residual components, variances, route) or None."""
        ab = self.edge(t, a, b, c)
        if ab is None:
            return None
        if family == "phase":
            bs, sa = self.edge(t, b, s, c), self.edge(t, s, a, c)
            if bs is None or sa is None:
                return None
            r, v = [], []
            for h in (0, 1):
                pd = ab[0][h, h] * bs[0][h, h] * sa[0][h, h]
                pm = ab[1][h, h] * bs[1][h, h] * sa[1][h, h]
                if pd == 0 or pm == 0:
                    return None
                r.append(np.angle(np.exp(1j * (np.angle(pd) - np.angle(pm)))))
                v.append(0.5 * sum(self._inv_snr2(e, h) for e in (ab, bs, sa)))
            return self._finite(np.array(r), np.array(v), s)
        sb = self.edge(t, s, b, c)
        if sb is None:
            return None
        n_tries = min(1 + self.reroute, len(self.stations) - 3)
        d = s
        for _ in range(n_tries):
            d = self.next(d, (a, b, s))
            sd, ad = self.edge(t, s, d, c), self.edge(t, a, d, c)
            if sd is None or ad is None:
                continue
            edges = (ab, sb, sd, ad)
            if family == "trace":
                td = self._trace(ab[0], sb[0], sd[0], ad[0])
                tm = self._trace(ab[1], sb[1], sd[1], ad[1])
                if td is None or tm is None:
                    return None
                var = 0.0
                for h in (0, 1):
                    p = ab[0][h, h] * sd[0][h, h] / (sb[0][h, h] * ad[0][h, h])
                    var += 0.25 * abs(p) ** 2 * sum(self._inv_snr2(e, h) for e in edges)
                return self._finite(np.array([td - tm]), np.array([var]), d)
            r, v = [], []
            for h in (0, 1):

                def closure(k, h=h, edges=edges):
                    amp = [np.log(abs(e[k][h, h])) for e in edges]
                    return amp[0] + amp[2] - amp[1] - amp[3]

                with np.errstate(divide="ignore", invalid="ignore"):
                    r.append(closure(0) - closure(1))
                v.append(0.5 * sum(self._inv_snr2(e, h) for e in edges))
            return self._finite(np.array(r), np.array(v), d)
        return None

    @staticmethod
    def _finite(r, v, route):
        if np.all(np.isfinite(r)) and np.all(np.isfinite(v)) and np.all(v > 0):
            return r, v, route
        return None

    @staticmethod
    def _normalised(rec):
        r, v, _ = rec
        return float(np.sqrt(np.mean(np.abs(r) ** 2 / v)))

    @staticmethod
    def _difference(family, x, y):
        d = x[0] - y[0]
        if family == "phase":
            d = np.angle(np.exp(1j * d))
        return float(np.sqrt(np.mean(np.abs(d) ** 2 / (x[1] + y[1]))))

    def sample(self, family, row_time, a, b, c, nchan, ntime, min_closures):
        """(residual, tv, count) of baseline (a, b) at (time, channel)."""
        t = row_time
        zs, es = [], []
        for s in self.stations:
            if s in (a, b):
                continue
            x = self.closure(family, t, c, a, b, s)
            if x is None:
                continue
            zs.append(self._normalised(x))
            edges = []
            for tt, cc in ((t - 1, c), (t + 1, c), (t, c - 1), (t, c + 1)):
                if not (0 <= tt < ntime and 0 <= cc < nchan):
                    continue
                y = self.closure(family, tt, cc, a, b, s)
                if y is not None and y[2] == x[2]:
                    edges.append(self._difference(family, x, y))
            if edges:
                es.append(np.mean(edges))
        residual = float(np.median(zs)) if len(zs) >= min_closures else np.nan
        tv = float(np.median(es)) if len(es) >= min_closures else np.nan
        return residual, tv, len(zs)


# --- maps, robust scores and statistics ---------------------------------------


def baseline_index(antenna1, antenna2, nant):
    """Dense baseline label per row (sorted unique (a, b)) and the pairs."""
    key = np.asarray(antenna1, np.int64) * nant + np.asarray(antenna2, np.int64)
    values, labels = np.unique(key, return_inverse=True)
    return labels, np.stack(np.divmod(values, nant), axis=1)


def bin_map(values, mask, time_bin, freq_bin, labels, shape, block=2048):
    """Mean of `values` over the `mask` samples with a finite value, per
    (time bin, frequency bin, baseline label); NaN where none."""
    ntb, nfb, nbl = shape
    total = np.zeros(ntb * nfb * nbl)
    count = np.zeros(ntb * nfb * nbl)
    freq_bin = np.asarray(freq_bin, np.int64)
    for start in range(0, len(values), block):
        s = slice(start, min(start + block, len(values)))
        v = np.asarray(values[s], np.float64)
        ok = np.asarray(mask[s], bool) & np.isfinite(v)
        r, c = np.nonzero(ok)
        idx = (time_bin[s][r] * nfb + freq_bin[c]) * nbl + labels[s][r]
        total += np.bincount(idx, weights=v[r, c], minlength=total.size)
        count += np.bincount(idx, minlength=count.size)
    out = np.full(total.size, np.nan)
    np.divide(total, count, out=out, where=count > 0)
    return out.reshape(shape), count.reshape(shape).astype(np.int64)


def antenna_map(baseline_map, pairs, nant):
    """Per (time bin, frequency bin, antenna): the median over the antenna's
    baselines of the finite baseline-map values; NaN where none."""
    ntb, nfb, _ = baseline_map.shape
    out = np.full((ntb, nfb, nant), np.nan)
    for i in range(nant):
        cols = np.flatnonzero((pairs[:, 0] == i) | (pairs[:, 1] == i))
        if len(cols) == 0:
            continue
        sub = baseline_map[:, :, cols]
        ok = np.isfinite(sub).any(axis=-1)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(np.where(ok[..., None], sub, 0.0), axis=-1)
        out[:, :, i] = np.where(ok, med, np.nan)
    return out


def robust_z(residual, mask, labels, floor=MAD_FLOOR):
    """`core_campaign_array.baseline_scores`' estimator on the closure
    residual: per baseline, over the `mask` samples with a finite positive
    residual, z = max((ln R - median) / max(1.4826 MAD, floor), 0); NaN
    elsewhere."""
    z = np.full(residual.shape, np.nan, np.float32)
    order = np.argsort(labels, kind="stable")
    cut = np.flatnonzero(np.diff(labels[order])) + 1
    for rows in np.split(order, cut):
        rows = np.sort(rows)
        r = residual[rows].astype(np.float64)
        ok = np.asarray(mask[rows], bool) & np.isfinite(r) & (r > 0)
        if not ok.any():
            continue
        x = np.log(r[ok])
        median = np.median(x)
        deviation = max(1.4826 * np.median(np.abs(x - median)), floor)
        block = z[rows]
        block[ok] = np.maximum((x - median) / deviation, 0)
        z[rows] = block
    return z


def top_mask(z, mask, threshold, max_fraction):
    """Training cells with z >= threshold, cut to `floor(max_fraction *
    |mask|)` by largest z (stable; ties by cell order). Returns sorted flat
    cell indices and the uncut count."""
    flat = z.reshape(-1)
    m = np.asarray(mask, bool).reshape(-1)
    cells = np.flatnonzero(m & np.isfinite(flat) & (flat >= threshold))
    limit = int(np.floor(max_fraction * np.count_nonzero(m)))
    proposed = len(cells)
    if len(cells) > limit:
        order = np.argsort(-flat[cells], kind="stable")
        cells = np.sort(cells[order[:limit]])
    return cells, proposed


def rank(x):
    """Average ranks (ties share the mean rank), as Spearman needs."""
    x = np.asarray(x, np.float64)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    ranks[order] = np.arange(len(x), dtype=np.float64)
    xs = x[order]
    start = np.r_[0, np.flatnonzero(np.diff(xs)) + 1]
    stop = np.r_[start[1:], len(x)]
    for a, b in zip(start, stop):
        if b - a > 1:
            ranks[order[a:b]] = 0.5 * (a + b - 1)
    return ranks


def spearman(x, y):
    """Spearman's rho over the pairs where both are finite; None if fewer
    than 3 pairs or a constant side."""
    x, y = np.asarray(x, np.float64).ravel(), np.asarray(y, np.float64).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return None
    rx, ry = rank(x[ok]), rank(y[ok])
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def r_squared(x, y):
    """Squared Pearson correlation of ln x and ln y over positive finite
    pairs; None if fewer than 3."""
    x, y = np.asarray(x, np.float64).ravel(), np.asarray(y, np.float64).ravel()
    ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    if ok.sum() < 3:
        return None
    lx, ly = np.log(x[ok]), np.log(y[ok])
    if lx.std() == 0 or ly.std() == 0:
        return None
    return float(np.corrcoef(lx, ly)[0, 1] ** 2)


def additive_r_squared(baseline_map, pairs, nant):
    """Fraction of the variance of ln(map) explained by a_p + a_q fitted per
    (time bin, frequency bin) by least squares, pooled over bins."""
    ntb, nfb = baseline_map.shape[:2]
    residual_ss, total_ss = 0.0, 0.0
    for t in range(ntb):
        for f in range(nfb):
            v = baseline_map[t, f]
            ok = np.isfinite(v) & (v > 0)
            if ok.sum() < 3:
                continue
            y = np.log(v[ok])
            design = np.zeros((ok.sum(), nant))
            rows = np.arange(ok.sum())
            design[rows, pairs[ok, 0]] = 1
            design[rows, pairs[ok, 1]] = 1
            coef, *_ = np.linalg.lstsq(design, y, rcond=None)
            residual_ss += float(np.sum((y - design @ coef) ** 2))
            total_ss += float(np.sum((y - y.mean()) ** 2))
    return 1 - residual_ss / total_ss if total_ss > 0 else None


def overlap(mask_cells, other_cells, ntrain):
    """|M n X|/|M|, |M n X|/|X| and the lift over chance, on sorted flat
    training-cell indices."""
    m = np.asarray(mask_cells, np.int64)
    x = np.asarray(other_cells, np.int64)
    both = int(np.intersect1d(m, x, assume_unique=True).size)
    of_mask = both / len(m) if len(m) else None
    of_other = both / len(x) if len(x) else None
    chance = len(x) / ntrain if ntrain else None
    return {
        "mask": len(m),
        "other": len(x),
        "both": both,
        "fraction_of_mask": of_mask,
        "fraction_of_other": of_other,
        "chance": chance,
        "lift": of_mask / chance if of_mask is not None and chance else None,
        "coincides": bool(
            of_mask is not None
            and chance
            and of_mask >= 0.10
            and of_mask / chance >= 3.0
        ),
    }
