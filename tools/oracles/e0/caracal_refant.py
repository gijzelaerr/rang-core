# SPDX-License-Identifier: GPL-3.0-or-later
"""CARACal's own `manage_antennas.get_refant` on one MS (task E0,
research/e0-refant-extend.md section 3.1).

    caracal_refant.py <caracal tree> <msdir> <msname> <result.json>

Runs in the msutils venv made by `msutils-venv.sh` (msutils 1.2.0, Python
3.11, numpy < 2, python-casacore, dask-ms, dask, bokeh) with HOME pointing
at a directory whose `.casarc` names casacore's measures data. CARACal's
`manage_antennas.py` is imported by file path and `get_refant` is called
with a stub pipeline and a stub Stimela recipe whose `run()` does what the
`cab/flagstats` cab's `run.py` does: `flag_stats.save_statistics(msname,
outfile=...)` with fields and antennas None (CARACal passes neither). The
cab writes the JSON to `output=pipeline.msdir`, where `get_refant` reads it.
"""

import hashlib
import importlib.util
import io
import json
import logging
import sys
from pathlib import Path


class Pipeline:
    def __init__(self, msdir):
        self.msdir = str(msdir)
        self.input = str(msdir)
        self.output = str(msdir)


class Recipe:
    """Stimela's recipe as get_refant uses it: add() then run()."""

    def __init__(self):
        self.jobs = []
        self.ran = []

    def add(self, cab, name, params, input=None, output=None, label=None):
        self.jobs.append((cab, name, dict(params), output))

    def run(self):
        from MSUtils import flag_stats

        for cab, name, params, output in self.jobs:
            assert cab == "cab/flagstats", cab
            msname = str(Path(output) / params["msname"])
            outfile = str(Path(output) / params["outfile"])
            flag_stats.save_statistics(
                msname, antennas=None, fields=None, outfile=outfile
            )
            self.ran.append(
                {"cab": cab, "step": name, "msname": msname, "outfile": outfile}
            )


def main(argv):
    tree, msdir, msname, result = Path(argv[1]), Path(argv[2]), argv[3], Path(argv[4])
    path = tree / "workers/utils/manage_antennas.py"
    spec = importlib.util.spec_from_file_location("manage_antennas", path)
    manants = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manants)
    log = io.StringIO()
    handler = logging.StreamHandler(log)
    logging.getLogger("MSUtils.flag_stats").addHandler(handler)
    logging.getLogger("MSUtils.flag_stats").setLevel(logging.DEBUG)
    recipe = Recipe()
    prefix = "e0"
    # crosscal_worker.py: manants.get_refant(pipeline, recipe, prefix, msname,
    # fields, pipeline.minbase[iobs], pipeline.maxdist[iobs], i), obsconf
    # defaults minbase 150, maxdist 1000 (schema examples, config_parser).
    error = None
    try:
        refant = manants.get_refant(
            Pipeline(msdir), recipe, prefix, msname, [], 150.0, 1000.0, 0
        )
    except Exception:  # noqa: BLE001 (msutils fails on some MSs, run -01)
        import traceback

        refant, error = None, traceback.format_exc()
    # Post hoc (research/e0-refant-extend.md section 9): get_refant's own
    # lines after the cab, on msutils' antenna part alone
    # (`antenna_flags_field`, which save_statistics calls third), written and
    # read through JSON as the cab's file is.
    from MSUtils import flag_stats

    part = {"Flag stats": [{}, {"antennas": flag_stats.antenna_flags_field(
        str(msdir / msname), None, None)}]}  # fmt: skip
    part = json.loads(json.dumps(part))
    core_ants = manants._get_core_antennas(part, 150.0, 1000.0)
    sorted_ants = sorted(core_ants.items(), key=lambda x: x[1])
    antenna_part = manants._prioritised_antennas(sorted_ants)
    import casacore
    import dask
    import daskms
    import MSUtils
    import numpy

    summary = msdir / f"{prefix}-flag-antenna_flag_summary.json"
    stats = json.loads(summary.read_text()) if summary.exists() else part
    out = {
        "refant": refant,
        "get_refant_error": error,
        "antenna_part_refant": antenna_part,
        "msname": msname,
        "ran": recipe.ran,
        "log": log.getvalue(),
        "fallback_to_antenna_0": "Using the first id antenna" in log.getvalue(),
        "antennas": stats["Flag stats"][1]["antennas"],
        "versions": {
            "python": sys.version,
            "numpy": numpy.__version__,
            "python-casacore": casacore.__version__,
            "dask": dask.__version__,
            "dask-ms": getattr(daskms, "__version__", "?"),
            "MSUtils": str(Path(MSUtils.__file__).parent),
            "flag_stats.py sha256": hashlib.sha256(
                (Path(MSUtils.__file__).parent / "flag_stats.py").read_bytes()
            ).hexdigest(),
            "manage_antennas.py sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    }
    result.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"refant": refant, "antenna_part": antenna_part, "error": bool(error),
                      "fallback": out["fallback_to_antenna_0"]}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
