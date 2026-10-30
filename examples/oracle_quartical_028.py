"""QuartiCal v0.2.8-dev re-validation for task RV1 (research/rv1-revalidate.md).

Usage:
    # Q0, in a QuartiCal venv (python-casacore): copy the archived MSs, set the solve flags
    python examples/oracle_quartical_028.py prepare outputs/<fresh>
    # one upstream arm, in that arm's venv (goquartical beside the interpreter)
    python examples/oracle_quartical_028.py solve outputs/<run> <fixture|luno> <arm> [key=value ...]
    # one core arm, in the worktree venv; RANG_SOLVE_OPTIONS taken from the environment
    python examples/oracle_quartical_028.py core outputs/<run> <fixture|luno> <arm>
    # the comparison, in the worktree venv
    python examples/oracle_quartical_028.py compare outputs/<run> outputs/<fresh>

`solve` takes the archived `command.json` of the input verbatim, changing only
`input_ms.path` and the output directories (and appending any extra
`key=value` options, e.g. `G.referenced=false`), runs it under
`/usr/bin/time`, checks that FLAG and FLAG_ROW of the copy are unchanged and
extracts gains, gain flags, `conv_iter` and `conv_perc` from `gains.qc::G` as
`examples/solve_luno.py` did. `compare` applies the archived phase 2 criteria
(research/core-phase2.md) unchanged. Nothing under the archived paths is
written.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "outputs/tv-response-wsl-20261029-01/clean"
FIXTURE_TRIAL = FIXTURE / "trials/clean-t2-f32"
FIXTURE_FLAGS = FIXTURE / "backups/clean-t2-f32-solve.npz"
LUNO = ROOT / "outputs/luno-solve-20261029-02"
LUNO_ARRAYS = ROOT / "outputs/core-phase2-inputs-20261029-01/arrays.npz"
LUNO_ARCHIVE = ROOT / "research/results/meerkat-luno-solved.json"
INPUTS = {
    "fixture": {"ms": FIXTURE / "work.ms", "command": FIXTURE_TRIAL / "command.json"},
    "luno": {"ms": LUNO / "work.ms", "command": LUNO / "solve/command.json"},
}
GRID = (2, 32)
GAIN_TOL = 1e-6
CONV_TOL = 1e-12
TIMEOUT = 1800


def tree_sha256(path):
    files = sorted(
        p for p in Path(path).rglob("*") if p.is_file() and p.name != "table.lock"
    )
    digest = sha256()
    for p in files:
        digest.update(p.relative_to(path).as_posix().encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def loadavg():
    return float(Path("/proc/loadavg").read_text().split()[0])


def archived_hashes():
    return {
        "fixture_work_ms": tree_sha256(FIXTURE / "work.ms"),
        "fixture_state": file_sha256(FIXTURE / "state.npz"),
        "fixture_solve_flags": file_sha256(FIXTURE_FLAGS),
        "fixture_diagnostics": file_sha256(FIXTURE_TRIAL / "diagnostics.npz"),
        "luno_work_ms": tree_sha256(LUNO / "work.ms"),
        "luno_arrays": file_sha256(LUNO_ARRAYS),
        "luno_gains": file_sha256(LUNO / "solve/gains.npy"),
        "luno_gain_flags": file_sha256(LUNO / "solve/gain_flags.npy"),
    }


# --- Q0 -----------------------------------------------------------------------


def prepare(out):
    from casacore.tables import table

    out.mkdir(parents=True, exist_ok=False)
    before = archived_hashes()
    inputs = out / "inputs"
    inputs.mkdir()
    checks = {}
    for name, spec in INPUTS.items():
        ms = inputs / f"{name}.ms"
        shutil.copytree(spec["ms"], ms)
        lock = ms / "table.lock"
        if lock.exists():
            lock.unlink()
    fixture_ms = str(inputs / "fixture.ms")
    with (
        np.load(FIXTURE / "state.npz") as s,
        np.load(FIXTURE_FLAGS) as z,
        table(fixture_ms, readonly=False, ack=False) as t,
    ):
        t.putcol("FLAG", z["FLAG"])
        t.putcol("FLAG_ROW", z["FLAG_ROW"])
        checks["fixture"] = {
            "FLAG": bool(np.array_equal(t.getcol("FLAG"), z["FLAG"])),
            "FLAG_ROW": bool(np.array_equal(t.getcol("FLAG_ROW"), z["FLAG_ROW"])),
            "DATA": bool(np.array_equal(t.getcol("DATA"), s["data"])),
            "RANG_MODEL_DATA": bool(
                np.array_equal(t.getcol("RANG_MODEL_DATA"), s["model"])
            ),
            "WEIGHT_SPECTRUM": bool(
                np.array_equal(t.getcol("WEIGHT_SPECTRUM"), s["weights"])
            ),
        }
    with (
        np.load(LUNO_ARRAYS) as a,
        table(
            str(inputs / "luno.ms"), readonly=True, ack=False, lockoptions="autonoread"
        ) as t,
    ):
        checks["luno"] = {
            name: bool(np.array_equal(t.getcol(name), a[name]))
            for name in (
                "FLAG",
                "FLAG_ROW",
                "DATA",
                "MODEL_DATA",
                "WEIGHT_SPECTRUM",
            )
        }
    receipt = {
        "archived_hashes_before": before,
        "checks": checks,
        "copies": {n: tree_sha256(inputs / f"{n}.ms") for n in INPUTS},
        "archived_unchanged": archived_hashes() == before,
    }
    (inputs / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps(receipt["checks"], indent=1), receipt["archived_unchanged"])
    if not all(all(c.values()) for c in checks.values()):
        raise SystemExit("input copies do not match the archived arrays")


# --- upstream arms ------------------------------------------------------------


def quartical_provenance():
    import importlib.metadata as md

    dist = md.distribution("quartical")
    direct = dist.read_text("direct_url.json")
    versions = {}
    for name in ("numba", "numpy", "dask", "dask-ms", "codex-africanus", "xarray"):
        try:
            versions[name] = md.version(name)
        except md.PackageNotFoundError:
            versions[name] = None
    return {
        "version": dist.version,
        "direct_url": json.loads(direct) if direct else None,
        "dependencies": versions,
        "python": platform.python_version(),
    }


def solve(run, name, arm, extra):
    from casacore.tables import table
    from daskms.experimental.zarr import xds_from_zarr

    ms = run / "inputs" / f"{name}.ms"
    out = run / name / arm
    out.mkdir(parents=True, exist_ok=False)
    archived = json.loads(INPUTS[name]["command"].read_text())
    command = []
    for item in archived:
        key = item.split("=", 1)[0]
        if key == "input_ms.path":
            item = f"input_ms.path={ms}"
        elif key == "output.gain_directory":
            item = f"output.gain_directory={out / 'gains.qc'}"
        elif key == "output.log_directory":
            item = f"output.log_directory={out / 'logs.qc'}"
        command.append(item)
    command += list(extra)
    command[0] = str(Path(sys.executable).parent / "goquartical")
    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as t:
        flags, rows = t.getcol("FLAG"), t.getcol("FLAG_ROW")
    summary = {
        "arm": arm,
        "input": name,
        "command": command,
        "archived_command": str(INPUTS[name]["command"]),
        "quartical": quartical_provenance(),
        "numba_cache_dir": os.environ.get("NUMBA_CACHE_DIR"),
        "numba_cache_files_before": sum(
            1 for _ in Path(os.environ["NUMBA_CACHE_DIR"]).rglob("*.nbi")
        )
        if os.environ.get("NUMBA_CACHE_DIR")
        and Path(os.environ["NUMBA_CACHE_DIR"]).exists()
        else 0,
        "load_before": loadavg(),
    }
    started = time.perf_counter()
    with (out / "quartical.log").open("x") as log:
        try:
            proc = subprocess.run(
                ["/usr/bin/time", "-f", "TIME %e %M", *command],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=TIMEOUT,
            )
            summary["returncode"] = proc.returncode
        except subprocess.TimeoutExpired:
            summary["returncode"] = None
            summary["timeout"] = True
    summary["seconds"] = time.perf_counter() - started
    summary["load_after"] = loadavg()
    for line in (out / "quartical.log").read_text().splitlines():
        if line.startswith("TIME "):
            _, wall, rss = line.split()
            summary["time_wall"], summary["max_rss_mb"] = float(wall), int(rss) / 1024
    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as t:
        summary["flags_unchanged"] = bool(
            np.array_equal(t.getcol("FLAG"), flags)
            and np.array_equal(t.getcol("FLAG_ROW"), rows)
        )
    if summary["returncode"] == 0:
        (ds,) = xds_from_zarr(f"{out / 'gains.qc'}::G")
        ds = ds.compute()
        gains = ds.gains.transpose(
            "gain_time", "gain_freq", "antenna", "direction", "correlation"
        ).values[..., 0, :]
        gflags = ds.gain_flags.transpose(
            "gain_time", "gain_freq", "antenna", "direction"
        ).values[..., 0]
        np.save(out / "gains.npy", gains.reshape(*gains.shape[:3], 2, 2))
        np.save(out / "gain_flags.npy", gflags)
        summary.update(
            {
                "type": ds.attrs.get("TYPE"),
                "shape": list(gains.shape),
                "conv_iter": np.asarray(
                    ds.attrs.get("conv_iter", ds.get("conv_iter", -1))
                ).tolist(),
                "conv_perc": np.asarray(
                    ds.attrs.get("conv_perc", ds.get("conv_perc", -1))
                ).tolist(),
                "flagged_gain_fraction": float(np.mean(gflags != 0)),
                "gain_attrs": {
                    k: v
                    for k, v in ds.attrs.items()
                    if isinstance(v, (str, int, float))
                },
            }
        )
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    print(arm, name, summary["returncode"], f"{summary['seconds']:.1f} s", flush=True)
    if summary["returncode"] != 0 or not summary["flags_unchanged"]:
        raise SystemExit("QuartiCal failed or altered flags")


# --- core arms ----------------------------------------------------------------


def bins(times, nchan):
    integration = np.unique(times, return_inverse=True)[1]
    return integration // GRID[0], np.arange(nchan) // GRID[1]


def load_input(name):
    """The arrays the phase 2 validator solves, with their bins and the
    observed-pair map (pairs with an unflagged cell in the interval)."""
    if name == "fixture":
        with np.load(FIXTURE / "state.npz") as z:
            s = {k: z[k] for k in z.files}
        with np.load(FIXTURE_FLAGS) as z:
            flag, flag_row = z["FLAG"], z["FLAG_ROW"]
        a = {
            "DATA": s["data"],
            "MODEL": s["model"],
            "WEIGHT": s["weights"],
            "FLAG": flag,
            "FLAG_ROW": flag_row,
            "ANTENNA1": s["antenna1"],
            "ANTENNA2": s["antenna2"],
            "TIME": s["times"],
        }
    else:
        with np.load(LUNO_ARRAYS) as z:
            z = {k: z[k] for k in z.files}
        a = {
            "DATA": z["DATA"],
            "MODEL": z["MODEL_DATA"],
            "WEIGHT": z["WEIGHT_SPECTRUM"],
            "FLAG": z["FLAG"],
            "FLAG_ROW": z["FLAG_ROW"],
            "ANTENNA1": z["ANTENNA1"],
            "ANTENNA2": z["ANTENNA2"],
            "TIME": z["TIME"],
        }
    tb, fb = bins(a["TIME"], a["DATA"].shape[1])
    return a, tb, fb


def reference(name):
    """The archived 0.2.7 gains and their flags, as the phase 2 validator reads them."""
    if name == "fixture":
        with np.load(FIXTURE_TRIAL / "diagnostics.npz") as z:
            return z["gains"].astype(np.complex128), ~z["gain_valid"], None, None
    archive = json.loads(LUNO_ARCHIVE.read_text())["solve_summary"]
    return (
        np.load(LUNO / "solve/gains.npy").astype(np.complex128),
        np.load(LUNO / "solve/gain_flags.npy") != 0,
        int(np.asarray(archive["conv_iter"]).ravel()[0]),
        float(np.asarray(archive["conv_perc"]).ravel()[0]),
    )


def core_arm(run, name, arm):
    import resource

    from rang import core

    out = run / name / arm
    out.mkdir(parents=True, exist_ok=False)
    a, tb, fb = load_input(name)
    qc, _, _, _ = reference(name)
    nt, nf, na = qc.shape[:3]
    started = time.perf_counter()
    rust = core.solve_complex(
        a["DATA"],
        a["WEIGHT"],
        a["FLAG"],
        a["FLAG_ROW"],
        a["ANTENNA1"],
        a["ANTENNA2"],
        tb,
        fb,
        ntime_bins=nt,
        nfreq_bins=nf,
        nant=na,
        model=a["MODEL"],
    )
    seconds = time.perf_counter() - started
    np.save(out / "gains.npy", rust.gains)
    np.save(out / "gain_flags.npy", rust.flags)
    summary = {
        "arm": arm,
        "input": name,
        "rang_solve_options": os.environ.get("RANG_SOLVE_OPTIONS"),
        "core_extension_sha256": file_sha256(core.library_path()),
        "conv_iter": int(rust.iterations),
        "conv_perc": float(rust.converged_fraction),
        "solve_seconds": seconds,
        "self_max_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(arm, name, f"{seconds:.3f} s", rust.iterations, rust.converged_fraction)


# --- comparison ---------------------------------------------------------------


def load_arm(run, name, arm):
    d = run / name / arm
    summary = json.loads((d / "summary.json").read_text())
    gains = np.load(d / "gains.npy").astype(np.complex128)
    flagged = (np.load(d / "gain_flags.npy") != 0) | ~np.isfinite(gains).all(
        axis=(-1, -2)
    )
    it = np.asarray(summary["conv_iter"]).ravel()
    pc = np.asarray(summary["conv_perc"]).ravel()
    return SimpleNamespace(
        gains=gains,
        flags=flagged.astype(np.int8),
        flagged=flagged,
        iterations=int(it[0]) if it.size else None,
        converged_fraction=float(pc[0]) if pc.size else None,
        summary=summary,
    )


def observed_pairs(name, nt, nf, na):
    a, tb, fb = load_input(name)
    ok = ~a["FLAG"].any(-1) & ~a["FLAG_ROW"][:, None] & (a["WEIGHT"] > 0).all(-1)
    obs = np.zeros((nt, nf, na, na), bool)
    rows, chans = np.nonzero(ok)
    obs[tb[rows], fb[chans], a["ANTENNA1"][rows], a["ANTENNA2"][rows]] = True
    return obs | obs.swapaxes(-1, -2)


def products_max(x, y, keep, pairs=None):
    worst = 0.0
    na = x.shape[2]
    for p in range(na):
        for q in range(p + 1, na):
            sel = keep[..., p] & keep[..., q]
            if pairs is not None:
                sel &= pairs[..., p, q]
            a = x[..., p, :, :] @ x[..., q, :, :].conj().swapaxes(-1, -2)
            b = y[..., p, :, :] @ y[..., q, :, :].conj().swapaxes(-1, -2)
            d = np.abs(a - b)[sel]
            if d.size:
                worst = max(worst, float(d.max()))
    return worst


def compare_one(name, arm, ref, ref_flagged, ref_iter, ref_conv, gauge_free, obs):
    sys.path.insert(0, str(ROOT / "examples"))
    from validate_core_phase2 import compare_gains

    c = compare_gains(arm, ref, ref_flagged)
    keep = ~ref_flagged
    c["max_abs_baseline_product_diff_observed_pairs"] = products_max(
        arm.gains, ref, keep, obs
    )
    c["reference_iterations"] = ref_iter
    c["reference_converged_fraction"] = ref_conv
    crit = {
        "1_gain_flags": c["flags_equal"],
        "2_products": c["max_abs_baseline_product_diff"] <= GAIN_TOL,
    }
    if not gauge_free:
        crit["2_entries"] = c["max_abs_gain_entry_diff"] <= GAIN_TOL
    if ref_iter is not None:
        crit["3_iterations"] = c["iterations"] == ref_iter
    if name == "luno" and ref_conv is not None:
        crit["3_converged_fraction"] = (
            c["converged_fraction"] is not None
            and abs(c["converged_fraction"] - ref_conv) <= CONV_TOL
        )
    c["criteria"] = crit
    c["pass"] = all(crit.values())
    return c


def compare(run, out):
    out.mkdir(parents=True, exist_ok=False)
    result = {"run": str(run), "tolerances": {"gain": GAIN_TOL, "conv": CONV_TOL}}
    for name in INPUTS:
        arms = {
            d.name: load_arm(run, name, d.name)
            for d in sorted((run / name).iterdir())
            if (d / "gains.npy").exists()
        }
        ref, ref_flagged, ref_iter, ref_conv = reference(name)
        nt, nf, na = ref.shape[:3]
        obs = observed_pairs(name, nt, nf, na)
        refs = {
            "archived-0.2.7": (ref, ref_flagged, ref_iter, ref_conv),
        }
        for r in ("qc027-cold", "core", "core-T", "qc028u"):
            if r in arms:
                x = arms[r]
                refs[r] = (x.gains, x.flagged, x.iterations, x.converged_fraction)
        table = {}
        for arm_name, arm in arms.items():
            for ref_name, (g, f, it, cv) in refs.items():
                if ref_name == arm_name:
                    continue
                gauge_free = arm_name.startswith("qc028-") or ref_name.startswith(
                    "qc028-"
                )
                table[f"{arm_name} vs {ref_name}"] = compare_one(
                    name, arm, g, f, it, cv, gauge_free, obs
                )
        result[name] = {
            "arms": {
                k: {
                    "iterations": v.iterations,
                    "converged_fraction": v.converged_fraction,
                    "flagged_gains": int(v.flagged.sum()),
                    "seconds": v.summary.get("seconds", v.summary.get("solve_seconds")),
                    "time_wall": v.summary.get("time_wall"),
                    "max_rss_mb": v.summary.get("max_rss_mb"),
                    "commit": (v.summary.get("quartical") or {})
                    .get("direct_url", {})
                    .get("vcs_info", {})
                    .get("commit_id")
                    if (v.summary.get("quartical") or {}).get("direct_url")
                    else None,
                    "version": (v.summary.get("quartical") or {}).get("version"),
                    "rang_solve_options": v.summary.get("rang_solve_options"),
                }
                for k, v in arms.items()
            },
            "comparisons": table,
        }
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    for name in INPUTS:
        for k, v in result[name]["comparisons"].items():
            print(
                f"{name:8s} {k:34s} pass={v['pass']!s:5s} flags={v['flags_equal']!s:5s}"
                f" entries={v['max_abs_gain_entry_diff']:.2e}"
                f" products={v['max_abs_baseline_product_diff']:.2e}"
                f" observed={v['max_abs_baseline_product_diff_observed_pairs']:.2e}"
                f" iter={v['iterations']}/{v['reference_iterations']}"
                f" conv={v['converged_fraction']}/{v['reference_converged_fraction']}"
            )
    return 0


def main():
    mode = sys.argv[1]
    if mode == "prepare":
        prepare(Path(sys.argv[2]))
    elif mode == "solve":
        solve(Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5:])
    elif mode == "core":
        core_arm(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
    elif mode == "compare":
        return compare(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(f"unknown mode {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
