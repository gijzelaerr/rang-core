"""F2: a small supervised RFI flagger and its measures (research/f2-flagger.md).

The network of section 3 (2,785 weights, per baseline, on the (time,
channel) plane of one scan), its NumPy feature reference, the JAX forward
pass and training (CPU), the shared wrapper (the class's CARACal strategy
without `sum_threshold` and `uvcontsub_flagger`, run by `core_flag.flag_rows`),
the comparators Z and R, and the measures Q1-Q3 and the Jaccard agreement.
Inference in Rust is `rang.core.cnnflag` (`core/src/cnnflag.rs`).
"""

import math
from pathlib import Path

import numpy as np

from . import core, core_flag

# CARACal's strategies (8f7bb363) as archived for the campaigns: the checkout's
# outputs/, else the main checkout's (a worktree has no outputs/ of its own).
_ARCHIVED = "outputs/caracal-strategy-inputs-8f7bb363"
STRATEGY_DIR = next(
    (
        p
        for p in (
            Path(__file__).resolve().parents[2] / _ARCHIVED,
            Path.home() / "Github/rang" / _ARCHIVED,
        )
        if p.is_dir()
    ),
    Path(__file__).resolve().parents[2] / _ARCHIVED,
)
STRATEGIES = {
    "calibrator": "mk_rfi_flagging_calibrator_fields_firstpass.yaml",
    "target": "mk_rfi_flagging_target_fields_firstpass.yaml",
}
MILD = "calibrator_mild_flagging.yaml"
NETWORK_TASKS = ("sum_threshold", "uvcontsub_flagger")
CHANNELS = (6, 8, 8, 8, 8)
DILATIONS = (1, 2, 4, 8, 16)
RADIUS = sum(DILATIONS)  # 31: half the receptive field
PROFILE_HALF = 16  # running median over 33 channels
MAD_SCALE = 1.4826
S_FLOOR = 1e-3
Z_TAU = 10.0
R_TAU = 10.0
GRID = (2, 32)


# -- strategies and the shared wrapper ---------------------------------------------


def strategy(name):
    return core_flag.parse_strategy((STRATEGY_DIR / name).read_text(encoding="utf-8"))


def shared_strategy(klass):
    """The class's strategy without the steps the network replaces."""
    return [s for s in strategy(STRATEGIES[klass]) if s["task"] not in NETWORK_TASKS]


def run_strategy(scan, steps, flags=None):
    """`flag_rows` on one scan dict; returns (row, chan) bool and seconds."""
    data = scan["data"]
    if flags is None:
        flags = np.zeros(data.shape, bool)
    result = core_flag.flag_rows(
        data,
        flags,
        scan["antenna1"],
        scan["antenna2"],
        scan["times"],
        scan["antenna_position"],
        scan["chan_freq"],
        scan["chan_width"],
        scan["corr_type"],
        steps,
        want_intensity=False,
        want_stages=False,
    )
    return np.array(result["flags"].any(-1)), result["seconds"]


# -- planes --------------------------------------------------------------------------


def baseline_index(antenna1, antenna2):
    """`flag_rows`'s baselines (`core_flag.unique_baselines`) and each row's index."""
    stacked = np.stack([antenna1, antenna2], axis=1).astype(np.int32)
    words = np.ascontiguousarray(stacked).view(np.int64).ravel()
    keys, index = np.unique(words, return_inverse=True)
    return keys.view(np.int32).reshape(-1, 2), index.astype(np.int64)


class Planes:
    """Row <-> (baseline, time) plane mapping in `flag_rows`'s baseline order."""

    def __init__(self, antenna1, antenna2, times):
        self.ubl, self.bl = baseline_index(antenna1, antenna2)
        self.tgrid, self.t = np.unique(times, return_inverse=True)
        self.nbl, self.nt = len(self.ubl), len(self.tgrid)

    def to_planes(self, x, fill):
        out = np.full((self.nbl, self.nt) + x.shape[1:], fill, x.dtype)
        out[self.bl, self.t] = x
        return out

    def from_planes(self, p):
        return p[self.bl, self.t]


# -- features (NumPy reference) ------------------------------------------------------


def _mad(x, axis=None):
    med = np.nanmedian(x, axis=axis, keepdims=True)
    return MAD_SCALE * np.nanmedian(np.abs(x - med), axis=axis)


def features(vis, flagged):
    """(nbl, nt, nc, 6) float32 inputs and (nbl, nt, nc, 4) float64 z (before
    asinh, 0 on flagged) from `vis` (nbl, nt, nc, 4) complex and `flagged`
    (nbl, nt, nc) bool. Section 3 of the protocol."""
    import warnings

    nbl, nt, nc, _ = vis.shape
    amp = np.abs(np.asarray(vis, np.complex128))
    with np.errstate(divide="ignore", invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        a = np.log(amp)
        bad = flagged[..., None] | ~np.isfinite(a)
        a[bad] = np.nan
        x = a - np.nanmedian(a, axis=1, keepdims=True)
        s = _mad(x.reshape(nbl, -1, 4), axis=1)
        s = np.where(np.isfinite(s), np.maximum(s, S_FLOOR), 1.0)
        z = x / s[:, None, None, :]
        z[~np.isfinite(z)] = 0.0
        p = np.nanmedian(0.5 * (a[..., 0] + a[..., 3]), axis=1)  # (nbl, nc)
        padded = np.pad(
            p, ((0, 0), (PROFILE_HALF, PROFILE_HALF)), constant_values=np.nan
        )
        windows = np.lib.stride_tricks.sliding_window_view(
            padded, 2 * PROFILE_HALF + 1, axis=1
        )
        r = p - np.nanmedian(windows, axis=-1)
        sp = _mad(r, axis=1)
        sp = np.where(np.isfinite(sp), np.maximum(sp, S_FLOOR), 1.0)
        zp = r / sp[:, None]
        zp[~np.isfinite(zp)] = 0.0
    out = np.empty((nbl, nt, nc, 6), np.float32)
    out[..., :4] = np.arcsinh(z)
    out[..., 4] = np.arcsinh(zp)[:, None, :]
    f = flagged
    out[f, :5] = 0.0
    z[f] = 0.0
    out[..., 5] = f
    return out, z


# -- the network (JAX) ---------------------------------------------------------------


def init_params(seed):
    """He-normal weights, zero biases: list of (W (3,3,cin,cout), b), head (8,1), (1,)."""
    rng = np.random.default_rng(seed)
    params = []
    cin = CHANNELS[0]
    for cout in CHANNELS[1:] + (8,):
        w = rng.normal(0, math.sqrt(2.0 / (9 * cin)), (3, 3, cin, cout))
        params.append((w.astype(np.float32), np.zeros(cout, np.float32)))
        cin = cout
    head = rng.normal(0, math.sqrt(2.0 / cin), (cin, 1)).astype(np.float32)
    params.append((head, np.zeros(1, np.float32)))
    return params


def count_weights(params):
    return int(sum(w.size + b.size for w, b in params))


def forward(params, x):
    """Logits (N, nt, nc) of inputs (N, nt, nc, 6), JAX, float32."""
    import jax
    import jax.numpy as jnp

    h = x
    for (w, b), d in zip(params[:-1], DILATIONS):
        h = jax.lax.conv_general_dilated(
            h,
            w,
            window_strides=(1, 1),
            padding="SAME",
            rhs_dilation=(d, d),
            dimension_numbers=("NHWC", "HWIO", "NHWC"),
            precision=jax.lax.Precision.HIGHEST,
        )
        h = jax.nn.relu(h + b)
    w, b = params[-1]
    return jnp.einsum("nhwc,co->nhwo", h, w, precision="highest")[..., 0] + b[0]


def logits_numpy(params, x, block=32):
    """JAX logits in baseline blocks, as NumPy float32."""
    import jax

    f = jax.jit(forward)
    out = np.empty(x.shape[:3], np.float32)
    for s in range(0, len(x), block):
        out[s : s + block] = np.asarray(f(params, x[s : s + block]))
    return out


def save_params(path, params, extra=None):
    arrays = {}
    for i, (w, b) in enumerate(params):
        arrays[f"w{i}"] = np.asarray(w, np.float32)
        arrays[f"b{i}"] = np.asarray(b, np.float32)
    np.savez(path, **arrays, **(extra or {}))


def load_params(path):
    z = np.load(path)
    n = sum(1 for k in z.files if k.startswith("w"))
    return [(z[f"w{i}"], z[f"b{i}"]) for i in range(n)]


def flat_weights(params):
    """The weights as one float32 vector in the Rust kernel's order: per layer
    W (ky, kx, cin, cout) row-major, then b."""
    return np.concatenate(
        [np.concatenate([np.ravel(w), np.ravel(b)]) for w, b in params]
    ).astype(np.float32)


# -- comparators ---------------------------------------------------------------------


def z_flags(z):
    """Z: max over correlations of the input z above Z_TAU."""
    return z.max(axis=-1) > Z_TAU


def solve(scan, flags, data=None, max_iterations=50):
    """`solve_complex` at GRID on one scan; returns the solution and maps."""
    data = scan["data"] if data is None else data
    planes = scan["planes"]
    tb = (planes.t // GRID[0]).astype(np.uint32)
    nch = data.shape[1]
    fb = (np.arange(nch) // GRID[1]).astype(np.uint32)
    order = np.argsort(tb, kind="stable")
    fl = np.broadcast_to(flags[..., None], data.shape)
    sol = core.solve_complex(
        np.ascontiguousarray(data[order]),
        np.ascontiguousarray(scan["weights"][order]),
        np.ascontiguousarray(fl[order]),
        np.ascontiguousarray(flags[order].all(axis=1)),
        scan["antenna1"][order],
        scan["antenna2"][order],
        tb[order],
        fb,
        ntime_bins=int(tb.max()) + 1,
        nfreq_bins=int(fb.max()) + 1,
        nant=scan["nant"],
        model=np.ascontiguousarray(scan["model"][order]),
        max_iterations=max_iterations,
    )
    return sol, tb, fb


def residual_z(scan, flags):
    """R's score: `baseline_scores` of the whitened residual amplitude."""
    from .core_campaign_array import baseline_scores

    sol, tb, fb = solve(scan, flags)
    valid = sol.flags == 0
    fused = core.fused_pass(
        scan["data"],
        scan["weights"],
        scan["antenna1"],
        scan["antenna2"],
        tb,
        fb,
        sol.gains,
        valid,
        np.ones(scan["data"].shape[:2], np.uint8),
        model=scan["model"],
        residuals=True,
        scores=False,
        normals=False,
    )
    amp = np.sqrt(
        np.sum(np.abs(fused.residuals * np.sqrt(scan["weights"])) ** 2, axis=-1)
    )
    good = (
        valid[tb[:, None], fb[None, :], scan["antenna1"][:, None]]
        & valid[tb[:, None], fb[None, :], scan["antenna2"][:, None]]
    )
    eligible = ~flags & good & np.isfinite(amp)
    return baseline_scores(amp, eligible, scan["antenna1"], scan["antenna2"])


def r_flags(scan, flags):
    return residual_z(scan, flags) > R_TAU


# -- measures ------------------------------------------------------------------------


def dilate_planes(mask_planes):
    """One-cell dilation in time and channel of (nbl, nt, nc) planes."""
    from scipy.ndimage import binary_dilation

    s = np.zeros((3, 3, 3), bool)
    s[1] = True
    return binary_dilation(mask_planes, structure=s)


def truth_counts(scan, flags, amp, shared, morph=None):
    """[hits, n] counts for Q1 (A >= 10; also A >= 3, by decade and by
    morphology) and Q2 (outside the truth mask dilated by one cell), on cells
    the shared wrapper leaves unflagged. `pooled` turns them into fractions."""
    planes = scan["planes"]
    scored = ~shared
    strong = scored & (amp >= 10)
    clean = scored & ~planes.from_planes(
        dilate_planes(planes.to_planes(amp > 0, False))
    )

    def c(sel):
        return [int(np.count_nonzero(flags & sel)), int(np.count_nonzero(sel))]

    out = {
        "q1": c(strong),
        "q1_ge3": c(scored & (amp >= 3)),
        "q2": c(clean),
        "scored": c(scored),
        "by_decade": {
            f"{lo}-{hi}": c(scored & (amp >= lo) & (amp < hi))
            for lo, hi in ((0.1, 1), (1, 3), (3, 10), (10, 100), (100, np.inf))
        },
    }
    if morph is not None:
        from .f2flag_sim import MORPHOLOGIES

        out["by_morphology"] = {
            name: c(strong & (morph == code)) for code, name in MORPHOLOGIES.items()
        }
    return out


def add_counts(total, part):
    """Add nested [hits, n] counts in place."""
    for k, v in part.items():
        if isinstance(v, dict):
            add_counts(total.setdefault(k, {}), v)
        else:
            t = total.setdefault(k, [0, 0])
            t[0] += v[0]
            t[1] += v[1]
    return total


def pooled(counts):
    """Nested counts to fractions (None where n = 0), keeping n."""
    out = {}
    for k, v in counts.items():
        if isinstance(v, dict):
            out[k] = pooled(v)
        else:
            out[k] = v[0] / v[1] if v[1] else None
            out[k + "_n"] = v[1]
    return out


def gain_products(gains, valid, antenna1, antenna2):
    """(t, f, bl, 2, 2) G_p G_q^H and their validity."""
    gp = gains[:, :, antenna1]
    gq = gains[:, :, antenna2]
    prod = np.einsum("tfbij,tfbkj->tfbik", gp, np.conj(gq))
    ok = valid[:, :, antenna1] & valid[:, :, antenna2]
    return prod, ok


def jaccard(a, b):
    union = np.count_nonzero(a | b)
    return float(np.count_nonzero(a & b) / union) if union else None


# -- training (JAX, CPU) -------------------------------------------------------------


def loss_fn(params, x, label, weight):
    import jax
    import jax.numpy as jnp

    logit = forward(params, x)
    per = jnp.maximum(logit, 0) - logit * label + jnp.log1p(jnp.exp(-jnp.abs(logit)))
    del jax
    return jnp.sum(per * weight) / jnp.maximum(jnp.sum(weight), 1.0)


def adam_step():
    """A jitted Adam step (rate 1e-3, betas 0.9, 0.999, eps 1e-8)."""
    import jax
    import jax.numpy as jnp

    rate, b1, b2, eps = 1e-3, 0.9, 0.999, 1e-8

    @jax.jit
    def step(params, m, v, k, x, label, weight):
        loss, grad = jax.value_and_grad(loss_fn)(params, x, label, weight)
        m = jax.tree_util.tree_map(lambda m, g: b1 * m + (1 - b1) * g, m, grad)
        v = jax.tree_util.tree_map(lambda v, g: b2 * v + (1 - b2) * g * g, v, grad)
        mh = jax.tree_util.tree_map(lambda m: m / (1 - b1**k), m)
        vh = jax.tree_util.tree_map(lambda v: v / (1 - b2**k), v)
        params = jax.tree_util.tree_map(
            lambda p, a, b: p - rate * a / (jnp.sqrt(b) + eps), params, mh, vh
        )
        return params, m, v, loss

    return step


def augment_flags(rng, nt, nc):
    """Section 4's synthetic input flags for one window's baseline plane."""
    f = np.zeros((nt, nc), bool)
    if rng.random() >= 0.5:
        return f
    target = rng.uniform(0, 0.6)
    if rng.random() < 0.05:
        f[:] = True
        return f
    for _ in range(int(rng.integers(1, 5))):
        if f.mean() >= target:
            break
        w = int(rng.integers(8, 257))
        c = int(rng.integers(0, nc - w + 1))
        f[:, c : c + w] = True
    for _ in range(int(rng.integers(0, 3))):
        if f.mean() >= target:
            break
        w = int(rng.integers(1, 9))
        t = int(rng.integers(0, max(1, nt - w + 1)))
        f[t : t + w] = True
    return f


WINDOW = 256
CROP = WINDOW + 2 * RADIUS


def crop_window(rng, nc):
    """(crop start, loss slice within the crop) for one 256-channel window."""
    s = int(rng.integers(0, nc - CROP + 1))
    lo, hi = RADIUS, RADIUS + WINDOW
    if s == 0:
        lo = 0
    if s == nc - CROP:
        hi = CROP
    return s, lo, hi


# -- inference (Rust) ----------------------------------------------------------------


def rust_logits(data, flagged, antenna1, antenna2, times, weights):
    """Logits (row, chan) float32 from the Rust kernel: `data` (row, chan, 4)
    complex64, `flagged` (row, chan) bool (flagged before the network),
    `weights` from `flat_weights`. Same rows in as `flag_rows`."""
    data = np.require(data, np.complex64, ["C", "A"])
    nrow, nchan = data.shape[:2]
    ubl, baseline = baseline_index(antenna1, antenna2)
    baseline = baseline.astype(np.uint32)
    _, tinv = np.unique(times, return_inverse=True)
    out = np.empty((nrow, nchan), np.float32)
    code = core.extension().cnnflag_logits(
        nchan,
        len(ubl),
        int(tinv.max()) + 1,
        data.view(np.float32),
        np.require(flagged, np.uint8, ["C", "A"]),
        baseline,
        np.ascontiguousarray(tinv, np.uint32),
        np.require(weights, np.float32, ["C", "A"]),
        out,
    )
    if code:
        raise RuntimeError(f"cnnflag_logits failed with code {code}")
    return out


def network_flags(scan, shared, weights, tau=0.0):
    """The network arm's final flags: shared wrapper OR logit > tau
    (research/f2-flagger.md, Amendment 3; tau = 0 unless picked)."""
    logit = rust_logits(
        scan["data"], shared, scan["antenna1"], scan["antenna2"], scan["times"], weights
    )
    return shared | (logit > tau), logit


def load_net(spec):
    """`PATH` or `PATH@TAU` to (flat weights, tau)."""
    path, _, tau = str(spec).partition("@")
    return flat_weights(load_params(path)), float(tau) if tau else 0.0
