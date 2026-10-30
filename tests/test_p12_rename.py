"""Task P12 (research/p12-rename.md): the package is `rang`, the extension
`rang._core`, the distribution `rang-core`; the old name `rangtoy` is gone."""

import importlib.metadata
import importlib.util
import subprocess
import sys


def test_old_package_name_is_not_importable():
    assert importlib.util.find_spec("rangtoy") is None


def test_package_and_extension_names():
    import rang
    import rang._core

    assert rang.__name__ == "rang"
    assert rang._core.__name__ == "rang._core"


def test_distribution_is_rang_core():
    dist = importlib.metadata.distribution("rang-core")
    assert dist.metadata["Name"] == "rang-core"
    scripts = {
        e.name: e.value for e in dist.entry_points if e.group == "console_scripts"
    }
    assert scripts == {"rang-core": "rang.core_cli:main"}


def test_isolated_interpreter_finds_no_rangtoy():
    # The installed environment, not this test session's sys.path, decides.
    code = "import importlib.util as u; import rang, rang._core; print(u.find_spec('rangtoy'))"
    out = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    assert out.stdout.strip() == "None"
