"""JHJ and JHR must not depend on which antenna of a baseline is ANTENNA1.

A row (p, q, V, W) and its conjugate (q, p, V^H, W^T) describe the same
measurement: the residual and its weighted norm are identical. The solver
accumulates each row into antenna p through V_pq and into antenna q through
V_qp = V_pq^H, so the q side has to use the transposed weights (XY and YX
swapped). Writing every row the other way round must therefore leave JHJ and
JHR unchanged, which only holds when the qp side uses W^T. The weights below
have w_XY != w_YX, as with robust reweighting or per-correlation
WEIGHT_SPECTRUM.

These tests drive each term's own compute_jhj_jhr (and so the shared
accumulation loop) on random inputs. The symmetry holds for any gains, so the
gains need not be consistent with the parameters.
"""
import numpy as np
import pytest
from numba import njit

from quartical.calibration.solver import meta_args_nt
from quartical.gains import TERM_TYPES
from quartical.gains.complex import kernel as complex_kernel
from quartical.gains.crosshand_phase import kernel as crosshand_phase_kernel
from quartical.gains.general.convenience import get_extents
from quartical.gains.general.generics import upsampled_intermediaries
from quartical.gains.rotation import kernel as rotation_kernel
from quartical.gains.rotation_measure import kernel as rotation_measure_kernel

N_ANT = 4
N_CHAN = 6
N_CORR = 4
TRANSPOSE = [0, 2, 1, 3]  # XX XY YX YY -> XX YX XY YY

KERNELS = {
    "complex": complex_kernel,
    "rotation": rotation_kernel,
    "rotation_measure": rotation_measure_kernel,
    "crosshand_phase": crosshand_phase_kernel,
}

_callers = {}


def get_caller(term_type):
    """A jitted caller for the overloaded compute_jhj_jhr of a term type."""
    if term_type not in _callers:
        compute_jhj_jhr = KERNELS[term_type].compute_jhj_jhr

        @njit
        def caller(ms_inputs, mapping_inputs, chain_inputs, meta_inputs,
                   upsampled_imdry, extents, corr_mode):
            compute_jhj_jhr(ms_inputs, mapping_inputs, chain_inputs,
                            meta_inputs, upsampled_imdry, extents, corr_mode)

        _callers[term_type] = caller
    return _callers[term_type]


def random_complex(rng, shape):
    return rng.normal(size=shape) + 1j * rng.normal(size=shape)


def make_rows(rng, n_dir):
    """All baselines in two time slots, one row each, plus random data."""
    a1, a2 = np.triu_indices(N_ANT, 1)
    a1 = np.tile(a1, 2).astype(np.int32)
    a2 = np.tile(a2, 2).astype(np.int32)
    n_row = a1.size
    data = random_complex(rng, (n_row, N_CHAN, N_CORR))
    model = random_complex(rng, (n_row, N_CHAN, n_dir, N_CORR))
    weight = rng.uniform(0.1, 1.0, (n_row, N_CHAN, N_CORR))
    weight[..., 1] *= 0.2  # XY
    weight[..., 2] *= 5.0  # YX
    return a1, a2, data, model, weight


def conjugate_rows(a1, a2, data, model, weight):
    """The same measurement with ANTENNA1 and ANTENNA2 exchanged."""
    return (
        a2.copy(),
        a1.copy(),
        data[..., TRANSPOSE].conj(),
        model[..., TRANSPOSE].conj(),
        weight[..., TRANSPOSE].copy()
    )


def compute_jhj_jhr(term_type, rows, gains, params):

    a1, a2, data, model, weight = rows
    term_cls = TERM_TYPES[term_type]
    n_row = a1.size

    ms_kwargs = dict(
        MODEL_DATA=model,
        DATA=data,
        ANTENNA1=a1,
        ANTENNA2=a2,
        WEIGHT=weight,
        FLAG=np.zeros((n_row, N_CHAN), dtype=np.int8),
        ROW_MAP=None,
        ROW_WEIGHTS=None,
        TIME=np.repeat([0.0, 8.0], n_row // 2),
        CHAN_FREQ=np.linspace(0.9e9, 1.6e9, N_CHAN),
    )
    t_map = np.zeros(n_row, dtype=np.int32)  # One solution interval.
    f_map = np.zeros(N_CHAN, dtype=np.int32)
    gain_f_map = np.arange(N_CHAN, dtype=np.int32) \
        if gains.shape[1] == N_CHAN else f_map
    mapping_kwargs = dict(
        time_bins=(t_map,),
        time_maps=(t_map,),
        freq_maps=(gain_f_map,),
        dir_maps=(np.zeros(model.shape[2], dtype=np.int32),),
        param_time_bins=(t_map,),
        param_time_maps=(t_map,),
        param_freq_maps=(f_map,),
    )
    chain_kwargs = dict(
        gains=(gains,),
        gain_flags=(np.zeros(gains.shape[:-1], dtype=np.int8),),
        params=(params,),
        param_flags=(np.zeros(params.shape[:-1], dtype=np.int8),),
    )
    ms_inputs = term_cls.ms_inputs(
        **{k: ms_kwargs[k] for k in term_cls.ms_inputs._fields}
    )
    mapping_inputs = term_cls.mapping_inputs(
        **{k: mapping_kwargs[k] for k in term_cls.mapping_inputs._fields}
    )
    chain_inputs = term_cls.chain_inputs(
        **{k: chain_kwargs[k] for k in term_cls.chain_inputs._fields}
    )
    meta_inputs = meta_args_nt(
        1, 0, 0.99, 1e-6, 1, False, 0, False, False, (0,), "antenna", False
    )

    if term_cls.is_parameterized:
        jhr = np.zeros(params.shape, dtype=np.float64)
        jhj = np.zeros(params.shape + params.shape[-1:], dtype=np.float64)
    else:
        jhr = np.zeros(gains.shape, dtype=gains.dtype)
        jhj = np.zeros(gains.shape[:4] + (N_CORR, N_CORR), dtype=gains.dtype)

    get_caller(term_type)(
        ms_inputs,
        mapping_inputs,
        chain_inputs,
        meta_inputs,
        upsampled_intermediaries(jhj, jhr),
        get_extents(t_map, f_map),
        N_CORR
    )

    return jhj, jhr


@pytest.mark.parametrize("n_dir", [1, 2])  # Single-direction and general path.
@pytest.mark.parametrize("term_type", list(KERNELS))
def test_jhj_jhr_conjugate_baseline_invariance(term_type, n_dir):

    rng = np.random.default_rng(452)

    rows = make_rows(rng, n_dir)
    n_gain_freq = N_CHAN if term_type == "rotation_measure" else 1
    gains = random_complex(rng, (1, n_gain_freq, N_ANT, 1, N_CORR))
    n_param = 1 if TERM_TYPES[term_type].is_parameterized else 0
    params = rng.normal(size=(1, 1, N_ANT, 1, max(n_param, 1)))

    jhj, jhr = compute_jhj_jhr(term_type, rows, gains, params)
    jhj_c, jhr_c = compute_jhj_jhr(
        term_type, conjugate_rows(*rows), gains, params
    )

    assert np.abs(jhj).max() > 0
    np.testing.assert_allclose(jhr_c, jhr, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(jhj_c, jhj, rtol=1e-10, atol=1e-10)
