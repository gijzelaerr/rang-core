"""Shared test setup: thread caps and the pointing reference fixtures.

The caps keep one pytest process from oversubscribing a shared host
(research/p10-tests.md): with NumPy/SciPy's OpenBLAS and XLA's CPU pools at
their defaults a full run held 145 threads and spent 7-9 cores spinning.
They are defaults; an explicit environment setting wins. They must be set
before NumPy, SciPy or JAX create their pools: no installed pytest plugin
imports them, and pytest imports this file before any test module.
"""

import json
import os
import subprocess

import pytest

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")
if "XLA_FLAGS" not in os.environ:
    os.environ["XLA_FLAGS"] = (
        "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1"
    )


def _pointing_reference(flag):
    """Rust reference rows as (parsed JSON, components, Observation)."""
    jax = pytest.importorskip("jax")
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp
    import numpy as np
    from rangtoy import build
    from rangtoy.pointing import Observation, component_list

    reference = json.loads(subprocess.check_output([str(build()), flag]))
    rows = np.asarray(reference["rows"])
    sky = np.asarray(reference["sources"])
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    components = component_list(sky[:, 0], sky[:, 1], sky[:, 2], sky[:, 3])
    return reference, components, obs


@pytest.fixture(scope="session")
def pointing_reference():
    """Thinned (every fifth row) four-source reference, built once."""
    return _pointing_reference("--pointing-reference")


@pytest.fixture(scope="session")
def pointing_full_reference():
    """Complete-coverage reference (24 x 4 x 28 rows), built once."""
    return _pointing_reference("--pointing-full-reference")
