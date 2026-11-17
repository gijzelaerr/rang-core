"""Scores of research/e2a-3b-k.md (composites as e2a-3b-diag: every 8th time,
pooled field map, `e2avg_common` unchanged).

    python k_score.py split        step 1: T-T against T-K3 (archived), the ratio split
    python k_score.py model        step 2: rang's MODEL_DATA, CASA's, Reynolds 1994 in NumPy
    python k_score.py real         step 3: TT against the nash CASA arms, and the controls
    python k_score.py sim TAG      step 4: the arms of one simulated case against truth
    python k_score.py f0           step F: full scale, E2-A field 0
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2avg_common as C
from rang import cal_apply, core_ms

O = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"
WIN = O / "win"
FCAL = "J1939-6342"
STEP = 8
POOLED = [cal_apply.POOLED] * 3
REF = "m022"
ODD = 50  # m053, its delay near the 2,392 ns ambiguity


def tabs(d, names):
    return [C.table(Path(d) / n) for n in names]


class Comp:
    """Composites on one MS's scored rows, cached per arm."""

    def __init__(self, ms):
        self.ms = ms
        self.fid = C.field_id(ms, FCAL)
        with core_ms.open_table(ms) as t:
            c = {
                n: np.asarray(t.getcol(n))
                for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")
            }
        rows = (c["FIELD_ID"] == self.fid) & (c["ANTENNA1"] != c["ANTENNA2"])
        times = np.unique(c["TIME"][rows])[::STEP]
        rows &= np.isin(c["TIME"], times)
        self.a1, self.a2 = c["ANTENNA1"][rows], c["ANTENNA2"][rows]
        self.cache = {}

    def get(self, key, tables):
        if key not in self.cache:
            self.cache[key] = C.composite(
                self.ms, self.fid, tables, [cal_apply.POOLED] * len(tables), step=STEP
            )
        return self.cache[key]

    def rel(self, ka, ta, kb, tb):
        a, fa = self.get(ka, ta)
        b, fb = self.get(kb, tb)
        out = C.rel_stats(a, fa, b, fb)
        keep = (self.a1 != ODD) & (self.a2 != ODD)
        out["without_id50"] = C.rel_stats(a[keep], fa[keep], b[keep], fb[keep])
        return out


def brief(x):
    return {
        "median": x["median"],
        "p95": x["p95"],
        "median_wo50": x["without_id50"]["median"],
    }


def split():
    """Step 1 on the real subset: r = J_TT / J_TK3."""
    t0 = time.perf_counter()
    cp = Comp(O / "src.ms")
    tt = WIN / "rang-tt.ms.rang-run" / "calibrate"
    tk3 = WIN / "casa-tk3"
    A = tabs(tt, ("K1", "G1", "B1"))
    B = [A[0], *tabs(tk3, ("G1", "B1"))]
    a, fa = cp.get("tt", A)
    b, fb = cp.get("tk3", B)
    ok = ~fa & ~fb & (np.abs(b) > 0)
    r = np.where(ok, a / np.where(ok, b, 1), np.nan)
    out = {"KGB1": brief(cp.rel("tt", A, "tk3", B))}
    # (a) a per-channel factor common to all rows (complex median per channel and hand)
    common = np.nanmedian(r.real, 0) + 1j * np.nanmedian(r.imag, 0)
    left = r / common[None]
    out["common_factor"] = {
        "abs_minus_1": C.stats(np.abs(np.abs(common[np.isfinite(common)]) - 1)),
        "phase_deg": C.stats(np.degrees(np.abs(np.angle(common[np.isfinite(common)])))),
        "left_rel": C.stats(np.abs(left - 1)[ok]),
    }
    # (b) amplitude against phase
    out["amplitude_part"] = C.stats(np.abs(np.abs(r) - 1)[ok])
    out["phase_part_rad"] = C.stats(np.abs(np.angle(r))[ok])
    # (c) G1 alone and B1 alone
    out["G1_only"] = brief(cp.rel("g_tt", [A[1]], "g_tk3", [B[1]]))
    out["B1_only"] = brief(cp.rel("b_tt", [A[2]], "b_tk3", [B[2]]))
    # per antenna (rows touching it)
    rel = np.abs(r - 1)
    out["per_antenna_median"] = {
        int(x): float(
            np.nanmedian(np.where(ok, rel, np.nan)[(cp.a1 == x) | (cp.a2 == x)])
        )
        for x in np.unique(np.concatenate([cp.a1, cp.a2]))
    }
    out["seconds"] = time.perf_counter() - t0
    C.write(O / "score-split.json", out)
    print(
        json.dumps(
            {k: v for k, v in out.items() if k != "per_antenna_median"}, indent=1
        )
    )
    return 0


def reynolds_jy(freq_hz):
    x = np.log10(freq_hz / 1e6)
    c = (-30.7667, 26.4908, -7.0977, 0.605334)  # Reynolds 1994, log10 nu/MHz
    return 10 ** sum(a * x**k for k, a in enumerate(c))


def model():
    """Step 2: |M_r / M_c - 1| over unflagged parallel-hand cross cells."""
    t0 = time.perf_counter()
    get = ("MODEL_DATA", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2", "TIME")
    with core_ms.open_table(O / "rang-u.ms") as t:
        r = {n: np.asarray(t.getcol(n)) for n in get}
    with core_ms.open_table(O / "casa-m.ms") as t:
        c = {
            n: np.asarray(t.getcol(n))
            for n in ("MODEL_DATA", "ANTENNA1", "ANTENNA2", "TIME")
        }
    for n in ("ANTENNA1", "ANTENNA2", "TIME"):
        assert np.array_equal(r[n], c[n]), n
    with core_ms.open_table(O / "src.ms") as t:
        flag = (
            np.asarray(t.getcol("FLAG"))
            | np.asarray(t.getcol("FLAG_ROW"))[:, None, None]
        )
    with core_ms.open_table(O / "src.ms" / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    cross = r["ANTENNA1"] != r["ANTENNA2"]
    s = reynolds_jy(freq)
    out = {}
    for h, k in (("XX", 0), ("YY", 3)):
        mr = r["MODEL_DATA"][cross][..., k].astype(complex)
        mc = c["MODEL_DATA"][cross][..., k].astype(complex)
        ok = ~flag[cross][..., k] & (np.abs(mc) > 0)
        q = mr[ok] / mc[ok]
        out[h] = {
            "rang_over_casa_abs_minus_1": C.stats(np.abs(np.abs(q) - 1)),
            "rang_over_casa_signed_median": float(np.median(np.abs(q) - 1)),
            "phase_deg": C.stats(np.degrees(np.abs(np.angle(q)))),
            "rang_over_reynolds_abs_minus_1": C.stats(
                np.abs(np.abs(mr) / s[None] - 1)[ok]
            ),
            "casa_over_reynolds_abs_minus_1": C.stats(
                np.abs(np.abs(mc) / s[None] - 1)[ok]
            ),
            "rang_time_variation": C.stats(
                (np.abs(mr) / np.median(np.abs(mr), 0) - 1)[ok]
            ),
        }
    # per-channel (median over rows) ratio, for the record
    q = np.abs(r["MODEL_DATA"][cross][..., 0]) / np.where(np.abs(c["MODEL_DATA"][cross][..., 0]) > 0,
                                                          np.abs(c["MODEL_DATA"][cross][..., 0]), np.nan)  # fmt: skip
    per = np.nanmedian(q, 0)
    out["per_channel_ratio_XX"] = {"min": float(np.nanmin(per)), "max": float(np.nanmax(per)),
                                   "band_ends": [float(per[0]), float(per[-1])]}  # fmt: skip
    out["seconds"] = time.perf_counter() - t0
    C.write(O / "score-model.json", out)
    print(json.dumps(out, indent=1))
    return 0


NAMES1 = ("K1", "G1", "B1")
NAMES0 = ("K0", "G0", "B0")


def real():
    t0 = time.perf_counter()
    cp = Comp(O / "src.ms")
    tt = WIN / "rang-tt.ms.rang-run" / "calibrate"
    arms = {"tt": tt, "win-tk3": WIN / "casa-tk3", "win-tf": WIN / "casa-tf",
            "ntk3": O / "casa-ntk3", "ntf": O / "casa-ntf", "tkg": O / "casa-tkg",
            "tk3m": O / "casa-tk3m", "u": O / "rang-u.ms.rang-run" / "calibrate",
            "d": O / "rang-d.ms.rang-run" / "calibrate"}  # fmt: skip
    shared = {"win-tk3": ("K0", "K1"), "ntk3": ("K0", "K1"), "tk3m": ("K0", "K1"),
              "tkg": ("K0", "G0", "K1", "G1")}  # fmt: skip

    def load(arm, names):
        d = arms[arm]
        out = []
        for n in names:
            src = tt if n in shared.get(arm, ()) else d
            if not (src / n).exists():
                return None
            out.append(C.table(src / n))
        return out

    pairs = [("tt", "win-tk3"), ("tt", "ntk3"), ("ntk3", "win-tk3"), ("ntf", "win-tf"),
             ("tt", "ntf"), ("tt", "win-tf"), ("tt", "tkg"), ("tt", "tk3m"), ("u", "tt"),
             ("u", "ntf"), ("d", "ntf"), ("d", "tt"), ("u", "d")]  # fmt: skip
    out = {}
    for a, b in pairs:
        for tag, names in (("KGB1", NAMES1), ("KGB0", NAMES0)):
            ta, tb = load(a, names), load(b, names)
            if ta is None or tb is None:
                continue
            out.setdefault(f"{a}-{b}", {})[tag] = cp.rel(
                f"{a}{tag}", ta, f"{b}{tag}", tb
            )
    out["seconds"] = time.perf_counter() - t0
    C.write(O / "score-real.json", out)
    print(json.dumps({k: {t: brief(v) for t, v in x.items()} for k, x in out.items()
                      if k != "seconds"}, indent=1))  # fmt: skip
    return 0


def _kvals(tab):
    t = np.round(tab.column("TIME"), 3)
    times = np.unique(t)
    ant = tab.column("ANTENNA1")
    nant = int(ant.max()) + 1
    v = np.full((len(times), nant, 2), np.nan)
    f = np.stack([np.asarray(x) for x in tab.main["FLAG"]])[:, 0, :]
    p = tab.params[:, 0, :].real.astype(float)
    ti = np.searchsorted(times, t)
    v[ti, ant] = np.where(f, np.nan, p)
    return times, v


def k_errors(arm, truth, centres, assign_t, refidx):
    """|(tau_p - tau_ref) - truth| per interval (rank-matched to `centres`),
    antenna, hand; truth averaged over the dumps nearest each centre."""
    _, va = _kvals(arm)
    tt, vt = _kvals(truth)
    if va.shape[0] != len(centres):
        return {"error": f"{va.shape[0]} intervals against {len(centres)}"}
    near = (
        np.abs(tt[:, None] - centres[None, :]).argmin(1)
        if assign_t is None
        else assign_t(tt)
    )
    mt = np.stack([np.nanmean(vt[near == i], 0) for i in range(len(centres))])
    da = va - va[:, refidx : refidx + 1]
    dt = mt - mt[:, refidx : refidx + 1]
    err = np.abs(da - dt)
    err[:, refidx] = np.nan
    keep = np.ones(err.shape[1], bool)
    keep[ODD] = False
    e = err[np.isfinite(err)]
    e50 = err[:, keep][np.isfinite(err[:, keep])]
    return {"all": C.stats(e), "without_id50": C.stats(e50)}


def sim(tag):
    t0 = time.perf_counter()
    u_ms = O / f"sim-{tag}-u.ms"
    cp = Comp(u_ms)
    with core_ms.open_table(u_ms / "ANTENNA") as t:
        refidx = [str(x) for x in t.getcol("NAME")].index(REF)
    truth = O / f"truth-{tag}"
    T = tabs(truth, ("K", "G", "B"))
    U = u_ms.parent / f"{u_ms.name}.rang-run" / "calibrate"
    D = O / f"sim-{tag}-d.ms.rang-run" / "calibrate"
    Cc = O / f"sim-{tag}-casa-c"
    CK = O / f"sim-{tag}-casa-ck"

    def arm(name, names):
        if name == "ck":
            src = [U if n[0] == "K" else CK for n in names]
        else:
            src = [{"u": U, "d": D, "c": Cc}[name]] * len(names)
        if not all((s / n).exists() for s, n in zip(src, names)):
            return None
        return [C.table(s / n) for s, n in zip(src, names)]

    out = {"tag": tag, "against_truth": {}, "pairs": {}, "k_errors": {}}
    for a in ("u", "d", "c", "ck"):
        for tg, names in (("KGB1", NAMES1), ("KGB0", NAMES0)):
            ta = arm(a, names)
            if ta is not None:
                out["against_truth"].setdefault(a, {})[tg] = cp.rel(
                    f"{a}{tg}", ta, "truth", T
                )
    for a, b in (
        ("u", "c"),
        ("u", "ck"),
        ("d", "c"),
        ("d", "ck"),
        ("u", "d"),
        ("c", "ck"),
    ):
        for tg, names in (("KGB1", NAMES1), ("KGB0", NAMES0)):
            ta, tb = arm(a, names), arm(b, names)
            if ta is not None and tb is not None:
                out["pairs"].setdefault(f"{a}-{b}", {})[tg] = cp.rel(
                    f"{a}{tg}", ta, f"{b}{tg}", tb
                )
    # K errors: K1 by rank against U's K1 times, K0 by scan
    tk = T[0]
    u1 = C.table(U / "K1")
    centres1 = np.unique(np.round(u1.column("TIME"), 3))
    u0 = C.table(U / "K0")
    centres0 = np.unique(np.round(u0.column("TIME"), 3))
    with core_ms.open_table(u_ms) as t:
        tm, sc = np.asarray(t.getcol("TIME")), np.asarray(t.getcol("SCAN_NUMBER"))
    scan_of = dict(zip(np.round(tm, 3), sc))
    scans0 = sorted(set(sc.tolist()))

    def by_scan(tt):
        return np.array([scans0.index(scan_of[x]) for x in np.round(tt, 3)])

    for a, d in (("u", U), ("d", D), ("c", Cc)):
        for n, centres, assign in (("K1", centres1, None), ("K0", centres0, by_scan)):
            if (d / n).exists():
                out["k_errors"].setdefault(a, {})[n] = k_errors(C.table(d / n), tk, centres,
                                                                assign, refidx)  # fmt: skip
    out["seconds"] = time.perf_counter() - t0
    C.write(O / f"score-sim-{tag}.json", out)
    show = {
        "truth": {a: {t: brief(v) for t, v in x.items()} for a, x in out["against_truth"].items()},
        "pairs": {a: {t: brief(v) for t, v in x.items()} for a, x in out["pairs"].items()},
        "k": {a: {n: (v["all"]["median"] if "all" in v else v, v.get("without_id50", {}).get("median"))
                  for n, v in x.items()} for a, x in out["k_errors"].items()},
    }  # fmt: skip
    print(json.dumps(show, indent=1))
    return 0


def f0():
    """Step F: E2-A field 0, rang's archived K1, G1 with D3's divided B1."""
    t0 = time.perf_counter()
    cp = Comp(O / "f0.ms")
    W = O / "f0win"
    rk = W / "rang-run" / "calibrate"
    r = tabs(rk, NAMES1)
    on = [r[0], r[1], C.table(W / "B1-on")]
    off = [r[0], r[1], C.table(W / "B1-off")]
    casa = tabs(W / "casa" / "tables", NAMES1)
    arms = {"rang archived": r, "rang B1 divided": on, "rang B1 off (control)": off}
    others = {"CASA archived (as frozen)": casa}
    k = O / "f0-casa-k"
    if (k / "B1").exists():
        others["CASA on rang's K (T-K3 construction)"] = [r[0], *tabs(k, ("G1", "B1"))]
    tf = O / "f0-casa-tf"
    if (tf / "B1").exists():
        others["CASA own K, matched flags"] = tabs(tf, NAMES1)
    out = {}
    for an, ta in arms.items():
        for on_, tb in others.items():
            out[f"{an} vs {on_}"] = cp.rel(an, ta, on_, tb)
    out["control: off vs archived"] = cp.rel(
        "rang B1 off (control)", off, "rang archived", r
    )
    if (k / "B1").exists() and (tf / "B1").exists():
        out["CASA own K vs CASA on rang's K"] = cp.rel(
            "CASA own K, matched flags",
            others["CASA own K, matched flags"],
            "CASA on rang's K (T-K3 construction)",
            others["CASA on rang's K (T-K3 construction)"],
        )
    out["seconds"] = time.perf_counter() - t0
    C.write(O / "score-f0.json", out)
    print(
        json.dumps({k_: brief(v) for k_, v in out.items() if k_ != "seconds"}, indent=1)
    )
    return 0


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    sys.exit(
        {"split": split, "model": model, "real": real, "sim": sim, "f0": f0}[step](
            *args
        )
    )
