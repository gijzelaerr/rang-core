"""Cut verbatim from tests/test_flagging_next.py at 43dc3c7 (task P8, research/p8-history.md).

Tests a file that moved to history/; not collected (testpaths = tests).
The repository paths below are the pre-move ones: run at 43dc3c7.
"""

from pathlib import Path


def test_native_scatter_recipe_matches_runtime_cabs_and_frozen_plan():
    # Static contract here: root also runs real Stimela schema validation in the
    # pinned container. Unit tests need no undeclared host YAML dependency.
    root = Path(__file__).resolve().parents[1]
    recipe = (root / "recipes/tv-flagging-next.yaml").read_text()
    assert "backend: {select: native}" in recipe
    assert "  for_loop:\n    var: track\n    over: tracks\n    scatter: 3\n" in recipe
    main = recipe.split("\ntv-flagging-next:\n", 1)[1]
    assert main.index("\n    initialize:\n") < main.index("\n    branches:\n")
    assert main.index("\n    branches:\n") < main.index("\n    gather:\n")
    assert "tracks: [trend, prospective, signal, provenance, imaging]" in main
    assert "caracal-dir: {dtype: Directory, required: true}" in main
    assert "caracal_dir: {dtype: Directory, required: true}" in recipe
    assert "caracal_dir: =recipe.caracal-dir" in main
    assert "path_policies: {mkdir_parent: false}" in main
    assert recipe.rstrip().endswith("DEFAULT: tv-flagging-next")
    plan = (root / "research/flagging-next-results.md").read_text()
    for required in (
        "TRAIN",
        "TEST",
        "18QC",
        "1.5GiB",
        "8GiB",
        "107/109",
        "not OS quotas",
        "at most18QC",
    ):
        assert required in plan
