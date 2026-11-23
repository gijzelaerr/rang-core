"""Gate 3c rerun on a Nyquist grid (research/gate3c-rerun.md): E2-N on nash and
E2-A on glacier, each in its own run root R holding the leg's MS copy.

    python g3r.py flaghash MS VERSION_TABLE OUT.json
    python g3r.py unit MS R                      matched state (WEIGHT_SPECTRUM away, unit WEIGHT)
    python g3r.py gemclean MS R ARM PY [THREADS] ARM n-dirty | n-clean | d-dirty
    python g3r.py wsclean MS R ARM KIND THREADS  ARM c3 | n; KIND dirty | clean
    python g3r.py logcheck R LABEL               WSClean log: minimal inversion, counts, maxuvw
    python g3r.py diff A_DIR B_DIR TAG OUT.json  WSClean dirty images against archived ones (R3)

R/c3/rang-run is the leg's own run directory with the frozen 3-arcsec image
stage (summary.json, config.resolved.json, FITS). Every arm's rang images go
to R/<arm>/rang-run/image/<sub>/ with a summary.json whose argv is the gemclean
call run, so e2_score3c_a.py reads them unchanged. WSClean's images go to
R/ws-<arm>/ (dirty and clean together, as the original oracle directory).
Containers run through e2_post.docker (Docker in WSL) or, on Linux, through
e2n_nash's apptainer substitute. Every WSClean call gets
-no-min-grid-resolution.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RES = HERE.parent
sys.path[:0] = [str(RES / "e2n-scripts"), str(RES / "e2-acceptance-scripts")]
if sys.platform.startswith("linux"):
    import e2n_nash  # noqa: F401  (patches e2_post.docker with apptainer)
import e2_post as P

NYQ = {"size": "6144", "scale": "2asec"}  # section 2: 12,288 arcsec kept
BLOCK = 4000

UNIT_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table, makecoldesc
ms, out = sys.argv[1:3]
t = table(ms, readonly=False, ack=False)
cols = t.colnames()
assert "G3R_WEIGHT" not in cols and "CORRECTED_DATA" in cols
n = t.nrows()
t.renamecol("WEIGHT_SPECTRUM", "G3R_WEIGHT_SPECTRUM")
t.renamecol("WEIGHT", "G3R_WEIGHT")
desc = t.getcoldesc("G3R_WEIGHT")
t.addcols(makecoldesc("WEIGHT", desc),
          {"TYPE": "StandardStMan", "NAME": "G3RUnitWeight", "SPEC": {}})
w = np.ones((n, t.getcell("G3R_WEIGHT", 0).shape[0]), np.float32)
t.putcol("WEIGHT", w)
rec = {"columns": t.colnames(), "rows": n}
t.close()
json.dump(rec, open(out, "w"), indent=1)
print(json.dumps(rec))
"""


def write(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def _hash(table_path):
    from rang import core_ms

    hf, hr = hashlib.sha256(), hashlib.sha256()
    with core_ms.open_table(table_path) as t:
        n = t.nrows
        for r0 in range(0, n, BLOCK):
            k = min(BLOCK, n - r0)
            hf.update(
                np.ascontiguousarray(
                    np.asarray(t.getcol("FLAG", r0, k), bool)
                ).tobytes()
            )
            hr.update(
                np.ascontiguousarray(
                    np.asarray(t.getcol("FLAG_ROW", r0, k), bool)
                ).tobytes()
            )
    return {
        "rows": int(n),
        "flag_sha256": hf.hexdigest(),
        "flag_row_sha256": hr.hexdigest(),
    }


def flaghash(ms, version, out):
    """R1: FLAG and FLAG_ROW of the MS against a saved flag version."""
    a, b = _hash(ms), _hash(version)
    rec = {
        "ms": str(ms),
        "version": str(version),
        "ms_hash": a,
        "version_hash": b,
        "equal": a == b,
    }
    write(out, rec)
    print(json.dumps({"equal": rec["equal"]}))
    return 0 if rec["equal"] else 1


def unit(ms, r):
    ms, r = Path(ms), Path(r)
    (r / "g3r_unit.py").write_text(UNIT_PY, encoding="utf-8")
    return P.docker(r, P.FORMATS_IMAGE, P.inplace_mounts(ms, r),
                    f"{P.QC_PY} -I /p/g3r_unit.py /c/{ms.name} /p/unit.json", "unit", 1)  # fmt: skip


def _entry(r):
    s = json.loads(
        (Path(r) / "c3" / "rang-run" / "image" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    (entry,) = s["images"]
    return s, entry


def _set(argv, key, *vals):
    out = list(argv)
    i = out.index(key)
    out[i + 1 : i + 1 + len(vals)] = list(vals)
    return out


def arm_argv(r, arm, ms):
    """The image stage's gemclean argv with only -name, -size, -scale (and
    -niter 0 for a dirty arm, -average-channels 1 for arm D) changed."""
    s, entry = _entry(r)
    gem = list(entry["argv"])
    sub = re.split(r"[\\/]", gem[gem.index("-name") + 1])[-2]
    name = Path(r) / arm / "rang-run" / "image" / sub / "image"
    gem = _set(gem, "-name", str(name))
    gem = _set(gem, "-size", NYQ["size"], NYQ["size"])
    gem = _set(gem, "-scale", NYQ["scale"])
    if arm.endswith("dirty"):
        gem = _set(gem, "-niter", "0")
    if arm.startswith("d-"):
        gem = _set(gem, "-average-channels", "1")
    gem[-1] = str(Path(ms))
    return s, entry, gem, name


def gemclean(ms, r, arm, py, threads="8"):
    r = Path(r)
    s, entry, gem, name = arm_argv(r, arm, ms)
    base = r / arm / "rang-run"
    name.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        r / "c3" / "rang-run" / "config.resolved.json", base / "config.resolved.json"
    )
    i = gem.index("-name")
    cmd = [py, "-m", "rang.gemclean", *gem[i:]]
    t0 = time.perf_counter()
    with open(r / f"{arm}-gemclean.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(
            cmd, stdout=fh, stderr=subprocess.STDOUT, check=False
        ).returncode
    entry = dict(entry, argv=cmd)
    write(base / "image" / "summary.json", dict(s, images=[entry]))
    write(r / f"{arm}-gemclean-run.json",
          {"exit": rc, "argv": cmd, "seconds": time.perf_counter() - t0,
           "fits": sorted(p.name for p in name.parent.glob("*.fits"))})  # fmt: skip
    return rc


def wsclean(ms, r, arm, kind, threads):
    """WSClean 3.7 on CORRECTED_DATA in the matched state: arm c3 at the
    frozen 4096 x 3 arcsec, arm n at the Nyquist grid; -no-min-grid-resolution."""
    from rang import core_ms

    ms, r = Path(ms), Path(r)
    if "G3R_WEIGHT" not in P.ms_columns(ms):
        raise SystemExit("run unit first")
    _s, entry = _entry(r)
    gem = list(entry["argv"])
    if arm == "n":
        gem = _set(gem, "-size", NYQ["size"], NYQ["size"])
        gem = _set(gem, "-scale", NYQ["scale"])
    if "-scans" in gem:
        with core_ms.open_table(ms) as t:
            fids = np.asarray(t.getcol("FIELD_ID", 0, t.nrows))
            scans = np.asarray(t.getcol("SCAN_NUMBER", 0, t.nrows))
        listed = {int(x) for x in gem[gem.index("-scans") + 1].split(",")}
        have = {int(x) for x in np.unique(scans[fids == int(entry["field_id"])])}
        if not have <= listed:
            raise SystemExit(
                f"-scans {sorted(listed)} selects part of the field: {sorted(have)}"
            )
    sub = f"ws-{arm}"
    (r / sub).mkdir(parents=True, exist_ok=True)
    tag = entry["field"].replace("+", "p").replace("-", "m")
    if sys.platform.startswith("linux"):
        tmp_host, temp = r / f"tmp-{arm}-{kind}", f"/p/tmp-{arm}-{kind}"
        tmp_host.mkdir(exist_ok=True)
        mounts = P.inplace_mounts(ms, r)
    else:  # WSL ext4, not 9p
        tmp_host, temp = f"$HOME/g3r-tmp-{arm}-{kind}", "/t"
        mounts = [*P.inplace_mounts(ms, r), (tmp_host, "/t")]
    argv, dropped = P.wsclean_argv(gem, name=f"/p/{sub}/{tag}-{kind}", column="CORRECTED_DATA",
                                   threads=threads, temp=temp, ms_inside=f"/c/{ms.name}",
                                   dirty=kind == "dirty")  # fmt: skip
    argv.insert(-1, "-no-min-grid-resolution")
    label = f"{sub}-{kind}"
    t0 = time.perf_counter()
    rc = P.docker(r, P.WSCLEAN_IMAGE, mounts, " ".join(argv), label, int(threads))
    if isinstance(tmp_host, Path):
        shutil.rmtree(tmp_host, ignore_errors=True)
    else:
        subprocess.run(["wsl", "-e", "bash", "-lc", f"rm -rf {tmp_host}"], check=False)
    write(r / f"{label}-run.json",
          {"exit": rc, "argv": argv, "gemclean_argv": gem, "dropped": dropped,
           "seconds": time.perf_counter() - t0,
           "fits": sorted(p.name for p in (r / sub).glob(f"{tag}-{kind}*.fits"))})  # fmt: skip
    return rc


def logcheck(r, label):
    text = (Path(r) / f"{label}.out").read_text(encoding="utf-8", errors="replace")
    rec = {"label": label,
           "minimal_inversion_lines": re.findall(r"Minimal inversion size.*", text),
           "gridded_visibility_counts": [int(x) for x in re.findall(r"Gridded visibility count: (\d+)", text)],
           "maxuvw_lambda": [float(x) for x in re.findall(r"maxuvw=([0-9.]+) lambda", text)]}  # fmt: skip
    if rec["maxuvw_lambda"]:
        m = max(rec["maxuvw_lambda"])
        rec["nyquist_lower_bound_arcsec"] = float(np.degrees(1 / (2 * m)) * 3600)
    write(Path(r) / f"{label}-logcheck.json", rec)
    print(
        json.dumps({k: v for k, v in rec.items() if k != "gridded_visibility_counts"})
    )
    return 0


def diff(a, b, tag, out):
    """R3: WSClean dirty images in A against those in B (same names), max
    |difference| over the peak of B, per image."""
    from e1b_score import _open

    per = {}
    for p in sorted(Path(b).glob(f"{tag}-dirty-*-dirty.fits")):
        x, y = _open(Path(a) / p.name)[0], _open(p)[0]
        per[p.name] = float(np.max(np.abs(x - y)) / np.max(np.abs(y)))
    rec = {"a": str(a), "b": str(b), "per_image": per, "max": max(per.values()) if per else None,
           "tolerance": 1e-6}  # fmt: skip
    rec["met"] = rec["max"] is not None and rec["max"] <= 1e-6
    write(out, rec)
    print(json.dumps({"max": rec["max"], "met": rec["met"], "n": len(per)}))
    return 0


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    sys.exit({"flaghash": flaghash, "unit": unit, "gemclean": gemclean, "wsclean": wsclean,
              "logcheck": logcheck, "diff": diff}[step](*args))  # fmt: skip
