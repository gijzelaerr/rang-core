"""F3's network for training (research/f3-flagger.md, sections 3 and 5): JAX,
float32, with no rang imports so that it runs in a NumPy-and-JAX-only
environment (the CUDA training venv in WSL). Inference is Rust
(`rang._core.f3flag_logits`); the weight order is `rang.f2flag.flat_weights`'s.
"""

import math

import numpy as np

NPLANES = 15
HIDDEN = 8
DILATIONS = (1, 2, 4, 8, 16)


def init_params(seed):
    """He-normal weights, zero biases: [(W (3,3,cin,cout), b)] * 5, (head (8,1), (1,))."""
    rng = np.random.default_rng(seed)
    params = []
    cin = NPLANES
    for _ in DILATIONS:
        w = rng.normal(0, math.sqrt(2.0 / (9 * cin)), (3, 3, cin, HIDDEN))
        params.append((w.astype(np.float32), np.zeros(HIDDEN, np.float32)))
        cin = HIDDEN
    head = rng.normal(0, math.sqrt(2.0 / cin), (cin, 1)).astype(np.float32)
    params.append((head, np.zeros(1, np.float32)))
    return params


def count_weights(params):
    return int(sum(np.size(w) + np.size(b) for w, b in params))


def forward(params, x):
    """Logits (N, nt, nc) of inputs (N, nt, nc, 15)."""
    import jax
    import jax.numpy as jnp

    h = x
    for (w, b), d in zip(params[:-1], DILATIONS, strict=True):
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


def loss_fn(params, x, label):
    """Unweighted binary cross-entropy over cells with label 0 or 1 (-1 ignored)."""
    import jax
    import jax.numpy as jnp

    z = forward(params, x)
    keep = label >= 0
    y = jnp.where(keep, label, 0).astype(jnp.float32)
    ce = jnp.maximum(z, 0) - z * y + jnp.log1p(jnp.exp(-jnp.abs(z)))
    n = jnp.maximum(keep.sum(), 1)
    del jax
    return jnp.where(keep, ce, 0.0).sum() / n


def adam_step(rate=1e-3, b1=0.9, b2=0.999, eps=1e-8):
    import jax
    import jax.numpy as jnp

    grad = jax.value_and_grad(loss_fn)

    @jax.jit
    def step(params, m, v, k, x, label):
        loss, g = grad(params, x, label)
        m = jax.tree_util.tree_map(lambda a, b: b1 * a + (1 - b1) * b, m, g)
        v = jax.tree_util.tree_map(lambda a, b: b2 * a + (1 - b2) * b * b, v, g)
        mh = jax.tree_util.tree_map(lambda a: a / (1 - b1**k), m)
        vh = jax.tree_util.tree_map(lambda a: a / (1 - b2**k), v)
        params = jax.tree_util.tree_map(
            lambda p, a, b: p - rate * a / (jnp.sqrt(b) + eps), params, mh, vh
        )
        return params, m, v, loss

    return step


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
    """The weights in the Rust kernel's order: per layer W (ky, kx, cin, cout)
    row-major, then b."""
    return np.concatenate(
        [np.concatenate([np.ravel(w), np.ravel(b)]) for w, b in params]
    ).astype(np.float32)
