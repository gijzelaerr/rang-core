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
    python examples/compare_df2b.py compare RUN_DIR OUT.json
    python examples/compare_df2b.py summary RUN_DIR... --out research/results/df2b-wgrid.json

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
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
