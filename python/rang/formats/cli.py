"""`rang-core formats convert IN OUT` and `rang-core formats check PATH`
(research/dfio-formats.md).

`check` detects a file's format, reads it with the core's reader and prints
a JSON summary (exit 1 when it cannot be read). `convert` reads one format
and writes another of the same kind:

- sky models: Tigger `.lsm.html`, Tigger ASCII `.lsm`/`.txt`, WSClean
  source lists (`.txt` with a `Format =` line, or `.wsclean`), BBS
  `.skymodel` (read only);
- gains: a QuartiCal store (a directory with term groups), a CASA
  calibration table (a directory with `table.dat` and a `VisCal` keyword),
  an H5parm (`.h5`), a killMS solution file (`.npz`); a complex diagonal
  or full term converts to H5parm (amplitude000/phase000, XX and YY) and to
  killMS.

DicoModel files are read only and only with `--trust` (a restricted
unpickler; never on files from elsewhere).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SKY_SUFFIXES = (
    ".lsm.html",
    ".html",
    ".lsm",
    ".txt",
    ".wsclean",
    ".skymodel",
    ".bbs",
    ".sky",
)


def detect(path):
    """The format of `path`: a short name."""
    p = Path(path)
    name = p.name.lower()
    if p.is_dir():
        if (p / "table.dat").exists():
            from ._aipsio import table_keywords

            return (
                "casa-caltable" if "VisCal" in table_keywords(p) else "casacore-table"
            )
        if (p / ".zgroup").exists():
            return "quartical-store"
        raise ValueError(f"{path}: an unknown directory format")
    if name.endswith((".h5", ".h5parm")):
        return "h5parm"
    if name.endswith(".dicomodel"):
        return "dicomodel"
    if name.endswith(".npy"):
        return "clustercat"
    if name.endswith(".npz"):
        return "killms"
    if name.endswith(SKY_SUFFIXES):
        from . import sky

        return {
            "tigger-html": "tigger-html",
            "tigger-ascii": "tigger-ascii",
            "bbs": "bbs",
            "wsclean": "wsclean",
        }[sky.kind_of(path)]
    raise ValueError(f"{path}: unknown format")


def summary(path, trust=False):
    kind = detect(path)
    out = {"path": str(path), "format": kind}
    if kind in ("tigger-html", "tigger-ascii", "bbs", "wsclean"):
        from . import sky

        out.update(sky.summary(sky.load_any(path)))
    elif kind == "casa-caltable":
        from . import caltable

        out.update(caltable.read(path).summary())
    elif kind == "quartical-store":
        from . import quartical_store

        out["terms"] = quartical_store.summary(quartical_store.read(path))
    elif kind == "h5parm":
        from . import h5parm

        out["solsets"] = h5parm.summary(h5parm.read(path))
    elif kind == "killms":
        from . import killms

        out.update(killms.summary(killms.read(path)))
    elif kind == "clustercat":
        from . import sky

        cat = sky.read_clustercat(path)
        out.update({"rows": len(cat), "dtype": str(cat.dtype)})
    elif kind == "dicomodel":
        if not trust:
            raise SystemExit(
                "rang-core formats: a DicoModel is a pickle; pass --trust for files you made"
            )
        from . import sky

        out.update(sky.dicomodel_summary(sky.load_dicomodel(path)))
    else:
        raise SystemExit(f"rang-core formats: no reader for {kind}")
    return out


def _gains_of(path):
    """(gains (t, f, a, d, 2, 2), times, freqs, antennas) of a gain file."""
    kind = detect(path)
    if kind == "quartical-store":
        from . import quartical_store

        terms = quartical_store.read(path)
        part = next(iter(terms.values()))[0]
        return (
            part.gains_2x2(),
            part["gain_time"],
            part["gain_freq"],
            [str(a) for a in part["antenna"]],
        )
    if kind == "h5parm":
        from . import h5parm

        ss = next(iter(h5parm.read(path).values()))
        g = h5parm.diagonal_gains(ss)
        full = np.zeros(g.shape[:4] + (2, 2), complex)
        full[..., 0, 0], full[..., 1, 1] = g[..., 0], g[..., 1]
        amp = ss.soltabs["amplitude000"]
        return (
            full,
            amp.axis_values["time"],
            amp.axis_values["freq"],
            list(amp.axis_values["ant"]),
        )
    if kind == "killms":
        from . import killms

        s = killms.read(path)
        g = np.asarray(s["Sols"].G)
        t = (np.asarray(s["Sols"].t0) + np.asarray(s["Sols"].t1)) / 2
        f = np.mean(s["FreqDomains"], axis=1)
        return g, t, f, [str(x) for x in s["StationNames"]]
    raise SystemExit(
        f"rang-core formats: {kind} is not a gain grid this command converts"
    )


def convert(src, dst):
    kind = detect(src)
    if kind in ("tigger-html", "tigger-ascii", "bbs", "wsclean"):
        from . import sky

        sky.save_any(sky.load_any(src), dst)
        return {"from": kind, "to": sky.kind_of(dst), "sources": len(sky.load_any(dst))}
    gains, times, freqs, antennas = _gains_of(src)
    name = str(dst).lower()
    if name.endswith((".h5", ".h5parm")):
        from . import h5parm

        diag = np.stack([gains[..., 0, 0], gains[..., 1, 1]], -1)
        h5parm.write(
            dst, {"sol000": h5parm.diagonal_solset(diag, times, freqs, antennas)}
        )
        return {"from": kind, "to": "h5parm", "shape": list(diag.shape)}
    if name.endswith(".npz"):
        from . import killms, sky

        t = np.asarray(times, float)
        dt = np.diff(t).min() if len(t) > 1 else 1.0
        f = np.asarray(freqs, float)
        df = np.diff(f).min() if len(f) > 1 else 1.0
        domains = np.stack([f - df / 2, f + df / 2], 1)
        cat = np.zeros(gains.shape[3], sky.CLUSTERCAT_DTYPE)
        killms.write(
            dst, killms.make_sols(t - dt / 2, t + dt / 2, gains), antennas, cat, domains
        )
        return {"from": kind, "to": "killms", "shape": list(gains.shape)}
    raise SystemExit(f"rang-core formats: cannot write {dst} from {kind}")


def main(argv):
    parser = argparse.ArgumentParser(
        prog="rang-core formats", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    c = sub.add_parser("check", help="read a file and print a JSON summary")
    c.add_argument("path")
    c.add_argument(
        "--trust", action="store_true", help="allow a DicoModel (pickle) you made"
    )
    v = sub.add_parser("convert", help="read IN and write OUT in another format")
    v.add_argument("src")
    v.add_argument("dst")
    args = parser.parse_args(argv)
    try:
        result = (
            summary(args.path, args.trust)
            if args.verb == "check"
            else convert(args.src, args.dst)
        )
    except (OSError, ValueError, KeyError) as err:
        print(f"rang-core formats: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    print(json.dumps(result, indent=1, default=str))
    return result


__all__ = ["convert", "detect", "main", "summary"]
