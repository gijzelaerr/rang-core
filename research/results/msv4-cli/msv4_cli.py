# SPDX-License-Identifier: MIT
"""`rang-core flag CONFIG STORE` measured (research/msv4-cli.md, #5 M7).

Steps (ROOT is `D:/rang/outputs/msv4-cli-<date>`; M6's root is read only):

    copy ROOT              store copies of M6's `before` stores, MSv2 copies
    cli ROOT               C1 and C4: the command on each store, restores, --force
    kill ROOT              C5: K1, K2, K3 on stores and MSv2 copies of c5, c6x
    refuse ROOT            C7: other stages and bad configs on a c5 store
    products ROOT          C6: run directory against M6's MSv2 run directory
    xcheck ROOT OUT        (xradio venv, no rang) C2 and C3
    check ROOT OUT         the rule over the step logs and the xcheck

Every step appends to ROOT/<step>.json; nothing outside ROOT is written. The
harness runs the command as `python -m rang.core_cli` in the rang venv; a
kill is `os._exit` in a wrapper process (`_kill`), so nothing is cleaned up.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

M6 = Path("D:/rang/outputs/msv4-next-20261125")
CASES = {  # case -> (before store's case, flag.column)
    "c1": ("c1", "DATA"),
    "c2": ("c2", "DATA"),
    "c3": ("c3", "DATA"),
    "c4": ("c4", "DATA"),
    "c5": ("c5", "DATA"),
    "c6x": ("c6x", "DATA"),
    "c8": ("c8", "DATA"),
    "c9": ("c9", "DATA"),
    "c10": ("c10", "DATA"),
    "c11": ("c11", "DATA"),
    "c11c": ("c11", "CORRECTED_DATA"),
}
DECIDING = ["c1", "c2", "c3", "c4", "c5", "c6x", "c8", "c9", "c11", "c11c"]
NO_MSV2 = {"c9": "the MSv2 command refuses two cell shapes (M6, task W4)"}
NOT_MEASURED = {"c7": "source MS deleted (M6 amendment A1)"}
ARMS = ("xradio", "xms-auto")
KILL_CASES = ("c5", "c6x")
HERE = Path(__file__).resolve()


def _log(root, step, key, entry):
    path = Path(root) / f"{step}.json"
    log = json.loads(path.read_text()) if path.exists() else {}
    log[key] = entry
    path.write_text(json.dumps(log, indent=1, sort_keys=True, default=str))
    print(step, key, json.dumps(entry, default=str)[:300], flush=True)


def m6_store(arm, case, kind):
    return M6 / "ps" / arm / f"{case}-{kind}.ps.zarr"


def store(root, arm, case, kind):
    return Path(root) / "ps" / arm / f"{case}-{kind}.ps.zarr"


def config_path(column):
    return M6 / f"config-{column}-p1.yaml"


def _files(path):
    path = Path(path)
    return {
        p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def _fresh(src, dst):
    dst = Path(dst)
    for p in (dst, Path(f"{dst}.flagversions"), Path(f"{dst}.rang-run")):
        if p.exists():
            shutil.rmtree(p)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return dst


def _cli(*argv):
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "rang.core_cli", *[str(a) for a in argv]],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "argv": [str(a) for a in argv],
        "returncode": proc.returncode,
        "seconds": round(time.perf_counter() - t0, 3),
        "stderr_tail": proc.stderr[-1200:],
    }


def _killed(where, target, cfg, *rest):
    """Run the command in a wrapper that `os._exit`s at `where`."""
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            str(HERE),
            "_kill",
            where,
            str(target),
            str(cfg),
            *map(str, rest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "where": where,
        "returncode": proc.returncode,
        "seconds": round(time.perf_counter() - t0, 3),
        "stderr_tail": proc.stderr[-800:],
    }


def _kill_main(where, target, cfg, *rest):
    from rang import core_chunks, core_cli, msv4, msv4_flags

    if where == "store-k1":

        def mark(self, *_):
            os._exit(9)

        msv4_flags.WriteSession.mark_flag_write = mark
    elif where == "store-k2":
        real = msv4._write_flags

        def write(*args):
            real(*args)
            os._exit(9)

        msv4._write_flags = write
    elif where == "msv2-k1":

        def rows(*args, **kw):
            os._exit(9)

        core_chunks.write_rows = rows
    elif where == "msv2-k2":
        real_rows = core_chunks.write_rows

        def rows(*args, **kw):
            real_rows(*args, **kw)
            os._exit(9)

        core_chunks.write_rows = rows
    else:
        raise SystemExit(f"unknown kill point {where}")
    core_cli.dispatch(["flag", cfg, target, *rest])
    raise SystemExit(3)  # not killed: the kill point was never reached


# --- copy -----------------------------------------------------------------------


def copy(root):
    root = Path(root)
    entry = {}
    for case, (src, _) in CASES.items():
        for arm in ARMS:
            before = m6_store(arm, src, "before")
            entry[f"{case}/{arm}"] = str(before)
            _fresh(before, store(root, arm, case, "cli"))
    for case in KILL_CASES:
        for arm in ARMS:
            for k in ("k1a", "k1b", "k2", "k3"):
                _fresh(m6_store(arm, case, "before"), store(root, arm, case, k))
        for k in ("k1a", "k1b", "k2", "k3"):
            _fresh(M6 / "ms-src" / f"{case}.ms", root / "msv2" / f"{case}-{k}.ms")
    refuse = store(root, "xradio", "c5", "refuse")
    _fresh(m6_store("xradio", "c5", "before"), refuse)
    _log(root, "copy", "sources", entry)


# --- cli: C1 and C4 ---------------------------------------------------------------


def _snapshot(root, arm, case, target):
    """The run directory and versions as the first run left them (C6)."""
    out = Path(root) / "products" / arm / case
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(f"{target}.rang-run", out / "rang-run")
    shutil.copytree(f"{target}.flagversions", out / "flagversions", ignore=lambda d, n: [x for x in n if x.startswith("flags.")])  # fmt: skip
    return str(out)


def cli(root, only=None):
    from rang import msv4_flags

    root = Path(root)
    for case, (src, column) in CASES.items():
        if only and case not in only:
            continue
        for arm in ARMS:
            target = store(root, arm, case, "cli")
            want = _files(m6_store(arm, case, "rang-p1"))
            before = _files(m6_store(arm, src, "before"))
            entry = {"store": str(target)}
            run = _cli("flag", config_path(column), target)
            entry["run"] = run
            if run["returncode"]:
                entry["c1"] = "refused" if case not in NO_MSV2 else "refused (c9?)"
                _log(root, "cli", f"{case}/{arm}", entry)
                continue
            entry["c1"] = "match" if _files(target) == want else "mismatch"
            entry["snapshot"] = _snapshot(root, arm, case, target)
            names = [n for n, _ in msv4_flags.versions(target)]
            entry["versions_after_run"] = names
            steps = []
            t0 = time.perf_counter()
            msv4_flags.restore_flags(target, "rang_original")
            steps.append(("restore rang_original == before", _files(target) == before))
            forced = _cli("flag", config_path(column), target, "--force")
            steps.append(
                (
                    "--force == rang-p1",
                    forced["returncode"] == 0 and _files(target) == want,
                )
            )
            state = json.loads(Path(f"{target}.rang-run/state.json").read_text())
            rerun = state["stages"]["flag"].get("saved_before_restore")
            msv4_flags.save(target, "m7_flagged")
            if rerun:
                msv4_flags.restore_flags(target, rerun)
                steps.append((f"restore {rerun} == before", _files(target) == before))
            else:
                steps.append(("--force saved rang_rerun_*", False))
            msv4_flags.restore_flags(target, "rang_original")
            steps.append(
                ("restore rang_original again == before", _files(target) == before)
            )
            msv4_flags.restore_flags(target, "m7_flagged")
            steps.append(("restore m7_flagged == rang-p1", _files(target) == want))
            entry["c4_steps"] = steps
            entry["c4"] = (
                "match"
                if names[:1] == ["rang_original"]
                and len(names) == 2
                and names[1].startswith("rang_flag_")
                and all(ok for _, ok in steps)
                else "mismatch"
            )
            entry["c4_seconds"] = round(time.perf_counter() - t0, 3)
            entry["forced"] = forced
            entry["versions_end"] = [n for n, _ in msv4_flags.versions(target)]
            _log(root, "cli", f"{case}/{arm}", entry)


# --- kill: C5 ---------------------------------------------------------------------


def _ms_flag(ms):
    import numpy as np
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        flag = np.asarray(t.getcol("FLAG"), bool)
    return hashlib.sha256(np.ascontiguousarray(flag).tobytes()).hexdigest()


def _partition_state(now, want, before):
    """Per partition: which reference its files equal."""
    parts = sorted({k.split("/")[0] for k in now if "/" in k})
    out = {}
    for p in parts:
        pick = {k: v for k, v in now.items() if k.startswith(p + "/")}
        w = {k: v for k, v in want.items() if k.startswith(p + "/")}
        b = {k: v for k, v in before.items() if k.startswith(p + "/")}
        out[p] = "rang-p1" if pick == w else "before" if pick == b else "other"
    return out


def kill(root, only=None):
    from rang import msv4_flags

    root = Path(root)
    cfg = config_path("DATA")
    for case in KILL_CASES:
        if only and case not in only:
            continue
        sides = [(arm, "store") for arm in ARMS] + [("msv2", "msv2")]
        for arm, side in sides:
            if side == "store":
                path = lambda k, arm=arm, case=case: store(root, arm, case, k)
                read = _files
                want = _files(m6_store(arm, case, "rang-p1"))
                before = _files(m6_store(arm, case, "before"))
                restore = msv4_flags.restore_flags
                journal = msv4_flags.read_journal
            else:
                from rang import core_writeback

                path = lambda k, case=case: root / "msv2" / f"{case}-{k}.ms"
                read = _ms_flag
                want = _ms_flag(M6 / "msv2" / f"{case}.ms")
                before = _ms_flag(M6 / "ms-src" / f"{case}.ms")
                restore = core_writeback.restore_flags
                journal = core_writeback.read_journal
            label = f"{case}/{arm}"
            res = {}
            # K1, same run directory (a) and a fresh one (b).
            for k, fresh in (("k1a", False), ("k1b", True)):
                target = path(k)
                e = {"kill": _killed(f"{side}-k1", target, cfg)}
                e["journal_written"] = (journal(target) or {}).get("written")
                e["unchanged_after_kill"] = read(target) == before
                extra = (
                    ["--run-dir", root / "rundirs" / f"{case}-{arm}-{k}"]
                    if fresh
                    else []
                )
                e["next"] = _cli("flag", cfg, target, *extra)
                e["final_is_reference"] = read(target) == want
                res[k] = e
            # K2: (a) a fresh run directory, (b) the same one.
            target = path("k2")
            e = {"kill": _killed(f"{side}-k2", target, cfg)}
            now = read(target)
            e["journal"] = journal(target)
            if side == "store":
                e["partitions_after_kill"] = _partition_state(now, want, before)
            e["after_kill_is"] = (
                "rang-p1" if now == want else "before" if now == before else "mixed"
            )
            e["fresh"] = _cli(
                "flag",
                cfg,
                target,
                "--run-dir",
                root / "rundirs" / f"{case}-{arm}-k2-other",
            )
            e["fresh_unchanged"] = read(target) == now
            e["fresh_names_restore"] = (
                "rang.msv4_flags.restore_flags"
                if side == "store"
                else "rang.core_writeback.restore_flags"
            ) in e["fresh"]["stderr_tail"] and str(
                e["journal"].get("flag_backup")
            ) in e["fresh"]["stderr_tail"]
            e["same"] = _cli("flag", cfg, target)
            e["same_final_is_reference"] = read(target) == want
            res["k2"] = e
            # K3: an explicit restore after a K2 kill, then a fresh run directory.
            target = path("k3")
            e = {"kill": _killed(f"{side}-k2", target, cfg)}
            version = journal(target)["flag_backup"]
            restore(target, version)
            e["restored_from"] = version
            e["journal_state"] = journal(target)["state"]
            e["restored_is_before"] = read(target) == before
            e["next"] = _cli(
                "flag", cfg, target, "--run-dir", root / "rundirs" / f"{case}-{arm}-k3"
            )
            e["final_is_reference"] = read(target) == want
            res["k3"] = e
            _log(root, "kill", label, res)


# --- refuse: C7 -------------------------------------------------------------------


def refuse(root):
    root = Path(root)
    target = store(root, "xradio", "c5", "refuse")
    before = _files(target)
    cfg = config_path("DATA")
    configs = root / "refuse-configs"
    configs.mkdir(exist_ok=True)
    text = cfg.read_text(encoding="utf-8")
    strategy = (M6 / "strategy.yaml").as_posix()
    head = "version: 1\ndata: {processes: 1}\n"
    run_cfg = configs / "run-flag-calibrate.yaml"
    run_cfg.write_text(
        head + f"flag: {{strategy: {strategy}, column: DATA}}\n"
        "run: {stages: [flag, calibrate]}\n",
        encoding="utf-8",
    )
    bad = configs / "fields-0.yaml"
    bad.write_text(
        head + f"flag: {{strategy: {strategy}, column: DATA, fields: ['0']}}\n",
        encoding="utf-8",
    )
    out = {"config_text": text}
    for stage in ("calibrate", "apply", "image", "selfcal"):
        out[stage] = _cli(stage, cfg, target)
    out["run"] = _cli("run", run_cfg, target)
    out["bad_fields"] = _cli("flag", bad, target)
    out["config_check"] = _cli("config", "check", cfg, target, "--stage", "flag")
    out["config_check_bad"] = _cli("config", "check", bad, target, "--stage", "flag")
    out["store_unchanged"] = _files(target) == before
    out["flagversions_absent"] = not Path(f"{target}.flagversions").exists()
    out["state_absent"] = not Path(f"{target}.rang-run/state.json").exists()
    codes = {
        k: out[k]["returncode"]
        for k in ("calibrate", "apply", "image", "selfcal", "run", "bad_fields")
    }
    names = all(
        ("M5" in out[k]["stderr_tail"] or "MSv4 store" in out[k]["stderr_tail"])
        for k in ("calibrate", "apply", "image", "selfcal", "run")
    )
    out["c7"] = (
        "match"
        if set(codes.values()) == {2}
        and names
        and out["config_check"]["returncode"] == 0
        and out["config_check_bad"]["returncode"] == 2
        and out["store_unchanged"]
        and out["flagversions_absent"]
        and out["state_absent"]
        else "mismatch"
    )
    # Reported: rang-core watch reads a store's run directory.
    out["watch"] = _cli(
        "watch", f"{store(root, 'xradio', 'c5', 'cli')}.rang-run", "--once", "--json"
    )
    _log(root, "refuse", "c5/xradio", out)


# --- products: C6 -----------------------------------------------------------------


def _groups(summary):
    return sorted(
        (g["field"], str(g["scan"]), g["rows"], g["flagged_before"], g["flagged_after"])
        for g in summary["groups"]
    )


def _versions_shape(path):
    lines = (Path(path) / "FLAG_VERSION_LIST").read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        name, _, comment = line.partition(" : ")
        stem = name.rsplit("_", 1)[0] if name.startswith("rang_flag_") else name
        out.append((stem, comment))
    return out


def products(root, only=None):
    root = Path(root)
    equal_summary = (
        "strategy", "strategy_sha256", "steps", "static_masks", "write", "column",
        "restored_before", "rows_flagged", "flagged_before", "flagged_after",
        "rang_original_saved_now",
    )  # fmt: skip
    equal_entry = ("config_sha256", "sections", "status", "attempts", "previous")
    for case in CASES:
        if only and case not in only:
            continue
        for arm in ARMS:
            snap = root / "products" / arm / case
            ms_run = M6 / "msv2" / f"{case}.ms.rang-run"
            if case in NO_MSV2 or not snap.exists():
                _log(
                    root,
                    "products",
                    f"{case}/{arm}",
                    {"c6": "not measured", "why": NO_MSV2.get(case, "no snapshot")},
                )
                continue
            a, b = snap / "rang-run", ms_run
            misses = []
            fa = sorted(
                p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file()
            )
            fb = sorted(
                p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file()
            )
            shape = lambda fs: sorted(
                "receipts/flag-*" if f.startswith("receipts/flag-") else f for f in fs
            )
            if shape(fa) != shape(fb):
                misses.append(f"file set {fa} vs {fb}")
            if (a / "config.resolved.json").read_bytes() != (
                b / "config.resolved.json"
            ).read_bytes():
                misses.append("config.resolved.json")
            sa = json.loads((a / "state.json").read_text())
            sb = json.loads((b / "state.json").read_text())
            if set(sa) != set(sb):
                misses.append(f"state keys {sorted(set(sa) ^ set(sb))}")
            if sa.get("telescope") != sb.get("telescope"):
                misses.append(
                    f"telescope {sa.get('telescope')!r} vs {sb.get('telescope')!r}"
                )
            ea, eb = sa["stages"]["flag"], sb["stages"]["flag"]
            if set(ea) != set(eb):
                misses.append(f"entry keys {sorted(set(ea) ^ set(eb))}")
            for k in equal_entry:
                if ea.get(k) != eb.get(k):
                    misses.append(f"entry {k}: {ea.get(k)!r} vs {eb.get(k)!r}")
            if set(ea["summary"]) != set(eb["summary"]) | {"store", "data_group"}:
                misses.append(
                    f"brief keys {sorted(set(ea['summary']) ^ set(eb['summary']))}"
                )
            ya = json.loads((a / "flag" / "summary.json").read_text())
            yb = json.loads((b / "flag" / "summary.json").read_text())
            if set(ya) != set(yb) | {"store", "data_group", "partitions"}:
                misses.append(f"summary keys {sorted(set(ya) ^ set(yb))}")
            for k in equal_summary:
                if ya.get(k) != yb.get(k):
                    misses.append(f"summary {k}: {ya.get(k)!r} vs {yb.get(k)!r}")
            if _groups(ya) != _groups(yb):
                misses.append("groups")
            ca, cb = dict(ya["chunking"]), dict(yb["chunking"])
            if sorted(ca.pop("blocks")) != sorted(cb.pop("blocks")) or ca != cb:
                misses.append(f"chunking {ca} vs {cb}")
            va = _versions_shape(snap / "flagversions")
            vb = _versions_shape(
                Path(str(M6 / "msv2" / f"{case}.ms") + ".flagversions")
            )
            if va != vb:
                misses.append(f"versions {va} vs {vb}")
            ja = json.loads((snap / "flagversions" / "rang-writeback.json").read_text())
            jb = json.loads(
                (
                    Path(str(M6 / "msv2" / f"{case}.ms") + ".flagversions")
                    / "rang-writeback.json"
                ).read_text()
            )
            if (
                set(ja) != set(jb)
                or ja["state"] != "closed"
                or ja["written"] != ["FLAG"]
            ):
                misses.append(
                    f"journal {sorted(set(ja) ^ set(jb))} {ja['state']} {ja['written']}"
                )
            _log(
                root,
                "products",
                f"{case}/{arm}",
                {
                    "c6": "match" if not misses else "mismatch",
                    "misses": misses,
                    "flag_sha256_equal": ya["flag_sha256"] == yb["flag_sha256"],
                    "seconds_store": ea.get("seconds"),
                    "seconds_msv2": eb.get("seconds"),
                },
            )


# --- xcheck: C2 and C3 (xradio venv, no rang) ----------------------------------------


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
    for case, (src, _) in CASES.items():
        for arm in ARMS:
            paths = {
                "before": m6_store(arm, src, "before"),
                "control": m6_store(arm, src, "control"),
                "oracle": m6_store(arm, case, "oracle"),
                "cli": store(root, arm, case, "cli"),
            }
            missing = [k for k, p in paths.items() if not p.exists()]
            entry = {}
            if case in NO_MSV2 or missing:
                entry["c2"] = "not measured"
                entry["why"] = NO_MSV2.get(case) or f"missing {missing}"
            else:
                trees = {k: open_processing_set(str(p)) for k, p in paths.items()}
                arrays = {k: _arrays(t) for k, t in trees.items()}
                nondet = _diff(arrays["before"], arrays["control"])
                d = _diff(arrays["oracle"], arrays["cli"])
                entry["differs"] = d
                entry["counted"] = [k for k in d if k not in nondet]
                entry["c2"] = "match" if not entry["counted"] else "mismatch"
                issues = {k: str(check_datatree(trees[k])) for k in ("before", "cli")}
                entry["schema_issues"] = issues
                entry["c3"] = (
                    "match" if issues["before"] == issues["cli"] else "mismatch"
                )
            if "c3" not in entry and not missing:
                trees = {
                    k: open_processing_set(str(paths[k])) for k in ("before", "cli")
                }
                issues = {k: str(check_datatree(t)) for k, t in trees.items()}
                entry["schema_issues"] = issues
                entry["c3"] = (
                    "match" if issues["before"] == issues["cli"] else "mismatch"
                )
            result[f"{case}/{arm}"] = entry
            print(case, arm, entry.get("c2"), entry.get("c3"), flush=True)
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True, default=str))


# --- check: the rule ---------------------------------------------------------------


def _load(root, step):
    path = Path(root) / f"{step}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _c5(kill):
    """C5 per kill case and arm, the MSv2 side's outcome classes beside it."""
    out = {}
    for case in KILL_CASES:
        ms = kill.get(f"{case}/msv2", {})
        for arm in ARMS:
            st = kill.get(f"{case}/{arm}")
            if not st:
                out[f"{case}/{arm}"] = "not measured"
                continue
            ok = []
            for k in ("k1a", "k1b"):
                e = st[k]
                ok.append(
                    e["kill"]["returncode"] == 9
                    and e["journal_written"] == []
                    and e["unchanged_after_kill"]
                )
                ok.append(e["next"]["returncode"] == 0 and e["final_is_reference"])
                ok.append(
                    e["next"]["returncode"] == ms[k]["next"]["returncode"]
                    and ms[k]["final_is_reference"]
                )
            e, m = st["k2"], ms["k2"]
            ok.append(
                e["kill"]["returncode"] == 9 and e["journal"]["written"] == ["FLAG"]
            )
            if case == "c6x":
                parts = list(e["partitions_after_kill"].values())
                ok.append(
                    parts.count("rang-p1") == 1
                    and parts.count("before") == len(parts) - 1
                )
            ok.append(e["fresh"]["returncode"] == m["fresh"]["returncode"] == 1)
            ok.append(e["fresh_unchanged"] and e["fresh_names_restore"])
            ok.append(e["same"]["returncode"] == m["same"]["returncode"] == 0)
            ok.append(e["same_final_is_reference"] and m["same_final_is_reference"])
            e, m = st["k3"], ms["k3"]
            ok.append(e["journal_state"] == m["journal_state"] == "restored")
            ok.append(e["restored_is_before"] and m["restored_is_before"])
            ok.append(e["next"]["returncode"] == m["next"]["returncode"] == 0)
            ok.append(e["final_is_reference"] and m["final_is_reference"])
            out[f"{case}/{arm}"] = (
                "match"
                if all(ok)
                else f"mismatch {[i for i, v in enumerate(ok) if not v]}"
            )
    return out


def check(root, xcheck_path, out):
    cli_log, kill_log = _load(root, "cli"), _load(root, "kill")
    prod, ref = _load(root, "products"), _load(root, "refuse")
    xc = json.loads(Path(xcheck_path).read_text())
    c5 = _c5(kill_log)
    table = {}
    for case in DECIDING + ["c10"]:
        for arm in ARMS:
            key = f"{case}/{arm}"
            c = cli_log.get(key, {})
            table[key] = {
                "c1": c.get("c1", "not measured"),
                "c2": xc.get(key, {}).get("c2", "not measured"),
                "c3": xc.get(key, {}).get("c3", "not measured"),
                "c4": c.get("c4", "not measured"),
                "c5": c5.get(key, "-"),
                "c6": prod.get(key, {}).get("c6", "not measured"),
                "seconds": c.get("run", {}).get("seconds"),
            }
    c7 = ref.get("c5/xradio", {}).get("c7", "not measured")

    def arm_ok(arm, measures):
        rows = [table[f"{c}/{arm}"] for c in DECIDING]
        good = all(
            r[m] in ("match", "not measured", "-") for r in rows for m in measures
        )
        some = all(any(r[m] == "match" for r in rows) for m in measures)
        return good and some

    verdict = {}
    for arm in ARMS:
        core = arm_ok(arm, ("c1", "c2", "c4"))
        rest = arm_ok(arm, ("c3", "c5", "c6")) and c7 == "match"
        verdict[arm] = "pass" if core and rest else "partial" if core else "fail"
    # c9: C1 and C4 measured (no MSv2 side): booked above as not measured otherwise.
    result = {
        "table": table,
        "c7": c7,
        "verdict": verdict,
        "c5": c5,
        "not_measured": {**NO_MSV2, **NOT_MEASURED},
    }
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps({"verdict": verdict, "c7": c7}, indent=1))


def main(argv):
    step, *rest = argv
    if step == "_kill":
        _kill_main(*rest)
        return
    root, *rest = rest
    only = None
    if rest and rest[-1].startswith("--only="):
        only = rest.pop()[7:].split(",")
    steps = {"copy": lambda: copy(root), "cli": lambda: cli(root, only), "kill": lambda: kill(root, only),
             "refuse": lambda: refuse(root), "products": lambda: products(root, only),
             "xcheck": lambda: xcheck(root, rest[0]), "check": lambda: check(root, rest[0], rest[1])}  # fmt: skip
    if step not in steps:
        raise SystemExit(__doc__)
    steps[step]()


if __name__ == "__main__":
    main(sys.argv[1:])
