"""Reader safety and layout diagnostics do not require optional casacore."""

import importlib.util
import json
from pathlib import Path
from zipfile import ZipInfo

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "ms_reader",
    Path(__file__).resolve().parents[1] / "examples/inspect_measurement_sets.py",
)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "a\\b"])
def test_unsafe_archive_paths(name):
    with pytest.raises(ValueError, match="unsafe"):
        info = ZipInfo("x")
        info.filename = name  # ZipInfo(name) turns a backslash into "/" on Windows
        reader.validate_members([info])


def test_archive_limits_links_and_duplicate_targets():
    reader.validate_members([ZipInfo("safe/"), ZipInfo("safe/data")])
    member = ZipInfo("data")
    with pytest.raises(ValueError, match="unsafe"):
        reader.validate_members([member, member])
    member.external_attr = 0o120777 << 16
    with pytest.raises(ValueError, match="unsafe"):
        reader.validate_members([member])
    member.external_attr = 0
    member.file_size = 200_000_001
    with pytest.raises(ValueError, match="200 MB"):
        reader.validate_members([member])


def test_pointing_layout_does_not_invent_antenna_labels():
    layout = reader.pointing_layout(np.repeat([1, 2, 3], 4), np.zeros(12), 4)
    assert layout["time_major_rectangular"]
    assert not layout["antenna_major_rectangular"]
    assert not layout["complete_antenna_labels"]
    layout = reader.pointing_layout(np.tile([1, 2, 3], 4), np.repeat(range(4), 3), 4)
    assert layout["antenna_major_rectangular"]
    assert layout["complete_antenna_labels"]


def test_numpy_metadata_serialization():
    value = {"units": np.array(["rad", "rad"]), "rows": np.int64(4)}
    assert json.loads(json.dumps(value, default=reader.json_default)) == {
        "units": ["rad", "rad"],
        "rows": 4,
    }
