"""QuartiCal #452 check through the full complex compute_jhj_jhr loop.

Noise-free data V_pq = G_p M G_q^H, weights with w_XY != w_YX. All antennas
start at the true gains except one, which starts at identity. For that
antenna: max|JHJ - J^H W J| (exact, with the weights of the visibility the
antenna sees) and the error of one Gauss-Newton step against the truth.
Antenna N-1 is only ever ANTENNA2 (qp side); antenna 0 only ANTENNA1 (pq).
"""

import sys
import time

import numpy as np
import quartical
from numba import njit
from quartical.calibration.solver import meta_args_nt
from quartical.gains import TERM_TYPES
from quartical.gains.complex import kernel as ck
from quartical.gains.general import generics
from quartical.gains.general.convenience import get_extents

UI = (
    getattr(generics, "upsampled_intermediaries", None)
    or generics.upsampled_itermediaries
)

N_ANT, N_TIME, N_CHAN = 5, 4, 4
I2 = np.eye(2, dtype=complex)
TERM = TERM_TYPES["complex"]


@njit
def caller(ms, mp, ch, meta, imdry, ext, cm):
    ck.compute_jhj_jhr(ms, mp, ch, meta, imdry, ext, cm)


def c(rng, *shape):
    return rng.normal(size=shape) + 1j * rng.normal(size=shape)


def run(target, w_scale):
    rng = np.random.default_rng(452)
    a1, a2 = np.triu_indices(N_ANT, 1)
    a1 = np.tile(a1, N_TIME).astype(np.int32)
    a2 = np.tile(a2, N_TIME).astype(np.int32)
    n_row = a1.size
    G = c(rng, N_ANT, 2, 2)
    M = c(rng, n_row, N_CHAN, 2, 2)
    V = G[a1][:, None] @ M @ np.conj(np.swapaxes(G[a2], -1, -2))[:, None]
    w = rng.uniform(0.5, 1.5, (n_row, N_CHAN, 4))
    if w_scale is None:  # control: w_YX = w_XY
        w[..., 2] = w[..., 1]
    else:
        w *= np.array(w_scale)
    G0 = G.copy()
    G0[target] = I2

    t_map = np.zeros(n_row, dtype=np.int32)
    f_map = np.zeros(N_CHAN, dtype=np.int32)
    ms_kw = dict(
        MODEL_DATA=M.reshape(n_row, N_CHAN, 1, 4),
        DATA=V.reshape(n_row, N_CHAN, 4),
        ANTENNA1=a1,
        ANTENNA2=a2,
        WEIGHT=w,
        FLAG=np.zeros((n_row, N_CHAN), np.int8),
        ROW_MAP=None,
        ROW_WEIGHTS=None,
        TIME=np.repeat(np.arange(N_TIME, dtype=float), n_row // N_TIME),
        CHAN_FREQ=np.linspace(0.9e9, 1.6e9, N_CHAN),
    )
    mp_kw = dict(
        time_bins=(t_map,),
        time_maps=(t_map,),
        freq_maps=(f_map,),
        dir_maps=(np.zeros(1, np.int32),),
    )
    gains = G0.reshape(1, 1, N_ANT, 1, 4).copy()
    ch_kw = dict(
        gains=(gains,),
        gain_flags=(np.zeros(gains.shape[:-1], np.int8),),
        params=(np.zeros((1, 1, N_ANT, 1, 1)),),
        param_flags=(np.zeros((1, 1, N_ANT, 1), np.int8),),
    )
    meta_kw = dict(
        iters=1,
        active_term=0,
        stop_frac=0.99,
        stop_crit=1e-6,
        threads=1,
        robust=False,
        reference_antenna=0,
        scalar=False,
        dd_term=False,
        pinned_directions=(0,),
        solve_per="antenna",
        referenced=False,
    )
    pick = lambda nt, kw: nt(**{k: kw[k] for k in nt._fields})
    jhr = np.zeros(gains.shape, complex)
    jhj = np.zeros(gains.shape[:4] + (4, 4), complex)
    caller(
        pick(TERM.ms_inputs, ms_kw),
        pick(TERM.mapping_inputs, mp_kw),
        pick(TERM.chain_inputs, ch_kw),
        pick(meta_args_nt, meta_kw),
        UI(jhj, jhr),
        get_extents(t_map, f_map),
        4,
    )

    H = np.zeros((4, 4), complex)
    for r in range(n_row):
        for f in range(N_CHAN):
            if a1[r] == target:  # pq side: V_pq = G_p (M G_q^H)
                B = M[r, f] @ G0[a2[r]].conj().T
                J, wv = np.kron(I2, B.T), w[r, f]
            elif a2[r] == target:  # qp side: V_qp = G_q (G_p M)^H
                rop = G0[a1[r]] @ M[r, f]
                J, wv = np.kron(I2, rop.conj()), w[r, f][[0, 2, 1, 3]]
            else:
                continue
            H += J.conj().T @ np.diag(wv) @ J
    jhj_t, jhr_t = jhj[0, 0, target, 0], jhr[0, 0, target, 0]
    step = np.linalg.solve(jhj_t, jhr_t).reshape(2, 2)
    return (
        np.abs(jhj_t - H).max(),
        np.abs(jhj_t).max(),
        np.abs(G0[target] + step - G[target]).max(),
    )


if __name__ == "__main__":
    import importlib.metadata as md

    print(
        "quartical", quartical.__file__, md.version("quartical"), "label", sys.argv[1]
    )
    t0 = time.time()
    # Base weights: uniform(0.5, 1.5) per sample and correlation, times the scale.
    for scale in (None, [1, 1, 1, 1], [1, 0.2, 5, 1], [1, 1, 4, 1], [1, 1, 25, 1]):
        label = "w_YX=w_XY (control)" if scale is None else f"w(XX,XY,YX,YY)x{scale}"
        for target, side in (
            (N_ANT - 1, "qp (ANTENNA2 only)"),
            (0, "pq (ANTENNA1 only)"),
        ):
            dj, mj, dg = run(target, scale)
            print(
                f"{sys.argv[1]} {label} antenna {target} {side}: "
                f"max|JHJ-J^HWJ| = {dj:.2e} (max|JHJ| {mj:.1e}), one-step gain error = {dg:.2e}"
            )
    print(f"wall {time.time() - t0:.1f} s")
