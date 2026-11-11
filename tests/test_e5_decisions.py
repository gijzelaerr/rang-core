"""Owner decisions and proposed fixes on the E5 pre-review (research/e5-prereview.md)."""

import hashlib
import json
from pathlib import Path

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
