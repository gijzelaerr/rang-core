"""Harness and comparators of big-plan task DF2b: the exact gridder in the
imaging drivers (`gridder="wgrid"`) and the C/I/K/L1 archives against
WSClean 3.7's wgridder (research/df2b-wgrid.md).

    python examples/compare_df2b.py floor OUT.json
    python examples/compare_df2b.py kinvert OUT_DIR [--gridder wstack|wgrid]
    python examples/compare_df2b.py dump-l1 OUT_DIR [--arms original ...]
    python examples/compare_df2b.py image NPZ OUT_PREFIX --gridder G [--groups N]
    python examples/compare_df2b.py ms-inputs OUT_DIR       (C and K MS inputs)
    python examples/compare_df2b.py write-ms NPZ OUT.ms      (inside the container)
    python examples/compare_df2b.py wsclean RUN_DIR NAME MS W H SCALE --gridder G
    python examples/compare_df2b.py make-ms RUN_DIR NAME NPZ    (host: write-ms in the container)
    python examples/compare_df2b.py compare RUN_DIR BASE_DIR OUT.json
    python examples/compare_df2b.py summary RUN_DIR BASE_DIR research/results/df2b-wgrid.json

`floor` measures the rounding floor of a legitimate reordering (the input
rows permuted) of the exact gridder on one input of each archive, the
precondition the frozen bit-level tolerance is set from. `kinvert` grids the
dumped task K inputs (P2's `inputs-k`) through `core_grid.invert` and saves
the images and their hashes. `dump-l1` rebuilds the L1 whole-array gridder
inputs of the named arms from the local LUNO tiles and L1 run `-01`'s saved
gains and additions (no solve is repeated). `image` grids one dumped input
in a fresh process and records wall and peak RSS. `write-ms` runs inside the
pinned WSClean 3.7 container (`rang-o-casa:6.7.6.14`, python-casacore
3.7.1) and writes a Measurement Set whose WSClean `-pol I` reader hands the
gridder exactly the dumped samples: XX = YY = the Stokes sample, XY = YX = 0,
`WEIGHT_SPECTRUM` = the full gridding weight / 4 on every correlation
(WSClean's reader takes 4 min(w_XX, w_YY)), flagged where that weight is
zero; with `-weight natural` the imaging weight is one, so WSClean grids the
same weighted samples as the core. `wsclean` runs WSClean on such an MS in
the container. `compare` and `summary` write the frozen comparisons.

Only `write-ms` runs inside the container; it imports NumPy and casacore
only. Everything else runs on the host venv.
"""

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
IMAGE_NAME = "rang-o-casa:6.7.6.14"
C_LIGHT = 299792458.0
C_INPUTS = OUTPUTS / "p2-gridder-20261030-01" / "inputs-c"
K_INPUTS = OUTPUTS / "p2-gridder-20261030-01" / "inputs-k"
C_ORACLE = OUTPUTS / "core-c-20261029-01"
L1_RUN = OUTPUTS / "luno-array-campaign-20261030-01"
PERMUTATION_SEED = 2032
EPSILON = 1e-6


def maxrss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def sha256_array(array):
    array = np.ascontiguousarray(array)
    return hashlib.sha256(array.tobytes()).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def _host():
    sys.path.insert(0, str(ROOT / "python"))
    sys.path.insert(0, str(ROOT / "examples"))


def load_npz(path):
    with np.load(path) as payload:
        out = {key: payload[key] for key in payload.files}
    out["settings"] = json.loads(str(out["settings"]))
    return out


def region_linf(diff, peak, border=2, interior=8):
    """L-infinity of `diff` over the peak: whole image, the outer `border`
    pixels, and the interior `interior` pixels in from every edge."""
    h, w = diff.shape
    mask = np.zeros((h, w), bool)
    mask[:border] = mask[-border:] = True
    mask[:, :border] = mask[:, -border:] = True
    inner = np.abs(diff[interior : h - interior, interior : w - interior])
    return {
        "linf_over_peak": float(np.abs(diff).max() / peak),
        "border_linf_over_peak": float(np.abs(diff[mask]).max() / peak),
        "interior_linf_over_peak": float(inner.max() / peak),
        "rms_over_peak": float(np.sqrt(np.mean(diff**2)) / peak),
    }


def central(diff, frac=0.25):
    h, w = diff.shape
    return diff[
        int(h * frac) : int(h * (1 - frac)), int(w * frac) : int(w * (1 - frac))
    ]


# ---------------------------------------------------------------- floor


def cmd_floor(args):
    """The exact gridder (as committed at the protocol's base) on one input
    per archive and on the same input with its rows permuted: the rounding
    floor of a legitimate reordering."""
    _host()
    from rang import core_wgridder

    rng = np.random.default_rng(PERMUTATION_SEED)
    cases = [("C", C_INPUTS / "c-clean-full.npz"), ("K", K_INPUTS / "k-original.npz")]
    for extra in args.extra:
        cases.append((Path(extra).stem, Path(extra)))
    out = {"seed": PERMUTATION_SEED, "epsilon": EPSILON, "cases": {}}
    for name, path in cases:
        inp = load_npz(path)
        s = inp["settings"]
        weight = inp["weights"] * inp["imaging_weights"]
        a = core_wgridder.fits_image(
            inp["uvw"],
            inp["frequencies"],
            inp["data"],
            weight,
            s["width"],
            s["height"],
            s["scale_arcsec"],
            epsilon=EPSILON,
        )
        perm = rng.permutation(len(inp["uvw"]))
        b = core_wgridder.fits_image(
            inp["uvw"][perm],
            inp["frequencies"],
            inp["data"][perm],
            weight[perm],
            s["width"],
            s["height"],
            s["scale_arcsec"],
            epsilon=EPSILON,
        )
        rec = {
            "input": str(path.relative_to(ROOT))
            if path.is_relative_to(ROOT)
            else str(path)
        }
        for kind in ("dirty", "psf"):
            peak = float(np.abs(a[kind]).max())
            rec[kind] = region_linf(b[kind] - a[kind], peak)
            rec[kind]["peak"] = peak
            rec[kind]["identical"] = bool(np.array_equal(a[kind], b[kind]))
        rec["info"] = a["info"]
        out["cases"][name] = rec
        print(
            name,
            json.dumps({k: rec[k]["linf_over_peak"] for k in ("dirty", "psf")}),
            flush=True,
        )
    write_json(args.out, out)


# ---------------------------------------------------------------- images


def _invert(inp, gridder, groups=1):
    _host()
    from rang import core_campaign_array, core_grid

    s = dict(inp["settings"])
    image = {
        k: s[k]
        for k in (
            "width",
            "height",
            "scale_arcsec",
            "w_layers",
            "kernel_size",
            "oversampling",
            "padding",
        )
    }
    if gridder != "wstack":
        image["gridder"] = gridder
    if groups == 1:
        return core_grid.invert(
            inp["uvw"],
            inp["frequencies"],
            inp["data"],
            inp["weights"],
            inp["imaging_weights"],
            **image,
        )
    return core_campaign_array.grouped_invert(
        inp["uvw"],
        inp["frequencies"],
        inp["data"],
        inp["weights"],
        inp["imaging_weights"],
        image,
        groups,
    )


def cmd_kinvert(args):
    """`core_grid.invert` on each dumped K arm; images saved as float64."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    rec = {"gridder": args.gridder, "inputs": str(args.inputs), "arms": {}}
    for path in sorted(Path(args.inputs).glob("*.npz")):
        inp = load_npz(path)
        t0 = time.perf_counter()
        prod = _invert(inp, args.gridder)
        wall = time.perf_counter() - t0
        for kind in ("dirty", "psf"):
            np.save(out / f"{path.stem}-{kind}.npy", prod[kind])
        rec["arms"][path.stem] = {
            "wall_s": wall,
            "stats": prod["stats"],
            "dirty_sha256": sha256_array(prod["dirty"]),
            "psf_sha256": sha256_array(prod["psf"]),
        }
        print(
            path.stem,
            f"{wall:.2f}s",
            rec["arms"][path.stem]["dirty_sha256"][:16],
            flush=True,
        )
    rec["max_rss_mb"] = maxrss_mb()
    write_json(out / "kinvert.json", rec)


def cmd_image(args):
    """One dumped input through `core_grid.invert` (or the grouped form) in
    this process: images as float64 `.npy`, stats, wall and peak RSS."""
    load0 = os.getloadavg()[0]
    t0 = time.perf_counter()
    inp = load_npz(args.npz)
    loaded = time.perf_counter()
    rss_loaded = maxrss_mb()
    _host()
    from rang import core

    core.library()
    t1 = time.perf_counter()
    prod = _invert(inp, args.gridder, args.groups)
    wall = time.perf_counter() - t1
    prefix = Path(args.out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for kind in ("dirty", "psf"):
        np.save(f"{prefix}-{kind}.npy", prod[kind])
    rec = {
        "npz": str(args.npz),
        "gridder": args.gridder,
        "groups": args.groups,
        "threads": os.environ.get("RAYON_NUM_THREADS"),
        "load_seconds": loaded - t0,
        "image_wall_s": wall,
        "max_rss_mb": maxrss_mb(),
        "rss_after_inputs_mb": rss_loaded,
        "loadavg_before": load0,
        "loadavg_after": os.getloadavg()[0],
        "stats": prod["stats"],
        "wgridder": prod.get("wgridder"),
        "dirty_sha256": sha256_array(prod["dirty"]),
        "psf_sha256": sha256_array(prod["psf"]),
    }
    write_json(f"{prefix}.json", rec)
    print(
        json.dumps(
            {k: rec[k] for k in ("gridder", "groups", "image_wall_s", "max_rss_mb")}
        ),
        flush=True,
    )


# ---------------------------------------------------------------- L1 dump


def cmd_dump_l1(args):
    """L1's corrected-data gridder inputs of `arms` from the local tiles and
    run `-01`'s saved gains and additions (the frozen `image_arm` path up to
    the gridder call: `corrected_stokes`, Briggs 0.5 on the padded grid)."""
    _host()
    from rang import core, core_campaign, core_weights
    from rang import core_campaign_array as array

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    core.library()
    t0 = time.perf_counter()
    stages = {}
    integrity = array.verify_inputs()
    if not (integrity["all_match_receipts"] and integrity["whole_tile_headers"]):
        raise RuntimeError("local inputs differ from the archived receipts")
    stages["integrity"] = time.perf_counter() - t0
    arrays, rows, _ = array.decode_inputs(None)
    extra = array.decode_extra(rows)
    nant = len(extra["antenna_names"])
    state = array.build_state(arrays, extra, nant)
    del arrays
    stages["decode_and_state"] = time.perf_counter() - t0
    result = json.loads((L1_RUN / "result.json").read_text())
    image = dict(array.ARRAY_IMAGE)
    rec = {"run": str(L1_RUN.relative_to(ROOT)), "image": image, "arms": {}}
    for arm in args.arms:
        a0 = time.perf_counter()
        with np.load(L1_RUN / "gains" / f"{arm}.npz") as g:
            gains, valid = g["gains"], g["gain_valid"]
        with np.load(L1_RUN / "flags" / f"{arm}.npz") as f:
            added = f["additions"]
        archived = result["arms"][arm]
        checks = {
            "gains_sha256": core_campaign.array_sha256(gains)
            == archived["gains_sha256"],
            "additions_sha256": core_campaign.array_sha256(added)
            == archived["additions_sha256"],
        }
        if not all(checks.values()):
            raise RuntimeError(
                f"{arm}: saved gains or additions differ from the archive"
            )
        solve = {
            "diagnostics": {"gains": gains, "gain_valid": valid},
            "added": np.flatnonzero(added),
        }
        sample, weight = array.corrected_stokes(state, solve)
        imaging = core_weights.imaging_weights(
            extra["uvw"],
            core_weights.wsclean_wavelengths(state["frequencies"]),
            weight,
            np.ones(len(weight), bool),
            mode="briggs",
            robust=core_campaign.ROBUST,
            width=core_weights.padded_size(image["width"], image["padding"]),
            height=core_weights.padded_size(image["height"], image["padding"]),
            pixel_scale=core_weights.pixel_scale_radians(image["scale_arcsec"]),
            return_grid=False,
        )
        model_flux, imaged = array.model_stokes_mean(state["model"], weight)
        np.savez(
            out / f"l1-{arm}.npz",
            uvw=extra["uvw"],
            frequencies=state["frequencies"],
            data=sample,
            weights=weight,
            imaging_weights=imaging["weights"],
            antenna1=state["antenna1"],
            antenna2=state["antenna2"],
            phase_dir=np.asarray(extra["phase_dir"], np.float64),
            settings=json.dumps(image),
        )
        rec["arms"][arm] = {
            "checks": checks,
            "model_flux": model_flux,
            "imaged_cells": imaged,
            "imaging_weight_sums": imaging["sums"],
            "boxes": archived["image"]["boxes_used"],
            "archived_image": {
                k: archived["image"][k]
                for k in (
                    "peak_jy_per_beam",
                    "residual_rms",
                    "offsource_rms",
                    "dirty_sha256",
                    "psf_sha256",
                    "gridder",
                )
            },
            "seconds": time.perf_counter() - a0,
        }
        del sample, weight, imaging
        print(arm, f"{rec['arms'][arm]['seconds']:.1f}s", flush=True)
    stages["total"] = time.perf_counter() - t0
    rec["stages"] = stages
    rec["max_rss_mb"] = maxrss_mb()
    write_json(out / "dump.json", rec)


# ---------------------------------------------------------------- MS inputs


def cmd_ms_inputs(args):
    """MS writer inputs for the C jobs and K arms: the dumped gridder inputs
    with the full gridding weight (f32 product, as the gridder forms it), and
    the C jobs' archived antennas and phase centre."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    common = {
        r: np.load(C_ORACLE / "inputs" / f"{r}-common.npz")
        for r in ("response", "caracal")
    }
    receipt = json.loads((C_ORACLE / "receipt.json").read_text())
    rec = {}
    for path in sorted(C_INPUTS.glob("*.npz")) + sorted(K_INPUTS.glob("*.npz")):
        inp = load_npz(path)
        weight = inp["weights"] * inp["imaging_weights"]
        nrow = len(inp["uvw"])
        if path.stem.startswith("c-"):
            shared = common[receipt["jobs"][path.stem[2:]]["role"]]
            if not np.array_equal(shared["UVW"], inp["uvw"]):
                raise RuntimeError(f"{path.stem}: UVW differs from the C export")
            a1, a2 = shared["ANTENNA1"], shared["ANTENNA2"]
            phase = shared["PHASE_DIR"]
        else:
            # The K dumps carry no antennas: the four stations' six baselines
            # in row order (no row is an autocorrelation; imaging ignores it).
            pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
            a1 = np.array([pairs[i % 6][0] for i in range(nrow)], np.int32)
            a2 = np.array([pairs[i % 6][1] for i in range(nrow)], np.int32)
            phase = np.array([5.146176, -1.111985])
        np.savez(
            out / f"{path.stem}.npz",
            uvw=inp["uvw"],
            frequencies=inp["frequencies"],
            data=inp["data"],
            weight=weight,
            antenna1=a1,
            antenna2=a2,
            phase_dir=phase,
        )
        rec[path.stem] = {
            "rows": nrow,
            "settings": inp["settings"],
            "weight_sha256": sha256_array(weight),
        }
    write_json(out / "ms-inputs.json", rec)


# ---------------------------------------------------------------- MS writer (container)


def cmd_write_ms(args):
    """Inside the container: a Measurement Set for WSClean's `-pol I`
    reader (see the module docstring). Rows are written in blocks."""
    from casacore import tables as pt

    with np.load(args.npz) as payload:
        inp = {key: payload[key] for key in payload.files}
    uvw, freq = inp["uvw"], inp["frequencies"]
    if "weight" in inp:
        weight = inp["weight"].astype(np.float32)
    else:
        weight = inp["weights"] * inp["imaging_weights"]
    nrow, nchan = weight.shape
    a1, a2 = inp["antenna1"].astype(np.int32), inp["antenna2"].astype(np.int32)
    nant = int(max(a1.max(), a2.max())) + 1
    desc = pt.maketabdesc(
        [
            pt.makearrcoldesc("DATA", 0j, valuetype="complex", shape=[nchan, 4]),
            pt.makearrcoldesc(
                "WEIGHT_SPECTRUM", 0.0, valuetype="float", shape=[nchan, 4]
            ),
        ]
    )
    ms = pt.default_ms(args.out, desc)
    ms.addrows(nrow)
    t0 = 5.0e9
    ms.putcol("TIME", t0 + 8.0 * np.arange(nrow))
    ms.putcol("TIME_CENTROID", t0 + 8.0 * np.arange(nrow))
    ms.putcol("INTERVAL", np.full(nrow, 8.0))
    ms.putcol("EXPOSURE", np.full(nrow, 8.0))
    ms.putcol("ANTENNA1", a1)
    ms.putcol("ANTENNA2", a2)
    ms.putcol("UVW", uvw)
    ms.putcol("SCAN_NUMBER", np.ones(nrow, np.int32))
    ms.putcol("FLAG_ROW", np.zeros(nrow, bool))
    quarter = (weight * np.float32(0.25)).astype(np.float32)
    if not np.array_equal(quarter * np.float32(4.0), weight):
        raise RuntimeError("weight / 4 is not exact (subnormal weights)")
    block = 1024
    for start in range(0, nrow, block):
        s = slice(start, min(start + block, nrow))
        n = s.stop - s.start
        data = np.zeros((n, nchan, 4), np.complex64)
        data[..., 0] = inp["data"][s]
        data[..., 3] = inp["data"][s]
        wspec = np.repeat(quarter[s][..., None], 4, axis=2)
        flag = np.repeat((weight[s] == 0)[..., None], 4, axis=2)
        ms.putcol("DATA", data, startrow=start, nrow=n)
        ms.putcol("WEIGHT_SPECTRUM", wspec, startrow=start, nrow=n)
        ms.putcol("FLAG", flag, startrow=start, nrow=n)
        ms.putcol("WEIGHT", np.ones((n, 4), np.float32), startrow=start, nrow=n)
        ms.putcol("SIGMA", np.ones((n, 4), np.float32), startrow=start, nrow=n)
    ms.close()
    ant = pt.table(f"{args.out}/ANTENNA", readonly=False, ack=False)
    ant.addrows(nant)
    ant.putcol("NAME", [f"m{i:03d}" for i in range(nant)])
    ant.putcol("STATION", [f"m{i:03d}" for i in range(nant)])
    ant.putcol("TYPE", ["GROUND-BASED"] * nant)
    ant.putcol("MOUNT", ["ALT-AZ"] * nant)
    ant.putcol("DISH_DIAMETER", np.full(nant, 13.5))
    base = np.array([5109224.3, 2006790.4, -3239100.6])
    ant.putcol("POSITION", base + np.arange(nant)[:, None] * np.array([10.0, 0.0, 0.0]))
    ant.close()
    spw = pt.table(f"{args.out}/SPECTRAL_WINDOW", readonly=False, ack=False)
    spw.addrows(1)
    width = np.full(nchan, freq[1] - freq[0] if nchan > 1 else 1e6)
    spw.putcell("CHAN_FREQ", 0, freq)
    spw.putcell("CHAN_WIDTH", 0, width)
    spw.putcell("EFFECTIVE_BW", 0, width)
    spw.putcell("RESOLUTION", 0, width)
    spw.putcell("NUM_CHAN", 0, nchan)
    spw.putcell("REF_FREQUENCY", 0, float(freq[0]))
    spw.putcell("TOTAL_BANDWIDTH", 0, float(width.sum()))
    spw.putcell("MEAS_FREQ_REF", 0, 5)
    spw.putcell("NAME", 0, "df2b")
    spw.close()
    pol = pt.table(f"{args.out}/POLARIZATION", readonly=False, ack=False)
    pol.addrows(1)
    pol.putcell("NUM_CORR", 0, 4)
    pol.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], np.int32))
    pol.putcell("CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32))
    pol.close()
    dd = pt.table(f"{args.out}/DATA_DESCRIPTION", readonly=False, ack=False)
    dd.addrows(1)
    dd.putcell("SPECTRAL_WINDOW_ID", 0, 0)
    dd.putcell("POLARIZATION_ID", 0, 0)
    dd.close()
    field = pt.table(f"{args.out}/FIELD", readonly=False, ack=False)
    field.addrows(1)
    direction = np.asarray(inp["phase_dir"], np.float64).reshape(1, 2)
    for col in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
        field.putcell(col, 0, direction)
    field.putcell("NAME", 0, "J1939-6342")
    field.close()
    obs = pt.table(f"{args.out}/OBSERVATION", readonly=False, ack=False)
    obs.addrows(1)
    obs.putcell("TELESCOPE_NAME", 0, "MeerKAT")
    obs.putcell("TIME_RANGE", 0, np.array([t0, t0 + 8.0 * nrow]))
    obs.close()
    print(
        "wrote",
        args.out,
        nrow,
        "rows",
        nchan,
        "channels",
        int(np.count_nonzero(weight)),
        "weighted",
    )


# ---------------------------------------------------------------- WSClean


def wsclean_args(name, ms, width, height, scale, gridder, accuracy, threads):
    cmd = [
        "wsclean",
        "-name",
        name,
        "-size",
        str(width),
        str(height),
        "-scale",
        f"{scale}asec",
        "-weight",
        "natural",
        "-pol",
        "I",
        "-data-column",
        "DATA",
        "-j",
        str(threads),
        "-abs-mem",
        "4",
        "-niter",
        "0",
        "-make-psf",
        "-no-update-model-required",
        "-no-min-grid-resolution",
        "-no-reorder",
        "-temp-dir",
        "/run/temp",
    ]
    if gridder == "wgridder":
        cmd += ["-gridder", "wgridder", "-wgridder-accuracy", f"{accuracy:g}"]
    else:
        cmd += ["-gridder", "wstacking", "-wstack-nwlayers", "64"]
    return cmd + [ms]


def docker(run_dir, cmd, timing_name, threads=1, extra_mounts=()):
    run_dir = Path(run_dir).resolve()
    (run_dir / "timing").mkdir(exist_ok=True)
    (run_dir / "temp").mkdir(exist_ok=True)
    mounts = [
        "-v",
        f"{ROOT.resolve()}:/code:ro",
        "-v",
        f"{OUTPUTS.resolve()}:/outputs:ro",
        "-v",
        f"{run_dir}:/run",
    ]
    for host, guest in extra_mounts:
        mounts += ["-v", f"{Path(host).resolve()}:{guest}:ro"]
    full = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--network",
        "none",
        "--tmpfs",
        "/tmp",
        "-e",
        "HOME=/tmp",
        "-e",
        f"OMP_NUM_THREADS={threads}",
        *mounts,
        "-w",
        "/run",
        IMAGE_NAME,
        "/usr/bin/time",
        "-f",
        "%e %M %x",
        "-o",
        f"/run/timing/{timing_name}.txt",
        *cmd,
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(full, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / f"{timing_name}.log").write_text(proc.stdout + proc.stderr)
    timing = (run_dir / "timing" / f"{timing_name}.txt").read_text().split()
    rec = {
        "command": cmd,
        "exit": proc.returncode,
        "docker_wall_s": wall,
        "wall_s": float(timing[-3]),
        "max_rss_mb": float(timing[-2]) / 1024.0,
    }
    if proc.returncode:
        raise RuntimeError(f"{timing_name} failed: {proc.stderr[-2000:]}")
    return rec


def cmd_make_ms(args):
    """`write-ms` in the container for one MS input npz (host side)."""
    run = Path(args.run_dir).resolve()
    npz = Path(args.npz).resolve()
    rec = docker(
        run,
        [
            "python3",
            "-I",
            "/code/examples/compare_df2b.py",
            "write-ms",
            f"/inp/{npz.name}",
            f"/run/{args.name}.ms",
        ],
        f"write-ms-{args.name}",
        extra_mounts=[(npz.parent, "/inp")],
    )
    write_json(run / f"write-ms-{args.name}.json", rec)
    print(args.name, f"{rec['wall_s']:.1f}s", flush=True)


def cmd_wsclean(args):
    run = Path(args.run_dir).resolve()
    name = f"{args.name}-{args.gridder}" + (
        f"-acc{args.accuracy:g}" if args.gridder == "wgridder" else ""
    )
    if args.threads != 1:
        name += f"-j{args.threads}"
    cmd = wsclean_args(
        f"/run/{name}",
        f"/run/{args.ms}",
        args.width,
        args.height,
        args.scale,
        args.gridder,
        args.accuracy,
        args.threads,
    )
    rec = docker(run, cmd, f"wsclean-{name}", threads=args.threads)
    rec["dirty_fits_sha256"] = sha256_file(run / f"{name}-dirty.fits")
    rec["psf_fits_sha256"] = sha256_file(run / f"{name}-psf.fits")
    write_json(run / f"wsclean-{name}.json", rec)
    print(name, f"{rec['wall_s']:.1f}s", f"{rec['max_rss_mb']:.0f} MB", flush=True)


# ---------------------------------------------------------------- compare

C_ARCHIVE_IMAGES = OUTPUTS / "core-c-20261029-01" / "images"
I_ARCHIVE_IMAGES = OUTPUTS / "tv-next-imaging-wsl-20261029-01" / "images"
K_ARCHIVE_IMAGES = OUTPUTS / "core-k-20261030-01" / "images"
K_ARCHIVE = ROOT / "research" / "results" / "core-k-luno-campaign.json"
DF1_SCIENCE = OUTPUTS / "df1-wgridder-20261030-01" / "science"
DF2_REF = OUTPUTS / "df2-20261030-01" / "ref"
DF2_THREADS = OUTPUTS / "df2-20261030-02" / "threads-final.json"
PRECONDITION = OUTPUTS / "df2b-20261030-00-precondition"
T3_TOLERANCE = 1e-5
T1_FLOOR_FACTOR = 100.0
F32_QUANTUM = 2.0**-23
L1_TOLERANCE = 1e-9
C_JOBS = (
    "caracal-firstpass-rejected",
    "caracal-mild",
    "caracal-no-change",
    "clean-full",
    "complete-adaptation",
    "complete-direct",
    "complete-full",
    "complete-total",
    "fixedG0-reference",
    "omitted-adaptation",
    "omitted-direct",
    "omitted-full",
    "omitted-total",
    "unit-compact",
    "unit-extended",
)
K_ARMS = (
    "original",
    "tricolour-firstpass",
    "tricolour-mild",
    "tv-policy",
    "tv-unguided-best",
    "tricolour-firstpass+tv",
)
L1_ARMS = ("original", "tricolour-firstpass", "tv-policy")


def read_fits_image(path):
    from astropy.io import fits

    with fits.open(path) as hdul:
        return hdul[0].data[0, 0].astype(np.float64), dict(hdul[0].header)


def diff_record(candidate, reference, kind):
    """L-infinity of `candidate - reference` over the reference peak (dirty)
    or absolute (PSF, peak one), with the central half and the border."""
    candidate = np.asarray(candidate, np.float64)
    reference = np.asarray(reference, np.float64)
    if candidate.shape != reference.shape:
        raise ValueError(f"shapes differ: {candidate.shape} {reference.shape}")
    peak = float(np.abs(reference).max())
    scale = peak if kind == "dirty" else 1.0
    d = candidate - reference
    rec = region_linf(d, scale)
    rec["central_half_linf_over_peak"] = float(np.abs(central(d)).max() / scale)
    rec["reference_peak"] = peak
    rec["identical"] = bool(np.array_equal(candidate, reference))
    rec["differing_pixels"] = int(np.count_nonzero(d))
    return rec


def _fits_hashes(directory):
    return {p.name: sha256_file(p) for p in sorted(Path(directory).glob("*.fits"))}


def _load_json(path):
    return json.loads(Path(path).read_text())


def _image_numbers(result):
    """The numbers of an I result that its images determine."""
    out = {"reference_fit": result["reference_fit"]}
    out["closures"] = result["dirty_image_closures_jy_per_beam"]
    for label, job in result["jobs"].items():
        out[label] = {
            k: job.get(k)
            for k in (
                "stats",
                "known_family_dirty_fit",
                "conditional_response_vs_fixedG0",
                "PSF_linf_difference_vs_fixedG0",
                "diagnostics",
            )
        }
    return out


def gate_g1(run, base):
    rec = {}
    for name in ("c", "i"):
        a = _fits_hashes(base / f"base-{name}" / "images")
        b = _fits_hashes(run / f"after-{name}" / "images")
        rec[f"{name}_fits"] = {"count": len(a), "identical": a == b and len(a) == 30}
    rc_a = _load_json(base / "base-c" / "result.json")["jobs"]
    rc_b = _load_json(run / "after-c" / "result.json")["jobs"]
    rec["c_stats_equal"] = all(rc_a[j]["stats"] == rc_b[j]["stats"] for j in rc_a)
    rec["i_image_numbers_equal"] = _image_numbers(
        _load_json(base / "base-i" / "result.json")
    ) == _image_numbers(_load_json(run / "after-i" / "result.json"))
    ka = _load_json(base / "base-k" / "kinvert.json")["arms"]
    kb = _load_json(run / "after-k" / "kinvert.json")["arms"]
    rec["k_arrays"] = {
        "count": len(ka),
        "identical": all(
            ka[a][k] == kb[a][k]
            for a in ka
            for k in ("dirty_sha256", "psf_sha256", "stats")
        ),
    }
    pa = _fits_hashes(base / "base-l1pre" / "replay" / "images")
    pb = _fits_hashes(run / "after-l1pre" / "replay" / "images")
    pre_b = _load_json(run / "after-l1pre" / "result.json")
    rec["l1_precondition_replay_fits"] = {
        "count": len(pa),
        "identical": pa == pb and len(pa) > 0,
    }
    rec["l1_precondition_passed_after"] = bool(pre_b["all_passed"])
    la = _load_json(base / "base-l1" / "original-wstack-g4.json")
    lb = _load_json(run / "after-l1" / "original-wstack-g4.json")
    rec["l1_wstack_g4"] = {
        "identical": all(
            la[k] == lb[k] for k in ("dirty_sha256", "psf_sha256", "stats")
        )
    }
    rec["pass"] = bool(
        rec["c_fits"]["identical"]
        and rec["i_fits"]["identical"]
        and rec["c_stats_equal"]
        and rec["i_image_numbers_equal"]
        and rec["k_arrays"]["identical"]
        and rec["l1_precondition_replay_fits"]["identical"]
        and rec["l1_precondition_passed_after"]
        and rec["l1_wstack_g4"]["identical"]
    )
    return rec


def _fits_image_of_product(inp, **kw):
    _host()
    from rang import core_wgridder

    s = inp["settings"]
    return core_wgridder.fits_image(
        inp["uvw"],
        inp["frequencies"],
        inp["data"],
        inp["weights"] * inp["imaging_weights"],
        s["width"],
        s["height"],
        s["scale_arcsec"],
        epsilon=EPSILON,
        **kw,
    )


def gate_g2(run, base):
    rec = {"c": {}, "k": {}, "l1": {}}
    for job in C_JOBS:
        inp = load_npz(C_INPUTS / f"c-{job}.npz")
        ref = _fits_image_of_product(inp)
        mine = _load_json(run / "images" / f"c-{job}-wgrid.json")
        fits_d, _ = read_fits_image(run / "wgrid-c" / "images" / f"{job}-dirty.fits")
        fits_p, _ = read_fits_image(run / "wgrid-c" / "images" / f"{job}-psf.fits")
        rec["c"][job] = {
            "invert_equals_fits_image_of_product": mine["dirty_sha256"]
            == sha256_array(ref["dirty"])
            and mine["psf_sha256"] == sha256_array(ref["psf"]),
            "driver_fits_equal_f32_of_invert": bool(
                np.array_equal(fits_d, ref["dirty"].astype(np.float32))
                and np.array_equal(fits_p, ref["psf"].astype(np.float32))
            ),
        }
    kinv = _load_json(run / "wgrid-k" / "kinvert.json")["arms"]
    for arm in K_ARMS:
        inp = load_npz(K_INPUTS / f"k-{arm}.npz")
        ref = _fits_image_of_product(inp)
        rec["k"][arm] = {
            "invert_equals_fits_image_of_product": kinv[f"k-{arm}"]["dirty_sha256"]
            == sha256_array(ref["dirty"])
            and kinv[f"k-{arm}"]["psf_sha256"] == sha256_array(ref["psf"])
        }
    for arm in L1_ARMS:
        inp = load_npz(base / "l1-inputs" / f"l1-{arm}.npz")
        ref = _fits_image_of_product(inp)
        tag = "l1-original-wgrid-r1" if arm == "original" else f"l1-{arm}-wgrid"
        mine = _load_json(run / "images" / f"{tag}.json")
        rec["l1"][arm] = {
            "invert_equals_fits_image_of_product": mine["dirty_sha256"]
            == sha256_array(ref["dirty"])
            and mine["psf_sha256"] == sha256_array(ref["psf"])
        }
        del inp, ref
    i_vs_c = {}
    for job in C_JOBS:
        for kind in ("dirty", "psf"):
            a, _ = read_fits_image(run / "wgrid-i" / "images" / f"{job}-{kind}.fits")
            b, _ = read_fits_image(run / "wgrid-c" / "images" / f"{job}-{kind}.fits")
            i_vs_c[f"{job}-{kind}"] = bool(np.array_equal(a, b))
    rec["i_fits_equal_c_fits"] = all(i_vs_c.values())
    rec["pass"] = all(
        all(v.values()) for part in ("c", "k", "l1") for v in rec[part].values()
    )
    return rec


def gate_g3(run):
    archived = _load_json(DF2_THREADS)["threads"]["1"]["hashes"]
    mine = _load_json(run / "g3-threads.json")
    rec = {"threads": {}}
    for n, entry in mine["threads"].items():
        rec["threads"][n] = {
            "outputs": len(entry["hashes"]),
            "equal_to_df2a_archive": entry["hashes"] == archived,
        }
    gates = _load_json(run / "g3-gates" / "gates.json")
    rec["gates_pass_criteria_1_2_3_5"] = gates["pass_criteria_1_2_3_5"]
    rec["gates_failures"] = gates["failures"]
    rec["gates_library"] = gates["library"]
    rec["library"] = mine.get("library")
    rec["pass"] = all(
        v["equal_to_df2a_archive"] for v in rec["threads"].values()
    ) and bool(gates["pass_criteria_1_2_3_5"])
    return rec


def gate_t1(run):
    floor = _load_json(PRECONDITION / "floor.json")["cases"]
    k_floor = max(floor["K"][k]["linf_over_peak"] for k in ("dirty", "psf"))
    k_bound = T1_FLOOR_FACTOR * k_floor
    rec = {"k_bound": k_bound, "k": {}, "c": {}, "i": {}}
    for arm in K_ARMS:
        for kind in ("dirty", "psf"):
            ref = np.load(DF2_REF / f"k_k-{arm}_f64_eps1e-06_{kind}.npy")
            mine = np.load(run / "images" / f"k-{arm}-wgrid-r1-{kind}.npy")
            r = diff_record(mine, ref, kind)
            r["pass"] = r["linf_over_peak"] <= k_bound
            rec["k"][f"{arm}-{kind}"] = r
    for name, images in (
        ("c", run / "wgrid-c" / "images"),
        ("i", run / "wgrid-i" / "images"),
    ):
        archive = DF1_SCIENCE / f"{name}-run" / "images"
        for job in C_JOBS:
            for kind in ("dirty", "psf"):
                mine, _ = read_fits_image(images / f"{job}-{kind}.fits")
                ref, _ = read_fits_image(archive / f"{job}-{kind}.fits")
                r = diff_record(mine, ref, kind)
                r["pass"] = r["linf_over_peak"] <= F32_QUANTUM * (
                    r["reference_peak"] if kind == "psf" else 1.0
                )
                rec[name][f"{job}-{kind}"] = r
    rec["pass"] = {
        part: all(v["pass"] for v in rec[part].values()) for part in ("k", "c", "i")
    }
    rec["l1"] = "no exact-gridder archive exists"
    return rec


def _wsclean_pair(wsdir, name, acc="1e-06", threads=1):
    stem = f"{name}-wgridder-acc{acc}" + (f"-j{threads}" if threads != 1 else "")
    d, hd = read_fits_image(wsdir / f"{stem}-dirty.fits")
    p, _ = read_fits_image(wsdir / f"{stem}-psf.fits")
    return d, p, hd


def gate_t3(run, base):
    _host()
    from rang import core_campaign_array as array

    ws = run / "wsclean"
    rec = {
        "tolerance": T3_TOLERANCE,
        "c": {},
        "i": {},
        "k": {},
        "l1": {},
        "reported": {},
    }

    def one(label, mine_d, mine_p, stats, name, acc="1e-06"):
        d, p, hd = _wsclean_pair(ws, name, acc)
        counters = {
            "wsclean_WSCIMGWG": float(hd["WSCIMGWG"]),
            "core_image_weight": stats["image_weight"],
            "image_weight_relative": abs(float(hd["WSCIMGWG"]) - stats["image_weight"])
            / stats["image_weight"],
            "wsclean_WSCNVIS": int(hd["WSCNVIS"]),
            "core_gridded_count": int(stats["gridded_count"]),
        }
        counters["pass"] = bool(
            counters["image_weight_relative"] <= 1e-9
            and counters["wsclean_WSCNVIS"] == counters["core_gridded_count"]
        )
        out = {
            "counters": counters,
            "dirty": diff_record(mine_d, d, "dirty"),
            "psf": diff_record(mine_p, p, "psf"),
        }
        out["pass"] = bool(
            counters["pass"]
            and out["dirty"]["linf_over_peak"] <= T3_TOLERANCE
            and out["psf"]["linf_over_peak"] <= T3_TOLERANCE
        )
        return out

    for job in C_JOBS:
        m = _load_json(run / "images" / f"c-{job}-wgrid.json")
        md = np.load(run / "images" / f"c-{job}-wgrid-dirty.npy")
        mp = np.load(run / "images" / f"c-{job}-wgrid-psf.npy")
        rec["c"][job] = one(job, md, mp, m["stats"], f"c-{job}")
        fd, _ = read_fits_image(run / "wgrid-i" / "images" / f"{job}-dirty.fits")
        fp, _ = read_fits_image(run / "wgrid-i" / "images" / f"{job}-psf.fits")
        rec["i"][job] = one(job, fd, fp, m["stats"], f"c-{job}")
    for arm in K_ARMS:
        m = _load_json(run / "images" / f"k-{arm}-wgrid-r1.json")
        md = np.load(run / "images" / f"k-{arm}-wgrid-r1-dirty.npy")
        mp = np.load(run / "images" / f"k-{arm}-wgrid-r1-psf.npy")
        rec["k"][arm] = one(arm, md, mp, m["stats"], f"k-{arm}")
    m = _load_json(run / "images" / "l1-original-wgrid-r1.json")
    md = np.load(run / "images" / "l1-original-wgrid-r1-dirty.npy")
    mp = np.load(run / "images" / "l1-original-wgrid-r1-psf.npy")
    rec["l1"]["original"] = one("original", md, mp, m["stats"], "l1-original")
    # Reported: WSClean's accuracy sweep, and the core with divide_by_n.
    cases = {
        "c-clean-full": (C_INPUTS / "c-clean-full.npz", "c-clean-full-wgrid"),
        "k-original": (K_INPUTS / "k-original.npz", "k-original-wgrid-r1"),
        "l1-original": (base / "l1-inputs" / "l1-original.npz", "l1-original-wgrid-r1"),
    }
    for name, (npz, tag) in cases.items():
        md = np.load(run / "images" / f"{tag}-dirty.npy")
        mp = np.load(run / "images" / f"{tag}-psf.npy")
        stats = _load_json(run / "images" / f"{tag}.json")["stats"]
        sweep = {}
        for acc in ("0.0001", "1e-06", "1e-08"):
            r = one(name, md, mp, stats, name, acc)
            sweep[acc] = {k: r[k]["linf_over_peak"] for k in ("dirty", "psf")}
            sweep[acc]["dirty_central_half"] = r["dirty"]["central_half_linf_over_peak"]
        inp = load_npz(npz)
        nd = _fits_image_of_product(inp, divide_by_n=True)
        del inp
        d, p, _ = _wsclean_pair(ws, name)
        rec["reported"][name] = {
            "accuracy_sweep": sweep,
            "divide_by_n_core_vs_wsclean": {
                "dirty": diff_record(nd["dirty"], d, "dirty")["linf_over_peak"],
                "psf": diff_record(nd["psf"], p, "psf")["linf_over_peak"],
            },
        }
    rec["pass"] = {
        part: all(v["pass"] for v in rec[part].values())
        for part in ("c", "i", "k", "l1")
    }
    del array
    return rec


def l1_metrics(dirty, psf, boxes, model_flux):
    _host()
    from rang import core_campaign_array as array

    return array.array_image_metrics(dirty, psf, boxes, model_flux)


def report_t2_and_l1(run, base):
    _host()
    from rang import core_campaign

    rec = {"c": {}, "i": {}, "k": {}, "l1": {}}
    for name, images, archive in (
        ("c", run / "wgrid-c" / "images", C_ARCHIVE_IMAGES),
        ("i", run / "wgrid-i" / "images", I_ARCHIVE_IMAGES),
    ):
        for job in C_JOBS:
            for kind in ("dirty", "psf"):
                mine, _ = read_fits_image(images / f"{job}-{kind}.fits")
                ref, _ = read_fits_image(archive / f"{job}-{kind}.fits")
                rec[name][f"{job}-{kind}"] = diff_record(mine, ref, kind)
    karch = _load_json(K_ARCHIVE)
    k_metrics = {}
    for arm in K_ARMS:
        md = np.load(run / "images" / f"k-{arm}-wgrid-r1-dirty.npy")
        mp = np.load(run / "images" / f"k-{arm}-wgrid-r1-psf.npy")
        for kind, mine in (("dirty", md), ("psf", mp)):
            ref, _ = read_fits_image(K_ARCHIVE_IMAGES / f"{arm}-{kind}.fits")
            rec["k"][f"{arm}-{kind}"] = diff_record(mine, ref, kind)
        archived = karch["arms"][arm]["image"]
        mine = core_campaign.image_metrics(md, mp, archived.get("model_stokes_i_jy"))
        k_metrics[arm] = {
            key: {"wgrid": mine[key], "archive": archived[key]}
            for key in (
                "peak_jy_per_beam",
                "residual_rms",
                "offsource_rms",
                "flux_recovery",
            )
            if key in archived
        }
    rec["k_metrics"] = k_metrics
    rec["k_hypotheses"] = {
        f"{c} vs {r}": {
            "residual_rms_ratio_wgrid": k_metrics[c]["residual_rms"]["wgrid"]
            / k_metrics[r]["residual_rms"]["wgrid"],
            "residual_rms_ratio_archive": k_metrics[c]["residual_rms"]["archive"]
            / k_metrics[r]["residual_rms"]["archive"],
        }
        for c, r in (
            ("tv-policy", "tricolour-firstpass"),
            ("tv-policy", "original"),
            ("tricolour-firstpass+tv", "tricolour-firstpass"),
        )
    }
    dump = _load_json(base / "l1-inputs" / "dump.json")["arms"]
    l1_result = _load_json(L1_RUN / "result.json")
    l1 = {}
    for arm in L1_ARMS:
        boxes = dump[arm]["boxes"]
        flux = dump[arm]["model_flux"]
        archived = l1_result["arms"][arm]["image"]
        entry = {}
        for g, tag in (
            (
                "wgrid",
                "l1-original-wgrid-r1" if arm == "original" else f"l1-{arm}-wgrid",
            ),
            (
                "wstack_g4",
                None if arm == "original" else f"l1-{arm}-wstack-g4",
            ),
        ):
            if tag is None:
                d = np.load(run / "after-l1" / "original-wstack-g4-dirty.npy")
                p = np.load(run / "after-l1" / "original-wstack-g4-psf.npy")
            else:
                d = np.load(run / "images" / f"{tag}-dirty.npy")
                p = np.load(run / "images" / f"{tag}-psf.npy")
            m = l1_metrics(d, p, boxes, flux)
            entry[g] = {
                k: m[k]
                for k in (
                    "peak_jy_per_beam",
                    "peak_pixel",
                    "residual_rms",
                    "offsource_rms",
                    "offsource_robust_sigma",
                    "residual_robust_sigma_offsource",
                    "psf_max_sidelobe",
                    "flux_recovery",
                )
            }
            for kind, img in (("dirty", d), ("psf", p)):
                ref, _ = read_fits_image(L1_RUN / "images" / f"{arm}-{kind}.fits")
                entry[f"{g}_vs_archive_{kind}"] = diff_record(img, ref, kind)
        entry["archive"] = {k: archived[k] for k in entry["wgrid"] if k in archived}
        rel = {
            k: abs(entry["wstack_g4"][k] - archived[k]) / abs(archived[k])
            for k in ("peak_jy_per_beam", "residual_rms", "offsource_rms")
        }
        entry["reconstruction"] = {
            "metric_relative_differences": rel,
            "metrics_pass": all(v <= L1_TOLERANCE for v in rel.values()),
            "pixels_pass": all(
                entry[f"wstack_g4_vs_archive_{k}"]["linf_over_peak"]
                <= F32_QUANTUM
                * (
                    1.0
                    if k == "dirty"
                    else entry[f"wstack_g4_vs_archive_{k}"]["reference_peak"]
                )
                for k in ("dirty", "psf")
            ),
        }
        l1[arm] = entry
    rec["l1"] = l1
    rec["l1_headline_residual_rms_ratio"] = {
        g: l1["tv-policy"][g]["residual_rms"]
        / l1["tricolour-firstpass"][g]["residual_rms"]
        for g in ("wgrid", "wstack_g4")
    }
    rec["l1_headline_residual_rms_ratio"]["archive"] = (
        l1_result["arms"]["tv-policy"]["image"]["residual_rms"]
        / l1_result["arms"]["tricolour-firstpass"]["image"]["residual_rms"]
    )
    g4 = np.load(run / "images" / "l1-original-wgrid-g4-dirty.npy")
    g1 = np.load(run / "images" / "l1-original-wgrid-r1-dirty.npy")
    rec["l1_wgrid_groups4_vs_1"] = diff_record(g4, g1, "dirty")
    rec["prediction_central_half_le_1pc"] = {
        part: max(
            v["central_half_linf_over_peak"]
            for k, v in rec[part].items()
            if k.endswith("-dirty")
        )
        for part in ("c", "i", "k")
    }
    return rec


def cost_table(run):
    rows = {}
    for path in sorted((run / "images").glob("*-r[123].json")):
        rec = _load_json(path)
        key = path.stem.rsplit("-r", 1)[0]
        rows.setdefault(key, []).append(
            {
                "wall_s": rec["image_wall_s"],
                "max_rss_mb": rec["max_rss_mb"],
                "rss_after_inputs_mb": rec["rss_after_inputs_mb"],
                "load": rec["loadavg_before"],
            }
        )
    out = {}
    for key, values in rows.items():
        walls = sorted(v["wall_s"] for v in values)
        out[key] = {
            "repeats": len(values),
            "median_wall_s": walls[len(walls) // 2],
            "min_wall_s": walls[0],
            "max_wall_s": walls[-1],
            "max_rss_mb": max(v["max_rss_mb"] for v in values),
            "rss_after_inputs_mb": max(v["rss_after_inputs_mb"] for v in values),
            "load": [v["load"] for v in values],
        }
    for extra in ("l1-original-wgrid-t16", "l1-original-wgrid-g4"):
        rec = _load_json(run / "images" / f"{extra}.json")
        out[extra] = {
            "wall_s": rec["image_wall_s"],
            "max_rss_mb": rec["max_rss_mb"],
            "threads": rec["threads"],
        }
    rec = _load_json(run / "after-l1" / "original-wstack-g4.json")
    out["l1-original-wstack-g4"] = {
        "wall_s": rec["image_wall_s"],
        "max_rss_mb": rec["max_rss_mb"],
    }
    ws = {}
    for path in sorted((run / "wsclean").glob("wsclean-*.json")):
        rec = _load_json(path)
        log = (run / "wsclean" / "logs" / f"{path.stem}.log").read_text()
        inversion = [line for line in log.splitlines() if line.startswith("Inversion:")]
        ws[path.stem] = {
            "wall_s": rec["wall_s"],
            "max_rss_mb": rec["max_rss_mb"],
            "inversion": inversion[-1] if inversion else None,
        }
    out["wsclean"] = ws
    return out


def cmd_compare(args):
    run, base = Path(args.run_dir), Path(args.base_dir)
    result = {
        "protocol": "research/df2b-wgrid.md",
        "run": str(run),
        "base": str(base),
        "G1_wstack_identity": gate_g1(run, base),
        "G2_two_weights_and_wiring": gate_g2(run, base),
        "G3_bindings": gate_g3(run),
        "T1_against_exact_archives": gate_t1(run),
        "T3_against_wsclean37": gate_t3(run, base),
        "T2_against_wstack_archives_and_L1": report_t2_and_l1(run, base),
        "cost": cost_table(run),
    }
    write_json(args.out, result)
    print(
        json.dumps(
            {k: v.get("pass") for k, v in result.items() if isinstance(v, dict)},
            indent=1,
        )
    )


def _worst(items, kind="dirty", key="linf_over_peak"):
    sel = {k: v for k, v in items.items() if k.endswith(f"-{kind}")} if kind else items
    name, rec = max(sel.items(), key=lambda kv: kv[1][key])
    return {"worst": rec[key], "where": name}


def cmd_summary(args):
    """The compact archive `research/results/df2b-wgrid.json` from the run's
    `compare.json`, the precondition and the run receipts."""
    run, base = Path(args.run_dir), Path(args.base_dir)
    c = _load_json(run / "compare.json")
    floor = _load_json(PRECONDITION / "floor.json")["cases"]
    harness = _load_json(PRECONDITION / "harness-check.json")
    g1, g2, g3 = (
        c["G1_wstack_identity"],
        c["G2_two_weights_and_wiring"],
        c["G3_bindings"],
    )
    t1, t3, t2 = (
        c["T1_against_exact_archives"],
        c["T3_against_wsclean37"],
        c["T2_against_wstack_archives_and_L1"],
    )
    icmp = _load_json(run / "wgrid-i" / "compare-archive.json")
    classes = {}
    for f in icmp["failures"]:
        key = f["class"] + (f"/{f['path'][-1]}" if f["class"] == "exact" else "")
        classes[key] = classes.get(key, 0) + 1

    def t3_part(part):
        items = t3[part]
        return {
            "inputs": len(items),
            "dirty_linf_over_peak": max(
                v["dirty"]["linf_over_peak"] for v in items.values()
            ),
            "dirty_central_half_linf_over_peak": max(
                v["dirty"]["central_half_linf_over_peak"] for v in items.values()
            ),
            "dirty_border_linf_over_peak": max(
                v["dirty"]["border_linf_over_peak"] for v in items.values()
            ),
            "psf_linf": max(v["psf"]["linf_over_peak"] for v in items.values()),
            "counters_max_image_weight_relative": max(
                v["counters"]["image_weight_relative"] for v in items.values()
            ),
            "counters_nvis_equal": all(
                v["counters"]["wsclean_WSCNVIS"] == v["counters"]["core_gridded_count"]
                for v in items.values()
            ),
            "pass": t3["pass"][part],
        }

    def t2_part(part):
        items = t2[part]
        d = {k: v for k, v in items.items() if k.endswith("-dirty")}
        p = {k: v for k, v in items.items() if k.endswith("-psf")}
        return {
            "dirty_linf_over_peak_range": [
                min(v["linf_over_peak"] for v in d.values()),
                max(v["linf_over_peak"] for v in d.values()),
            ],
            "dirty_central_half_max": max(
                v["central_half_linf_over_peak"] for v in d.values()
            ),
            "psf_linf_max": max(v["linf_over_peak"] for v in p.values()),
            "psf_central_half_max": max(
                v["central_half_linf_over_peak"] for v in p.values()
            ),
        }

    l1 = {}
    for arm, e in t2["l1"].items():
        l1[arm] = {
            "reconstruction": e["reconstruction"],
            "metrics": {
                "wgrid": e["wgrid"],
                "wstack_g4": e["wstack_g4"],
                "archive": e["archive"],
            },
            "wgrid_vs_archive": {
                kind: {
                    k: e[f"wgrid_vs_archive_{kind}"][k]
                    for k in (
                        "linf_over_peak",
                        "central_half_linf_over_peak",
                        "rms_over_peak",
                    )
                }
                for kind in ("dirty", "psf")
            },
        }
    out = {
        "schema_version": 1,
        "task": "big plan DF2b",
        "protocol": "research/df2b-wgrid.md",
        "protocol_commit": "abfb2e4",
        "code_commit": (run / "head.txt").read_text().split()[0],
        "runs": {
            "precondition": str(PRECONDITION.relative_to(ROOT)),
            "baseline": str(base),
            "measured": str(run),
        },
        "precondition": {
            "permutation_floor": {
                name: {
                    kind: floor[name][kind]["linf_over_peak"]
                    for kind in ("dirty", "psf")
                }
                for name in floor
            },
            "ms_harness_wstacking37_vs_archive36": {
                kind: harness[f"wstacking37_vs_archive36_{kind}"]
                for kind in ("dirty", "psf")
            },
        },
        "G1_wstack_identity": g1,
        "G2_two_weights_and_wiring": {
            "pass": g2["pass"],
            "inputs": {part: len(g2[part]) for part in ("c", "k", "l1")},
            "i_fits_equal_c_fits": g2["i_fits_equal_c_fits"],
        },
        "G3_bindings": {**g3, "gates_library": Path(g3["gates_library"]).name},
        "T1_against_exact_archives": {
            "k_bound": t1["k_bound"],
            "f32_quantum_over_peak": F32_QUANTUM,
            **{
                part: {
                    **_worst(t1[part], kind=None),
                    "differing_pixels": sum(
                        v["differing_pixels"] for v in t1[part].values()
                    ),
                    "pass": t1["pass"][part],
                }
                for part in ("k", "c", "i")
            },
            "l1": t1["l1"],
        },
        "T2_against_wstack_archives": {
            **{part: t2_part(part) for part in ("c", "i", "k")},
            "prediction_central_half_le_0.01": {
                part: v <= 0.01
                for part, v in t2["prediction_central_half_le_1pc"].items()
            },
            "i_comparator_failures_by_class": classes,
            "k_metrics": t2["k_metrics"],
            "k_residual_rms_calls": t2["k_hypotheses"],
            "l1": l1,
            "l1_headline_residual_rms_ratio": t2["l1_headline_residual_rms_ratio"],
            "l1_wgrid_groups4_vs_1_dirty_linf_over_peak": t2["l1_wgrid_groups4_vs_1"][
                "linf_over_peak"
            ],
        },
        "T3_against_wsclean37": {
            "image": IMAGE_NAME,
            "wsclean_binary_sha256": "f098c035443a78e811ac35a3333ebca65cddd389e1f3e40191b2ea95b29d3498",
            "accuracy": 1e-6,
            "tolerance": T3_TOLERANCE,
            **{part: t3_part(part) for part in ("c", "i", "k", "l1")},
            "reported": t3["reported"],
        },
        "cost": c["cost"],
    }
    write_json(args.out, out)
    print("wrote", args.out)


# ---------------------------------------------------------------- main


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("floor")
    s.add_argument("out")
    s.add_argument("--extra", nargs="*", default=[])
    s.set_defaults(fn=cmd_floor)
    s = sub.add_parser("kinvert")
    s.add_argument("out")
    s.add_argument("--inputs", default=str(K_INPUTS))
    s.add_argument("--gridder", default="wstack")
    s.set_defaults(fn=cmd_kinvert)
    s = sub.add_parser("image")
    s.add_argument("npz")
    s.add_argument("out_prefix")
    s.add_argument("--gridder", default="wstack")
    s.add_argument("--groups", type=int, default=1)
    s.set_defaults(fn=cmd_image)
    s = sub.add_parser("dump-l1")
    s.add_argument("out")
    s.add_argument("--arms", nargs="+", default=["original"])
    s.set_defaults(fn=cmd_dump_l1)
    s = sub.add_parser("ms-inputs")
    s.add_argument("out")
    s.set_defaults(fn=cmd_ms_inputs)
    s = sub.add_parser("write-ms")
    s.add_argument("npz")
    s.add_argument("out")
    s.set_defaults(fn=cmd_write_ms)
    s = sub.add_parser("make-ms")
    s.add_argument("run_dir")
    s.add_argument("name")
    s.add_argument("npz")
    s.set_defaults(fn=cmd_make_ms)
    s = sub.add_parser("wsclean")
    s.add_argument("run_dir")
    s.add_argument("name")
    s.add_argument("ms")
    s.add_argument("width", type=int)
    s.add_argument("height", type=int)
    s.add_argument("scale", type=float)
    s.add_argument("--gridder", default="wgridder", choices=("wgridder", "wstacking"))
    s.add_argument("--accuracy", type=float, default=EPSILON)
    s.add_argument("--threads", type=int, default=1)
    s.set_defaults(fn=cmd_wsclean)
    s = sub.add_parser("compare")
    s.add_argument("run_dir")
    s.add_argument("base_dir")
    s.add_argument("out")
    s.set_defaults(fn=cmd_compare)
    s = sub.add_parser("summary")
    s.add_argument("run_dir")
    s.add_argument("base_dir")
    s.add_argument("out")
    s.set_defaults(fn=cmd_summary)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
