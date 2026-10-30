"""Big-plan task P2 (research/p2-gridder.md): the layer-parallel gridder gives
the same images at any thread count, and flagged cells change nothing."""

import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from rangtoy import core_grid

C_LIGHT = 299792458.0
SETTINGS = {"width": 64, "height": 48, "scale_arcsec": 30.0, "w_layers": 24}


def _case(seed=20261030, nrow=120):
    rng = np.random.default_rng(seed)
    frequencies = np.array([1.0e9, 1.05e9, 1.1e9])
    radius = rng.uniform(5.0, 200.0, nrow)
    angle = rng.uniform(0.0, 2 * math.pi, nrow)
    uvw = np.stack(
        [radius * np.cos(angle), radius * np.sin(angle), rng.normal(0, 20, nrow)], 1
    )
    scale = SETTINGS["scale_arcsec"] * math.pi / 648000.0
    l, m = 7 * scale, -4 * scale
    n = math.sqrt(1.0 - l * l - m * m)
    phase = (
        2
        * math.pi
        * (uvw[:, :1] * l + uvw[:, 1:2] * m + uvw[:, 2:3] * (n - 1))
        / (C_LIGHT / frequencies)
    )
    data = np.exp(1j * phase).astype(np.complex64)
    weights = rng.uniform(0.5, 2.0, data.shape).astype(np.float32)
    weights[rng.random(data.shape) < 0.3] = 0.0
    imaging = rng.uniform(0.2, 1.0, data.shape).astype(np.float32)
    return uvw, frequencies, data, weights, imaging


def _digest(products):
    return [hashlib.sha256(products[k].tobytes()).hexdigest() for k in ("dirty", "psf")]


_CHILD = """
import json, sys
sys.path.insert(0, {tests!r})
from test_p2_gridder import _case, _digest, SETTINGS
from rangtoy import core_grid
products = core_grid.invert(*_case(), **SETTINGS)
print(json.dumps(_digest(products) + [products["stats"]]))
"""


def test_images_identical_across_thread_counts():
    results = []
    for threads in (1, 4):
        env = dict(os.environ, RAYON_NUM_THREADS=str(threads))
        out = subprocess.run(
            [sys.executable, "-c", _CHILD.format(tests=str(Path(__file__).parent))],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        results.append(json.loads(out.stdout.strip().splitlines()[-1]))
    assert results[0] == results[1]


def test_flagged_cells_do_not_change_the_images():
    uvw, frequencies, data, weights, imaging = _case()
    products = core_grid.invert(uvw, frequencies, data, weights, imaging, **SETTINGS)
    other = data.copy()
    other[weights == 0] = np.complex64(3.0 - 2.0j)
    again = core_grid.invert(uvw, frequencies, other, weights, imaging, **SETTINGS)
    np.testing.assert_array_equal(products["dirty"], again["dirty"])
    np.testing.assert_array_equal(products["psf"], again["psf"])
    assert products["stats"] == again["stats"]
    height, width = products["psf"].shape
    assert products["psf"][height // 2, width // 2] == 1.0
    peak = np.unravel_index(np.argmax(products["dirty"]), products["dirty"].shape)
    assert peak == (height // 2 - 4, width // 2 - 7)
