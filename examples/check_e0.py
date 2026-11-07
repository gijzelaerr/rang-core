"""Task E0's comparisons (research/e0-refant-extend.md sections 3 and 4).

    check_e0.py refant <run> <case> ...   R1-R6: rang.cal_refant against
                                          CARACal's own get_refant
    check_e0.py extend <run> <case> ...   X1-X5: rang.flag_extend against CASA
                                          6.7.6.14 flagdata(mode='extend')

Each run directory gets a `.code/` snapshot beside it. The CARACal side runs
in the msutils venv of `tools/oracles/e0/msutils-venv.sh` (E0_MSUTILS, default
~/Build/tmp/20261106-e0-msutils); the CASA side in `rang-o-casa:6.7.6.14`
(`check_formats.docker`). Run it under `flock ~/.rang-heavy.lock`.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import check_formats as cf
from check_c2e import snapshot, write
from check_gain import rfi_flags
from rang import cal_refant, core_ms, flag_extend

E0 = ROOT / "tools/oracles/e0"
OUTPUTS = Path.home() / "Github/rang/outputs"
CARACAL = OUTPUTS / "c1-sources-20261105/caracal-8f7bb363"
MSUTILS = Path(
    os.environ.get("E0_MSUTILS", Path.home() / "Build/tmp/20261106-e0-msutils")
)
CASA = "/opt/casa/bin/python"
SLICE = OUTPUTS / "o-casa-20261030-01/work.ms"
A1 = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth")
A1S = A1 / "small/a1-small.ms"
A1F = A1 / "full/a1-full.ms"
H128 = Path("/mnt/d/rang/outputs/c2e-20261106-h128/holdout128/a1-holdout128.ms")
POLH = Path("/mnt/d/rang/outputs/c6-20261106-sets/polholdout/a1-polholdout.ms")

# CARACal 8f7bb363 polcal_worker.py, "preliminary flags".
CARACAL_FLAGDATA = {
    "mode": "extend",
    "ntime": "60s",
    "combinescans": True,
    "growtime": 80.0,
    "growfreq": 80.0,
    "growaround": True,
    "flagnearfreq": True,
    "flagneartime": True,
    "flagbackup": False,
}
REFANT_CASES = {"R1": SLICE, "R2": A1S, "R3": A1F, "R4": A1S, "R5": A1S, "R6": A1S}
EXTEND_CASES = {
    "X1": {"src": SLICE, "rfi": None, "fields": ["J1939-6342"], "scans": None},
    "X2": {"src": A1S, "rfi": A1S, "fields": ["3C286-SIM", "J1939-6342"], "scans": None},
    "X3": {"src": H128, "rfi": H128, "fields": ["3C286-SIM", "J1939-6342"],
           "scans": [8, 14, 22, 23]},
    "X4": {"src": A1S, "rfi": A1S, "fields": ["SIM-TARGET", "SIM-GCAL"], "scans": None,
           "edit": "x4"},
    "X5": {"src": POLH, "rfi": POLH, "fields": ["3C286-SIM", "J1939-6342"], "scans": None},
    # Post hoc (section 9): X1-X4 never fire growfreq or extendpols (A1's RFI
    # mask flags all four correlations alike), so X6 flags the mask in XX only
    # and adds an 85 % band burst in XX at 3C286-SIM's second integration.
    "X6": {"src": A1S, "rfi": A1S, "fields": ["3C286-SIM", "J1939-6342"], "scans": None,
           "rfi_mode": "xx_burst"},
}  # fmt: skip


def docker(args, mounts, label):
    return cf.docker(cf.CASA_IMAGE, args, mounts, label)


def cols(ms, names):
    with core_ms.open_table(ms) as t:
        return {n: t.getcol(n) for n in names}


def names_of(ms, sub, col="NAME"):
    with core_ms.open_table(Path(ms) / sub) as t:
        return [str(n) for n in t.getcol(col)]


def sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


# -- refant ------------------------------------------------------------------------


def refant_input(run, case):
    """The MS of `case` in its own msdir (CARACal writes its JSON there)."""
    src = REFANT_CASES[case]
    msdir = run / case / "msdir"
    msdir.mkdir(parents=True)
    ms = msdir / f"{case.lower()}.ms"
    if case == "R3":
        ms.symlink_to(src)  # 35.8 GB: read in place, read-only opens only
        return ms
    mounts = [(run / case, "/run", "rw"), (E0, "/e0", "ro"), (src, "/src/ms", "ro")]
    docker(["python3", "-I", "/e0/casa_side.py", "prepare", "/src/ms",
            f"/run/msdir/{ms.name}"], mounts, f"{case} copy")  # fmt: skip
    names = names_of(ms, "ANTENNA")
    spec = {}
    if case == "R4":
        spec["antenna_names"] = names[::-1]
    elif case == "R5":
        spec["telescope"] = "E0-NOWHERE"
    elif case == "R6":
        spec["antenna_names"] = [names[(i + 5) % len(names)] for i in range(len(names))]
        spec["telescope"] = "meerkat"
    if spec:
        write(run / case / "edit.json", spec)
        docker(["python3", "-I", "/e0/casa_side.py", "edit", f"/run/msdir/{ms.name}",
                "/run/edit.json"], mounts, f"{case} edit")  # fmt: skip
    if case == "R4":
        # Flag every row of the antenna whose (new) name sorts first among
        # those that qualify by position.
        first = cal_refant.caracal_refant(ms).names[0]
        ant = names_of(ms, "ANTENNA").index(first)
        c = cols(ms, ["ANTENNA1", "ANTENNA2"])
        rows = np.flatnonzero((c["ANTENNA1"] == ant) | (c["ANTENNA2"] == ant))
        write(run / case / "edit2.json", {"flag_rows": rows.tolist()})
        docker(["python3", "-I", "/e0/casa_side.py", "edit", f"/run/msdir/{ms.name}",
                "/run/edit2.json"], mounts, f"{case} flag {first}")  # fmt: skip
        (run / case / "flagged_antenna.txt").write_text(first + "\n")
    return ms


def refant(run, cases):
    report = {"cases": {}}
    for case in cases:
        ms = refant_input(run, case)
        try:
            choice = cal_refant.caracal_refant(ms)
            got, refused, record = ",".join(choice.names), None, choice.record()
        except cal_refant.NoReferenceAntenna as exc:
            got, refused, record = "", str(exc), None
        out = run / case / "caracal.json"
        start = time.perf_counter()
        proc = subprocess.run(
            [str(MSUTILS / "venv/bin/python"), "-I", str(E0 / "caracal_refant.py"),
             str(CARACAL), str(ms.parent), ms.name, str(out)],
            capture_output=True, text=True, check=False,
            env={**os.environ, "HOME": str(MSUTILS / "home")},
        )  # fmt: skip
        wall = time.perf_counter() - start
        (run / case / "caracal.log").write_text(proc.stdout + proc.stderr)
        if proc.returncode:
            raise SystemExit(f"{case}: CARACal's get_refant failed, see caracal.log")
        ref = json.loads(out.read_text())
        fallback_ok = ref["fallback_to_antenna_0"] == (case == "R5")

        def agrees(want, got=got, refused=refused, fallback_ok=fallback_ok):
            return (want is not None and got == want
                    and (want != "" or refused is not None) and fallback_ok)  # fmt: skip

        report["cases"][case] = {
            "ms": str(ms), "rang": got, "rang_refused": refused,
            "caracal": ref["refant"], "caracal_error": ref["get_refant_error"],
            "caracal_antenna_part": ref["antenna_part_refant"],
            "caracal_fallback_to_antenna_0": ref["fallback_to_antenna_0"],
            "caracal_wall_s": wall, "rang_record": record, "versions": ref["versions"],
            "pass": bool(agrees(ref["refant"])),
            # post hoc (section 9): get_refant's lines on msutils' antenna part
            "pass_antenna_part": bool(agrees(ref["antenna_part_refant"])),
        }  # fmt: skip
    report["pass"] = all(c["pass"] for c in report["cases"].values())
    write(run / "refant.json", report)
    return report


# -- extend ------------------------------------------------------------------------


def x4_edit(ms):
    """Section 3.2's X4 edits, as rows of the prepared copy."""
    c = cols(ms, ["FIELD_ID", "SCAN_NUMBER", "TIME", "ANTENNA1", "ANTENNA2"])
    names = names_of(ms, "ANTENNA")
    spec = {"time": []}

    def scan_rows(s):
        rows = np.flatnonzero(c["SCAN_NUMBER"] == s)
        assert set(c["FIELD_ID"][rows]) == {3}, s  # SIM-TARGET
        return rows, np.unique(c["TIME"][rows])

    rows4, t4 = scan_rows(4)
    last4 = rows4[np.isin(c["TIME"][rows4], t4[-4:])]
    spec["scan"] = {"rows": last4.tolist(), "value": 99}
    spec["time"].append({"rows": rows4[c["TIME"][rows4] == t4[-1]].tolist(),
                         "value": float(t4[0] + 59.985)})  # fmt: skip
    rows6, t6 = scan_rows(6)
    spec["time"].append({"rows": rows6[c["TIME"][rows6] == t6[-1]].tolist(),
                         "value": float(t6[0] + 59.995)})  # fmt: skip
    a, b = names.index("m000"), names.index("m004")
    bl = (c["ANTENNA1"][rows4] == a) & (c["ANTENNA2"][rows4] == b)
    spec["remove_rows"] = rows4[bl & np.isin(c["TIME"][rows4], t4[1:3])].tolist()
    assert len(spec["remove_rows"]) == 2
    return spec


def extend(run, cases):
    report = {"cases": {}}
    for case in cases:
        d = EXTEND_CASES[case]
        cdir = run / case
        (cdir / "edits").mkdir(parents=True)
        mounts = [(cdir, "/run", "rw"), (E0, "/e0", "ro"), (d["src"], "/src/ms", "ro")]
        args = [
            "python3",
            "-I",
            "/e0/casa_side.py",
            "prepare",
            "/src/ms",
            "/run/prepared.ms",
        ]
        if d["rfi"] is not None:
            with core_ms.open_table(d["src"]) as t:
                nchan = t.getcol("FLAG", 0, 1).shape[1]
            rfi = rfi_flags(
                d["src"], str(d["rfi"]).replace(".ms", ".rfi_mask.npz"), nchan
            )
            if d.get("rfi_mode") == "xx_burst":
                rfi[..., 1:] = False
                c = cols(d["src"], ["FIELD_ID", "SCAN_NUMBER", "TIME"])
                rows = np.flatnonzero((c["FIELD_ID"] == 1) & (c["SCAN_NUMBER"] == 2))
                t = np.unique(c["TIME"][rows])
                burst = rows[c["TIME"][rows] == t[1]]
                rfi[burst, : int(0.85 * nchan), 0] = True
            np.savez(cdir / "edits/rfi.npz", flag=rfi)
            args.append("/run/edits/rfi.npz")
        docker(args, mounts, f"{case} prepare")
        if d.get("edit") == "x4":
            write(cdir / "edits/x4.json", x4_edit(cdir / "prepared.ms"))
            docker(["python3", "-I", "/e0/casa_side.py", "edit", "/run/prepared.ms",
                    "/run/edits/x4.json"], mounts, f"{case} edit")  # fmt: skip
        for side in ("casa", "rang"):
            shutil.copytree(cdir / "prepared.ms", cdir / f"{side}.ms")
        calls = [dict(CARACAL_FLAGDATA, field=f) for f in d["fields"]]
        if d["scans"]:
            for c in calls:
                c["scan"] = ",".join(str(s) for s in d["scans"])
        write(cdir / "calls.json", calls)
        docker([CASA, "-I", "/e0/casa_side.py", "flagdata", "/run/casa.ms",
                "/run/calls.json", "/run/casa-result.json"], mounts, f"{case} flagdata")  # fmt: skip
        fields = names_of(cdir / "rang.ms", "FIELD")
        ids = [fields.index(f) for f in d["fields"]]
        start = time.perf_counter()
        summary = flag_extend.extend_ms(cdir / "rang.ms", ids, scans=d["scans"],
                                        flag_backup="e0_before_extend", stage="e0")  # fmt: skip
        wall = time.perf_counter() - start
        report["cases"][case] = compare(cdir, ids, d["scans"], summary, wall)
    report["pass"] = all(c["pass"] for c in report["cases"].values())
    write(run / "extend.json", report)
    return report


def compare(cdir, ids, scans, summary, wall):
    names = ["FLAG", "FLAG_ROW", "FIELD_ID", "SCAN_NUMBER"]
    other = ["DATA", "WEIGHT", "SIGMA", "TIME", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2"]
    before = cols(cdir / "prepared.ms", names)
    casa = cols(cdir / "casa.ms", names + other)
    rang = cols(cdir / "rang.ms", names + other)
    sel = np.isin(before["FIELD_ID"], ids)
    if scans:
        sel &= np.isin(before["SCAN_NUMBER"], scans)
    cf_, rf_, bf = casa["FLAG"], rang["FLAG"], before["FLAG"]
    cells = int(sel.sum() * np.prod(bf.shape[1:]))
    added = int((cf_[sel] & ~bf[sel]).sum())
    unflagged = int((~cf_[sel]).sum())
    out = {
        "rows": len(bf),
        "selected_rows": int(sel.sum()),
        "flag_equal": bool(np.array_equal(cf_, rf_)),
        "flag_cells_differ": int((cf_ != rf_).sum()),
        "flag_differ_rows": np.flatnonzero((cf_ != rf_).any(axis=(1, 2)))[:20].tolist(),
        "rang_only": int((rf_ & ~cf_).sum()),
        "casa_only": int((cf_ & ~rf_).sum()),
        "flag_row_equal_and_unchanged": bool(
            np.array_equal(casa["FLAG_ROW"], rang["FLAG_ROW"])
            and np.array_equal(casa["FLAG_ROW"], before["FLAG_ROW"])
        ),
        "outside_selection_unchanged": bool(
            np.array_equal(cf_[~sel], bf[~sel]) and np.array_equal(rf_[~sel], bf[~sel])
        ),
        "other_columns_equal": {n: sha(casa[n]) == sha(rang[n]) for n in other},
        "selected_cells": cells,
        "flagged_before": int(bf[sel].sum()),
        "casa_added": added,
        "casa_added_fraction": added / cells if cells else 0.0,
        "casa_unflagged_fraction": unflagged / cells if cells else 0.0,
        "rang_added_by_rule": summary["added"],
        "rang_chunks": summary["chunks"],
        "rang_wall_s": wall,
        "flag_sha256": {"casa": sha(cf_), "rang": sha(rf_)},
    }
    out["non_saturated"] = bool(
        out["casa_added_fraction"] >= 0.01 and out["casa_unflagged_fraction"] >= 0.10
    )
    out["pass"] = bool(
        out["flag_equal"]
        and out["flag_row_equal_and_unchanged"]
        and out["outside_selection_unchanged"]
        and all(out["other_columns_equal"].values())
    )
    return out


# -- the command (also checked, not gated) ----------------------------------------

COMMAND_CONFIG = """\
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], xcal: [3C286-SIM], target: [SIM-TARGET]}
data: {chunk_rows: 700}
calibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: %(refant)s
  uvrange: ">150"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}
  secondary:
    terms:
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
  polcal:
    model: {source: nrao, name: 3C286}
    feed_angle_rotation: -90.0
    extendflags: %(extend)s
    terms:
      - {type: Gpol, name: Gpol, solint: 60s, preapply: [K, G, B]}
      - {type: KCROSS, name: Kcross, solint: inf, preapply: [K, G, B, Gpol]}
      - {type: Xf, name: Xf, solint: inf, combine: scan, preapply: [K, G, B, Gpol, Kcross]}
      - {type: Df, name: Df, field: [fcal], solint: inf, combine: scan,
         clip: [-0.6, 0.6], preapply: [K, G, B, Kcross, Xf]}
run: {stages: [calibrate]}
"""
RANG_CORE = ROOT / ".venv/bin/rang-core"


def command(run):
    """`rang-core calibrate` on A1 small (prepared) with refant auto and
    extendflags (a), with the names written out (b) and without the
    extension (c): (a) equals (b) in every table and FLAG; (c) differs."""
    mounts = [(run, "/run", "rw"), (E0, "/e0", "ro"), (A1S, "/src/ms", "ro")]
    with core_ms.open_table(A1S) as t:
        nchan = t.getcol("FLAG", 0, 1).shape[1]
    np.savez(run / "rfi.npz", flag=rfi_flags(A1S, str(A1S).replace(".ms", ".rfi_mask.npz"),
                                              nchan))  # fmt: skip
    docker(["python3", "-I", "/e0/casa_side.py", "prepare", "/src/ms", "/run/prepared.ms",
            "/run/rfi.npz"], mounts, "command prepare")  # fmt: skip
    variants = {"a": ("auto", "true"), "b": ("[m008, m024, m032]", "true"),
                "c": ("auto", "false")}  # fmt: skip
    out = {}
    for name, (refant_value, ext) in variants.items():
        d = run / name
        d.mkdir()
        ms = d / "a1.ms"
        shutil.copytree(run / "prepared.ms", ms)
        config = d / "config.yaml"
        config.write_text(COMMAND_CONFIG % {"refant": refant_value, "extend": ext})
        start = time.perf_counter()
        with open(d / "calibrate.log", "w") as fh:
            done = subprocess.run([str(RANG_CORE), "calibrate", str(config), str(ms),
                                   "--run-dir", str(d / "rundir")],
                                  stdout=fh, stderr=subprocess.STDOUT, check=False)  # fmt: skip
        summary = json.loads((d / "rundir/calibrate/summary.json").read_text())
        tables = {}
        for t in summary["tables"]:
            digest = hashlib.sha256()
            with core_ms.open_table(t["path"]) as tab:
                for col in sorted(tab.colnames()):
                    digest.update(col.encode())
                    try:
                        v = np.asarray(tab.getcol(col))
                    except OSError as exc:  # an unwritten column, such as WEIGHT
                        digest.update(str(exc).encode())
                        continue
                    digest.update(repr(v.tolist()).encode() if v.dtype == object
                                  else np.ascontiguousarray(v).tobytes())  # fmt: skip
            tables[t["name"]] = digest.hexdigest()
        out[name] = {"returncode": done.returncode, "wall_s": time.perf_counter() - start,
                     "flag_sha256": sha(cols(ms, ["FLAG"])["FLAG"]), "tables": tables,
                     "refant_auto": summary.get("refant_auto", {}).get("names"),
                     "steps": [s["type"] for s in summary["steps"]],
                     "extend": [s.get("extended") for s in summary["steps"]
                                if s["type"] == "extend"]}  # fmt: skip
    a, b, c = out["a"], out["b"], out["c"]
    report = {
        "variants": out,
        "a_equals_b": a["flag_sha256"] == b["flag_sha256"]
        and a["tables"] == b["tables"],
        "a_differs_from_c": a["flag_sha256"] != c["flag_sha256"],
        "names": a["refant_auto"],
        "extend_first_in_polcal": a["steps"].index("extend")
        == a["steps"].index("Gpol") - 1,
    }
    report["pass"] = bool(all(v["returncode"] == 0 for v in out.values())
                          and report["a_equals_b"] and report["a_differs_from_c"]
                          and report["names"] == ["m008", "m024", "m032"]
                          and report["extend_first_in_polcal"])  # fmt: skip
    write(run / "command.json", report)
    return report


def main(argv):
    if len(argv) == 3 and argv[1] == "command":
        run = Path(argv[2])
        if run.exists():
            raise SystemExit(f"{run} exists; choose a fresh run directory")
        run.mkdir(parents=True)
        snapshot(run)
        report = command(run)
        write(run / "timings.json", cf.TIMINGS)
        print(
            json.dumps({k: v for k, v in report.items() if k != "variants"}, indent=1)
        )
        return 0 if report["pass"] else 1
    if len(argv) < 4 or argv[1] not in ("refant", "extend"):
        print(__doc__)
        return 2
    run = Path(argv[2])
    if run.exists():
        raise SystemExit(f"{run} exists; choose a fresh run directory")
    run.mkdir(parents=True)
    snapshot(run)
    cases = argv[3:]
    report = refant(run, cases) if argv[1] == "refant" else extend(run, cases)
    write(run / "timings.json", cf.TIMINGS)
    brief = {c: {k: v for k, v in r.items() if k in (
        "rang", "caracal", "pass", "flag_equal", "flag_cells_differ", "non_saturated",
        "casa_added_fraction", "casa_unflagged_fraction", "rang_added_by_rule")}
        for c, r in report["cases"].items()}  # fmt: skip
    print(json.dumps({"pass": report["pass"], "cases": brief}, indent=1))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
