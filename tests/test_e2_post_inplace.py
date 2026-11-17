"""E2-A's in-place gate 2b order in e2_post.py (research/e2-acceptance.md 9.9):
the plan picks rang's apply output and flag versions from the run directory,
the prep script renames and resets flags without a copy (run here against a
casacore stand-in, since python-casacore lives in the oracle container), and
the CASA steps mount the leg's MS itself."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1] / "research/results/e2-acceptance-scripts"
spec = importlib.util.spec_from_file_location("e2_post", HERE / "e2_post.py")
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)


def make_run(tmp_path, selfcal=True, marker_from="CORRECTED_DATA"):
    ms = tmp_path / "e2a.ms"
    ms.mkdir()
    rd = Path(str(ms) + ".rang-run")
    (rd / "apply").mkdir(parents=True)
    stages = {"apply": {"status": "done", "finished": "T-apply"}}
    if selfcal:
        stages["selfcal"] = {"status": "done", "flag_version": "rang_selfcal_X"}
        (rd / "selfcal-input.json").write_text(json.dumps(
            {"column": "CORRECTED_1GC", "copied_from": marker_from, "apply_finished": "T-apply"}))  # fmt: skip
    (rd / "state.json").write_text(json.dumps({"stages": stages}))
    summary = {
        "column": "CORRECTED_DATA",
        "flag_version": "rang_apply_Y",
        "applied": [],
    }
    (rd / "apply" / "summary.json").write_text(json.dumps(summary))
    return ms


def test_plan_with_selfcal_uses_the_1gc_copy(tmp_path):
    plan = post.inplace_plan(make_run(tmp_path))
    assert plan == {"rang_column": "CORRECTED_1GC", "rang_flag_version": "rang_selfcal_X",
                    "flag_before_apply": "rang_apply_Y", "applycal_writes": "CORRECTED_DATA"}  # fmt: skip


def test_plan_without_selfcal_uses_corrected_data(tmp_path):
    plan = post.inplace_plan(make_run(tmp_path, selfcal=False))
    assert plan["rang_column"] == "CORRECTED_DATA"
    assert plan["rang_flag_version"] is None


def test_plan_refuses_a_stale_copy(tmp_path):
    with pytest.raises(SystemExit):
        post.inplace_plan(make_run(tmp_path, marker_from="MODEL_DATA"))


def test_order_has_no_copy_and_reads_come_first():
    order = post.ORDER_INPLACE
    assert "copy" not in order and all(s in post.STEPS for s in order)
    prep = order.index("prep-inplace")
    for read in ("casacore", "casa-ro", "wsclean0", "daskms"):
        assert order.index(read) < prep
    assert prep < order.index("applycal-inplace") < order.index("compare-inplace")
    assert (
        order.index("compare-inplace")
        < order.index("restore")
        < order.index("tricolour")
    )


def test_casa_steps_mount_the_ms_itself(tmp_path, monkeypatch):
    ms = make_run(tmp_path)
    r = tmp_path / "R"
    (r / "rang-run" / "apply").mkdir(parents=True)
    (r / "rang-run" / "apply" / "summary.json").write_text(json.dumps({"applied": []}))
    (r / "applycal-result.json").write_text("[]")
    seen = []
    monkeypatch.setattr(post, "docker", lambda r_, image, mounts, script, label, threads=8:
                        seen.append((label, mounts)) or 1)  # fmt: skip
    post.applycal_inplace(ms, r)
    post.compare_inplace(ms, r)
    post.snapshot_inplace(ms, r)
    for label, mounts in seen:
        assert mounts[0] == (ms.parent, "/c"), label
        assert all(m[0] != r / "casa" for m in mounts), label


# --- the prep script against a casacore stand-in ---------------------------------

N, NCHAN = 10, 3


class FakeTable:
    def __init__(self, cols):
        self.cols = cols

    def colnames(self):
        return list(self.cols)

    def nrows(self):
        return len(next(iter(self.cols.values())))

    def renamecol(self, a, b):
        self.cols[b] = self.cols.pop(a)

    def getdminfo(self, c):
        return {"NAME": "x", "SPEC": {"HYPERCUBES": {}}}

    def getcoldesc(self, c):
        return {"c": c}

    def addcols(self, desc, dm):
        self.cols[desc["name"]] = np.zeros_like(self.cols["FLAG"])

    def getcol(self, c, r0=0, k=None):
        v = self.cols[c]
        return v.copy() if k is None else v[r0 : r0 + k].copy()

    def putcol(self, c, v, r0=0, k=None):
        if k is None:
            self.cols[c] = v
        else:
            self.cols[c][r0 : r0 + k] = v

    def close(self):
        pass


def run_prep(tmp_path, monkeypatch, angle_deg=-90.0, plan=None):
    rng = np.random.default_rng(1)
    flags = {name: rng.random((N, NCHAN, 4)) < 0.3 for name in ("now", "sc", "before")}
    main = FakeTable({
        "DATA": np.ones((N, NCHAN, 4), np.complex64),
        "CORRECTED_1GC": np.full((N, NCHAN, 4), 2, np.complex64),
        "CORRECTED_DATA": np.full((N, NCHAN, 4), 3, np.complex64),
        "MODEL_DATA": np.ones((N, NCHAN, 4), np.complex64),
        "FLAG": flags["now"].copy(), "FLAG_ROW": np.zeros(N, bool)})  # fmt: skip
    ms = "MS"
    reg = {
        ms: main,
        ms + "/FEED": FakeTable({"RECEPTOR_ANGLE": np.full((2, 2), np.deg2rad(angle_deg))}),
        ms + ".flagversions/flags.rang_selfcal_X": FakeTable(
            {"FLAG": flags["sc"], "FLAG_ROW": np.zeros(N, bool)}),
        ms + ".flagversions/flags.rang_apply_Y": FakeTable(
            {"FLAG": flags["before"], "FLAG_ROW": np.ones(N, bool)}),
    }  # fmt: skip
    mod = types.ModuleType("casacore.tables")
    mod.table = lambda path, readonly=True, ack=False: reg[path]
    mod.makecoldesc = lambda name, desc: {"name": name}
    monkeypatch.setitem(sys.modules, "casacore", types.ModuleType("casacore"))
    monkeypatch.setitem(sys.modules, "casacore.tables", mod)
    plan = plan or {"rang_column": "CORRECTED_1GC", "rang_flag_version": "rang_selfcal_X",
                    "flag_before_apply": "rang_apply_Y", "applycal_writes": "CORRECTED_DATA"}  # fmt: skip
    pp, out = tmp_path / "plan.json", tmp_path / "out.json"
    pp.write_text(json.dumps(plan))
    monkeypatch.setattr(sys, "argv", ["prep", ms, str(pp), str(out)])
    code = compile(post.PREP_INPLACE_PY, "prep_inplace", "exec")
    exec(code, {"__name__": "__main__"})  # noqa: S102 - the script under test
    return main, flags, json.loads(out.read_text())


def test_prep_renames_and_resets_flags(tmp_path, monkeypatch):
    t, flags, rec = run_prep(tmp_path, monkeypatch)
    cols = set(t.colnames())
    assert {
        "RANG_CORRECTED_DATA",
        "RANG_MODEL_DATA",
        "RANG_FLAG",
        "CORRECTED_DATA",
    } <= cols
    assert "CORRECTED_1GC" not in cols and "MODEL_DATA" not in cols
    assert (
        t.cols["RANG_CORRECTED_DATA"] == 2
    ).all()  # the 1GC copy, not selfcal's output
    assert (t.cols["RANG_FLAG"] == flags["sc"]).all()  # FLAG after apply
    assert (t.cols["FLAG"] == flags["before"]).all() and t.cols["FLAG_ROW"].all()
    assert rec["rows"] == N


def test_prep_without_selfcal_keeps_flag_as_rang_flag(tmp_path, monkeypatch):
    plan = {"rang_column": "CORRECTED_DATA", "rang_flag_version": None,
            "flag_before_apply": "rang_apply_Y", "applycal_writes": "CORRECTED_DATA"}  # fmt: skip
    t, flags, _ = run_prep(tmp_path, monkeypatch, plan=plan)
    assert (t.cols["RANG_CORRECTED_DATA"] == 3).all()
    assert (t.cols["RANG_FLAG"] == flags["now"]).all()


def test_prep_refuses_another_receptor_angle(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        run_prep(tmp_path, monkeypatch, angle_deg=0.0)
