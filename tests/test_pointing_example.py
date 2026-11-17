# SPDX-License-Identifier: MIT
"""Exercise the README command, including serialization of solver outputs."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_pointing_example_exports_results(tmp_path):
    pytest.importorskip("jax")
    import numpy as np

    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            sys.executable,
            str(root / "examples/pointing.py"),
            "--output",
            str(tmp_path),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    result = json.loads((tmp_path / "results.json").read_text())
    assert result["success"]
    assert result["fit_heldout_rms_jy"] < result["fixed_heldout_rms_jy"]
    assert 60 * result["pointing_rmse_arcmin"] < 3
    gains = result["gains"]
    np.testing.assert_allclose(gains["real"], 1)
    np.testing.assert_allclose(gains["imag"], 0)
    assert (tmp_path / "trajectories.svg").read_text().startswith("<svg")
