"""The extension against the archive of the retired ctypes oracle
(research/p7-architecture.md, criterion 1; before: research/core-j-packaging.md).

Every case below ran at `5965d37` under both backends of that commit (the
extension and the ctypes C ABI of `core/`; the root-crate kernels through
ctypes on `librang_toy` in both runs) with byte-identical results, and those
results were archived in `tests/data/core-backends-golden.npz` (arrays) and
`.json` (scalars, strings and the SHA-256 of every array). The ctypes path
is gone; each case now runs on the extension and must reproduce the archive
byte for byte on Linux x86_64, where the archive was made. Elsewhere the
kernels that call the platform's libm (sin, cos, exp, hypot: predict, the
gridder, gain TV, the projector) differ in the last bits (measured on
Windows MSVC by task P7; X1's bit-equality held for the Tricolour port,
which uses no libm), so floating-point arrays must agree within a labelled
tolerance (relative 1e-9, absolute 1e-12 of the array's largest value), not
bit for bit, and error messages only in their exception class.

`RANG_GOLDEN_WRITE=1` writes the archive (into `RANG_GOLDEN_DIR`, default
`tests/data`) instead of checking it; do that only for a deliberate,
documented change of a kernel.
"""

import hashlib
import importlib.util
import json
import math
import os
import platform
import sys
from pathlib import Path

import numpy as np
import pytest
from rang import core, core_flag, core_grid, core_ms, core_weights, core_zarr

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("RANG_GOLDEN_DIR", ROOT / "tests" / "data"))
GOLDEN_NPZ = DATA / "core-backends-golden.npz"
GOLDEN_JSON = DATA / "core-backends-golden.json"
HAS_EXTENSION = importlib.util.find_spec("rang._core") is not None
C_LIGHT = 299792458.0
WRITE = os.environ.get("RANG_GOLDEN_WRITE") == "1"
EXACT = sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")
# Leaves whose bits come from NumPy's bundled LAPACK (lstsq, qr, svd), not from
# a kernel of this project: they differ in the last bits between NumPy wheels
# (the wheels workflow's Linux x86_64 runners failed on `root_projector.2` with
# NumPy 2.2.6 against this archive written with NumPy 2.5), so they take the
# labelled tolerance on every platform.
NUMPY_LAPACK = {"root_projector"}
_written_arrays = {}
_written_scalars = {}

pytestmark = pytest.mark.skipif(not HAS_EXTENSION, reason="rang._core is not built")


def _flatten(value, prefix):
    """(key, leaf) pairs of a nested result, in a stable order."""
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _flatten(value[key], f"{prefix}.{key}")
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            yield from _flatten(item, f"{prefix}.{i}")
    else:
        yield prefix, value


def _scalar(value):
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "len": len(value)}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, np.integer):
        return int(value)
    return {"float": float(value).hex()}


@pytest.fixture(scope="module")
def golden():
    if WRITE:
        yield None
        DATA.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(GOLDEN_NPZ, **_written_arrays)
        GOLDEN_JSON.write_text(
            json.dumps(_written_scalars, indent=1, sort_keys=True) + "\n"
        )
        return
    if not GOLDEN_NPZ.is_file():
        pytest.skip("golden archive missing")
    with np.load(GOLDEN_NPZ) as arrays:
        yield {k: arrays[k] for k in arrays.files}, json.loads(GOLDEN_JSON.read_text())


def _check(golden, name, result):
    """Compare a nested result with the archive (or record it)."""
    leaves = list(_flatten(result, name))
    if WRITE:
        for key, value in leaves:
            if isinstance(value, np.ndarray):
                _written_arrays[key] = value
                _written_scalars[key] = {
                    "sha256": hashlib.sha256(value.tobytes()).hexdigest(),
                    "dtype": str(value.dtype),
                    "shape": list(value.shape),
                }
            else:
                _written_scalars[key] = _scalar(value)
        return
    arrays, scalars = golden
    exact = EXACT and name not in NUMPY_LAPACK
    expected = {k for k in scalars if k == name or k.startswith(name + ".")}
    assert {k for k, _ in leaves} == expected, name
    for key, value in leaves:
        if isinstance(value, np.ndarray):
            want = arrays[key]
            assert value.dtype == want.dtype and value.shape == want.shape, key
            if exact or value.dtype.kind not in "fc":
                assert value.tobytes() == want.tobytes(), key
                digest = hashlib.sha256(value.tobytes()).hexdigest()
                assert digest == scalars[key]["sha256"], key
            else:  # labelled tolerance off the archive's platform
                finite = np.abs(want[np.isfinite(want)])
                scale = float(finite.max()) if finite.size else 0.0
                np.testing.assert_allclose(
                    value, want, rtol=1e-9, atol=1e-12 * scale, equal_nan=True
                )
        elif isinstance(value, str) and not exact and name == "errors":
            assert value.split(":")[0] == scalars[key].split(":")[0], key
        elif exact or not isinstance(scalars[key], dict) or "float" not in scalars[key]:
            assert _scalar(value) == scalars[key], key
        else:
            want = float.fromhex(scalars[key]["float"])
            assert math.isclose(float(value), want, rel_tol=1e-9), key


def _fused_case(seed=3, nchan=6):
    rng = np.random.default_rng(seed)
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    times = np.repeat([0.0, 1.0, 2.0, 3.0], len(pairs))
    p = np.tile([a for a, _ in pairs], 4).astype(np.int32)
    q = np.tile([b for _, b in pairs], 4).astype(np.int32)
    shape = (len(times), nchan, 4)
    data = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
        np.complex64
    )
    model = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
        np.complex64
    )
    weights = rng.uniform(0.5, 2.0, shape).astype(np.float32)
    gains = np.eye(2) + 0.1 * (
        rng.standard_normal((2, 2, 4, 2, 2)) + 1j * rng.standard_normal((2, 2, 4, 2, 2))
    )
    valid = np.ones((2, 2, 4), bool)
    tb = (np.unique(times, return_inverse=True)[1] // 2).astype(np.uint32)
    fb = (np.arange(nchan) // (nchan // 2)).astype(np.uint32)
    split = rng.integers(0, 4, (len(times), nchan)).astype(np.uint8)
    return data, model, weights, p, q, tb, fb, gains, valid, split


def test_fused_pass(golden):
    data, model, weights, p, q, tb, fb, gains, valid, split = _fused_case()
    result = core.fused_pass(
        data, weights, p, q, tb, fb, gains, valid, split, model=model
    )
    scalar = core.fused_pass(
        data,
        weights,
        p,
        q,
        tb,
        fb,
        gains,
        valid,
        split,
        scalar_model=np.linspace(1.0, 2.0, data.shape[1]),
        scores=False,
        normals=False,
    )
    _check(
        golden,
        "fused",
        [
            result.residuals,
            result.scores,
            result.diag_h,
            result.diag_b,
            result.diag_count,
            result.split_stats,
            scalar.residuals,
            scalar.split_stats,
            scalar.scores,
        ],
    )


def solve_case():
    data, model, weights, p, q, tb, fb, _gains, _valid, _split = _fused_case(seed=11)
    nrow = data.shape[0]
    flags = np.zeros(data.shape, bool)
    flags[:, 1] = True
    rows = np.zeros(nrow, bool)
    rows[-1] = True
    return data, model, weights, p, q, tb, fb, flags, rows


def solve(data, model, weights, p, q, tb, fb, flags, rows):
    s = core.solve_complex(
        data,
        weights,
        flags,
        rows,
        p,
        q,
        tb,
        fb,
        ntime_bins=2,
        nfreq_bins=2,
        nant=4,
        model=model,
        max_iterations=20,
    )
    return [s.gains, s.flags, s.iterations, s.converged_fraction]


def test_solve_complex(golden):
    _check(golden, "solve", solve(*solve_case()))


def test_predict_components(golden):
    rng = np.random.default_rng(4)
    uvw = rng.uniform(-2000, 2000, (12, 3))
    freq = np.linspace(1.0e9, 1.4e9, 5)
    arcmin = math.pi / 10800
    vis, spec = core.predict_components(
        uvw,
        freq,
        np.array([[1.0, -2.0], [0.5, 0.25]]) * arcmin,
        np.array([0, 1]),
        np.array([0.06, 1.5]),
        np.array([[-0.5], [-0.7]]),
        np.ones(2, bool),
        np.full(2, 1.284e9),
        np.array([[0.0, 0.0, 0.0], [3 * arcmin, 2 * arcmin, 0.3]]),
        spectra=True,
    )
    _check(golden, "predict", [vis, spec])


def _memcpyed_chunk(payload, blocksize):
    header = bytes([2, 1, 0x02, 4])
    header += len(payload).to_bytes(4, "little")
    header += blocksize.to_bytes(4, "little")
    header += (16 + len(payload)).to_bytes(4, "little")
    return header + payload


def test_blosc_and_zarr(golden, tmp_path):
    values = np.arange(60, dtype="<i4").reshape(20, 3)
    chunk = _memcpyed_chunk(values.tobytes(), blocksize=48)
    path = tmp_path / "0"
    path.write_bytes(chunk)
    raw, stats = core_zarr.read_rows(path, 12, [1, 7, 19])
    rows, blocks = core.blosc_decode_rows(chunk, 12, [0, 19])
    _check(
        golden,
        "blosc",
        [
            core.blosc_decode(chunk),
            raw,
            stats["blocks_decoded"],
            stats["blocks_total"],
            rows,
            blocks,
            core_zarr.header_fields(chunk[:16]),
            core_zarr.read_chunk(path),
        ],
    )


def test_weights(golden):
    rng = np.random.default_rng(7)
    data = (
        rng.standard_normal((5, 3, 4)) + 1j * rng.standard_normal((5, 3, 4))
    ).astype(np.complex64)
    weights = rng.uniform(0.5, 2.0, (5, 3, 4)).astype(np.float32)
    flags = rng.integers(0, 2, (5, 3, 4)).astype(bool)
    uvw = rng.uniform(-300, 300, (5, 3))
    wavelength = np.array([0.2, 0.22, 0.25])
    vis_weights = rng.uniform(0.0, 2.0, (5, 3)).astype(np.float32)
    selected = np.array([True, True, False, True, True])
    vis, weight = core_weights.stokes_i(data, weights, flags)
    out = [
        vis,
        weight,
        core_weights.padded_size(512),
        core_weights.grid_shape(616, 616),
    ]
    for mode in ("briggs", "uniform", "natural"):
        result = core_weights.imaging_weights(
            uvw, wavelength, vis_weights, selected, mode=mode, robust=0.5
        )
        out.extend([result["weights"], result["grid"], result["sums"]])
    _check(golden, "weights", out)


def test_gridder(golden):
    rng = np.random.default_rng(20261029)
    frequencies = np.array([1.0e9, 1.1e9])
    radius = rng.uniform(5.0, 120.0, 80)
    angle = rng.uniform(0.0, 2 * math.pi, 80)
    uvw = np.stack(
        [radius * np.cos(angle), radius * np.sin(angle), rng.normal(0, 4, 80)], 1
    )
    scale = 60.0 * math.pi / 648000.0
    l, m = 5 * scale, -3 * scale
    n = math.sqrt(1.0 - l * l - m * m)
    phase = (
        2
        * math.pi
        * (uvw[:, :1] * l + uvw[:, 1:2] * m + uvw[:, 2:3] * (n - 1))
        / (C_LIGHT / frequencies)
    )
    data = np.exp(1j * phase).astype(np.complex64)
    weights = np.ones(data.shape, np.float32)
    result = core_grid.invert(
        uvw,
        frequencies,
        data,
        weights,
        weights,
        width=48,
        height=48,
        scale_arcsec=60.0,
        w_layers=4,
    )
    out = [result["dirty"], result["psf"], result["stats"], core_grid.kernel()]
    _check(golden, "grid", out)


def flag_case():
    rng = np.random.default_rng(20261029)
    nchan, ntime = 64, 6
    antenna1, antenna2, times = [], [], []
    for t in range(ntime):
        for a1, a2 in ((0, 0), (0, 1), (1, 1)):
            antenna1.append(a1)
            antenna2.append(a2)
            times.append(1.0e9 + 8.0 * t)
    nrow = len(times)
    data = (
        rng.normal(size=(nrow, nchan, 4)) + 1j * rng.normal(size=(nrow, nchan, 4))
    ).astype(np.complex64)
    data[:, :, 0] += 50.0
    data[:, :, 3] += 50.0
    data[7, 20:24, 1] += 400.0
    flags = np.zeros((nrow, nchan, 4), dtype=bool)
    strategies = core_flag.parse_strategy(
        "strategies:\n"
        "    -\n        name: a\n        task: flag_nans_zeros\n"
        "    -\n        name: b\n        task: sum_threshold\n"
        "        kwargs:\n            outlier_nsigma: 10\n"
        "            windows_time: [1, 2]\n            windows_freq: [1, 2, 4]\n"
        "    -\n        name: c\n        task: flag_autos\n"
        "    -\n        name: d\n        task: combine_with_input_flags\n"
    )
    return (
        data,
        flags,
        np.array(antenna1, np.int32),
        np.array(antenna2, np.int32),
        np.array(times),
        np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]]),
        1.0e9 + 1.0e6 * np.arange(nchan),
        np.full(nchan, 1.0e6),
        np.array([9, 10, 11, 12], np.int32),
        strategies,
    )


def test_flag_rows(golden):
    result = core_flag.flag_rows(*flag_case(), masks=[np.array([1.0e9 + 3.0e6])])
    out = [result["flags"], result["intensity"], result["stages"], result["ubl"]]
    _check(golden, "flag", out)
    assert out[0].any(), (
        "the strategy must flag something for the test to mean anything"
    )


def _fixture_antenna(tmp_path):
    """ms0's ANTENNA from the public fixture zip named by RANG_FIXTURE: scan
    9 is ms0 file for file (research/t1-casacure-ci.md), so this runs where
    outputs/ is absent (the wheel test jobs), or None."""
    import zipfile

    from rang.notebook import data as fixture_data

    source = os.environ.get("RANG_FIXTURE")
    if not source or not Path(source).is_file():
        return None
    if fixture_data._sha256(source) != fixture_data.FIXTURE_SHA256:
        pytest.fail(f"{source} is not the pinned public fixture")
    prefix = fixture_data.FIXTURE_SCAN + "/ANTENNA/"
    with zipfile.ZipFile(source) as zipped:
        for info in fixture_data._safe_members(zipped, prefix):
            zipped.extract(info, tmp_path)
    return tmp_path / prefix


def test_ms_reader(golden, tmp_path):
    path = _fixture_antenna(tmp_path)
    if path is None:
        receipt = ROOT / "outputs/core-e-oracle-20261029-01/receipt.json"
        if not receipt.is_file():
            pytest.skip("MS oracle not present")
        entry = json.loads(receipt.read_text())["tables"]["ms0.ANTENNA"]
        path = ROOT / "outputs" / Path(*Path(entry["path"]).parts[2:])
        if not path.is_dir():
            pytest.skip("fixture MS not present")
    assert core_ms.has_reader()
    with core_ms.open_table(path) as table:
        # The archive's path (ms0 in outputs/), whichever copy was read.
        description = dict(table.description)
        description["path"] = (
            "<ROOT>/outputs/tv-caracal-wsl-20261029-01/original.ms/ANTENNA"
        )
        out = [
            json.dumps(description, sort_keys=True),
            [str(x) for x in table.getcol("NAME")],
            table.getcol("POSITION"),
            table.getcol("POSITION", 1, 2),
            table.getcol("FLAG_ROW"),
        ]
    _check(golden, "ms", out)


def test_errors(golden):
    caught = []
    for action in (
        lambda: core.blosc_decode(b"not a blosc chunk"),
        lambda: core_weights.grid_shape(10, 10, super_weight=0.0),
        lambda: core_ms.open_table(ROOT / "no-such-table.ms"),
        lambda: core.solve_complex(
            np.zeros((2, 2, 4), np.complex64),
            np.ones((2, 2, 4), np.float32),
            np.zeros((2, 2, 4), bool),
            np.zeros(2, bool),
            np.array([0, 0], np.uint32),
            np.array([1, 1], np.uint32),
            np.zeros(2, np.uint32),
            np.zeros(2, np.uint32),
            ntime_bins=1,
            nfreq_bins=1,
            nant=2,
            model=np.zeros((2, 2, 4), np.complex64),
        ),
    ):
        try:
            action()
            caught.append(None)
        except Exception as exc:  # noqa: BLE001 - the class is the result
            # The MS error names the checkout's path; keep it out of the archive.
            message = str(exc).replace(str(ROOT), "<root>")
            caught.append(f"{type(exc).__name__}: {message}")
    _check(golden, "errors", caught)
    assert all(c is not None for c in caught[:3])


# The root-crate kernels (ctypes on librang_toy at 5965d37, now the extension).


def _gain_grid(seed, shape=(5, 4, 3)):
    rng = np.random.default_rng(seed)
    gains = np.eye(2) + 0.2 * (
        rng.standard_normal((*shape, 2, 2)) + 1j * rng.standard_normal((*shape, 2, 2))
    )
    valid = rng.uniform(size=shape) > 0.2
    times = np.cumsum(rng.uniform(1.0, 2.0, shape[0]))
    times[-1] += 30.0  # one gap edge
    frequencies = 1.0e9 + 1.0e6 * np.cumsum(rng.uniform(1.0, 1.5, shape[1]))
    return gains, valid, times, frequencies


def test_root_gain_tv(golden):
    from rang import core_policy as flagging

    gains, valid, times, frequencies = _gain_grid(5)
    out = flagging.gain_tv(gains, valid, times, frequencies, scale=1.3)
    caught = []
    try:
        flagging.gain_tv(gains * np.nan, np.ones_like(valid), times, frequencies)
    except ValueError as exc:
        caught.append(str(exc))
    _check(golden, "root_tv", [out, caught])


def test_root_trend(golden):
    from rang import core_trend_run as flagging_trend

    gains, valid, times, frequencies = _gain_grid(6, (6, 5, 3))
    support = np.random.default_rng(1).uniform(size=valid.shape) > 0.1
    slopes, counts = flagging_trend.estimate_trend(
        gains, valid, times, frequencies, support
    )
    _check(golden, "root_trend", [slopes, counts])


def test_root_response(golden):
    from rang import core_influence as influence

    rng = np.random.default_rng(8)

    def jones():
        return np.eye(2) + 0.3 * (
            rng.standard_normal((2, 2)) + 1j * rng.standard_normal((2, 2))
        )

    jac = influence.jones_jacobian(jones(), jones(), jones())
    gains = np.stack([np.stack([jones() for _ in range(4)]) for _ in range(2)])
    pairs = [(a, b) for a in range(4) for b in range(a + 1, 4)] * 3
    n = len(pairs)
    p, q = (np.array(x) for x in zip(*pairs, strict=True))
    models = np.stack([jones() for _ in range(n)])
    residuals = 0.01 * np.stack([jones() for _ in range(n)])
    weights = rng.uniform(0.5, 2.0, (n, 4))
    bins = np.arange(n) % 2
    h, b, counts = influence.training_normals(
        gains, models, residuals, weights, p, q, bins
    )
    active = np.array([True, True, True, False])
    full = influence.anchored_response(
        h[0], b[0], 0.1 * h[0], 0.1 * b[0], gains[0], active
    )
    zero_h, zero_b = np.zeros((32, 32)), np.zeros(32)
    under = influence.anchored_response(
        zero_h, zero_b, zero_h, zero_b, gains[0], active
    )
    _check(golden, "root_response", [jac, h, b, counts, full, under])


def test_root_projector(golden):
    from rang import projector

    rng = np.random.default_rng(9)
    a = rng.standard_normal((30, 4))
    a[:, 3] = a[:, 0] + a[:, 1]  # rank 3
    z = rng.standard_normal((30, 2))
    out, rank = projector.project_out(a, z)
    groups = np.repeat([0, 1, 2], 10)
    grouped, total = projector.project_grouped(
        rng.standard_normal((30, 2)), rng.standard_normal((30, 2)), z, groups
    )
    _check(golden, "root_projector", [out, rank, grouped, total])
