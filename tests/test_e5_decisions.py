"""Owner decisions and proposed fixes on the E5 pre-review (research/e5-prereview.md)."""

import hashlib
import json
from pathlib import Path

import pytest
import rang

DATA = Path(rang.__file__).with_name("data")


def test_the_observatory_table_has_its_source_and_hash():
    """E5-34: the shipped casacore observatory table names its source and the
    SHA256 of the file that ships."""
    table = DATA / "casacore_observatories.json"
    readme = (DATA / "README.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(table.read_bytes()).hexdigest()
    assert digest in readme
    source = json.loads(table.read_text(encoding="utf-8"))["source"]
    assert source.startswith("casacore-data 20250826-160001-5")
    assert "casacore-data 20250826-160001-5" in readme
    assert "licence was not checked" in readme


def test_a_run_without_run_stages_runs_the_whole_chain(tmp_path, monkeypatch):
    """E5-28 (owner: "All six stages"): with no `run.stages`, `rang-core run`
    runs flag, calibrate, apply, image and selfcal, so it never images
    uncalibrated DATA."""
    from rang import core_ms_write

    if not core_ms_write.has_creator():
        pytest.skip("extension built without the table writer")
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    import test_w2_commands as w2

    ms = w2.make_ms(tmp_path / "x.ms")
    config = w2.write_config(tmp_path)
    assert "run:" not in config.read_text(encoding="utf-8")
    state = w2.cli("run", config, ms)
    assert list(state["stages"]) == ["flag", "calibrate", "apply", "image", "selfcal"]
    assert {e["status"] for e in state["stages"].values()} == {"done"}
