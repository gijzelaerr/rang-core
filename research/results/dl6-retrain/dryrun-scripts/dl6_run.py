# SPDX-License-Identifier: MIT
"""DL6 dry run (research/dl6-retrain.md section 8): run one of F5's stage
scripts (branch dl3-f5, `examples/f5_*.py`) on the 1k configuration (rule 1
of section 3) without editing them. Points `rang.f5flag`'s set list and
loader at dl6_load_ms.py's scans, and F5's cached T/A flags at DL2's teacher
labels (rang = T, aoflagger = A), then calls the script's main().

    DL6_SCANS=DIR DL6_LABELS=DIR python dl6_run.py examples/f5_shards.py ARGS...

Channels: F5's band only (BAND_HZ, 512 of 1,024). Dry-run reductions (labelled in the note): train scans 1 and 3 with two
realisations each, validation scan 19, no F-SIM scans. Held-out scans 23 and
25 are refused.
"""

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
from rang import f5flag as f5

CBID = "1735892129"
SPLIT = {
    ("calibrator", "train"): [f"dl2:{CBID}:scan001", f"dl2:{CBID}:scan003"],
    ("calibrator", "validation"): [f"dl2:{CBID}:scan019"],
}
HELDOUT = {"scan023", "scan025"}
# F5's band: LUNO tiles 8-23 of 4k, 1070.0-1497.8 MHz (rang.f3flag.LUNO_TILES);
# at 1k that is channels 256-767.
BAND_HZ = (1069.9e6, 1497.9e6)
SCANS = Path(os.environ["DL6_SCANS"])
LABELS = Path(os.environ["DL6_LABELS"])


def real_sets(klass, role):
    return list(SPLIT[(klass, role)])


def load(spec, heldout=False):
    kind, cbid, name = spec.split(":")
    if kind != "dl2" or cbid != CBID:
        raise ValueError(spec)
    if name in HELDOUT:
        raise PermissionError(f"{spec} is held out for DL6's agent test")
    z = np.load(SCANS / f"{name}.npz")
    ch = _band(z["chan_freq"])
    scan = {k: np.ascontiguousarray(z[k]) for k in z.files if k != "keep"}
    for k in ("data", "input_flags"):
        scan[k] = np.ascontiguousarray(scan[k][:, ch])
    for k in ("chan_freq", "chan_width"):
        scan[k] = np.ascontiguousarray(scan[k][ch])
    scan["field"] = f"DL2 {cbid} {name}"
    scan["klass"] = "calibrator"
    scan["nant"] = len(scan["antenna_position"])
    return scan


def _band(freq):
    return np.flatnonzero((freq >= BAND_HZ[0]) & (freq <= BAND_HZ[1]))


def _teacher(teacher, name, keep, nchan, ncorr, ch):
    d = LABELS / teacher / CBID / name
    packed = np.load(d / "flag.npy")
    bits = np.unpackbits(packed, axis=1, count=nchan * ncorr).astype(bool)
    return np.ascontiguousarray(bits.reshape(-1, nchan, ncorr)[keep][:, ch].any(-1))


def cached_flags(name, klass, sources):
    scan = name.split("-")[-1]
    z = np.load(SCANS / f"{scan}.npz", mmap_mode="r")
    keep = z["keep"]
    nchan, ncorr = z["input_flags"].shape[1:]
    ch = _band(z["chan_freq"])
    t = _teacher("rang", scan, keep, nchan, ncorr, ch)
    a = _teacher("aoflagger", scan, keep, nchan, ncorr, ch)
    return t, a, str(LABELS)


def patch_shards(sh):
    sh.REALISATIONS = {"train": 2, "validation": 2}
    sh.cached_flags = cached_flags
    sh.sim_scans = lambda klass, role: []


def write_cache(root):
    """DL2's teacher labels in F4's flag-cache layout
    (`<root>/calibrator/flags/<name>-T.npy`, `-A.npy`), which F5's tau and
    shard scripts read."""
    d = Path(root) / "calibrator" / "flags"
    d.mkdir(parents=True, exist_ok=True)
    for specs in SPLIT.values():
        for spec in specs:
            name = spec.replace(":", "-")
            t, a, _ = cached_flags(name, "calibrator", [])
            np.save(d / f"{name}-T.npy", t)
            np.save(d / f"{name}-A.npy", a)
            print(name, t.shape, round(float(t.mean()), 4), round(float(a.mean()), 4))


def main():
    if sys.argv[1] == "cache":
        write_cache(sys.argv[2])
        return
    script = Path(sys.argv[1]).resolve()
    f5.real_sets = real_sets
    f5.load = load
    spec = importlib.util.spec_from_file_location(script.stem, script)
    mod = importlib.util.module_from_spec(spec)
    sys.argv = [str(script)] + sys.argv[2:]
    spec.loader.exec_module(mod)
    if script.stem == "f5_shards":
        patch_shards(mod)
    elif hasattr(mod, "sh"):
        patch_shards(mod.sh)
    mod.main()


if __name__ == "__main__":
    main()
