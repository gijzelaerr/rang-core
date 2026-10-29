from rangtoy.core_compare import compare, key_and_parent


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
