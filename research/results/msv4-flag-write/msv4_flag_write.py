# SPDX-License-Identifier: MIT
"""The MSv4 round trip of the flag stage (research/msv4-flag-write.md).

Steps, in order (ROOT is `D:/rang/outputs/msv4-next-<date>`, `/mnt/d/...` in
WSL):

    copy ROOT                 (Windows) source MSs into ROOT/ms-src, MSv2-side copies
    msv2 ROOT                 (Windows, rang venv) `rang-core flag` on the copies
    convert ROOT              (WSL oracle venv) before, control and oracle stores
    flag ROOT                 (Windows, rang venv) `rang.msv4.flag` on copies of before
    xcheck ROOT OUT           (Windows, xradio venv, no rang) O1 and O3
    check ROOT RECEIPT XCHECK (Windows, rang venv) O2, O4, O5, the rule

Every step appends to ROOT/<step>.json; nothing outside ROOT is written.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

OLD = "D:/rang/outputs/msv4-20261116"
SOURCES = {
    "c1": f"{OLD}/fixture/outer_scans/1672727931_sdp_l0_scan_1.ms",
    "c2": f"{OLD}/fixture/outer_scans/1672727931_sdp_l0_scan_4.ms",
    "c3": f"{OLD}/fixture/outer_scans/1672727931_sdp_l0_scan_5.ms",
    "c4": f"{OLD}/fixture/outer_scans/1672727931_sdp_l0_scan_8.ms",
    "c5": f"{OLD}/fixture/outer_scans/1672727931_sdp_l0_scan_9.ms",
    "c6x": "D:/rang/outputs/e0-20261106-05/X3/casa.ms",
    "c8": f"{OLD}/ms/c8-scan9-gaps.ms",
    "c9": "D:/rang/outputs/msv2-edge-cases/20261113/ms/m05-var-spw-tssm",
    "c10": f"{OLD}/ms/c10-flag-row.ms",
    "c11": f"{OLD}/ms/c11-corrected-model.ms",
}
NOT_MEASURED = {"c7": "source MS deleted (amendment A1)"}
# Flag runs: case -> (source case, flag.column).
RUNS = {c: (c, "DATA") for c in SOURCES}
RUNS["c11c"] = ("c11", "CORRECTED_DATA")
DECIDING = ["c1", "c2", "c3", "c4", "c5", "c6x", "c8", "c9", "c11", "c11c"]
NON_VACUOUS = ["c1", "c2", "c3", "c4", "c5"]
ARMS = ("xradio", "xms-auto")
STRATEGY = "research/results/e2-acceptance-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml"
STRATEGY_SHA = "ce9ac66aba75c62e778eabbc951e8f9760447f7824f8fd37b26b91974ec71774"
HERE = Path(__file__).resolve()
REPO = HERE.parents[3]


def _native(path):
    path = str(path)
    if os.name != "nt" and len(path) > 2 and path[1] == ":":
        return f"/mnt/{path[0].lower()}{path[2:]}"
    return path


def _log(root, step, key, entry):
    path = Path(root) / f"{step}.json"
    log = json.loads(path.read_text()) if path.exists() else {}
    log[key] = entry
    path.write_text(json.dumps(log, indent=1, sort_keys=True, default=str))
    print(step, key, json.dumps(entry, default=str)[:400], flush=True)


def store(root, arm, case, kind):
    return Path(root) / "ps" / arm / f"{case}-{kind}.ps.zarr"


def config_path(root, column, processes=1):
    return Path(root) / f"config-{column}-p{processes}.yaml"


# --- copy (Windows) -----------------------------------------------------------


def copy(root):
    root = Path(root)
    for case, src in SOURCES.items():
        dst = root / "ms-src" / f"{case}.ms"
        if not dst.exists():
            shutil.copytree(src, dst)
        _log(root, "copy", case, {"from": src, "to": str(dst)})
    strategy = REPO / STRATEGY
    sha = hashlib.sha256(strategy.read_bytes()).hexdigest()
    assert sha == STRATEGY_SHA, sha
    shutil.copy(strategy, root / "strategy.yaml")
    for column in ("DATA", "CORRECTED_DATA"):
        for processes in (1, 2):
            config_path(root, column, processes).write_text(
                "version: 1\n"
                f"data: {{processes: {processes}}}\n"
                f"flag: {{strategy: strategy.yaml, column: {column}}}\n",
                encoding="utf-8",
            )


# --- msv2 (Windows, the stage as shipped) --------------------------------------


def _flag_cells(ms):
    import numpy as np
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        try:
            flag = np.asarray(t.getcol("FLAG"), bool)
        except OSError:  # variable cell shape (c9): row by row, flattened
            flag = np.concatenate(
                [np.asarray(t.getcol("FLAG", r, 1), bool).ravel() for r in range(t.nrows)]
            )
    return flag, hashlib.sha256(np.ascontiguousarray(flag).tobytes()).hexdigest()


def msv2(root, only=None):
    root = Path(root)
    for case, (src, column) in RUNS.items():
        if only and case not in only:
            continue
        dst = root / "msv2" / f"{case}.ms"
        for p in (dst, Path(str(dst) + ".flagversions"), Path(str(dst) + ".rang-run")):
            if p.exists():
                shutil.rmtree(p)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root / "ms-src" / f"{src}.ms", dst)
        before, sha_before = _flag_cells(dst)
        t0 = time.perf_counter()
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "rang.core_cli",
                "flag",
                str(config_path(root, column)),
                str(dst),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        seconds = time.perf_counter() - t0
        entry = {
            "ms": str(dst),
            "column": column,
            "returncode": proc.returncode,
            "seconds": round(seconds, 3),
            "stderr_tail": proc.stderr[-1500:],
        }
        if proc.returncode == 0:
            after, sha_after = _flag_cells(dst)
            entry.update(
                {
                    "cells": int(before.size),
                    "flagged_before": int(before.sum()),
                    "flagged_after": int(after.sum()),
                    "cells_changed": int((before != after).sum()),
                    "flag_sha256_before": sha_before,
                    "flag_sha256_after": sha_after,
                }
            )
        _log(root, "msv2", case, entry)


# --- convert (WSL, the writers) -------------------------------------------------


def convert(root, only=None, arms=ARMS):
    import xarray
    from xradio.measurement_set import convert_msv2_to_processing_set

    root = Path(_native(root))
    jobs = []
    for case, (src, _column) in RUNS.items():
        if only and case not in only:
            continue
        if case == src:
            jobs += [(case, "before", root / "ms-src" / f"{src}.ms")]
            jobs += [(case, "control", root / "ms-src" / f"{src}.ms")]
        jobs += [(case, "oracle", root / "msv2" / f"{case}.ms")]
    for case, kind, ms in jobs:
        for arm in arms:
            out = Path(_native(store(root, arm, case, kind)))
            if out.exists():
                shutil.rmtree(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter()
            entry = {"ms": str(ms)}
            try:
                if arm == "xradio":
                    convert_msv2_to_processing_set(
                        in_file=str(ms), out_file=str(out), persistence_mode="w"
                    )
                else:
                    tree = xarray.open_datatree(
                        str(ms), engine="xarray-ms:msv2", auto_corrs=True
                    )
                    tree.to_zarr(str(out))
                entry["outcome"] = "written"
            except Exception as exc:  # noqa: BLE001 (booked `writer fails`)
                entry["outcome"] = "writer fails"
                entry["error"] = f"{type(exc).__name__}: {exc}"[:500]
            entry["seconds"] = round(time.perf_counter() - t0, 3)
            _log(root, "convert", f"{case}/{arm}/{kind}", entry)


# --- flag (Windows, rang.msv4.flag) -------------------------------------------


def _before_of(case):
    return RUNS[case][0]


def flag(root, only=None, arms=ARMS):
    from rang import core_config, msv4

    root = Path(root)
    for case, (src, column) in RUNS.items():
        if only and case not in only:
            continue
        for arm in arms:
            before = store(root, arm, src, "before")
            if not before.exists():
                _log(root, "flag", f"{case}/{arm}", {"outcome": "no before store"})
                continue
            variants = [("rang-p1", 1, None), ("rang-p2", 2, None)]
            if case == "c5":
                variants.append(("rang-blocks", 1, 40))
            for kind, processes, max_rows in variants:
                out = store(root, arm, case, kind)
                if out.exists():
                    shutil.rmtree(out)
                shutil.copytree(before, out)
                cfg_path = config_path(root, column, processes)
                config = core_config.validate_file(cfg_path, ["flag"])
                t0 = time.perf_counter()
                entry = {
                    "store": str(out),
                    "processes": processes,
                    "max_rows": max_rows,
                }
                try:
                    summary = msv4.flag(out, config, cfg_path, max_rows=max_rows)
                    entry["outcome"] = "flagged"
                    entry["summary"] = summary
                except Exception as exc:  # noqa: BLE001 (booked refused)
                    entry["outcome"] = "refused"
                    entry["error"] = f"{type(exc).__name__}: {exc}"[:800]
                entry["seconds"] = round(time.perf_counter() - t0, 3)
                _log(root, "flag", f"{case}/{arm}/{kind}", entry)


# --- xcheck (Windows, xradio 1.3.1 only) ----------------------------------------


def _arrays(tree):
    import numpy as np

    out = {}
    for node in tree.subtree:
        path = node.path
        ds = node.to_dataset(inherit=False)
        for name, var in list(ds.data_vars.items()) + list(ds.coords.items()):
            kind = "var" if name in ds.data_vars else "coord"
            out[f"{path}:{kind}:{name}"] = np.asarray(var.values)
            out[f"{path}:{kind}:{name}:attrs"] = json.dumps(
                var.attrs, sort_keys=True, default=str
            )
            out[f"{path}:{kind}:{name}:dims"] = list(var.dims)
        out[f"{path}:attrs"] = json.dumps(node.attrs, sort_keys=True, default=str)
    return out


def _equal(a, b):
    import numpy as np

    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if not (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)):
            return False
        if a.dtype != b.dtype or a.shape != b.shape:
            return False
        if a.dtype.kind in "OUS":
            return a.tolist() == b.tolist()
        return np.ascontiguousarray(a).tobytes() == np.ascontiguousarray(b).tobytes()
    return a == b


def _diff(a, b):
    keys = sorted(set(a) | set(b))
    return sorted(k for k in keys if k not in a or k not in b or not _equal(a[k], b[k]))


def xcheck(root, out):
    from importlib.metadata import version

    from xradio.measurement_set import open_processing_set
    from xradio.schema.check import check_datatree

    root = Path(root)
    result = {
        "versions": {
            n: version(n) for n in ("xradio", "xarray", "zarr", "numcodecs", "numpy")
        }
    }
    for case, (src, _column) in RUNS.items():
        for arm in ARMS:
            paths = {
                "before": store(root, arm, src, "before"),
                "control": store(root, arm, src, "control"),
                "oracle": store(root, arm, case, "oracle"),
                "rang": store(root, arm, case, "rang-p1"),
            }
            entry = {}
            missing = [k for k, p in paths.items() if not p.exists()]
            if missing:
                entry["outcome"] = f"missing {missing}"
                result[f"{case}/{arm}"] = entry
                print(case, arm, entry, flush=True)
                continue
            trees = {k: open_processing_set(str(p)) for k, p in paths.items()}
            arrays = {k: _arrays(t) for k, t in trees.items()}
            nondet = _diff(arrays["before"], arrays["control"])
            o1_diff = _diff(arrays["oracle"], arrays["rang"])
            entry["nondeterministic"] = nondet
            entry["o1_differs"] = o1_diff
            entry["o1_differs_excluded"] = [k for k in o1_diff if k in nondet]
            entry["o1_differs_counted"] = [k for k in o1_diff if k not in nondet]
            entry["o1"] = "match" if not entry["o1_differs_counted"] else "mismatch"
            entry["rang_vs_before"] = _diff(arrays["before"], arrays["rang"])
            issues = {
                k: str(check_datatree(trees[k])) for k in ("before", "rang", "oracle")
            }
            entry["schema_issues"] = issues
            entry["o3"] = "match" if issues["before"] == issues["rang"] else "mismatch"
            result[f"{case}/{arm}"] = entry
            print(
                case, arm, entry["o1"], entry["o3"], entry["o1_differs"][:6], flush=True
            )
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True, default=str))


# --- check (Windows, rang venv) ----------------------------------------------------


def _files(path):
    path = Path(path)
    return {
        p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def _flag_vars(path):
    from rang import msv4

    ps = msv4.open_processing_set(path)
    return {f"{name}/{ps.partition(name).variables['flag']}/c/" for name in ps.names}


def _readback(root, arm, case):
    """FLAG of rang-p1 by rang.msv4, mapped by key to the flagged MSv2."""
    import numpy as np
    from rang import core_ms, msv4

    ms = Path(root) / "msv2" / f"{case}.ms"
    with core_ms.open_table(ms) as t:
        ref = {c: t.getcol(c) for c in ("TIME", "ANTENNA1", "ANTENNA2", "DATA_DESC_ID")}
        flag = np.asarray(t.getcol("FLAG"), bool) if _uniform(t) else None
        cells = (
            None
            if flag is not None
            else [t.getcol("FLAG", r, 1)[0] for r in range(t.nrows)]
        )
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
    ps = msv4.open_processing_set(store(root, arm, case, "rang-p1"))
    key = {}
    pads = 0
    for part in ps.partitions(RUNS[case][1] == "DATA" and "base" or "corrected"):
        rows = part.rows()
        pads += rows["PADS"]
        for i, (tm, a, b) in enumerate(
            zip(rows["TIME"], rows["ANTENNA1"], rows["ANTENNA2"])
        ):
            key[
                (tm, part.antenna_names[a], part.antenna_names[b], len(part.frequency))
            ] = rows["FLAG"][i]
    same = 0
    for r in range(len(ref["TIME"])):
        want = flag[r] if flag is not None else cells[r]
        got = key.get(
            (
                ref["TIME"][r],
                names[ref["ANTENNA1"][r]],
                names[ref["ANTENNA2"][r]],
                want.shape[0],
            )
        )
        if got is not None and got.tobytes() == want.tobytes():
            same += 1
    return {
        "rows": len(ref["TIME"]),
        "rows_equal": same,
        "store_rows": len(key),
        "pads": int(pads),
    }


def _uniform(t):
    try:
        t.getcol("FLAG")
        return True
    except Exception:  # noqa: BLE001 (variable shape: per row)
        return False


def check(root, receipt, xcheck_path):
    root = Path(root)
    x = json.loads(Path(xcheck_path).read_text())
    m2 = json.loads((root / "msv2.json").read_text())
    fl = json.loads((root / "flag.json").read_text())
    result = {
        "note": "research/msv4-flag-write.md",
        "commit": subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
        ).stdout.strip(),
        "xradio_reader": x.get("versions"),
        "strategy_sha256": STRATEGY_SHA,
        "not_measured": dict(NOT_MEASURED),
        "cases": {},
    }
    for case, (src, _column) in RUNS.items():
        side = m2.get(case, {})
        c = {
            "msv2": {
                k: side.get(k)
                for k in (
                    "returncode",
                    "seconds",
                    "cells",
                    "flagged_before",
                    "flagged_after",
                    "cells_changed",
                )
            }
        }
        if side.get("returncode") != 0:
            c["outcome"] = "not measured"
            c["reason"] = side.get("stderr_tail", "no msv2 run")[-400:]
            result["cases"][case] = c
            continue
        c["o5"] = "match" if side["cells_changed"] > 0 else "mismatch"
        for arm in ARMS:
            a = {}
            xe = x.get(f"{case}/{arm}", {})
            a["o1"] = xe.get("o1", xe.get("outcome", "not measured"))
            a["o1_differs_counted"] = xe.get("o1_differs_counted")
            a["o1_excluded"] = xe.get("o1_differs_excluded")
            a["o3"] = xe.get("o3", "not measured")
            p1 = store(root, arm, case, "rang-p1")
            before = store(root, arm, src, "before")
            runs = {
                k: fl.get(f"{case}/{arm}/{k}", {})
                for k in ("rang-p1", "rang-p2", "rang-blocks")
            }
            a["flag_outcome"] = {k: v.get("outcome") for k, v in runs.items() if v}
            a["seconds"] = {k: v.get("seconds") for k, v in runs.items() if v}
            if runs["rang-p1"].get("outcome") != "flagged":
                a["outcome"] = "refused"
                a["error"] = runs["rang-p1"].get("error")
                c[arm] = a
                continue
            fb, fp = _files(before), _files(p1)
            allowed = _flag_vars(p1)
            changed = sorted(k for k in set(fb) | set(fp) if fb.get(k) != fp.get(k))
            a["files_changed"] = len(changed)
            a["files_changed_outside_flag"] = [
                k for k in changed if not any(k.startswith(v) for v in allowed)
            ]
            a["o2"] = "match" if not a["files_changed_outside_flag"] else "mismatch"
            o4 = []
            for k in ("rang-p2", "rang-blocks"):
                if runs[k]:
                    same = (
                        runs[k].get("outcome") == "flagged"
                        and _files(store(root, arm, case, k)) == fp
                    )
                    o4.append(same)
                    a[f"o4_{k}"] = "match" if same else "mismatch"
            a["o4"] = "match" if o4 and all(o4) else "mismatch"
            a["readback"] = _readback(root, arm, case)
            ok = all(a[m] == "match" for m in ("o1", "o2", "o3", "o4"))
            a["outcome"] = "met" if ok else "not met"
            c[arm] = a
        result["cases"][case] = c
    deciding = [
        c
        for c in DECIDING
        if result["cases"].get(c, {}).get("outcome") != "not measured"
    ]
    xr = {c: result["cases"][c].get("xradio", {}) for c in deciding}
    o1_all = all(v.get("o1") == "match" for v in xr.values())
    rest = all(
        all(v.get(m) == "match" for m in ("o2", "o3", "o4")) for v in xr.values()
    )
    o5 = all(result["cases"].get(c, {}).get("o5") == "match" for c in NON_VACUOUS)
    refused = [c for c, v in xr.items() if v.get("outcome") == "refused"]
    if o1_all and rest and o5 and not refused:
        rule = "pass"
    elif o1_all and o5 and not refused:
        rule = "partial"
    else:
        rule = "fail"
    xms = {c: result["cases"][c].get("xms-auto", {}).get("outcome") for c in deciding}
    result["deciding_measured"] = deciding
    result["rule"] = rule
    result["xms_auto"] = xms
    Path(receipt).write_text(json.dumps(result, indent=1, sort_keys=True, default=str))
    print("rule", rule, "deciding", deciding, "xms-auto", xms)


def main(argv):
    step, root, *rest = argv
    only = None
    if rest and rest[-1].startswith("--only="):
        only = rest.pop()[7:].split(",")
    if step == "copy":
        copy(root)
    elif step == "msv2":
        msv2(root, only)
    elif step == "convert":
        convert(root, only)
    elif step == "flag":
        flag(root, only)
    elif step == "xcheck":
        xcheck(root, rest[0])
    elif step == "check":
        check(root, rest[0], rest[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
