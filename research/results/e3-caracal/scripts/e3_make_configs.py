"""Write E3's CARACal configs from the shipped samples (CARACal 8f7bb363) by
exact, counted text edits; each edit is one A0 6.4 deviation (or E3's own,
labelled in research/e3-caracal.md section 3). Run from the repo root:

    python research/results/e3-caracal/scripts/e3_make_configs.py PASS NCPU [TILE]

PASS is 'correct' or 'timed'; NCPU goes to selfcal.ncpu (8 or 0 = all 16).
Writes research/results/e3-caracal/configs/e3{a,b}-PASS.yml.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHIP = HERE.parent / "shipped"
OUT = HERE.parent / "configs"


def edit(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 match of {old!r}, found {n}")
    return text.replace(old, new)


def general(prefix):
    # Deviation 1 (names, directories) and the backend. msdir/output on D:,
    # the converted MS read-only in rawdatadir (never written; checked after).
    return (
        "general:\n"
        f"  prefix: {prefix}\n"
        "  backend: docker\n"
        "  rawdatadir: /mnt/d/rang/outputs/e3-20261111-input\n"
        "  msdir: msdir\n"
        "  input: input\n"
        "  output: output\n"
    )


def e3a(ncpu):
    t = (SHIP / "meerkat-defaults.yml").read_text()
    t = edit(t, "general:\n  prefix: mypipelinerun\n", general("e3a"), "dev1 general")
    t = edit(t, "  dataid: ['']\n", "  dataid: ['e2a']\n", "dev1 dataid")
    t = edit(t, "obsconf:\n  refant: '0'\n",
             "obsconf:\n  refant: '0'\n"  # dev 7: shipped value kept
             "  target: ['ESO137-001']\n  gcal: ['J1939-6342']\n"
             "  bpcal: ['J1939-6342']\n  fcal: ['J1939-6342']\n", "dev2 roles")
    t = edit(t, "inspect:\n  enable: true\n", "inspect:\n  enable: false\n", "dev4 inspect")
    t = edit(t, "transform__2:\n  enable: true\n  split_field:\n    enable: true\n",
             "transform__2:\n  enable: true\n  split_field:\n    enable: true\n    chan_avg: 8\n",
             "dev5 chan_avg")
    t = edit(t, "selfcal:\n  enable: true\n",
             f"selfcal:\n  enable: true\n  ncpu: {ncpu}\n", "E3 ncpu")
    t = edit(t, "  calibrate:\n    enable: true\n    gsols_timeslots: [120]\n",
             "  calibrate:\n    enable: true\n    gsols_timeslots: [120]\n    shared_mem: 20Gb\n",
             "dev6 shared_mem")
    t = edit(t, "line:\n  enable: true\n", "line:\n  enable: false\n", "dev8 line")
    return t


def e3b(ncpu):
    t = (SHIP / "meerkat-fullStokes-continuum-defaults.yml").read_text()
    t = edit(t, "general:\n  prefix: mypipelinerun\n", general("e3b"), "dev1 general")
    t = edit(t, "  dataid: ['MS']\n", "  dataid: ['e2b']\n", "dev1 dataid")
    t = edit(t, "obsconf:\n  xcal:\n    - 'J0521+1638'\n",
             "obsconf:\n  xcal:\n    - 'J1331+3030'\n"
             "  fcal: ['J1939-6342']\n  bpcal: ['J1939-6342']\n  gcal: ['J1833-2103']\n",
             "dev2 roles")  # refant unset: schema default 'auto' (dev 7)
    # dev 3a, used: the smoke pass stopped in obsconf (no TARGET-intent field)
    t = edit(t, "  gcal: ['J1833-2103']\n", "  gcal: ['J1833-2103']\n  target: ['J1833-2103']\n",
             "dev3a target")
    t = edit(t, "inspect:\n  enable: true\n", "inspect:\n  enable: false\n", "dev4 inspect")
    t = edit(t, "inspect__polcal: \n  enable: true\n", "inspect__polcal: \n  enable: false\n",
             "dev4 inspect__polcal")
    # dev 11, post hoc 2026-11-12 (note 10.10): MeqTrees tile size, a memory
    # parameter of CARACal's shipped sequence, lowered after set_model_cal hit
    # the WSL VM's 30 GiB at the shipped 128. Not a change of method.
    if TILE:
        sm = "  set_model:\n    enable: true\n    meerkat_skymodel: true\n"
        t = edit(t, sm, sm + f"    tile_size: {TILE}\n", "dev11 crosscal tile")
        pc = "polcal:\n  enable: true\n"
        t = edit(t, pc, pc + f"  set_model_leakage:\n    tile_size: {TILE}\n", "dev11 polcal tile")
    for st in ("transform__2", "prep__2", "flag__2", "selfcal", "polimg"):
        t = edit(t, f"{st}:\n  enable: true\n", f"{st}:\n  enable: false\n", f"dev3 {st}")
    return t


TILE = None


def main():
    global TILE
    pas, ncpu = sys.argv[1], int(sys.argv[2])
    TILE = int(sys.argv[3]) if len(sys.argv) > 3 else None  # dev 11 (E3-B only)
    OUT.mkdir(exist_ok=True)
    for name, fn in (("e3a", e3a), ("e3b", e3b)):
        p = OUT / f"{name}-{pas}.yml"
        p.write_text(fn(ncpu), newline="\n")
        print(p)


if __name__ == "__main__":
    main()
