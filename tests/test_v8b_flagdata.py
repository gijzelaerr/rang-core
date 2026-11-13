"""V8b flagdata (research/v8b-flagdata.md): the CASA keyword layer's
refusals, the selection parsers, and rang's flags on the synthetic MSs
against the archive of CASA 6.7.6.14's flags on the same MSs
(`research/results/v8b-flagdata-casa-synthetic.json`), so CI checks parity
without CASA."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms, core_ms_write, flagdata, tasks
from rang.core_cli import dispatch

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cases = _load("v8b_cases", ROOT / "tools/oracles/casa/v8b_cases.py")
plan = _load("v8b_plan", ROOT / "tools/oracles/casa/v8b_plan.py")
ARCHIVE = ROOT / "research/results/v8b-flagdata-casa-synthetic.json"

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("v8b")
    cases.build_edges(out / "syn-edges.ms")
    cases.build_tfcrop(out / "syn-rfi.ms", rfi=True)
    cases.build_tfcrop(out / "syn-noise.ms", rfi=False)
    return out


def _copy(src, dst):
    import shutil

    shutil.copytree(src, dst)
    return dst


def _flag_sha(ms):
    with core_ms.open_table(ms) as t:
        flag = np.asarray(t.getcol("FLAG"), bool)
        row = np.asarray(t.getcol("FLAG_ROW"), bool)
    return (hashlib.sha256(np.packbits(flag.reshape(-1)).tobytes()).hexdigest(),
            hashlib.sha256(np.packbits(row).tobytes()).hexdigest())  # fmt: skip


@pytest.mark.parametrize(
    "kw",
    [
        {"mode": "rflag"},
        {"mode": "antint"},
        {"mode": "manual", "intent": "*CALIBRATE*"},
        {"mode": "shadow", "addantenna": "ants.txt"},
        {"mode": "clip", "channelavg": True},
        {"mode": "manual", "action": "calculate"},
        {"mode": "manual", "savepars": True},
        {"mode": "tfcrop", "datacolumn": "FLOAT_DATA"},
        {"mode": "tfcrop", "usewindowstats": "maybe"},
        {"mode": "quack", "quackmode": "middle"},
        {"mode": "manual", "uvrange": "<10klambda"},
        {"mode": "manual", "spw": "0:0~10^2"},
    ],
)
def test_refused_before_any_write(built, tmp_path, kw):
    ms = _copy(built / "syn-edges.ms", tmp_path / "e.ms")
    before = _flag_sha(ms)
    with pytest.raises((tasks.Unsupported, flagdata.SelectionError)):
        tasks.flagdata(vis=str(ms), flagbackup=False, **kw)
    assert _flag_sha(ms) == before


def test_parsers(built):
    meta = flagdata.read_meta(built / "syn-edges.ms")
    t0 = cases.T0 + 3 * 3600.0
    assert flagdata._parse_time("2026/01/01/03:00:40", t0) == t0 + 40
    assert flagdata._parse_time("03:01:20.5", t0) == t0 + 80.5
    assert flagdata.parse_ntime("60s") == 60.0
    assert flagdata.parse_ntime("1.5min") == 90.0
    spw = flagdata.select_spw(meta, "0:0~9;20~29,1:3")
    assert spw[0].sum() == 20 and spw[1].sum() == 1
    op, corr = flagdata.parse_correlation(meta, "ABS_XX,YY", "clip")
    assert op == "ABS" and corr.tolist() == [True, False, False, True]
    bl = flagdata.select_baselines(meta, "m001&m002")
    a1, a2 = meta.main["ANTENNA1"][bl], meta.main["ANTENNA2"][bl]
    assert set(zip(a1.tolist(), a2.tolist())) == {(1, 2)}


def test_command_line_summary(built, capsys):
    record = dispatch(["flagdata", str(built / "syn-edges.ms"), "mode=summary"])
    assert record["total"] > record["flagged"] > 0
    assert json.loads(capsys.readouterr().out)["total"] == record["total"]


def _archive():
    if not ARCHIVE.exists():
        pytest.skip("no CASA archive yet")
    return json.loads(ARCHIVE.read_text(encoding="utf-8"))


def _gated(arch):
    return [name for name, v in arch["cases"].items() if v.get("gate") == "exact"]


@pytest.mark.parametrize("name", _gated(json.loads(ARCHIVE.read_text(encoding="utf-8")))
                         if ARCHIVE.exists() else [])  # fmt: skip
def test_matches_casa_archive(built, tmp_path, name):
    """rang's FLAG and FLAG_ROW on a synthetic case hash to CASA's, and
    every count of CASA's summaries is rang's."""
    arch = _archive()
    entry = arch["cases"][name]
    case = name.split(".", 1)[0]
    calls = next(c for c in plan.dev_plan() if c["name"] == name)["calls"]
    ms = _copy(built / f"{case}.ms", tmp_path / f"{case}.ms")
    returns = [tasks.flagdata(vis=str(ms), flagbackup=False, **p) for p in calls]
    assert list(_flag_sha(ms)) == entry["sha256"]
    for k, want in entry.get("summaries", {}).items():
        got = returns[int(k)]
        for group, values in want.items():
            if isinstance(values, dict):
                for key, counts in values.items():
                    assert got[group][key]["total"] == counts["total"], (group, key)
                    assert got[group][key]["flagged"] == counts["flagged"], (group, key)
            elif group in ("total", "flagged"):
                assert got[group] == values, group


def test_a_refused_call_leaves_the_ms_writable(built, tmp_path):
    """A selection CASA rejects (no rows) is refused before the write-back
    session opens, so the next call on the same MS runs."""
    ms = _copy(built / "syn-edges.ms", tmp_path / "e.ms")
    with pytest.raises(flagdata.SelectionError):
        tasks.flagdata(vis=str(ms), mode="manual", uvrange="1~3km", flagbackup=False)
    got = tasks.flagdata(vis=str(ms), mode="manual", scan="2", flagbackup=False)
    assert got["flagged_after"] > got["flagged_before"]
