import json
from pathlib import Path

import numpy as np
import pytest
from rangtoy import core_flag

ROOT = Path(__file__).resolve().parents[1]
FIRSTPASS = """# comment
strategies:
    -
        name: nan_dropouts_flag
        task: flag_nans_zeros
    -
        name: background_static_mask
        task: apply_static_mask
        kwargs:
            accumulation_mode: "or"
            uvrange: ""
    -
        name: background_flags
        task: sum_threshold
        kwargs:
            outlier_nsigma: 10
            windows_time: [1, 2, 4, 8]
            windows_freq: [32, 48, 64, 128]
            spike_width_time: 2
            rho: 1.3
    -
        name: residual_flag_initial
        task: uvcontsub_flagger
        kwargs:
            major_cycles: 7
            or_original_from_cycle: 1
            taylor_degrees: 20
            sigma: 15.0
    -
        name: flag_autos
        task: flag_autos
    -
        name: combine_with_input_flags
        task: combine_with_input_flags
"""


def test_parse_strategy_reads_tasks_kwargs_and_types():
    steps = core_flag.parse_strategy(FIRSTPASS)
    assert [s["task"] for s in steps] == [
        "flag_nans_zeros",
        "apply_static_mask",
        "sum_threshold",
        "uvcontsub_flagger",
        "flag_autos",
        "combine_with_input_flags",
    ]
    assert steps[1]["kwargs"] == {"accumulation_mode": "or", "uvrange": ""}
    assert steps[2]["kwargs"]["windows_freq"] == [32, 48, 64, 128]
    assert steps[2]["kwargs"]["spike_width_time"] == 2
    assert steps[3]["kwargs"] == {
        "major_cycles": 7,
        "or_original_from_cycle": 1,
        "taylor_degrees": 20,
        "sigma": 15.0,
    }
    assert steps[4]["kwargs"] == {}


def test_parse_strategy_matches_the_archived_caracal_inspection():
    archive = json.loads(
        (ROOT / "research/results/caracal-strategies.json").read_text()
    )
    strategy_dir = ROOT / "outputs/caracal-strategy-inputs-8f7bb363"
    if not strategy_dir.is_dir():
        # The downloaded strategies are ignored inputs; the committed
        # inspection archive still pins the parser's expectations below.
        record = archive["files"]["calibrator_mild_flagging.yaml"]
        assert record["tasks"][0] == "flag_nans_zeros"
        assert record["sum_threshold"][0]["windows_time"] == [1, 2, 4, 8]
        return
    for name, record in archive["files"].items():
        if not name.endswith(".yaml") or "tasks" not in record:
            continue
        steps = core_flag.parse_strategy((strategy_dir / name).read_text())
        assert [s["task"] for s in steps] == record["tasks"], name
        parsed = [s["kwargs"] for s in steps if s["task"] == "sum_threshold"]
        assert parsed == record["sum_threshold"], name


def test_casa_style_range():
    assert core_flag.casa_style_range("") == (0.0, np.inf)
    assert core_flag.casa_style_range("0~550") == (0.0, 550.0)
    assert core_flag.casa_style_range("10~250m") == (10.0, 250.0)
    with pytest.raises(ValueError):
        core_flag.casa_style_range("abc")


def test_encode_steps_applies_tricolour_defaults():
    table = core_flag.encode_steps(core_flag.parse_strategy(FIRSTPASS))
    assert table.shape == (6, core_flag.STEP_WIDTH)
    assert list(table[:, 0]) == [0, 1, 2, 3, 4, 5]
    assert table[1, 1] == 1 and table[1, 2] == 0 and table[1, 3] == np.inf
    sum_threshold = table[2]
    assert sum_threshold[1] == 10
    assert list(sum_threshold[3:7]) == [1, 2, 4, 8]
    assert list(sum_threshold[12:16]) == [32, 48, 64, 128]
    assert sum_threshold[21] == 1  # background_iterations default
    assert sum_threshold[22] == 2  # spike_width_time from the file
    assert sum_threshold[31] == 5  # num_major_iterations default
    assert list(table[3, 1:5]) == [7, 1, 20, 15.0]
    with pytest.raises(ValueError):
        core_flag.encode_steps([{"task": "sum_threshold", "kwargs": {"bogus": 1}}])


def test_static_masks_load_with_the_archived_coverage():
    paths = core_flag.static_mask_files()
    assert [p.name for p in paths] == list(core_flag.STATIC_MASK_FILES)
    lband, uhf = (core_flag.load_static_mask(p) for p in paths)
    # Tricolour's log: 41.50% of 32768 channels between 0.856 and 1.712 GHz.
    assert lband.size == 13600 and uhf.size == 190
    assert 0.855e9 < lband.min() and lband.max() < 1.712e9
    assert np.all(np.diff(lband) > 0)


def _synthetic(nchan=64, ntime=6):
    rng = np.random.default_rng(20261029)
    antenna1, antenna2, times = [], [], []
    pairs = [(0, 0), (0, 1), (1, 1)]
    for t in range(ntime):
        for a1, a2 in pairs:
            antenna1.append(a1)
            antenna2.append(a2)
            times.append(1.0e9 + 8.0 * t)
    nrow = len(times)
    data = (
        rng.normal(size=(nrow, nchan, 4)) + 1j * rng.normal(size=(nrow, nchan, 4))
    ).astype(np.complex64)
    data[:, :, 0] += 50.0  # bright unpolarised source: XX and YY equal
    data[:, :, 3] += 50.0
    flags = np.zeros((nrow, nchan, 4), dtype=bool)
    meta = {
        "antenna1": np.array(antenna1, np.int32),
        "antenna2": np.array(antenna2, np.int32),
        "times": np.array(times),
        "antenna_position": np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]]),
        "chan_freq": 1.0e9 + 1.0e6 * np.arange(nchan),
        "chan_width": np.full(nchan, 1.0e6),
        "corr_type": np.array([9, 10, 11, 12], np.int32),
    }
    return data, flags, meta


def _run(data, flags, meta, strategies, masks):
    return core_flag.flag_rows(
        data,
        flags,
        meta["antenna1"],
        meta["antenna2"],
        meta["times"],
        meta["antenna_position"],
        meta["chan_freq"],
        meta["chan_width"],
        meta["corr_type"],
        strategies,
        masks=masks,
    )


def test_flag_rows_polarisation_mode_flags_a_polarised_spike_and_autos():
    data, flags, meta = _synthetic()
    # A strong polarised spike on the cross baseline at (time 2, channel 20).
    cross = (meta["antenna1"] == 0) & (meta["antenna2"] == 1)
    row = np.flatnonzero(cross)[2]
    data[row, 20, 1] += 400.0
    flags[row, 5, 2] = True  # one input flag on a single correlation
    strategies = core_flag.parse_strategy(
        """strategies:
    -
        task: flag_nans_zeros
    -
        task: sum_threshold
        kwargs:
            outlier_nsigma: 10
            windows_time: [1, 2]
            windows_freq: [1, 2]
            background_iterations: 1
            spike_width_time: 2
            spike_width_freq: 4
            freq_chunks: 2
            num_major_iterations: 1
    -
        task: flag_autos
    -
        task: combine_with_input_flags
"""
    )
    result = _run(data, flags, meta, strategies, masks=[])
    out = result["flags"]
    assert out.shape == data.shape and out.dtype == bool
    # Every correlation of a cell carries the same flag.
    assert np.all(out == out[..., :1])
    assert out[row, 20].all()
    assert out[row, 5].all()
    autos = meta["antenna1"] == meta["antenna2"]
    assert out[autos].all()
    # Window order follows Tricolour's 64-bit (a1, a2) sort.
    assert result["ubl"].tolist() == [[0, 0], [0, 1], [1, 1]]
    assert result["intensity"].shape == (3, 1, 6, 64)
    assert result["intensity"].dtype == np.complex64
    assert set(result["stages"]) == {
        "00-flag_nans_zeros",
        "01-sum_threshold",
        "02-flag_autos",
        "03-combine_with_input_flags",
    }
    # A clean unflagged cross cell away from the spike stays unflagged.
    assert not out[np.flatnonzero(cross)[0], 40].any()


def test_static_mask_respects_uvrange_and_channel_bounds():
    data, flags, meta = _synthetic()
    masks = [np.array([1.010e9 + 0.4e6, 1.030e9])]  # channels 10 and 30
    strategies = core_flag.parse_strategy(
        """strategies:
    -
        task: apply_static_mask
        kwargs:
            accumulation_mode: "or"
            uvrange: "0~50"
"""
    )
    out = _run(data, flags, meta, strategies, masks)["flags"]
    autos = meta["antenna1"] == meta["antenna2"]
    # The cross baseline is 100 m, outside 0~50 (Tricolour halves the
    # squared length, so the cut is at 50 * sqrt(2) m); autos are inside.
    assert out[autos][:, [10, 30]].all()
    assert not out[autos][:, [9, 11, 29, 31]].any()
    assert not out[~autos].any()
    strategies[0]["kwargs"]["uvrange"] = ""
    out = _run(data, flags, meta, strategies, masks)["flags"]
    assert out[:, [10, 30]].all() and not out[:, 11].any()


def test_uvcontsub_discards_prior_flags_before_the_or_cycle():
    data, flags, meta = _synthetic(nchan=128)
    flags[:, 3, :] = True  # an input flag that cycle 0 must drop
    cross = (meta["antenna1"] == 0) & (meta["antenna2"] == 1)
    row = np.flatnonzero(cross)[1]
    data[row, 64, 1] += 300.0
    strategies = core_flag.parse_strategy(
        """strategies:
    -
        task: uvcontsub_flagger
        kwargs:
            major_cycles: 2
            or_original_from_cycle: 1
            taylor_degrees: 4
            sigma: 8.0
"""
    )
    out = _run(data, flags, meta, strategies, masks=[])["flags"]
    assert out[row, 64].all()
    assert not out[np.flatnonzero(cross)[0], 3].any()


def test_flag_rows_rejects_mismatched_inputs():
    data, flags, meta = _synthetic()
    with pytest.raises(ValueError):
        _run(data, flags[:, :10], meta, [], masks=[])
    with pytest.raises(ValueError):
        core_flag.encode_steps(
            [{"task": "apply_static_mask", "kwargs": {"accumulation_mode": "xor"}}]
        )
