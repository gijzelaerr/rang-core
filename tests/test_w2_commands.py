"""W2 (research/w2-commands.md): the configuration schema and the commands
`rang-core flag | calibrate | apply | image | selfcal | run` on a Measurement
Set written by the core writer inside each test, with resume, flag backups,
receipts and refusals. The end-to-end run on A1's MS is
`tools/oracles/w2/run.sh`."""

import importlib.util
import itertools
import json
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from rang import core, core_cli, core_config, core_flag, core_ms, core_ms_write
from rang import core_pipeline as pipe
from rang import core_writeback as wb
from rang.formats import flagversions, quartical_store

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "w2"
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
POSIX = pytest.mark.skipif(os.name != "posix", reason="POSIX only")

STRATEGY = """\
strategies:
  - name: nans
    task: flag_nans_zeros
  - name: st
    task: sum_threshold
    kwargs:
      outlier_nsigma: 4.5
      windows_time: [1, 2, 4]
      windows_freq: [1, 2, 4]
      freq_chunks: 2
  - name: combine
    task: combine_with_input_flags
"""
NANT, NCHAN, NROW = 4, 16, 240  # 6 baselines x 40 integrations


def make_ms(path, ncorr=4):
    """W1's synthetic MS (random FLAG 10 %, FLAG_ROW 5 %) with antennas, two
    fields and two scans: integrations 0-19 field CAL scan 1, then TGT scan 2."""
    ms = w1.make_ms(path, NROW, NCHAN, ncorr=ncorr, flag="tiled", nant=NANT)
    base = np.array([5109224.0, 2006790.0, -3239100.0])
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("POSITION", base + 150.0 * np.arange(NANT)[:, None] * [1, 0.5, 0.2])
        t.putcol("NAME", [f"m{a:03d}" for a in range(NANT)])
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(2)
        t.putcol("NAME", ["CAL", "TGT"])
        # Phase centres (calmodels and gainfield nearest read them).
        t.putcol("PHASE_DIR", np.array([[[0.0, -1.0]], [[0.1, -1.0]]]))
    integration = np.arange(NROW) // 6
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FIELD_ID", (integration >= 20).astype(np.int32))
        t.putcol("SCAN_NUMBER", 1 + (integration >= 20).astype(np.int32))
    return ms


def write_config(tmp_path, extra="", name="config.yaml", gemclean=None):
    (tmp_path / "strategy.yaml").write_text(STRATEGY, encoding="utf-8")
    text = textwrap.dedent(
        f"""\
        version: 1
        fields: {{fcal: [CAL], target: [TGT]}}
        flag: {{strategy: strategy.yaml}}
        calibrate:
          primary:
            terms: [{{type: complex, solint: 4, freqint: 8}}]
        image:
          gemclean: {gemclean or "auto"}
          size: [64, 64]
          scale: 20asec
          niter: 10
          threads: 1
        """
    )
    path = tmp_path / name
    path.write_text(text + extra, encoding="utf-8")
    return path


def cli(*argv):
    return core_cli.dispatch([*map(str, argv)])


def column(ms, name):
    with core_ms.open_table(ms) as t:
        return t.getcol(name)


def fake_gemclean(tmp_path):
    """A stand-in that writes the files gemclean names after `-name`."""
    script = tmp_path / "fake-gemclean.py"
    script.write_text(
        "import sys\n"
        "a = sys.argv[1:]\n"
        "name = a[a.index('-name') + 1]\n"
        "open(name + '-image.fits', 'w').write('fake\\n')\n",
        encoding="utf-8",
    )
    # A .cmd wrapper on Windows, which cannot run a #! script.
    if os.name == "nt":
        path = tmp_path / "fake-gemclean.cmd"
        path.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        path = tmp_path / "fake-gemclean"
        path.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
        )
        path.chmod(0o755)
    return path


def expected_flags(ms, strategy_text):
    """The call examples/run_core_flags.py makes, per field/ddid/scan group."""
    strategies = core_flag.parse_strategy(strategy_text)
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    with core_ms.open_table(ms) as t:
        c = {
            n: t.getcol(n)
            for n in (
                "DATA",
                "FLAG",
                "ANTENNA1",
                "ANTENNA2",
                "TIME",
                "FIELD_ID",
                "DATA_DESC_ID",
                "SCAN_NUMBER",
            )
        }
    with core_ms.open_table(ms / "ANTENNA") as t:
        pos = t.getcol("POSITION")
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq, width = t.getcol("CHAN_FREQ")[0], t.getcol("CHAN_WIDTH")[0]
    with core_ms.open_table(ms / "POLARIZATION") as t:
        corr = t.getcol("CORR_TYPE")[0]
    out = c["FLAG"].copy()
    keys = np.stack([c["FIELD_ID"], c["DATA_DESC_ID"], c["SCAN_NUMBER"]], 1)
    for key in np.unique(keys, axis=0):
        idx = np.flatnonzero((keys == key).all(1))
        out[idx] = core_flag.flag_rows(
            c["DATA"][idx],
            c["FLAG"][idx],
            c["ANTENNA1"][idx],
            c["ANTENNA2"][idx],
            c["TIME"][idx],
            pos,
            freq,
            width,
            corr,
            strategies,
            masks=masks,
        )["flags"]
    return out


# -- the schema ------------------------------------------------------------------


def test_defaults_are_written_down_and_round_trip():
    text = core_config.defaults_yaml()
    config, errors = core_config.resolve(core_config.loads(text))
    assert errors == []
    assert config == core_config.resolve({"version": 1})[0]

    def walk(spec):
        for item in spec.values():
            if isinstance(item, dict):
                walk(item)
            else:
                assert item.doc, item

    walk(core_config.SCHEMA)
    assert all(k.doc for k in core_config.TERM_KEYS.values())
    assert "complex" in text and "C2e" in text and "C2a" not in text


def test_schema_errors_are_all_reported_with_their_paths():
    raw = core_config.loads(
        "version: 2\n"
        "flag: {strategy: 3, writ: or}\n"
        "calibrate: {primary: {terms: [{type: G, freqint: 4}, {type: Q}]}}\n"
        "image: {size: [65, 64]}\n"
        "bogus: 1\n"
    )
    _, errors = core_config.resolve(raw)
    paths = {p for p, _ in errors}
    assert {
        "version",
        "flag.strategy",
        "flag.writ",
        "calibrate.primary.terms[0].freqint",
        "calibrate.primary.terms[1].type",
        "image.size",
        "bogus",
    } <= paths
    with pytest.raises(core_config.ConfigError) as exc:
        core_config.validate(raw, ["flag"])
    assert "flag.writ: unknown key" in str(exc.value)
    _, errors = core_config.resolve({})
    assert errors == [("version", "required (default 1)")]


def test_yaml_numbers_without_a_dot_are_numbers():
    config, errors = core_config.resolve(
        core_config.loads(
            "version: 1\ncalibrate: {primary: {terms: [{type: complex, "
            "stop_criterion: 1e-6}]}}\n"
        )
    )
    assert errors == []
    assert config["calibrate"]["primary"]["terms"][0]["stop_criterion"] == 1e-6


def _tasks(path, stages=None):
    raw = core_config.load(path)
    config, errors = core_config.resolve(raw)
    assert errors == [], errors
    stages = stages or config["run"]["stages"]
    return {r.task for r in core_config.refusals(config, stages) if r.task}


def test_the_acceptance_configurations_parse_and_wait_for_their_tasks():
    # Since task C2e (research/c2e-calibrate.md) K, G, B, A and F run, and
    # since task C5 (research/c5-selfcal.md) the selfcal rounds.
    # Since task G4 (research/g4-masks.md) the automatic mask runs; E2-A's
    # needs an mgain, a configuration refusal (no task left).
    assert _tasks(DATA / "e2a.yaml") == set()
    # Since task C6w (research/c6w-polwire.md) Gpol, KCROSS, Xf, Df and P run,
    # and since task E0 (research/e0-refant-extend.md) refant auto and
    # extendflags; since task W6 (research/w6-imaging-inputs.md) data.scans and
    # data.weights: uniform reach gemclean (-scans, -unit-weights), and since
    # task G9 (research/g9-stokes.md) IQUV with joined polarisations: nothing
    # is left.
    assert _tasks(DATA / "e2b.yaml") == set()


def test_the_complex_term_refuses_what_its_kernel_cannot_take():
    raw = {
        "version": 1,
        "calibrate": {
            "refant": "m000",
            "primary": {
                "terms": [
                    {"type": "complex", "solint": "60s", "combine": "scan"},
                    {"type": "complex", "name": "c2", "preapply": ["complex"]},
                ]
            },
        },
    }
    config, errors = core_config.resolve(raw)
    assert errors == []
    refused = core_config.refusals(config, ["calibrate"])
    # What the complex kernel never takes is a configuration error pointing
    # to the CASA terms (task C2e), not a refusal naming a task.
    assert {(r.path.rsplit(".", 1)[-1], r.task) for r in refused} == {
        ("solint", ""),
        ("combine", ""),
        ("refant", ""),
        ("preapply", ""),
    }
    assert all("K, G and B terms" in r.text for r in refused)


# -- the commands ----------------------------------------------------------------


def test_flag_writes_the_port_flags_with_backups_and_a_receipt(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    want = expected_flags(ms, STRATEGY)
    before_flag, before_row = column(ms, "FLAG"), column(ms, "FLAG_ROW")
    others = {c: w1.sha(ms, c) for c in ("DATA", "WEIGHT", "TIME", "FLAG_ROW")}
    config = write_config(tmp_path)
    state = cli("flag", config, ms)
    assert state["stages"]["flag"]["status"] == "done"
    assert np.array_equal(column(ms, "FLAG"), want)
    assert {c: w1.sha(ms, c) for c in others} == others
    names = [n for n, _ in flagversions.versions(ms)]
    assert names[0] == "rang_original" and names[1].startswith("rang_flag_")
    assert len(names) == 2
    assert np.array_equal(flagversions.load(ms, "rang_original")[0], before_flag)
    assert np.array_equal(flagversions.load(ms, "rang_original")[1], before_row)
    run = ms.with_name("x.ms.rang-run")
    receipts = sorted((run / "receipts").glob("flag-*.rang-receipt.json"))
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["schema"] == "rang.receipt" and receipt["version"] == 5
    assert receipt["command"][:2] == ["rang-core", "flag"] and receipt["exit"] == 0
    # Owner decision E5-20: the modified MS by its listing hash only; the
    # stage summary hashes the flags written.
    (modified,) = [o for o in receipt["outputs"] if o.get("modified")]
    assert modified["path"] == ms.as_posix() and "listing_sha256" in modified
    assert "tree_sha256" not in modified
    summary = json.loads((run / "flag" / "summary.json").read_text(encoding="utf-8"))
    assert [g["field"] for g in summary["groups"]] == ["CAL", "TGT"]
    # A second flag is skipped: nothing written, no new version.
    cli("flag", config, ms)
    assert len(flagversions.versions(ms)) == 2
    assert np.array_equal(column(ms, "FLAG"), want)


def test_calibrate_writes_the_core_solve_bit_for_bit(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path)
    cli("flag", config, ms)
    cli("calibrate", config, ms)
    store = ms.with_name("x.ms.rang-run") / "calibrate" / "complex.qc"
    parts = quartical_store.read(store)["complex"]
    assert [p.attrs["FIELD_NAME"] for p in parts] == ["CAL"]
    with core_ms.open_table(ms) as t:
        c = {
            n: t.getcol(n)
            for n in (
                "DATA",
                "FLAG",
                "FLAG_ROW",
                "ANTENNA1",
                "ANTENNA2",
                "TIME",
                "FIELD_ID",
                "WEIGHT",
            )
        }
    rows = np.flatnonzero(c["FIELD_ID"] == 0)
    rows = rows[np.argsort(c["TIME"][rows], kind="stable")]
    unique, inverse = np.unique(c["TIME"][rows], return_inverse=True)
    solution = core.solve_complex(
        c["DATA"][rows],
        np.repeat(c["WEIGHT"][rows][:, None, :], NCHAN, axis=1),
        c["FLAG"][rows],
        c["FLAG_ROW"][rows],
        c["ANTENNA1"][rows],
        c["ANTENNA2"][rows],
        (inverse // 4).astype(np.uint32),
        (np.arange(NCHAN) // 8).astype(np.uint32),
        ntime_bins=5,
        nfreq_bins=2,
        nant=NANT,
        scalar_model=np.ones(NCHAN),
    )
    stored = parts[0]["gains"].reshape(solution.gains.shape)
    assert stored.tobytes() == solution.gains.tobytes()
    assert np.array_equal(parts[0]["gain_flags"][..., 0], solution.flags)
    assert len(unique) == 20


def test_a_changed_configuration_is_refused_and_force_restores_first(tmp_path, capsys):
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path)
    cli("flag", config, ms)
    cli("calibrate", config, ms)
    first = column(ms, "FLAG")
    changed = write_config(tmp_path, name="changed.yaml")
    text = changed.read_text(encoding="utf-8").replace(
        "flag: {strategy: strategy.yaml}", "flag: {strategy: strategy.yaml, write: or}"
    )
    changed.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli("flag", changed, ms)
    assert exc.value.code == 2
    # E5: the hint names forms both commands accept.
    hint = capsys.readouterr().err
    assert "`rang-core flag ... --force`" in hint
    assert "`rang-core run ... --force flag`" in hint
    cli("flag", config, ms, "--force")
    # The forced rerun starts from the flags saved before the first run.
    assert np.array_equal(column(ms, "FLAG"), first)
    # rang_original, the two attempts' versions and (E5) the flags the
    # restore replaced.
    assert len(flagversions.versions(ms)) == 4
    state = json.loads(
        (ms.with_name("x.ms.rang-run") / "state.json").read_text(encoding="utf-8")
    )
    assert state["stages"]["flag"]["summary"]["restored_before"].startswith(
        "rang_flag_"
    )
    assert state["stages"]["calibrate"]["status"] == "stale"


def test_a_rerun_saves_the_flags_its_restore_replaces(tmp_path):
    """E5 (WB-06): flags set outside rang after a stage ran survive its
    forced rerun as a flag version, rang_rerun_<time>."""
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path)
    cli("--no-receipt", "flag", config, ms)
    with core_ms_write.open_table(ms, readonly=False) as t:
        flag = t.getcol("FLAG")
        flag[100:140] = True  # flagged by hand, say with CASA flagdata
        t.putcol("FLAG", flag)
    by_hand = column(ms, "FLAG")
    cli("--no-receipt", "flag", config, ms, "--force")
    state = json.loads(
        (ms.with_name("x.ms.rang-run") / "state.json").read_text(encoding="utf-8")
    )
    saved = state["stages"]["flag"]["saved_before_restore"]
    assert saved.startswith("rang_rerun_")
    assert np.array_equal(flagversions.load(ms, saved)[0], by_hand)


def test_a_missing_recorded_flag_version_is_warned_about(tmp_path, capsys):
    """E5-42 (WB-12): when the version the last attempt recorded is gone (the
    MS copied without its .flagversions), the rerun says so and records it."""
    import shutil

    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path)
    cli("--no-receipt", "flag", config, ms)
    shutil.rmtree(flagversions.root(ms))
    capsys.readouterr()
    cli("--no-receipt", "flag", config, ms, "--force")
    err = capsys.readouterr().err
    state = json.loads(
        (ms.with_name("x.ms.rang-run") / "state.json").read_text(encoding="utf-8")
    )
    entry = state["stages"]["flag"]
    assert entry["status"] == "done"
    assert entry["restore_missing"].startswith("rang_flag_")
    assert f"warning: flag version {entry['restore_missing']}" in err


def test_data_from_another_telescope_is_warned_about_not_refused(tmp_path, capsys):
    """E5-39: rang is tested on MeerKAT only; another TELESCOPE_NAME runs with
    a warning in the W4 style and is recorded in the state."""
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path)
    assert pipe.inspect_ms(ms)["telescope"] == ""  # no OBSERVATION row: no warning
    assert pipe.scope_warnings(pipe.inspect_ms(ms)) == []
    with core_ms_write.open_table(ms / "OBSERVATION", readonly=False) as t:
        t.addrows(1)
        t.putcol("TELESCOPE_NAME", ["MeerKAT"])
    assert pipe.inspect_ms(ms)["telescope"] == "MeerKAT"
    assert pipe.scope_warnings(pipe.inspect_ms(ms)) == []
    with core_ms_write.open_table(ms / "OBSERVATION", readonly=False) as t:
        t.putcol("TELESCOPE_NAME", ["ASKAP"])
    capsys.readouterr()
    cli("--no-receipt", "flag", config, ms)
    err = capsys.readouterr().err
    assert "warning:" in err and "is from ASKAP, not MeerKAT" in err
    assert "task W4" in err
    state = json.loads(
        (ms.with_name("x.ms.rang-run") / "state.json").read_text(encoding="utf-8")
    )
    assert state["telescope"] == "ASKAP"
    assert state["stages"]["flag"]["status"] == "done"


def test_a_stale_stage_reruns_on_the_new_upstream_flags(tmp_path):
    """E5: after `--force flag` with a changed strategy, the stale apply stage
    must not restore the flags saved before its earlier attempt (the old flag
    output); FLAG equals a fresh run with the new configuration."""
    rerun, fresh = make_ms(tmp_path / "one.ms"), make_ms(tmp_path / "two.ms")
    a = write_config(
        tmp_path, "run: {stages: [flag, calibrate, apply]}\n", name="a.yaml"
    )
    b = tmp_path / "b.yaml"
    b.write_text(
        a.read_text(encoding="utf-8").replace(
            "flag: {strategy: strategy.yaml}",
            "flag: {strategy: strategy.yaml, fields: [CAL]}",
        ),
        encoding="utf-8",
    )
    cli("--no-receipt", "run", a, rerun)
    old = column(rerun, "FLAG")
    cli("--no-receipt", "run", b, rerun, "--force", "flag")
    cli("--no-receipt", "run", b, fresh)
    assert not np.array_equal(column(fresh, "FLAG"), old)
    assert np.array_equal(column(rerun, "FLAG"), column(fresh, "FLAG"))
    assert np.array_equal(
        column(rerun, "CORRECTED_DATA"), column(fresh, "CORRECTED_DATA"), equal_nan=True
    )


def test_a_stage_that_wrote_no_flags_leaves_the_later_restore_in_place(tmp_path):
    """E5: a forced complex calibrate writes no FLAG, so the stale apply
    still restores the flags saved before its own earlier attempt, and
    flags it added (here set by hand in its place) do not survive."""
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(
        tmp_path, "run: {stages: [flag, calibrate, apply]}\n", name="a.yaml"
    )
    cli("--no-receipt", "run", config, ms)
    first = column(ms, "FLAG")
    with core_ms_write.open_table(ms, readonly=False) as t:
        flag = t.getcol("FLAG")
        # What an earlier apply might have added, on target rows that
        # calibrate does not read.
        flag[200:230] = True
        t.putcol("FLAG", flag)
    assert not np.array_equal(column(ms, "FLAG"), first)
    cli("--no-receipt", "run", config, ms, "--force", "calibrate")
    state = ms.with_name("x.ms.rang-run") / "state.json"
    stages = json.loads(state.read_text(encoding="utf-8"))["stages"]
    assert stages["apply"]["summary"]["restored_before"]
    # The same configuration again: the same flags as the first run.
    assert np.array_equal(column(ms, "FLAG"), first)


@POSIX
def test_run_resumes_at_the_failed_stage(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    # The three stages this test was written for (the default is the whole
    # chain since E5-28).
    stages = "run: {stages: [flag, calibrate, image]}\n"
    bad = write_config(tmp_path, stages, name="bad.yaml", gemclean=tmp_path / "missing")
    with pytest.raises(SystemExit) as exc:
        cli("run", bad, ms)
    assert exc.value.code == 1
    run = ms.with_name("x.ms.rang-run")
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    status = {s: e["status"] for s, e in state["stages"].items()}
    assert status == {"flag": "done", "calibrate": "done", "image": "failed"}
    flags, versions = column(ms, "FLAG"), flagversions.versions(ms)
    good = write_config(
        tmp_path, stages, name="good.yaml", gemclean=fake_gemclean(tmp_path)
    )
    state = cli("run", good, ms)
    assert {s: e["status"] for s, e in state["stages"].items()} == {
        "flag": "done",
        "calibrate": "done",
        "image": "done",
    }
    assert state["stages"]["flag"]["attempts"] == 1
    assert state["stages"]["image"]["attempts"] == 2
    assert np.array_equal(column(ms, "FLAG"), flags)
    assert flagversions.versions(ms) == versions
    assert (run / "image" / "TGT" / "image-image.fits").is_file()
    argv = json.loads((run / "image" / "summary.json").read_text(encoding="utf-8"))
    argv = argv["images"][0]["argv"]
    assert argv[argv.index("-data-column") + 1] == "DATA"
    assert argv[argv.index("-field") + 1] == "1"


@POSIX
def test_a_killed_flag_write_resumes_from_its_backup(tmp_path):
    reference = make_ms(tmp_path / "ref.ms")
    killed = make_ms(tmp_path / "killed.ms")
    config = write_config(tmp_path, "data: {chunk_rows: 64}\n")
    cli("flag", config, reference)
    script = tmp_path / "kill.py"
    script.write_text(
        textwrap.dedent(
            """\
            import os, signal, sys
            from rang import core_cli, core_writeback
            put = core_writeback.WriteBack._put
            def _put(self, name, start, values):
                put(self, name, start, values)
                if name == "FLAG" and start > 0:
                    os.kill(os.getpid(), signal.SIGKILL)
            core_writeback.WriteBack._put = _put
            core_cli.main(["flag", *sys.argv[1:]])
            """
        ),
        encoding="utf-8",
    )
    done = subprocess.run(
        [sys.executable, str(script), str(config), str(killed)],
        capture_output=True,
        check=False,
    )
    assert done.returncode == -signal.SIGKILL
    assert wb.read_journal(killed)["state"] == "open"
    assert not np.array_equal(column(killed, "FLAG"), column(reference, "FLAG"))
    state = cli("flag", config, killed)
    assert state["stages"]["flag"]["attempts"] == 2
    assert np.array_equal(column(killed, "FLAG"), column(reference, "FLAG"))
    original = flagversions.load(killed, "rang_original")[0]
    assert np.array_equal(original, flagversions.load(reference, "rang_original")[0])


def test_selfcal_and_unsolved_apply_targets_are_refused(tmp_path, capsys):
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path, gemclean=fake_gemclean(tmp_path))
    # Task C5: selfcal runs, and needs its input column (exit 1, no write).
    with pytest.raises(SystemExit) as exc:
        cli("selfcal", config, ms)
    assert exc.value.code == 1
    assert "has no CORRECTED_1GC" in capsys.readouterr().err
    assert not flagversions.versions(ms)
    # W2b: a complex term applies only to the fields it is solved on.
    transfer = write_config(
        tmp_path,
        "apply: {targets: [{field: [TGT], tables: [complex]}]}\n",
        name="transfer.yaml",
    )
    with pytest.raises(SystemExit) as exc:
        cli("apply", transfer, ms)
    assert exc.value.code == 2
    assert "solve G and F terms" in capsys.readouterr().err
    assert not flagversions.versions(ms)
    refused = "run: {stages: [flag, selfcal]}\nselfcal: {terms: [{type: complex}]}\n"
    with pytest.raises(SystemExit) as exc:
        cli("run", write_config(tmp_path, refused), ms)
    assert exc.value.code == 2 and not flagversions.versions(ms)
    # apply before calibrate fails (exit 1) before writing anything.
    with pytest.raises(SystemExit) as exc:
        cli("apply", config, ms)
    assert exc.value.code == 1 and not flagversions.versions(ms)


def reference_apply(data, flag, a1, a2, gains, valid, tb, fb):
    """float64 NumPy reference of the complex apply (research/c4b-apply-ms.md
    3.3): inverses by np.linalg.inv, a bad side the identity, and a cell
    flagged in all four correlations by any input flag or a bad side."""
    out = np.empty(data.shape, np.complex64)
    out_flag = np.empty(data.shape, bool)
    for r in range(data.shape[0]):
        for c in range(data.shape[1]):
            sides = []
            for a in (a1[r], a2[r]):
                g = gains[tb[r], fb[c], a]
                ok = bool(valid[tb[r], fb[c], a]) and abs(np.linalg.det(g)) > 0
                sides.append((np.linalg.inv(g) if ok else np.eye(2), ok))
            (ip, okp), (iq, okq) = sides
            v = data[r, c].astype(np.complex128).reshape(2, 2)
            out[r, c] = (ip @ v @ iq.conj().T).reshape(4)
            out_flag[r, c] = flag[r, c].any() or not (okp and okq)
    return out, out_flag


def test_apply_writes_the_complex_term_on_its_own_bins(tmp_path):
    from rang import cal_apply

    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path, "run: {stages: [flag, calibrate, apply]}\n")
    before = {n: column(ms, n) for n in ("DATA", "FIELD_ID", "TIME")}
    cli("flag", config, ms)
    flag_in = column(ms, "FLAG")
    state = cli("run", config, ms)
    assert state["stages"]["apply"]["status"] == "done"
    run = ms.with_name("x.ms.rang-run")
    part = quartical_store.read(run / "calibrate" / "complex.qc")["complex"][0]
    gains = part.gains_2x2()[:, :, :, 0]
    valid = part["gain_flags"][:, :, :, 0] == 0
    cd, flag = column(ms, "CORRECTED_DATA"), column(ms, "FLAG")
    a1, a2 = column(ms, "ANTENNA1"), column(ms, "ANTENNA2")
    cal = np.flatnonzero(before["FIELD_ID"] == 0)
    cal = cal[np.argsort(before["TIME"][cal], kind="stable")]
    tb, fb, _, _ = pipe.solution_grid(
        before["TIME"][cal], NCHAN, np.arange(NCHAN, dtype=float), 4, 8
    )
    want, want_flag = reference_apply(
        before["DATA"][cal], flag_in[cal], a1[cal], a2[cal], gains, valid, tb, fb
    )
    assert cal_apply.class_c(cd[cal], want, np.ones(want.shape, bool))["pass"]
    assert np.array_equal(flag[cal], want_flag)
    tgt = before["FIELD_ID"] == 1
    assert cd[tgt].tobytes() == before["DATA"][tgt].tobytes()
    assert np.array_equal(flag[tgt], flag_in[tgt])
    names = [n for n, _ in flagversions.versions(ms)]
    assert names[0] == "rang_original"
    assert any(n.startswith("rang_apply_") for n in names)
    # Applying again gives the same bytes (from DATA, flags OR'd).
    cli("apply", config, ms, "--force")
    assert column(ms, "CORRECTED_DATA").tobytes() == cd.tobytes()
    assert np.array_equal(column(ms, "FLAG"), flag)


@POSIX
def test_image_auto_reads_corrected_data_after_apply(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(
        tmp_path,
        "run: {stages: [flag, calibrate, apply, image]}\n",
        gemclean=fake_gemclean(tmp_path),
    )
    cli("run", config, ms)
    run = ms.with_name("x.ms.rang-run")
    argv = json.loads((run / "image" / "summary.json").read_text(encoding="utf-8"))
    argv = argv["images"][0]["argv"]
    assert argv[argv.index("-data-column") + 1] == "CORRECTED_DATA"


def test_calibrate_writes_a_manual_model_and_solves_against_it(tmp_path):
    from rang import calmodels

    ms = make_ms(tmp_path / "x.ms")
    direct = make_ms(tmp_path / "direct.ms")
    config = write_config(tmp_path, name="model.yaml")
    text = config.read_text(encoding="utf-8").replace(
        "calibrate:\n",
        "calibrate:\n  model: {source: manual, flux_jy: [2.5, 0, 0, 0], "
        "reffreq_hz: 1.4e9, spix: [-0.7]}\n",
    )
    config.write_text(text, encoding="utf-8")
    state = cli("calibrate", config, ms)
    entry = state["stages"]["calibrate"]
    assert entry["status"] == "done"
    assert entry["flag_version"].startswith("rang_calibrate_")
    calmodels.set_model(direct, [0], calmodels.Manual(2.5, 1.4e9, (-0.7,)))
    model = column(ms, "MODEL_DATA")
    assert model.tobytes() == column(direct, "MODEL_DATA").tobytes()
    assert np.any(model[column(ms, "FIELD_ID") == 0] != 1)
    run = ms.with_name("x.ms.rang-run")
    part = quartical_store.read(run / "calibrate" / "complex.qc")["complex"][0]
    names = ("DATA", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2", "TIME", "FIELD_ID")
    c = {n: column(ms, n) for n in (*names, "WEIGHT")}
    rows = np.flatnonzero(c["FIELD_ID"] == 0)
    rows = rows[np.argsort(c["TIME"][rows], kind="stable")]
    _, inverse = np.unique(c["TIME"][rows], return_inverse=True)
    solution = core.solve_complex(
        c["DATA"][rows],
        np.repeat(c["WEIGHT"][rows][:, None, :], NCHAN, axis=1),
        c["FLAG"][rows],
        c["FLAG_ROW"][rows],
        c["ANTENNA1"][rows],
        c["ANTENNA2"][rows],
        (inverse // 4).astype(np.uint32),
        (np.arange(NCHAN) // 8).astype(np.uint32),
        ntime_bins=5,
        nfreq_bins=2,
        nant=NANT,
        model=model[rows],
    )
    stored = part["gains"].reshape(solution.gains.shape)
    assert stored.tobytes() == solution.gains.tobytes()


def test_model_and_apply_refusals_name_their_tasks(monkeypatch):
    def tasks(raw, stages):
        config, errors = core_config.resolve({"version": 1, **raw})
        assert errors == [], errors
        return {(r.path, r.task) for r in core_config.refusals(config, stages)}

    # A polarised manual model is written since C7a (research/c7a-polmodels.md).
    model = {
        "source": "manual",
        "flux_jy": [1, 0.1, 0, 0],
        "reffreq_hz": 1e9,
        "rotmeas": 3.0,
    }
    assert tasks({"calibrate": {"model": model}}, ["calibrate"]) == set()
    one_sided = {**model, "flux_jy": [1], "polindex": [0.1]}
    assert tasks({"calibrate": {"model": one_sided}}, ["calibrate"]) == {
        ("calibrate.model.polindex", "")
    }
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: None if name == "astropy" else real(name, *a),
    )
    assert tasks({"calibrate": {"model": model}}, ["calibrate"]) == {
        ("calibrate.model.spix", "")
    }
    monkeypatch.undo()
    elsewhere = {"source": "setjy", "polangle": [0.5]}
    assert tasks({"calibrate": {"model": elsewhere}}, ["calibrate"]) == {
        ("calibrate.model.polangle", "")
    }
    secondary = {
        "calibrate": {
            "model": {"source": "setjy"},
            "secondary": {"terms": [{"type": "complex", "name": "c2"}]},
        }
    }
    assert ("calibrate.secondary", "") in tasks(secondary, ["calibrate"])
    target = {"field": ["fcal"], "tables": ["complex"], "interp": ["linear"]}
    assert tasks({"apply": {"targets": [target]}}, ["apply"]) == {
        ("apply.targets[0].interp[0]", "")
    }
    lsm = {"calibrate": {"model": {"source": "lsm"}}}
    assert ("calibrate.model.lsm", "") in tasks(lsm, ["calibrate"])


def test_unsupported_data_is_refused_naming_w4(tmp_path):
    # Since W4 (research/w4-unsupported.md) the refusals depend on the stage:
    # two correlations are refused by calibrate and apply, not by flag.
    config, _ = core_config.resolve(
        {"version": 1, "fields": {"fcal": ["CAL"], "target": ["TGT"]}}
    )
    two = make_ms(tmp_path / "two.ms", ncorr=2)
    info = pipe.inspect_ms(two)
    pipe.preflight(config, info, ["flag"])
    with pytest.raises(pipe.Refused, match="four correlations.*W4"):
        pipe.preflight(config, info, ["calibrate"])
    ms = make_ms(tmp_path / "x.ms")
    with core_ms_write.open_table(ms / "DATA_DESCRIPTION", readonly=False) as t:
        t.addrows(1)
        t.putcol("SPECTRAL_WINDOW_ID", np.array([0, 0], np.int32))
        t.putcol("POLARIZATION_ID", np.array([0, 0], np.int32))
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("DATA_DESC_ID", (np.arange(NROW) % 2).astype(np.int32))
    with pytest.raises(pipe.Refused, match="2 data descriptions.*W4"):
        pipe.preflight(config, pipe.inspect_ms(ms), ["flag"])
    # Two spectral windows of different widths (criterion 6 as frozen).
    widths = make_ms(tmp_path / "w.ms")
    with core_ms_write.open_table(widths / "SPECTRAL_WINDOW", readonly=False) as t:
        t.addrows(1)
        t.putcell("CHAN_FREQ", 1, 1.6e9 + 1e6 * np.arange(8))
        for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
            t.putcell(col, 1, np.full(8, 1e6))
        t.putcol("NUM_CHAN", np.array([NCHAN, 8], np.int32))
    with core_ms_write.open_table(widths / "DATA_DESCRIPTION", readonly=False) as t:
        t.addrows(1)
        t.putcol("SPECTRAL_WINDOW_ID", np.array([0, 1], np.int32))
        t.putcol("POLARIZATION_ID", np.array([0, 0], np.int32))
    with core_ms_write.open_table(widths, readonly=False) as t:
        t.putcol("DATA_DESC_ID", (np.arange(NROW) % 2).astype(np.int32))
    with pytest.raises(pipe.Refused, match="differ in shape.*W4"):
        pipe.inspect_ms(widths)
    with pytest.raises(SystemExit) as exc:
        cli("flag", write_config(tmp_path), widths)
    assert exc.value.code == 2 and not flagversions.versions(widths)


def test_unknown_fields_are_refused_before_anything_is_written(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path, name="c.yaml")
    text = config.read_text(encoding="utf-8").replace("target: [TGT]", "target: [NOPE]")
    config.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli("run", config, ms)
    assert exc.value.code == 2 and not flagversions.versions(ms)


def test_the_running_probe_never_signals_off_posix_or_itself(monkeypatch):
    import socket

    def kill(pid, sig):
        raise AssertionError("os.kill must not be called")

    entry = {"host": socket.gethostname(), "pid": os.getpid()}
    monkeypatch.setattr(pipe.os, "kill", kill)
    assert pipe._alive(entry) is False  # its own pid
    monkeypatch.setattr(pipe.os, "name", "nt")
    assert pipe._alive({**entry, "pid": 1}) is False
    assert pipe._alive({"host": "elsewhere", "pid": 1}) is False


def test_a_second_command_on_a_locked_run_directory_is_refused(tmp_path):
    """E5: the lock holds on every OS (Windows had none before), so a second
    command cannot write the same MS while the first runs."""
    ms = tmp_path / "x.ms"
    second = pipe.RunDir(tmp_path / "run", ms)
    with (
        pipe.RunDir(tmp_path / "run", ms).locked(),
        pytest.raises(pipe.Refused, match="in use by another rang-core command"),
        second.locked(),
    ):
        pass
    with pipe.RunDir(tmp_path / "run", ms).locked() as again:
        assert again.state["stages"] == {}


def test_research_stages_moved(capsys):
    with pytest.raises(SystemExit) as exc:
        core_cli.main(["flags", "-h"])
    # E5-40: exit 2, the hint on stderr.
    assert exc.value.code == 2
    assert "rang-core research flags -h" in capsys.readouterr().err
    core_cli.main(["research", "-h"])
    assert "stages and verbs" in capsys.readouterr().out


def test_config_check_and_defaults(tmp_path, capsys):
    ms = make_ms(tmp_path / "x.ms")
    config = write_config(tmp_path)
    cli("config", "check", config, ms)
    # Owner decision E5-28: the default run.stages is the whole chain.
    assert "valid for flag, calibrate, apply, image, selfcal" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli("config", "check", DATA / "e2a.yaml")
    err = capsys.readouterr().err
    assert "image.auto_mask" in err and "task C2" not in err  # K, G, B, A run (C2e)
    assert "task G4" not in err  # masks run (G4)
    assert "task C5" not in err  # selfcal runs (C5)
    cli("config", "defaults")
    assert capsys.readouterr().out == core_config.defaults_yaml()


def test_cli_imports_no_numpy_for_the_new_commands():
    probe = (
        "import sys\n"
        "import rang.core_cli as c\n"
        "assert 'numpy' not in sys.modules and 'yaml' not in sys.modules\n"
        "print('ok')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "ok"


def test_the_multiscale_image_options_reach_gemclean():
    """G5 (research/g5-multiscale.md): multiscale and its options are passed to
    gemclean; an option without multiscale is a configuration error."""
    image = {
        "size": [64, 64],
        "scale": "2asec",
        "multiscale": True,
        "multiscale_scales": [0, 5, 12.5],
        "multiscale_max_scales": 3,
        "multiscale_scale_bias": 0.7,
        "multiscale_shape": "gaussian",
        "multiscale_gain": 0.1,
    }
    config, errors = core_config.resolve({"version": 1, "image": image})
    assert errors == []
    assert [
        r for r in core_config.refusals(config, ["image"]) if r.path.startswith("image")
    ] == []
    args = pipe.gemclean_arguments(config["image"], "DATA", 0, "out/img", "x.ms")
    pairs = list(itertools.pairwise(args))
    assert "-multiscale" in args
    assert ("-multiscale-scales", "0.0,5.0,12.5") in pairs
    assert ("-multiscale-max-scales", "3") in pairs
    assert ("-multiscale-scale-bias", "0.7") in pairs
    assert ("-multiscale-shape", "gaussian") in pairs
    assert ("-multiscale-gain", "0.1") in pairs
    assert args[-1] == "x.ms"
    plain, _ = core_config.resolve(
        {"version": 1, "image": {"size": [64, 64], "scale": "2asec"}}
    )
    flags = pipe.gemclean_arguments(plain["image"], "DATA", 0, "out/img", "x.ms")
    assert not [f for f in flags if f.startswith("-multiscale")]
    alone, _ = core_config.resolve(
        {"version": 1, "image": {**image, "multiscale": False}}
    )
    refused = {r.path for r in core_config.refusals(alone, ["image"])}
    assert {
        "image.multiscale_scales",
        "image.multiscale_max_scales",
        "image.multiscale_scale_bias",
        "image.multiscale_shape",
        "image.multiscale_gain",
    } <= refused
    assert "G5" not in core_config.TASKS


def test_the_mask_taper_and_uv_options_reach_gemclean():
    """G4 (research/g4-masks.md): masks, tapers and uv limits are passed to
    gemclean only when set; the automatic mask needs mgain and an
    auto_threshold below it."""
    image = {
        "size": [64, 64],
        "scale": "2asec",
        "mgain": 0.8,
        "auto_threshold": 1.0,
        "auto_mask": 6.0,
        "abs_auto_mask": 0.001,
        "auto_mask_nmiter": 3,
        "fits_mask": "mask.fits",
        "taper_gaussian": "10asec",
        "taper_tukey": 5000.0,
        "taper_inner_tukey": 200.0,
        "minuv_l": 300.0,
        "maxuv_l": 20000.0,
        "minuvw_m": 150.0,
        "maxuvw_m": 5000.0,
    }
    config, errors = core_config.resolve({"version": 1, "image": image})
    assert errors == []
    assert [
        r for r in core_config.refusals(config, ["image"]) if r.path.startswith("image")
    ] == []
    args = pipe.gemclean_arguments(config["image"], "DATA", 0, "out/img", "x.ms")
    pairs = list(itertools.pairwise(args))
    for flag, value in (
        ("-auto-mask", "6.0"),
        ("-abs-auto-mask", "0.001"),
        ("-auto-mask-nmiter", "3"),
        ("-fits-mask", "mask.fits"),
        ("-taper-gaussian", "10asec"),
        ("-taper-tukey", "5000.0"),
        ("-taper-inner-tukey", "200.0"),
        ("-minuv-l", "300.0"),
        ("-maxuv-l", "20000.0"),
        ("-minuvw-m", "150.0"),
        ("-maxuvw-m", "5000.0"),
    ):
        assert (flag, value) in pairs
    plain, _ = core_config.resolve(
        {"version": 1, "image": {"size": [64, 64], "scale": "2asec"}}
    )
    flags = pipe.gemclean_arguments(plain["image"], "DATA", 0, "out/img", "x.ms")
    assert not [f for f in flags if "mask" in f or "taper" in f or "uv" in f]
    bad, _ = core_config.resolve(
        {
            "version": 1,
            "image": {
                "size": [64, 64],
                "scale": "2asec",
                "auto_mask": 3.0,
                "auto_threshold": 3.0,
                "uvrange": ">150",
                "pol": "IQUV",
            },
        }
    )
    refused = {r.path for r in core_config.refusals(bad, ["image"])}
    assert {"image.auto_mask", "image.auto_threshold", "image.uvrange"} <= refused
    assert "G4" not in core_config.TASKS


def test_the_spectral_image_options_reach_gemclean():
    """G3 (research/g3-spectral.md): channels out, joined channels, the
    polynomial fit and channel averaging are passed to gemclean; a fit
    without joined channels is refused as a configuration error."""
    image = {
        "size": [64, 64],
        "scale": "2asec",
        "channels_out": 4,
        "join_channels": True,
        "fit_spectral_pol": 2,
        "average_channels": 2,
    }
    config, errors = core_config.resolve({"version": 1, "image": image})
    assert errors == []
    assert [
        r for r in core_config.refusals(config, ["image"]) if r.path.startswith("image")
    ] == []
    args = pipe.gemclean_arguments(config["image"], "DATA", 0, "out/img", "x.ms")
    pairs = list(itertools.pairwise(args))
    assert ("-average-channels", "2") in pairs
    assert ("-channels-out", "4") in pairs
    assert ("-fit-spectral-pol", "2") in pairs
    assert "-join-channels" in args
    assert args[-1] == "x.ms"
    plain, _ = core_config.resolve(
        {"version": 1, "image": {"size": [64, 64], "scale": "2asec"}}
    )
    flags = pipe.gemclean_arguments(plain["image"], "DATA", 0, "out/img", "x.ms")
    assert not {"-channels-out", "-join-channels", "-fit-spectral-pol"} & set(flags)
    assert "-no-update-model-required" in flags  # G6: written through WriteBack
    assert not {"-scans", "-unit-weights"} & set(flags)
    w6 = pipe.gemclean_arguments(plain["image"], "DATA", 0, "o", "x.ms", [4, 6], True)
    assert ("-scans", "4,6") in list(itertools.pairwise(w6))
    assert "-unit-weights" in w6 and w6[-1] == "x.ms"
    assert "-average-channels" not in flags
    for change in (
        {"join_channels": False},
        {"channels_out": 1},
        {"fit_spectral_pol": 0},
    ):
        config, errors = core_config.resolve(
            {"version": 1, "image": {**image, **change}}
        )
        assert errors == []
        refused = core_config.refusals(config, ["image"])
        assert ("image.fit_spectral_pol", "") in {(r.path, r.task) for r in refused}
        with pytest.raises(core_config.ConfigError):
            core_config.validate(
                {"version": 1, "image": {**image, **change}}, ["image"]
            )


def test_the_polarisation_options_reach_gemclean():
    """G9 (research/g9-stokes.md): image.pol and image.join_polarizations
    are passed to gemclean, only when not the defaults; E2-B's image
    section validates; a join of one polarisation, XY and circular
    correlations are refused."""
    image = {
        "size": [64, 64],
        "scale": "2asec",
        "pol": "IQUV",
        "join_polarizations": True,
    }
    config, errors = core_config.resolve({"version": 1, "image": image})
    assert errors == []
    assert core_config.refusals(config, ["image"]) == []
    args = pipe.gemclean_arguments(config["image"], "DATA", 0, "out/img", "x.ms")
    assert ("-pol", "IQUV") in list(itertools.pairwise(args))
    assert "-join-polarizations" in args
    plain, _ = core_config.resolve(
        {"version": 1, "image": {"size": [64, 64], "scale": "2asec"}}
    )
    flags = pipe.gemclean_arguments(plain["image"], "DATA", 0, "out/img", "x.ms")
    assert "-pol" not in flags and "-join-polarizations" not in flags
    for change, path in (
        ({"pol": "I"}, "image.join_polarizations"),
        ({"pol": "XY,YX"}, "image.pol"),
        ({"pol": "RR,LL"}, "image.pol"),
        ({"write_model": True}, "image.write_model"),  # Stokes I only (G6)
        ({"multiscale": True}, "image.multiscale"),  # one polarisation (G5)
    ):
        config, errors = core_config.resolve(
            {"version": 1, "image": {**image, **change}}
        )
        assert errors == []
        assert path in {r.path for r in core_config.refusals(config, ["image"])}
    assert core_config.parse_pol("xx,yy") == ["XX", "YY"]
    assert core_config.parse_pol("VUQI") == ["I", "Q", "U", "V"]
    config, errors = core_config.resolve(
        {"version": 1, "image": {**image, "join_polarizations": False}}
    )
    assert errors == []
    assert "image.pol" in {r.path for r in core_config.refusals(config, ["selfcal"])}
    raw = core_config.load(DATA / "e2b.yaml")
    config, errors = core_config.resolve(raw)
    assert errors == []
    assert not [
        r
        for r in core_config.refusals(config, ["image"])
        if r.path.startswith("image.") and r.path != "image.fields"
    ]
