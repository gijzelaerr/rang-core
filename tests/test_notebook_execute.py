"""Execute the tutorial notebooks end to end with nbconvert.

All runs start together (one kernel process each) so the module stays near
the slowest notebook's time. The fixture runs switch LUNO sections off
(`RANG_NOTEBOOK_LUNO=0`), which exercises their skip path; one extra run of
notebook 01 with LUNO on is skipped without the local slice. Everything is
skipped without the fixture or the notebook extra.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")
pytest.importorskip("nbconvert")
pytest.importorskip("ipykernel")
pytest.importorskip("matplotlib")
pytest.importorskip("pandas")

from rangtoy.notebook import data

ROOT = Path(__file__).resolve().parents[1]
BOOKS = sorted(p.name for p in (ROOT / "notebooks").glob("*.ipynb"))
LUNO_BOOK = "01-data-and-rank.ipynb"


def _execute(name, env):
    from jupyter_client.manager import KernelManager
    from nbconvert.preprocessors import ExecutePreprocessor

    book = nbformat.read(ROOT / "notebooks" / name, as_version=4)
    manager = KernelManager(kernel_name="python3")
    manager.start_kernel(env={**os.environ, **env}, cwd=str(ROOT / "notebooks"))
    try:
        ExecutePreprocessor(timeout=300).preprocess(
            book, {"metadata": {"path": str(ROOT / "notebooks")}}, km=manager
        )
    finally:
        manager.shutdown_kernel(now=True)
    return book


def _text(book):
    return "".join(
        "".join(o.get("text", "")) + str(o.get("data", {}).get("text/plain", ""))
        for c in book.cells
        if c.cell_type == "code"
        for o in c.outputs
    )


@pytest.fixture(scope="module")
def executed(tmp_path_factory):
    if data.find_fixture() is None:
        pytest.skip("fixture archive not present")
    cache = tmp_path_factory.mktemp("notebook-cache")
    # Extract once before the kernels start, so they do not race on the cache.
    data.extract_fixture(data.find_fixture(), cache)
    base = {
        "RANG_NOTEBOOK_CACHE": str(cache),
        "MPLBACKEND": "Agg",
        "RAYON_NUM_THREADS": os.environ.get("RAYON_NUM_THREADS", "2"),
    }
    jobs = {name: {**base, "RANG_NOTEBOOK_LUNO": "0"} for name in BOOKS}
    if data.find_luno_slice() is not None:
        jobs["luno:" + LUNO_BOOK] = {**base, "RANG_NOTEBOOK_LUNO": "1"}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {
            key: pool.submit(_execute, key.removeprefix("luno:"), env)
            for key, env in jobs.items()
        }
    results = {}
    for key, future in futures.items():
        try:
            results[key] = future.result()
        except Exception as exc:  # noqa: BLE001 - reported by the test
            results[key] = exc
    return results


@pytest.mark.parametrize("name", BOOKS)
def test_notebook_runs_on_the_fixture(name, executed):
    book = executed[name]
    if isinstance(book, Exception):
        raise book
    assert "LUNO slice available: False" in _text(book)


def test_luno_sections(executed):
    key = "luno:" + LUNO_BOOK
    if key not in executed:
        pytest.skip("local LUNO slice not present")
    book = executed[key]
    if isinstance(book, Exception):
        raise book
    text = _text(book)
    assert "LUNO slice available: True" in text
    assert "skipped: no local LUNO slice" not in text
