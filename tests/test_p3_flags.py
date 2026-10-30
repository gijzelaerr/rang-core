"""Task P3: the Tricolour port in parallel over baselines gives the same flags.

research/p3-sumthreshold.md. The thread count of rayon's global pool is fixed
when the pool starts, so each thread count runs in its own interpreter.
"""

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
from rang import core_campaign, core_flag

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = """strategies:
    -
        task: flag_nans_zeros
    -
        task: apply_static_mask
        kwargs:
            accumulation_mode: "or"
            uvrange: ""
    -
        task: sum_threshold
        kwargs:
            outlier_nsigma: 4.5
            windows_time: [1, 2, 4, 8]
            windows_freq: [1, 2, 4, 8]
            spike_width_time: 2.0
    -
        task: uvcontsub_flagger
        kwargs:
            major_cycles: 3
            or_original_from_cycle: 1
            taylor_degrees: 10
            sigma: 5.0
    -
        task: sum_threshold
        kwargs:
            outlier_nsigma: 4.5
            windows_time: [1, 2, 4]
            windows_freq: [1, 2, 4, 8, 16]
            freq_chunks: 3
    -
        task: flag_autos
    -
        task: combine_with_input_flags
"""


def synthetic(nant=6, ntime=12, nchan=200, seed=20261030):
    """Every baseline (autos included) with noise, polarised RFI and flags."""
    rng = np.random.default_rng(seed)
    pairs = [(a, b) for a in range(nant) for b in range(a, nant)]
    antenna1, antenna2, times = [], [], []
    for t in range(ntime):
        for a, b in pairs:
            antenna1.append(a)
            antenna2.append(b)
            times.append(1.0e9 + 8.0 * t)
    nrow = len(times)
    data = (
        rng.normal(size=(nrow, nchan, 4)) + 1j * rng.normal(size=(nrow, nchan, 4))
    ).astype(np.complex64)
    data[:, :, 0] += 30.0
    data[:, :, 3] += 30.0
    spikes = rng.random((nrow, nchan)) < 0.01
    data[spikes, 1] += 60.0  # polarised: XY only
    data[:, 50:53, 2] += 25.0j  # a narrow band in YX on every row
    flags = rng.random((nrow, nchan, 4)) < 0.02
    flags[:, 120:124, :] = True
    positions = rng.normal(scale=300.0, size=(nant, 3))
    meta = {
        "antenna1": np.array(antenna1, np.int32),
        "antenna2": np.array(antenna2, np.int32),
        "times": np.array(times),
        "antenna_position": positions,
        "chan_freq": 1.0e9 + 1.0e6 * np.arange(nchan),
        "chan_width": np.full(nchan, 1.0e6),
        "corr_type": np.array([9, 10, 11, 12], np.int32),
    }
    return data, flags, meta


def run(data, flags, meta, text=STRATEGY):
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
        core_flag.parse_strategy(text),
        masks=[np.array([1.0505e9, 1.1505e9])],
    )


def digest(result):
    h = sha256(np.ascontiguousarray(result["flags"]).tobytes())
    for name in sorted(result["stages"]):
        h.update(name.encode())
        h.update(np.ascontiguousarray(result["stages"][name]).tobytes())
    return h.hexdigest()


CHILD = """
import sys
sys.path.insert(0, {tests!r})
from test_p3_flags import digest, run, synthetic
print(digest(run(*synthetic())))
"""


def test_flags_and_stages_are_identical_across_thread_counts():
    result = run(*synthetic())
    assert 0.02 < result["flags"].mean() < 0.9
    for name, stage in result["stages"].items():
        assert stage.any(), name
    expected = digest(result)
    code = CHILD.format(tests=str(Path(__file__).parent))
    for threads in ("1", "2", "5"):
        env = dict(os.environ, RAYON_NUM_THREADS=threads)
        out = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert out.stdout.strip() == expected, threads


def test_replicated_baselines_carry_their_originals_flags():
    data, flags, meta = synthetic(nant=4)
    nant = meta["antenna_position"].shape[0]
    copies = 3
    replicated = {
        "antenna1": np.concatenate(
            [meta["antenna1"] + k * nant for k in range(copies)]
        ),
        "antenna2": np.concatenate(
            [meta["antenna2"] + k * nant for k in range(copies)]
        ),
        "times": np.tile(meta["times"], copies),
        "antenna_position": np.tile(meta["antenna_position"], (copies, 1)),
    }
    replicated.update({k: meta[k] for k in ("chan_freq", "chan_width", "corr_type")})
    single = run(data, flags, meta)
    many = run(
        np.concatenate([data] * copies), np.concatenate([flags] * copies), replicated
    )
    nrow = data.shape[0]
    for k in range(copies):
        assert np.array_equal(many["flags"][k * nrow : (k + 1) * nrow], single["flags"])


def test_task_k_additions_equal_the_archive():
    fetched = ROOT / "outputs/core-k-20261030-01/fetch"
    if not fetched.is_dir():
        pytest.skip("the task K fetch is an ignored input")
    from rang import core_fetch

    arrays, _ = core_fetch.decode_slice(fetched)
    rows = np.asarray(json.loads((fetched / "result.json").read_text())["rows"])
    extra = core_campaign.decode_extra(fetched, rows)
    state = core_campaign.build_state(arrays, extra)
    archived = json.loads(
        (ROOT / "research/results/core-k-luno-campaign.json").read_text()
    )["arms"]
    for label, strategy in core_campaign.STRATEGIES.items():
        additions, _ = core_campaign.tricolour_arm(
            state, extra, core_campaign.STRATEGY_DIR / strategy
        )
        assert (
            core_campaign.array_sha256(additions) == archived[label]["additions_sha256"]
        ), label
