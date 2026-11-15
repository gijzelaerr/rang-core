"""E2-A's reads of rang's columns after gate 2b in e2_post.py (research/
e2-acceptance.md 9.10): gate 3c's WSClean command from the image stage's
argv, the self-calibration row's averaged QuartiCal inputs (layout, sums,
apply flags, the whole qc-avg step on stand-ins for rang's reader and
predictor), the class B measure, the order and the guards. Nothing here
runs a container or reads a real MS."""

import importlib.util
import json
import os
import shutil
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/results/e2-acceptance-scripts"
spec = importlib.util.spec_from_file_location("e2_post_reads", HERE / "e2_post.py")
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)
ARCHIVED = ROOT / "research/results/e2-acceptance/e2a-interrupted"


# --- the order and the guards -----------------------------------------------------


def test_order_puts_the_reads_after_2b_and_before_restore():
    o = post.ORDER_INPLACE
    assert all(s in post.STEPS for s in o) and len(set(o)) == len(o)
    at = o.index
    assert at("prep-inplace") < at("compare-inplace") < at("snapshot-inplace")
    assert at("snapshot-inplace") < at("drop-corrected-inplace") < at("qc-avg")
    assert at("qc-avg") < at("qc-selfcal") < at("unit-on-a")
    assert at("unit-on-a") < at("wsclean3c-a-dirty") < at("wsclean3c-a-clean")
    assert at("wsclean3c-a-clean") < at("score3c-a") < at("wsclean3c-a-nosi-dirty")
    assert at("wsclean3c-a-nosi-dirty") < at("score3c-a-nosi") < at("unit-off-a")
    assert at("unit-off-a") < at("restore") < at("tricolour")
    assert "wsclean3c" not in o and "copy" not in o  # E2-B's IQUV oracle and copy


def fake_colnames(monkeypatch, cols):
    from rang import core_ms

    class T:
        nrows = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def colnames(self):
            return list(cols)

    monkeypatch.setattr(core_ms, "open_table", lambda path: T())


def test_restore_refuses_the_matched_state(tmp_path, monkeypatch):
    from rang import core_writeback

    fake_colnames(monkeypatch, ["DATA", "FLAG", "E2_CASA_FLAG", "E2_WEIGHT", "WEIGHT"])
    monkeypatch.setattr(core_writeback, "restore_flags",
                        lambda *a: pytest.fail("restore wrote FLAG in the matched state"))  # fmt: skip
    with pytest.raises(SystemExit, match="unit-off-a"):
        post.restore(tmp_path / "e2a.ms", tmp_path, tmp_path / "input.json")


def test_wsclean_refuses_outside_the_matched_state(tmp_path, monkeypatch):
    fake_colnames(monkeypatch, ["DATA", "FLAG", "RANG_FLAG", "RANG_CORRECTED_DATA"])
    with pytest.raises(SystemExit, match="unit-on-a"):
        post.wsclean3c_a_dirty(tmp_path / "e2a.ms", tmp_path)


def test_drop_needs_compare_and_snapshot(tmp_path, monkeypatch):
    ms, r = tmp_path / "e2a.ms", tmp_path / "R"
    ms.mkdir()
    r.mkdir()
    seen = []
    monkeypatch.setattr(post, "docker", lambda r_, image, mounts, script, label, threads=8:
                        seen.append((label, mounts, script)) or 0)  # fmt: skip
    with pytest.raises(SystemExit):
        post.drop_corrected_inplace(ms, r)
    (r / "df-flag-snapshot").mkdir()
    (r / "df-flag-snapshot" / "flags-after-applycal.npz").write_bytes(b"")
    for failed in ({"compare_exit": 1, "compared_cells": 0, "applycal_errors": []},
                   {"compare_exit": 0, "compared_cells": 5, "applycal_errors": [{"field": "x"}]},
                   {"compare_exit": 0, "compared_cells": 0, "applycal_errors": []}):  # fmt: skip
        (r / "g2b-applycal.json").write_text(json.dumps(failed))
        with pytest.raises(SystemExit, match="did not complete"):
            post.drop_corrected_inplace(ms, r)
    assert not seen
    (r / "g2b-applycal.json").write_text(
        json.dumps({"compare_exit": 0, "compared_cells": 5, "applycal_errors": []})
    )
    assert post.drop_corrected_inplace(ms, r) == 0
    ((_label, mounts, script),) = seen
    assert mounts[0] == (ms.parent, "/c") and "/c/e2a.ms" in script
    rec = json.loads((r / "drop-corrected-run.json").read_text())
    assert {"free_gib_before", "free_gib_after"} <= set(rec)


def test_docker_mounts_wsl_ext4_without_double_quotes(tmp_path, monkeypatch):
    got = []

    class Done:
        returncode = 0

    monkeypatch.setattr(
        post.subprocess, "run", lambda argv, **kw: got.append(argv) or Done()
    )
    post.docker(
        tmp_path, "img", [(tmp_path, "/p"), ("$HOME/e2a-qc", "/q")], "true", "x", 1
    )
    inner = got[0][-1]
    assert inner.startswith("mkdir -p $HOME/e2a-qc && docker run")
    assert "-v $HOME/e2a-qc:/q:rw" in inner and '"' not in inner


# --- gate 3c: the WSClean command ---------------------------------------------------


def image_argv():
    s = json.loads((ARCHIVED / "image" / "summary.json").read_text(encoding="utf-8"))
    (entry,) = s["images"]
    return entry["argv"]


def test_wsclean_argv_keeps_the_image_stage_settings():
    # the frozen settings as the interrupted run's image stage ran them
    gem = image_argv()
    argv, dropped = post.wsclean_argv(
        gem, name="/p/w/ESO137m001-clean", column="RANG_CORRECTED_DATA", threads=4,
        temp="/p/w/tmp", ms_inside="/c/e2a.ms", dirty=False)  # fmt: skip
    assert argv[0] == "wsclean" and argv[-1] == "/c/e2a.ms"

    def value(a, flag, n=1):
        i = a.index(flag)
        return a[i + 1 : i + 1 + n]

    for flag, n in (("-size", 2), ("-scale", 1), ("-weight", 2), ("-niter", 1),
                    ("-mgain", 1), ("-auto-threshold", 1), ("-auto-mask", 1),
                    ("-wgridder-accuracy", 1), ("-channels-out", 1), ("-fit-spectral-pol", 1),
                    ("-field", 1)):  # fmt: skip
        assert value(argv, flag, n) == value(gem, flag, n), flag
    for flag in ("-multiscale", "-join-channels", "-no-update-model-required"):
        assert flag in argv
    assert value(argv, "-data-column") == ["RANG_CORRECTED_DATA"]
    assert value(argv, "-j") == ["4"] and value(argv, "-gridder") == ["wgridder"]
    assert value(argv, "-name") == ["/p/w/ESO137m001-clean"]
    for flag in ("-average-channels", "-scans", "-unit-weights", "-no-small-inversion"):
        assert flag not in argv
    assert dropped["-average-channels"] == ["8"] and dropped["-unit-weights"] is True
    assert dropped["-data-column"] == ["CORRECTED_DATA"]
    assert argv.count("-name") == 1 and gem[-1] not in argv


def test_wsclean_argv_dirty_and_nosi():
    argv, _ = post.wsclean_argv(image_argv(), name="n", column="C", threads=2, temp="t",
                                ms_inside="/c/m", dirty=True, nosi=True)  # fmt: skip
    assert argv[argv.index("-niter") + 1] == "0"
    assert argv[-2] == "-no-small-inversion"


# --- the self-calibration row: layout, sums, flags, products ------------------------


def small_meta(seed=0, nant=4, ntime=(7, 5), autos=True):
    """Two scans of rows in time order, baselines in a fixed order, a gap."""
    rng = np.random.default_rng(seed)
    t, s, a1, a2 = [], [], [], []
    t0 = 100.0
    for scan, n in zip((3, 5), ntime):
        for k in range(n):
            for p in range(nant):
                for q in range(p if autos else p + 1, nant):
                    if rng.random() < 0.05 and p != q:
                        continue  # a missing row
                    t.append(t0 + 8.0 * k)
                    s.append(scan)
                    a1.append(p)
                    a2.append(q)
        t0 += 1000.0
    return np.array(t), np.array(s), np.array(a1), np.array(a2)


@pytest.mark.parametrize("n", [0, 1, 3])
def test_layout_bins_are_rangs_time_bins(n):
    from rang import cal_selfcal

    time, scan, a1, a2 = small_meta()
    lay = post.qc_layout(time, scan, a1, a2, n)
    tb, bin_scan, gain_time = cal_selfcal.time_bins(time, scan, np.zeros_like(scan),
                                                    n if n else "inf")  # fmt: skip
    assert np.array_equal(lay["bin"], tb)
    assert np.array_equal(lay["bin_scan"], bin_scan)
    assert np.array_equal(lay["bin_time"], gain_time)


def test_layout_rows():
    time, scan, a1, a2 = small_meta()
    lay = post.qc_layout(time, scan, a1, a2, 3)
    out = lay["out"]
    assert (out[a1 == a2] == -1).all() and (out[a1 != a2] >= 0).all()
    assert np.array_equal(np.sort(lay["template"]), lay["template"])  # first-row order
    for k in range(len(lay["template"])):
        src = np.flatnonzero(out == k)
        assert src[0] == lay["template"][k]
        assert (a1[src] == lay["a1"][k]).all() and (a2[src] == lay["a2"][k]).all()
        assert (lay["bin"][src] == lay["out_bin"][k]).all()
    keys = set(zip(lay["out_bin"].tolist(), lay["a1"].tolist(), lay["a2"].tolist()))
    assert len(keys) == len(lay["template"])


def naive_means(out, data, model, flag, flag_row, nout):
    shape = (nout, *data.shape[1:])
    n, d, m = np.zeros(shape), np.zeros(shape, complex), np.zeros(shape, complex)
    live = np.zeros(nout, bool)
    for i in range(len(out)):
        if out[i] < 0 or flag_row[i]:
            continue
        live[out[i]] = True
        use = ~flag[i]
        n[out[i]] += use
        d[out[i]] += np.where(use, data[i], 0)
        m[out[i]] += np.where(use, model[i], 0)
    good = n > 0
    return {"data": np.where(good, d / np.where(good, n, 1), 0).astype(np.complex64),
            "model": np.where(good, m / np.where(good, n, 1), 0).astype(np.complex64),
            "weight": n.astype(np.float32), "flag": ~good, "flag_row": ~live}  # fmt: skip


def test_sums_are_the_weighted_means_in_any_blocks():
    rng = np.random.default_rng(3)
    time, scan, a1, a2 = small_meta(1)
    lay = post.qc_layout(time, scan, a1, a2, 2)
    nrow, nchan = len(time), 5
    data = (rng.normal(size=(nrow, nchan, 4)) + 1j * rng.normal(size=(nrow, nchan, 4))).astype(np.complex64)  # fmt: skip
    model = (data * 0.5 + 1).astype(np.complex64)
    flag = rng.random((nrow, nchan, 4)) < 0.3
    flag_row = rng.random(nrow) < 0.1
    nout = len(lay["template"])
    want = naive_means(lay["out"], data, model, flag, flag_row, nout)
    for block in (nrow, 7, 1):
        s = post.QcSums(nout, nchan, 4)
        for r0 in range(0, nrow, block):
            sl = slice(r0, r0 + block)
            s.add(lay["out"][sl], data[sl], model[sl], flag[sl], flag_row[sl])
        got = s.means()
        for k in want:
            assert np.array_equal(got[k], want[k]), (block, k)


def test_apply_flags():
    rng = np.random.default_rng(4)
    valid = rng.random((3, 2, 5)) < 0.7  # (interval, freq bin, antenna)
    tb = rng.integers(0, 3, 40)
    a1, a2 = rng.integers(0, 5, 40), rng.integers(0, 5, 40)
    fb = np.array([0, 0, 1, 1, 1])
    got = post.apply_flags(valid, tb, fb, a1, a2)
    for i in range(40):
        for c in range(5):
            assert got[i, c] == (
                not valid[tb[i], fb[c], a1[i]] or not valid[tb[i], fb[c], a2[i]]
            )


def test_products_measure():
    rng = np.random.default_rng(5)
    g = np.exp(1j * rng.normal(size=(2, 1, 6, 2))) * (
        1 + 0.1 * rng.normal(size=(2, 1, 6, 2))
    )
    f = np.zeros((2, 1, 6), bool)
    ref = np.exp(1j * rng.normal(size=(2, 1, 1, 1)))  # another reference: gauge
    same = post.qc_products(g, f, g * ref, f.copy())
    assert same["pass"] and same["max"] < 1e-12 and same["products"] == 2 * 15 * 2
    qg = g.copy()
    qg[0, 0, 2] *= 1.01
    off = post.qc_products(g, f, qg, f.copy())
    assert off["max"] == pytest.approx(0.01 / 1.01, rel=1e-6)  # relative to QuartiCal's
    qf = f.copy()
    qf[0, 0, 2] = True  # the perturbed antenna's flagged solution is not compared
    assert post.qc_products(g, f, qg, qf)["max"] < 1e-12


def test_qc_options():
    opts = post.qc_options({"type": "Sa", "solint": 120}, 23)
    assert "G.type=diag_complex" in opts and "G.time_interval=1" in opts
    assert "G.freq_interval=0" in opts and "solver.reference_antenna=23" in opts
    assert "input_ms.weight_column=WEIGHT_SPECTRUM" in opts
    assert (
        "input_ms.time_chunk=1" in opts and "solver.convergence_fraction=0.99" in opts
    )
    assert (
        "solver.iter_recipe=[50]" in opts
        and "solver.convergence_criteria=1e-07" in opts
    )
    assert "G.type=phase" in post.qc_options({"type": "Sp", "solint": 120}, 0)


# --- qc-avg end to end on stand-ins for rang's reader, predictor and stores ----------

NCHAN, NCORR, FID = 6, 4, 1


def make_ms(tmp_path, rng):
    """An MS-shaped stand-in: field 0 rows, then field 1 (the target) rows
    of two scans, autocorrelations included."""
    t1, s1, a1, a2 = small_meta(2, nant=5, ntime=(9, 6))
    t0, s0, b1, b2 = small_meta(3, nant=5, ntime=(2, 1))
    cols = {"TIME": np.r_[t0 - 50, t1], "SCAN_NUMBER": np.r_[s0 * 0 + 1, s1],
            "ANTENNA1": np.r_[b1, a1], "ANTENNA2": np.r_[b2, a2],
            "FIELD_ID": np.r_[np.zeros(len(t0), int), np.full(len(t1), FID)]}  # fmt: skip
    n = len(cols["TIME"])
    cols["UVW"] = rng.normal(size=(n, 3)) * 100
    cols["RANG_CORRECTED_DATA"] = (rng.normal(size=(n, NCHAN, NCORR))
                                   + 1j * rng.normal(size=(n, NCHAN, NCORR))).astype(np.complex64)  # fmt: skip
    return cols


def fake_predict(name, uvw, nchan):
    k = 1.0 + float(name.endswith("round-2/image"))
    return ((uvw[:, :1] * k + 1j * uvw[:, 1:2]) * np.arange(1, nchan + 1)).astype(
        np.complex64
    )


def setup_qc_avg(tmp_path, monkeypatch, *, break_model=False):
    from rang import _core, cal_selfcal, core_model, core_ms, core_pipeline
    from rang.formats import flagversions

    rng = np.random.default_rng(7)
    cols = make_ms(tmp_path, rng)
    n = len(cols["TIME"])
    keep = cols["FIELD_ID"] == FID
    cross = keep & (cols["ANTENNA1"] != cols["ANTENNA2"])
    sel = np.flatnonzero(cross)
    mapped = np.array(
        [0, 1, 2, 4]
    )  # channel 3 and 5 not predicted: kept from the column
    a, b = 0, 3
    flag0 = rng.random((n, NCHAN, NCORR)) < 0.2
    frow0 = rng.random(n) < 0.05
    ms = tmp_path / "e2a.ms"
    ms.mkdir()
    rd = Path(str(ms) + ".rang-run")
    (rd / "apply").mkdir(parents=True)
    (rd / "selfcal").mkdir()
    names = [str(rd / "selfcal" / "f" / f"round-{k}" / "image") for k in (1, 2)]
    # the column holds round 2's model on mapped channels, something else elsewhere
    model = (rng.normal(size=(n, NCHAN, NCORR)) * (1 + 1j)).astype(np.complex64)
    vis2 = fake_predict(names[1], cols["UVW"][sel], NCHAN)
    m = model[sel]
    m[:, mapped, :] = 0
    m[:, mapped, a] = vis2[:, mapped]
    m[:, mapped, b] = vis2[:, mapped]
    model[sel] = m
    if break_model:
        model[sel[3], 0, a] += 1e-3
    cols["RANG_MODEL_DATA"] = model
    lay = post.qc_layout(cols["TIME"][keep], cols["SCAN_NUMBER"][keep],
                         cols["ANTENNA1"][keep], cols["ANTENNA2"][keep], 4)  # fmt: skip
    nbin = len(lay["bin_time"])
    g1 = np.exp(1j * rng.normal(size=(nbin, 1, 5, 2)))
    f1 = rng.random((nbin, 1, 5)) < 0.2  # round 1 flags some solutions
    g2 = g1 * 1.1
    f2 = np.zeros((nbin, 1, 5), bool)
    stores = {"s1": (g1, f1), "s2": (g2, f2)}
    # round 1's apply flags, as rang counted them over every target row
    rows = np.flatnonzero(keep)
    bad = post.apply_flags(~f1, lay["bin"], np.zeros(NCHAN, int),
                           cols["ANTENNA1"][rows], cols["ANTENNA2"][rows])  # fmt: skip
    bad = np.broadcast_to(bad[..., None], (len(rows), NCHAN, NCORR))
    want1 = int((bad & ~flag0[rows]).sum())
    term = {"type": "Sp", "solint": 4}
    rounds = [{"round": k, "term": dict(term, type=ty), "store": f"s{k}",
               "solve": {"name": ty}, "model": {"name": names[k - 1]},
               "apply": {"cells_flagged_before": 0, "cells_flagged_after": w}}
              for k, ty, w in ((1, "Sp", want1), (2, "Sa", 0))]  # fmt: skip
    (rd / "selfcal" / "summary.json").write_text(json.dumps(
        {"fields": [{"field_id": FID, "rounds": rounds}], "refant": 0,
         "model_column": "MODEL_DATA"}))  # fmt: skip
    (rd / "config.resolved.json").write_text(json.dumps(
        {"data": {"weights": "uniform", "scans": [1, 3, 5]},
         "image": {"extra_args": [], "channels_out": 2, "average_channels": 1,
                   "wgridder_accuracy": 1e-4}}))  # fmt: skip
    (rd / "state.json").write_text(json.dumps({"stages": {
        "apply": {"status": "done", "finished": "T"},
        "selfcal": {"status": "done", "flag_version": "rang_selfcal_X"}}}))  # fmt: skip
    (rd / "selfcal-input.json").write_text(json.dumps(
        {"column": "CORRECTED_1GC", "copied_from": "CORRECTED_DATA", "apply_finished": "T"}))  # fmt: skip
    (rd / "apply" / "summary.json").write_text(json.dumps(
        {"column": "CORRECTED_DATA", "flag_version": "rang_apply_Y", "applied": []}))  # fmt: skip

    class T:
        nrows = n

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

        def colnames(self):
            return list(cols)

        def getcol(self, c, r0=0, k=None):
            return cols[c][r0 : r0 + k].copy()

    monkeypatch.setattr(core_ms, "open_table", lambda path: T())
    monkeypatch.setattr(flagversions, "load",
                        lambda ms_, v, r0, k: (flag0[r0 : r0 + k].copy(), frow0[r0 : r0 + k].copy()))  # fmt: skip
    monkeypatch.setattr(core_model, "band", lambda ms_, f, d: (np.arange(NCHAN) * 1e6 + 1e9, [9, 10, 11, 12], (0.0, 0.0)))  # fmt: skip
    monkeypatch.setattr(core_model, "selected_rows", lambda ms_, f, d, s: sel.copy())
    monkeypatch.setattr(cal_selfcal, "read_store", lambda path, name: (
        stores[path][0], stores[path][1], lay["bin_time"], np.array([1e9]), lay["bin_scan"]))  # fmt: skip
    cmap = np.full(NCHAN, -1)
    cmap[mapped] = 0
    monkeypatch.setattr(_core, "gemclean_channel_map", lambda *a: cmap)
    monkeypatch.setattr(_core, "gemclean_block_rows", lambda nchan: 13)

    def predict(name, nout, rng_, avg, eps, wg, single, phase_dir, uvw, freq, out):
        out[...] = fake_predict(name, uvw, len(freq))

    monkeypatch.setattr(_core, "gemclean_predict", predict)
    monkeypatch.setattr(core_pipeline, "_gridder_single", lambda img, extra: True)
    monkeypatch.setattr(post, "QC_SUB", 5)
    return ms, cols, keep, lay, flag0, frow0, bad, names, mapped, (a, b)


def test_qc_avg_on_stand_ins(tmp_path, monkeypatch):
    ms, cols, keep, lay, flag0, frow0, bad, names, mapped, (a, b) = setup_qc_avg(
        tmp_path, monkeypatch
    )
    r = tmp_path / "R"
    r.mkdir()
    assert post.qc_avg(ms, r) == 0
    rec = json.loads((r / "qc-avg.json").read_text())
    assert rec["model_control"]["met"] and rec["model_control"]["elements_differ"] == 0
    assert (
        rec["data_column"] == "RANG_CORRECTED_DATA"
        and rec["model_column"] == "RANG_MODEL_DATA"
    )
    assert [x["apply_flags_equal"] for x in rec["rounds"]] == [True, True]
    assert rec["rounds"][0]["apply_flags_recomputed"] > 0
    rows = np.flatnonzero(keep)
    d = r / "qc-selfcal"
    assert np.array_equal(np.load(d / "template_rows.npy"), rows[lay["template"]])
    for k, extra_flag in ((1, np.zeros_like(bad)), (2, bad)):
        model = cols["RANG_MODEL_DATA"][rows].copy()
        c = np.flatnonzero(lay["out"] >= 0)
        vis = fake_predict(names[k - 1], cols["UVW"][rows[c]], NCHAN)
        m = model[c]
        m[:, mapped, :] = 0
        m[:, mapped, a] = vis[:, mapped]
        m[:, mapped, b] = vis[:, mapped]
        model[c] = m
        want = naive_means(lay["out"], cols["RANG_CORRECTED_DATA"][rows], model,
                           flag0[rows] | extra_flag, frow0[rows], len(lay["template"]))  # fmt: skip
        for name, arr in want.items():
            assert np.array_equal(np.load(d / f"round-{k}" / f"{name}.npy"), arr), (
                k,
                name,
            )


def test_qc_avg_model_control_fails_on_another_model(tmp_path, monkeypatch):
    ms, cols, keep, lay, flag0, frow0, bad, *_ = setup_qc_avg(
        tmp_path, monkeypatch, break_model=True
    )
    r = tmp_path / "R"
    r.mkdir()
    assert post.qc_avg(ms, r) == 0
    ctrl = json.loads((r / "qc-avg.json").read_text())["model_control"]
    assert not ctrl["met"] and ctrl["elements_differ"] == 1
    rows = np.flatnonzero(keep)  # the last round averages the MS's own column
    want = naive_means(lay["out"], cols["RANG_CORRECTED_DATA"][rows],
                       cols["RANG_MODEL_DATA"][rows], flag0[rows] | bad, frow0[rows],
                       len(lay["template"]))  # fmt: skip
    got = np.load(r / "qc-selfcal" / "round-2" / "model.npy")
    assert np.array_equal(got, want["model"])


# --- snapshot in blocks -------------------------------------------------------------


def test_snapshot_script_packs_in_blocks(tmp_path, monkeypatch):
    rng = np.random.default_rng(8)
    n = 9001
    cols = {
        "FLAG": rng.random((n, 3, 4)) < 0.5,
        "RANG_FLAG": rng.random((n, 3, 4)) < 0.5,
    }
    for c in ("ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER", "TIME"):
        cols[c] = np.arange(n)

    class T:
        def nrows(self):
            return n

        def getcol(self, c, r0=0, k=None):
            return cols[c] if k is None else cols[c][r0 : r0 + k]

    mod = types.ModuleType("casacore.tables")
    mod.table = lambda path, ack=False: T()
    monkeypatch.setitem(sys.modules, "casacore", types.ModuleType("casacore"))
    monkeypatch.setitem(sys.modules, "casacore.tables", mod)
    out = tmp_path / "snap.npz"
    monkeypatch.setattr(sys, "argv", ["snap", "MS", str(out)])
    exec(compile(post.SNAP_PY, "snap", "exec"), {"__name__": "__main__"})  # noqa: S102
    got = np.load(out)
    for c in ("FLAG", "RANG_FLAG"):
        assert np.array_equal(got[c], np.packbits(cols[c], axis=-1))


def test_launcher_runs_order_inplace_with_a_booking_per_step():
    text = (HERE / "e2a_post.sh").read_text(encoding="utf-8")
    block = text.split('STEPS="', 1)[1].split('"', 1)[0]
    rows = [line.split() for line in block.strip().splitlines()]
    assert [r[0] for r in rows] == post.ORDER_INPLACE
    for step, slots, mem, which in rows:
        assert 1 <= int(slots) <= 8 and 0 < float(mem) <= 24, step
        assert which == ("wpy" if step == "qc-avg" else "py"), step


def test_qc_selfcal_compares_stored_gains(tmp_path, monkeypatch):
    from rang import cal_selfcal

    rng = np.random.default_rng(9)
    ms, r = tmp_path / "e2a.ms", tmp_path / "R"
    rd = Path(str(ms) + ".rang-run")
    (rd / "selfcal").mkdir(parents=True)
    (rd / "selfcal" / "summary.json").write_text(json.dumps({"refant": 2}))
    g = np.exp(1j * rng.normal(size=(3, 1, 5, 2)))
    f = np.zeros((3, 1, 5), bool)
    f[1, 0, 4] = True
    gt = np.array([10.0, 20.0, 30.0])
    rounds = []
    for k, ty in ((1, "Sp"), (2, "Sa")):
        out = r / "qc-selfcal" / f"qc-round-{k}"
        out.mkdir(parents=True)
        q = np.zeros((3, 1, 5, 4), complex)
        q[..., 0], q[..., 3] = g[..., 0] * 1j, g[..., 1] * 1j  # another phase reference
        np.save(out / "gains.npy", q)
        np.save(out / "gain_flags.npy", np.zeros((3, 1, 5), np.int8))
        (out / "summary.json").write_text(json.dumps({"gain_times": gt.tolist()}))
        rounds.append({"round": k, "term": {"type": ty, "solint": 120}, "store": f"s{k}",
                       "solve_name": ty, "apply_flags_equal": True})  # fmt: skip
    (r / "qc-avg.json").write_text(json.dumps(
        {"rounds": rounds, "solint_integrations": 120, "baselines": 1830, "channels": 4096,
         "model_control": {"met": False}}))  # fmt: skip
    monkeypatch.setattr(cal_selfcal, "read_store", lambda p, n: (g, f, gt, None, None))
    monkeypatch.setattr(
        post, "docker", lambda *a, **k: pytest.fail("no container here")
    )
    assert post.qc_selfcal(ms, r) == 0
    res = json.loads((r / "qc-selfcal.json").read_text())
    r1, r2 = res["rounds"]
    assert r1["quartical"].startswith("void")  # the model control voids round 1 only
    assert r2["pass"] and r2["gain_times_equal"] and r2["max"] < 1e-12
    assert r2["products"] == 3 * 10 * 2 - 4 * 2  # antenna 4's flagged bin left out
    un = res["unaveraged_form"]
    assert not un["run"] and un["gb_per_interval_data_model_weights"] > WSL_GB


WSL_GB = 44


@pytest.mark.skipif(
    sys.platform != "win32"
    or shutil.which("cygpath") is None
    or os.environ.get("E2A_LAUNCHER_DRY") != "1",
    reason="Git Bash on the Windows host, opt-in only (E2A_LAUNCHER_DRY=1): the "
    "coordinator does not want the launcher run, not even dry, during E2-A",
)
def test_launcher_dry_run_visits_every_step(tmp_path):
    import subprocess

    env = dict(os.environ, DRY="1", R=str(tmp_path))
    bash = str(
        Path(shutil.which("cygpath")).with_name("bash.exe")
    )  # Git Bash, not WSL's
    done = subprocess.run([bash, (HERE / "e2a_post.sh").as_posix()], env=env, capture_output=True,
                          text=True, timeout=60, check=False)  # fmt: skip
    assert done.returncode == 0, done.stderr
    steps = [line.split(" -- ")[-1].split()[2] for line in done.stdout.splitlines()
             if line.startswith("DRY ")]  # fmt: skip
    assert steps == post.ORDER_INPLACE  # the stand-in drains stdin: no step is lost
    assert not list(tmp_path.iterdir())
    env["NOSI"] = "0"
    done = subprocess.run([bash, (HERE / "e2a_post.sh").as_posix()], env=env, capture_output=True,
                          text=True, timeout=60, check=False)  # fmt: skip
    steps = [line.split(" -- ")[-1].split()[2] for line in done.stdout.splitlines()
             if line.startswith("DRY ")]  # fmt: skip
    assert steps == [s for s in post.ORDER_INPLACE if "nosi" not in s]


def test_nosi_follows_the_primary_reading(tmp_path, monkeypatch):
    fake_colnames(monkeypatch, ["E2_CASA_FLAG", "RANG_CORRECTED_DATA"])
    with pytest.raises(SystemExit, match="score3c-a"):
        post.wsclean3c_a_nosi_dirty(tmp_path / "e2a.ms", tmp_path)
    (tmp_path / "g3c-a.json").write_text("{}")
    seen = []
    monkeypatch.setattr(post, "wsclean3c_a", lambda ms, r, kind, threads, nosi=False:
                        seen.append((kind, threads, nosi)) or 0)  # fmt: skip
    assert post.wsclean3c_a_nosi_dirty(tmp_path / "e2a.ms", tmp_path) == 0
    assert seen == [("dirty", "2", True)]


def test_nosi_argv_writes_its_own_directory():
    argv, _ = post.wsclean_argv(image_argv(), name="/p/wsclean3c-a-nosi/T-dirty", column="C",
                                threads=2, temp="t", ms_inside="/c/m", dirty=True, nosi=True)  # fmt: skip
    assert "-no-small-inversion" in argv and argv[argv.index("-name") + 1].startswith(
        "/p/wsclean3c-a-nosi/"
    )
