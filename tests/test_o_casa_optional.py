"""O-CASA oracle (research/o-casa.md): host helpers offline, the image optionally.

The comparison helpers of `tools/oracles/casa/compare.py` are checked on
synthetic diagonal gains (always). The image checks skip when docker or
the `rang-o-casa:6.7.6.14` image is absent; the archive check skips when
the archive is not present.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "rang-o-casa:6.7.6.14"
ARCHIVE = ROOT / "research/results/o-casa-crosscal.json"


def _compare():
    spec = importlib.util.spec_from_file_location(
        "o_casa_compare", ROOT / "tools/oracles/casa/compare.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic(seed=3, nrow=6, nchan=8):
    rng = np.random.default_rng(seed)
    gains = rng.normal(1, 0.1, (4, nchan, 2)) * np.exp(
        1j * rng.normal(0, 0.3, (4, nchan, 2))
    )
    a1 = np.array([0, 0, 0, 1, 1, 2])[:nrow]
    a2 = np.array([1, 2, 3, 2, 3, 3])[:nrow]
    model = np.zeros((nrow, nchan, 4), complex)
    model[..., 0] = model[..., 3] = 15.0
    hands = ((0, 0), (0, 1), (1, 0), (1, 1))
    product = np.stack(
        [gains[a1, :, i] * np.conj(gains[a2, :, j]) for i, j in hands], axis=-1
    )
    data = product * model + 0.01
    return gains, a1, a2, model, product, data


def test_applied_products_are_exact_for_diagonal_gains():
    compare = _compare()
    _, _, _, _, product, data = _synthetic()
    corrected = data / product
    export = {
        "DATA": data,
        "CORRECTED_DATA": corrected,
        "FLAG": np.zeros(data.shape, bool),
    }
    recovered, ok = compare.casa_products(export)
    assert ok.all()
    np.testing.assert_allclose(recovered, product, rtol=1e-12)


def test_flagged_or_zero_corrected_cells_are_unavailable():
    compare = _compare()
    _, _, _, _, product, data = _synthetic()
    corrected = data / product
    flag = np.zeros(data.shape, bool)
    flag[0, 0, 0] = True
    corrected[1, 1, 3] = 0
    _, ok = compare.casa_products(
        {"DATA": data, "CORRECTED_DATA": corrected, "FLAG": flag}
    )
    assert not ok[0, 0, 0] and not ok[1, 1, 3]
    assert ok.sum() == ok.size - 2


def test_mse_is_the_campaign_definition_and_counts_unavailable_cells():
    compare = _compare()
    _, _, _, model, product, data = _synthetic()
    weights = np.full(data.shape, 2.0)
    cells = np.ones(data.shape[:2], bool)
    ok = np.ones(data.shape[:2], bool)
    ok[0, 0] = False
    value, used, unavailable = compare.mse(data, product * model, weights, cells, ok)
    # Residual is the constant 0.01 on every correlation: w|r|^2 = 2e-4.
    assert value == pytest.approx(2e-4)
    assert used == cells.size - 1 and unavailable == 1


def test_product_comparison_is_gauge_free():
    compare = _compare()
    gains, a1, a2, _, product, _ = _synthetic()
    phase = np.exp(1j * 0.7)
    rotated = np.stack(
        [
            (gains[a1, :, i] * phase) * np.conj(gains[a2, :, j] * phase)
            for i, j in ((0, 0), (0, 1), (1, 0), (1, 1))
        ],
        axis=-1,
    )
    ok = np.ones(product.shape, bool)
    stats = compare.compare_products(
        product, ok, rotated, np.ones(product.shape[:2], bool), a1, a2
    )
    for corr in ("XX", "YY"):
        assert stats[corr]["amp_rel_diff_p95"] < 1e-12
        assert stats[corr]["phase_diff_deg_p95"] < 1e-9


def test_archive_is_small_and_complete():
    if not ARCHIVE.is_file():
        pytest.skip("archive not present")
    assert ARCHIVE.stat().st_size < 200_000
    archive = json.loads(ARCHIVE.read_text())
    for key in ("image", "runs", "reproducible", "arms", "comparison", "flagdata"):
        assert key in archive
    assert archive["reproducible"]["identical"] is True


def _image_present():
    if shutil.which("docker") is None:
        return False
    found = subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
    )
    return found.returncode == 0


@pytest.mark.skipif(not _image_present(), reason="docker or the O-CASA image absent")
def test_image_tools_and_versions():
    script = (
        "wsclean --version | grep WSClean; aoflagger --version; "
        "python3 -c 'import casacore; print(casacore.__version__)'; "
        "/opt/casa/bin/python -I -c 'import casatools; print(casatools.version_string())' "
        "2>/dev/null | tail -1"
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--tmpfs",
            "/tmp",
            "-e",
            "HOME=/tmp",
            "-w",
            "/tmp",
            IMAGE,
            "bash",
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    )
    out = result.stdout
    assert "WSClean version 3.7" in out
    assert "AOFlagger 3.5" in out
    assert "3.7.1" in out
    assert "6.7.6-14" in out
