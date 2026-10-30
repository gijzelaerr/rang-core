from rang.core_compare import compare, key_and_parent


def classify(path):
    key, parent = key_and_parent(path)
    if key == "seconds":
        return "excluded"
    if key == "noise":
        return "reported"
    if key == "benefit":
        return "difference"
    if key in ("tv",) or parent == "losses":
        return "float"
    return "exact"


def test_classes_and_failures():
    archived = {
        "seconds": 5.0,
        "trial": "a",
        "tv": 1.0,
        "losses": {"train": 2.0, "test": None},
        "benefit": 1e-13,
        "noise": 1e-17,
        "items": [{"tv": 3.0}],
    }
    core = {
        "trial": "a",
        "tv": 1.0 + 1e-12,
        "losses": {"train": 2.0, "test": None},
        "benefit": 5e-13,
        "noise": 9e-17,
        "items": [{"tv": 3.0}],
    }
    report = compare(archived, core, classify)
    assert report["failures"] == []
    assert report["excluded"] == 1
    assert report["classes"]["reported"]["max_rel"] > 1
    core["items"][0]["tv"] = 3.1
    core["trial"] = "b"
    del core["losses"]
    failures = compare(archived, core, classify)["failures"]
    paths = sorted(str(f["path"]) for f in failures)
    assert paths == sorted([str(["items", 0, "tv"]), str(["trial"]), str(["losses"])])


def test_key_and_parent_skip_indices():
    assert key_and_parent(["cases", 0, "losses", "train"]) == ("train", "losses")
    assert key_and_parent(["cases", 3]) == ("cases", None)


# --- Task P9 (research/p9-cli.md): the engine holds every comparator.


def test_tolerance_table_accumulated_reports_and_reason():
    from rang.core_compare import INJ_TOLERANCES, injections_classify

    archived = {
        "polar_gauge_gain_mse_to_clean": 1e-13,
        "target_train_occupancy": 0.5,
        "tv": 2.0,
        "nested": {"a": 1},
    }
    core = {
        "polar_gauge_gain_mse_to_clean": 9e-13,  # abs 8e-13 <= 1e-12: passes
        "target_train_occupancy": 0.5 * (1 + 1e-11),  # 1e-11 > 1e-12: fails
        "tv": 2.0 * (1 + 1e-10),  # 1e-10 <= 1e-9: passes
        "nested": 3,
    }
    report = {"classes": {}, "excluded": 0, "failures": []}
    for key, value in archived.items():
        compare(
            value,
            core[key],
            injections_classify,
            root=[key],
            tolerances=INJ_TOLERANCES,
            report=report,
            not_dict="missing or not a dict",
        )
    assert sorted(report["classes"]) == ["distance", "float", "injection_float"]
    reasons = {
        str(f["path"]): f.get("reason", f.get("class")) for f in report["failures"]
    }
    assert reasons == {
        str(["target_train_occupancy"]): "injection_float",
        str(["nested"]): "missing or not a dict",
    }


def test_injections_classify_takes_the_key_before_a_trailing_index():
    from rang.core_compare import injections_classify

    assert injections_classify(["cases", 0, "delta_abs_jy_quantiles", 2]) == (
        "injection_float"
    )
    assert injections_classify(["cases", 0, "losses", "train"]) == "float"


def test_unwrap_reads_the_new_archive_and_the_legacy_layouts():
    from rang.core_compare import unwrap

    result = {"x": 1}
    assert unwrap({"schema": "rang.archive", "version": 1, "result": result}) is result
    assert unwrap({"raw_result": result}, "raw_result") is result
    assert unwrap(result, "raw_result") is result
    assert unwrap(result) is result


def test_run_returns_the_verdict_contract(tmp_path, capsys):
    import json

    from rang import core_compare

    result = tmp_path / "result.json"
    oracle = tmp_path / "oracle.json"
    result.write_text(json.dumps({"records": [], "tv": 1.0}))
    oracle.write_text(json.dumps({"raw_result": {"records": [], "tv": 1.0}}))
    verdict = core_compare.run(
        "trend", [str(result), str(oracle), str(tmp_path / "r.json")]
    )
    assert set(verdict) == {"name", "exit", "passed", "failures", "counts", "receipt"}
    assert verdict["passed"] is True and verdict["exit"] == 0
    assert verdict["counts"] == {"classes": {"exact": 1}, "excluded": 0}
    assert json.loads(capsys.readouterr().out)["passed"] is True
    assert (
        core_compare.main("trend", [str(result), str(oracle), str(tmp_path / "s.json")])
        == 0
    )
    assert (tmp_path / "r.json").read_bytes() == (tmp_path / "s.json").read_bytes()


def test_backends_skips_cli_receipts(tmp_path):
    from rang.core_compare import backends_files

    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "a.run.rang-receipt.json").write_text("{}")
    (tmp_path / "x.log").write_text("")
    assert [p.as_posix() for p in backends_files(tmp_path)] == ["a.json"]
