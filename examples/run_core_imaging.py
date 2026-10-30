"""Replay the archived imaging track on the Rang core and compare it with the
archive and the host reproduction (research/core-i-imaging-replay.md).

    .venv/bin/python examples/run_core_imaging.py OUTPUT [ARCHIVE] [EXPORT]

OUTPUT is a fresh `outputs/core-i-<date>-NN` directory; ARCHIVE the archived
imaging run (default `outputs/tv-next-imaging-wsl-20261029-01`) and EXPORT
task C's python-casacore export used to check the core's Measurement Set
reads (default `outputs/core-c-20261029-01/inputs`). The run writes
`result.json`, `side-effects.json` and `images/`, then runs the frozen
comparator against `research/results/gain-tv-next-imaging.json` (with the
archived FITS pixels) and against the archive run's own `result.json`,
writing `compare-archive.json` and `compare-host.json`. Exit status 1 when
either comparison fails.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from rang import core_imaging


def main(argv):
    if len(argv) not in (2, 3, 4):
        print(__doc__, file=sys.stderr)
        return 2
    output = Path(argv[1])
    archive = Path(argv[2]) if len(argv) > 2 else core_imaging.DEFAULT_ARCHIVE
    export = Path(argv[3]) if len(argv) > 3 else core_imaging.DEFAULT_EXPORT
    core_imaging.run(output, archive, export)
    code = 0
    for name, oracle, images in (
        ("archive", core_imaging.DEFAULT_ORACLE, archive / "images"),
        ("host", archive / "result.json", None),
    ):
        try:
            core_imaging.compare(
                output / "result.json",
                oracle,
                output / f"compare-{name}.json",
                output / "images" if images is not None else None,
                images,
            )
        except SystemExit as exc:
            code = exc.code or 1
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
