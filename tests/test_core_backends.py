"""The two core backends, extension and ctypes, give byte-identical results
(research/core-j-packaging.md, criteria 3-5).

Every wrapper function runs under both backends on the same inputs; outputs
are compared with `tobytes()`. The tests skip when the extension is not
built (`maturin develop` or `pip install -e .`).
"""

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from rangtoy import core, core_flag, core_grid, core_ms, core_weights, core_zarr

ROOT = Path(__file__).resolve().parents[1]
HAS_EXTENSION = importlib.util.find_spec("rangtoy._core") is not None
C_LIGHT = 299792458.0


def _select(monkeypatch, backend):
    monkeypatch.setenv("RANG_CORE_BACKEND", backend)
    monkeypatch.delenv("RANG_CORE_LIB", raising=False)
    core.reset_backend()
    assert core.backend_name() == backend


@pytest.fixture(autouse=True)
def _restore():
    yield
    core.reset_backend()


def _both(monkeypatch, run):
    """`run()` under each backend; returns (extension result, ctypes result)."""
    if not HAS_EXTENSION:
        pytest.skip("rangtoy._core is not built")
    results = []
    for backend in ("extension", "ctypes"):
        _select(monkeypatch, backend)
        results.append(run())
    return results


def _assert_identical(a, b):
    if isinstance(a, dict):
        assert set(a) == set(b)
        for key in a:
            _assert_identical(a[key], b[key])
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            _assert_identical(x, y)
    elif isinstance(a, np.ndarray):
        assert a.dtype == b.dtype and a.shape == b.shape
        assert a.tobytes() == b.tobytes()
    elif a is None or isinstance(a, (bytes, str, bool, int)):
        assert a == b
    else:
        assert float(a) == float(b)


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


def test_fused_pass_identical(monkeypatch):
    data, model, weights, p, q, tb, fb, gains, valid, split = _fused_case()

    def run():
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
        return [
            result.residuals,
            result.scores,
            result.diag_h,
            result.diag_b,
            result.diag_count,
            result.split_stats,
            scalar.residuals,
            scalar.split_stats,
            scalar.scores,
        ]

    a, b = _both(monkeypatch, run)
    _assert_identical(a, b)


def test_solve_complex_identical(monkeypatch):
    data, model, weights, p, q, tb, fb, _gains, _valid, _split = _fused_case(seed=11)
    nrow, _nchan = data.shape[:2]
    flags = np.zeros(data.shape, bool)
    flags[:, 1] = True
    rows = np.zeros(nrow, bool)
    rows[-1] = True

    def run():
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

    a, b = _both(monkeypatch, run)
    _assert_identical(a, b)


def test_predict_components_identical(monkeypatch):
    rng = np.random.default_rng(4)
    uvw = rng.uniform(-2000, 2000, (12, 3))
    freq = np.linspace(1.0e9, 1.4e9, 5)
    arcmin = math.pi / 10800

    def run():
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
        return [vis, spec]

    a, b = _both(monkeypatch, run)
    _assert_identical(a, b)


def _memcpyed_chunk(payload, blocksize):
    header = bytes([2, 1, 0x02, 4])
    header += len(payload).to_bytes(4, "little")
    header += blocksize.to_bytes(4, "little")
    header += (16 + len(payload)).to_bytes(4, "little")
    return header + payload


def test_blosc_and_zarr_identical(monkeypatch, tmp_path):
    values = np.arange(60, dtype="<i4").reshape(20, 3)
    chunk = _memcpyed_chunk(values.tobytes(), blocksize=48)
    path = tmp_path / "0"
    path.write_bytes(chunk)

    def run():
        raw, stats = core_zarr.read_rows(path, 12, [1, 7, 19])
        rows, blocks = core.blosc_decode_rows(chunk, 12, [0, 19])
        return [
            core.blosc_decode(chunk),
            raw,
            stats["blocks_decoded"],
            stats["blocks_total"],
            rows,
            blocks,
            core_zarr.header_fields(chunk[:16]),
            core_zarr.read_chunk(path),
        ]

    a, b = _both(monkeypatch, run)
    _assert_identical(a, b)


def test_weights_identical(monkeypatch):
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

    def run():
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
        return out

    a, b = _both(monkeypatch, run)
    _assert_identical(a, b)


def test_gridder_identical(monkeypatch):
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

    def run():
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
        return [result["dirty"], result["psf"], result["stats"], core_grid.kernel()]

    a, b = _both(monkeypatch, run)
    _assert_identical(a, b)


def test_flag_rows_identical(monkeypatch):
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

    def run():
        result = core_flag.flag_rows(
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
            masks=[np.array([1.0e9 + 3.0e6])],
        )
        return [result["flags"], result["intensity"], result["stages"], result["ubl"]]

    a, b = _both(monkeypatch, run)
    _assert_identical(a, b)
    assert a[0].any(), "the strategy must flag something for the test to mean anything"


def test_ms_reader_identical(monkeypatch):
    receipt = ROOT / "outputs/core-e-oracle-20261029-01/receipt.json"
    if not receipt.is_file():
        pytest.skip("MS oracle not present")
    entry = json.loads(receipt.read_text())["tables"]["ms0.ANTENNA"]
    path = ROOT / "outputs" / Path(*Path(entry["path"]).parts[2:])
    if not path.is_dir():
        pytest.skip("fixture MS not present")

    def run():
        assert core_ms.has_reader()
        with core_ms.open_table(path) as table:
            return [
                table.description,
                table.getcol("NAME"),
                table.getcol("POSITION"),
                table.getcol("POSITION", 1, 2),
                table.getcol("FLAG_ROW"),
            ]

    a, b = _both(monkeypatch, run)
    assert a[0] == b[0]
    assert a[1].tolist() == b[1].tolist()
    _assert_identical(a[2:], b[2:])


def test_same_errors_under_both_backends(monkeypatch):
    def run():
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
                caught.append((type(exc).__name__, str(exc)))
        return caught

    a, b = _both(monkeypatch, run)
    assert a == b
    assert all(c is not None for c in a[:3])


@pytest.mark.skipif(not HAS_EXTENSION, reason="rangtoy._core is not built")
def test_extension_reads_arrays_in_place():
    from rangtoy import _core

    for dtype in (
        np.float32,
        np.float64,
        np.uint8,
        np.int8,
        np.uint32,
        np.int32,
        np.uint64,
        np.uintp,
    ):
        array = np.arange(24, dtype=dtype).reshape(4, 6)
        assert _core.data_address(array) == array.ctypes.data
        assert _core.data_address(array[1:3]) == array[1:3].ctypes.data
        with pytest.raises(TypeError):
            _core.data_address(array[:, ::2])  # not contiguous: refused, not copied
    # WSClean's kernel settings; `rang_core_grid_kernel` has no catch_unwind,
    # so unrealistic settings would abort the process on either backend.
    out = np.zeros(7 * 1023, np.float64)
    assert _core.grid_kernel(7, 1023, out) == 0 and out.any(), "filled in place"
    assert _core.grid_kernel(7, 1022, out) == 1, "wrong length is refused"
    frozen = np.zeros(7 * 1023, np.float64)
    frozen.setflags(write=False)
    with pytest.raises(TypeError):
        _core.grid_kernel(7, 1023, frozen)


def test_backend_policy(monkeypatch):
    if not HAS_EXTENSION:
        pytest.skip("rangtoy._core is not built")
    _select(monkeypatch, "ctypes")
    assert core.extension() is None
    _select(monkeypatch, "extension")
    monkeypatch.setattr(core, "library", lambda: pytest.fail("ctypes used"))
    data, model, weights, p, q, tb, fb, gains, valid, split = _fused_case()
    core.fused_pass(data, weights, p, q, tb, fb, gains, valid, split, model=model)
    assert core.library_path().name.startswith("_core")
    monkeypatch.undo()
    core.reset_backend()
    # An explicit library wins over the implicit extension; the extension
    # binary itself exports the C ABI, so it can serve as that library.
    monkeypatch.delenv("RANG_CORE_BACKEND", raising=False)
    from rangtoy import _core

    monkeypatch.setenv("RANG_CORE_LIB", _core.__file__)
    core.reset_backend()
    assert core.backend_name() == "ctypes"
    assert core.library_path() == Path(_core.__file__).resolve()
    assert hasattr(core.library(), "rang_core_fused")
    core.reset_backend()
    monkeypatch.delenv("RANG_CORE_LIB")
    core.reset_backend()
    assert core.backend_name() == "extension"
    monkeypatch.setenv("RANG_CORE_BACKEND", "nonsense")
    core.reset_backend()
    with pytest.raises(ValueError):
        core.backend_name()
