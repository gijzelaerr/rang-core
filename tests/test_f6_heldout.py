"""F6's scorer wrapper: SARAO sets respect the manifest's split (research/f6-flagger.md 2d)."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _wrapper():
    spec = importlib.util.spec_from_file_location(
        "f6_heldout", ROOT / "examples" / "f6_heldout.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _manifest(tmp_path):
    entries = [
        {"cbid": "1", "scan": "3", "split": "train", "class": "calibrator", "ms": "x"},
        {"cbid": "2", "scan": "5", "split": "validation", "class": "target", "ms": "x"},
        {"cbid": "3", "scan": "7", "split": "heldout", "class": "target", "ms": "x"},
    ]
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "stage1.json").write_text(
        json.dumps({"entries": entries})
    )


def test_split_guard(tmp_path):
    w = _wrapper()
    _manifest(tmp_path)
    w.SARAO_ROOT = str(tmp_path)
    with pytest.raises(PermissionError, match="training"):
        w.load_sarao_set("sarao:1:3", heldout=False)
    with pytest.raises(PermissionError, match="held out"):
        w.load_sarao_set("sarao:3:7", heldout=True)
    with pytest.raises(PermissionError, match="validation"):
        w.load_sarao_set("sarao:2:5", heldout=True)
    with pytest.raises(KeyError):
        w.load_sarao_set("sarao:9:9", heldout=False)
    assert w.sarao_entry(str(tmp_path), "3", "007")["split"] == "heldout"


def test_reserved_eso_guard(monkeypatch):
    w = _wrapper()
    monkeypatch.setattr(w.f3, "read_eso", lambda chunk: {"chunk": chunk})
    w.HELDOUT_READ = False
    with pytest.raises(PermissionError, match="held out"):
        w.load_eso_set("eso:1", heldout=True)
    with pytest.raises(PermissionError, match="held out"):
        w.load_eso_set("eso:17", heldout=False)
    assert w.load_eso_set("eso:10", heldout=False) is None  # F4's guard decides
    w.HELDOUT_READ = True
    with pytest.raises(PermissionError, match="held out"):
        w.load_eso_set("eso:3", heldout=False)
    assert w.load_eso_set("eso:15", heldout=True) == {"chunk": 15}
