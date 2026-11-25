# SPDX-License-Identifier: MIT
"""`rang-core flag CONFIG STORE` and the flag versions of an MSv4 store
(research/msv4-cli.md), on the public fixture's xradio 1.3.1 store of m05
(two partitions: a kill between their writes leaves a mixed store).
Everything skips without the `[msv4]` extra."""

import json
import shutil
import zipfile
from pathlib import Path

import pytest
from rang import msv4

pytestmark = pytest.mark.skipif(
    not msv4.has_msv4(), reason="the [msv4] extra is absent"
)

DATA = Path(__file__).resolve().parent / "data" / "msv4"
STRATEGY = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "results"
    / "e2-acceptance-scripts"
    / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)


class Killed(BaseException):
    """Stands for a kill: neither `execute` nor the CLI catch it."""


def _files(path):
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in sorted(Path(path).rglob("*"))
        if p.is_file()
    }


def _config(path, extra=""):
    path.write_text(
        f"version: 1\n{extra}flag: {{strategy: {STRATEGY.as_posix()}}}\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="module")
def m05(tmp_path_factory):
    """(before, api): the store as converted, and as `rang.msv4.flag` leaves it."""
    top = tmp_path_factory.mktemp("m05")
    with zipfile.ZipFile(DATA / "m05.zip") as z:
        z.extractall(top)
    before = top / "m05.ps.zarr"
    api = top / "api.ps.zarr"
    shutil.copytree(before, api)
    msv4.flag(api, _config(top / "flag.yaml"))
    return _files(before), _files(api), before


def _store(tmp_path, m05):
    store = tmp_path / "s.ps.zarr"
    shutil.copytree(m05[2], store)
    return store


def _cli(*argv):
    from rang import core_cli

    return core_cli.dispatch(["--no-pin-threads", *[str(a) for a in argv]])


def _partition_files(files, name):
    return {k: v for k, v in files.items() if k.startswith(f"{name}/")}


def test_is_store(tmp_path, m05):
    assert msv4.is_store(m05[2])
    (tmp_path / "x.ms").mkdir()
    (tmp_path / "x.ms" / "table.dat").write_bytes(b"")
    (tmp_path / "x.ms" / "zarr.json").write_text("{}")
    assert not msv4.is_store(tmp_path / "x.ms")
    assert not msv4.is_store(tmp_path / "missing")


def test_cli_equals_api_and_keeps_a_run_directory(tmp_path, m05):
    store = _store(tmp_path, m05)
    state = _cli("flag", _config(tmp_path / "c.yaml"), store)
    assert _files(store) == m05[1]
    entry = state["stages"]["flag"]
    assert entry["status"] == "done" and entry["flag_version"].startswith("rang_flag_")
    run = Path(str(store) + ".rang-run")
    names = {p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file()}
    assert {"config.resolved.json", "lock", "state.json", "flag/summary.json"} <= names
    assert any(n.startswith("receipts/flag-") for n in names)
    summary = json.loads((run / "flag" / "summary.json").read_text())
    assert summary["rang_original_saved_now"] is True
    assert summary["restored_before"] is None
    assert summary["rows_flagged"] == sum(p["rows"] for p in summary["partitions"])
    assert {g["partition"] for g in summary["groups"]} == {
        p["name"] for p in summary["partitions"]
    }
    assert 0 <= summary["flagged_before"] <= summary["flagged_after"] <= 1
    from rang import msv4_flags

    assert [n for n, _ in msv4_flags.versions(store)] == [
        "rang_original",
        entry["flag_version"],
    ]
    journal = msv4_flags.read_journal(store)
    assert journal["state"] == "closed" and journal["written"] == ["FLAG"]
    # A finished stage is skipped, nothing written.
    _cli("flag", tmp_path / "c.yaml", store)
    assert _files(store) == m05[1]


def test_versions_round_trip(tmp_path, m05):
    from rang import msv4_flags

    store = _store(tmp_path, m05)
    config = _config(tmp_path / "c.yaml")
    _cli("flag", config, store)
    msv4_flags.restore_flags(store, "rang_original")
    assert _files(store) == m05[0]
    state = _cli("flag", config, store, "--force")
    assert _files(store) == m05[1]
    entry = state["stages"]["flag"]
    rerun = entry["saved_before_restore"]
    assert rerun.startswith("rang_rerun_")
    msv4_flags.save(store, "m7_flagged")
    msv4_flags.restore_flags(store, rerun)  # the flags the rerun replaced
    assert _files(store) == m05[0]
    msv4_flags.restore_flags(store, "m7_flagged")
    assert _files(store) == m05[1]
    msv4_flags.restore_flags(store, "rang_original")
    assert _files(store) == m05[0]


def test_restore_refuses_another_array(tmp_path, m05):
    from rang import msv4_flags

    store = _store(tmp_path, m05)
    msv4_flags.save(store, "v")
    name, var = msv4_flags.flag_variables(store)[0]
    meta = store / name / var / "zarr.json"
    meta.write_text(meta.read_text().replace('"FLAG"', '"FLAG" '), encoding="utf-8")
    with pytest.raises(ValueError, match="not the array"):
        msv4_flags.restore(store, "v")


def _kill_after_first_partition(monkeypatch):
    real = msv4._write_flags
    calls = []

    def write(*args):
        real(*args)
        calls.append(args[2].name)
        raise Killed(calls[0])

    monkeypatch.setattr(msv4, "_write_flags", write)
    return calls


def test_interrupted_write_is_refused_or_recovered(tmp_path, m05, monkeypatch):
    from rang import msv4_flags

    store = _store(tmp_path, m05)
    config = _config(tmp_path / "c.yaml")
    calls = _kill_after_first_partition(monkeypatch)
    with pytest.raises(Killed):
        _cli("flag", config, store)
    monkeypatch.undo()
    first = calls[0]
    now = _files(store)
    names = {k.split("/")[0] for k in now if "/" in k}
    assert len(names) == 2
    assert _partition_files(now, first) == _partition_files(m05[1], first)
    (second,) = names - {first}
    assert _partition_files(now, second) == _partition_files(m05[0], second)
    assert _partition_files(m05[0], first) != _partition_files(m05[1], first)
    assert msv4_flags.read_journal(store)["written"] == ["FLAG"]
    # Another run directory: refused inside the stage, as on an MSv2 (exit 1).
    with pytest.raises(SystemExit) as exc:
        _cli("flag", config, store, "--run-dir", tmp_path / "other")
    assert exc.value.code == 1
    assert _files(store) == now
    # The run directory that saved the version: restores, then flags.
    _cli("flag", config, store)
    assert _files(store) == m05[1]
    summary = json.loads(
        (Path(str(store) + ".rang-run") / "flag" / "summary.json").read_text()
    )
    assert summary["restored_before"].startswith("rang_flag_")


def test_explicit_restore_after_a_kill(tmp_path, m05, monkeypatch):
    from rang import msv4_flags

    store = _store(tmp_path, m05)
    config = _config(tmp_path / "c.yaml")
    _kill_after_first_partition(monkeypatch)
    with pytest.raises(Killed):
        _cli("flag", config, store)
    monkeypatch.undo()
    version = msv4_flags.read_journal(store)["flag_backup"]
    msv4_flags.restore_flags(store, version)
    assert _files(store) == m05[0]
    assert msv4_flags.read_journal(store)["state"] == "restored"
    _cli("flag", config, store, "--run-dir", tmp_path / "fresh")
    assert _files(store) == m05[1]


def test_kill_before_any_write_is_not_refused(tmp_path, m05, monkeypatch):
    from rang import msv4_flags

    store = _store(tmp_path, m05)
    config = _config(tmp_path / "c.yaml")

    def mark(self, *_):
        raise Killed("before the first put")

    monkeypatch.setattr(msv4_flags.WriteSession, "mark_flag_write", mark)
    with pytest.raises(Killed):
        _cli("flag", config, store)
    monkeypatch.undo()
    assert _files(store) == m05[0]
    assert msv4_flags.read_journal(store)["written"] == []
    _cli("flag", config, store, "--run-dir", tmp_path / "fresh")
    assert _files(store) == m05[1]


def test_other_stages_and_bad_configs_are_refused_before_writing(tmp_path, m05):
    from rang import core_config, core_pipeline

    store = _store(tmp_path, m05)
    config_path = _config(tmp_path / "c.yaml")
    config = core_config.validate_file(config_path, ["flag"])
    with pytest.raises(core_pipeline.Refused, match="M5"):
        core_pipeline.execute(config, config_path, store, ["flag", "calibrate"])
    for stage in ("calibrate", "apply", "image", "selfcal"):
        with pytest.raises(SystemExit) as exc:
            _cli(stage, config_path, store)
        assert exc.value.code == 2
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        f"version: 1\nflag: {{strategy: {STRATEGY.as_posix()}, fields: ['0']}}\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        _cli("flag", bad, store)
    assert exc.value.code == 2
    assert _files(store) == m05[0]
    assert not Path(str(store) + ".flagversions").exists()
    assert not (Path(str(store) + ".rang-run") / "state.json").exists()
    _cli("config", "check", config_path, store, "--stage", "flag")
    with pytest.raises(SystemExit) as exc:
        _cli("config", "check", bad, store, "--stage", "flag")
    assert exc.value.code == 2
