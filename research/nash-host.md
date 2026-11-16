# nash, a shared Linux host

Status, 2026-11-16: **set up and checked; smoke timings measured.** ra-ng
builds and passes its quick check on nash.ru.ac.za, a multi-user Linux server
at Rhodes University. This note is the host's handbook: what is installed
where, the nice rule, the heavy-lock settings, how to run a job and how to
label its timings.

## Hardware

| | |
| --- | --- |
| CPU | 2 x Intel Xeon E5-2695 v4 (Broadwell), 2.1 GHz, 18 cores each, no SMT: 36 threads, 2 NUMA nodes (even CPUs node 0, odd node 1), 90 MiB L3 |
| Instruction set | AVX2, FMA, BMI2: the repository's `x86-64-v3` build target runs; no AVX-512 |
| Memory | 503 GB |
| Disks | `/` 458 GB (407 GB free); `/home` 53 TB (16 TB free), quota 10 TB per user |
| GPU | none |
| OS | Ubuntu 24.04, gcc 13.3, git 2.43 |
| System tools | WSClean 3.7 (`/usr/bin/wsclean`), CASA (casalite, `/usr/bin/casa`), docker, podman 4.9, apptainer 1.5; no Slurm |

Other people use the host. Our jobs must never get in their way.

## The nice rule (the owner's, not negotiable)

Every job ra-ng starts on nash runs at the lowest priority:

```sh
nice -n 19 ionice -c3 <command>
```

Builds, tests, checks, downloads, imaging, everything that runs longer than
a moment. No sudo, no system settings, nothing outside `~gijs`.

`heavy_lock.py run` can add the prefix itself (`RANG_HEAVY_NICE=19`, set in
`~/.rang-env.sh`; on the branch `nash-host`, live once merged): every
command it starts, nested ones included, runs under `nice -n 19 ionice -c3`.
That only covers commands started through the lock; prefix everything else
by hand, and prefix the lock call too, since the prefix is inherited.

Nice protects CPU time, not memory or the page cache. That is why the lock's
memory cap below matters more than its slot cap.

## What is where

The home directory follows the owner's Windows layout:

| Path | Contents |
| --- | --- |
| `~/Github/rang` | the main checkout of `https://github.com/gijzelaerr/rang-core.git`, on `main` |
| `~/Worktrees/rang/<branch>` | extra checkouts |
| `~/Build/cache/{uv,pip,npm}` | download caches (`UV_CACHE_DIR`, `PIP_CACHE_DIR`, `npm_config_cache`); safe to wipe |
| `~/Build/tmp/<yyyymmdd>-<what>` | scratch that outlives a session |
| `~/rang-data` | raw observations and outputs, the equivalent of `D:\rang`: `outputs/`, `fixtures/outer_scans.zip` (the public fixture, SHA256 checked), `locks/heavy` (the heavy lock) |
| `~/.local/bin/uv` | uv 0.13.8, official installer; Python 3.14.10 installed by uv |
| `~/.cargo`, `~/.rustup` | rustup; stable 1.100 and the check's 1.93 with clippy and rustfmt |
| `~/.rang-env.sh` | the environment below; sourced by `~/.profile` and at the top of `~/.bashrc`, so non-interactive `ssh nash '<command>'` gets it too |

`~/.rang-env.sh` sets `PATH` (uv, cargo), the caches, `UV_INDEX_URL` and
`PIP_INDEX_URL` (public PyPI only), `UV_PYTHON=3.14`, the lock settings below
and `RANG_FIXTURE`. Git: `user.name` Gijs Molenaar, `user.email`
gijsmolenaar@gmail.com. No push credentials: nash clones over https and does
not push.

### Set-up steps a fresh checkout needs

1. `uv venv --python 3.14 .venv`. The system Python is 3.12, and the `docs`
   extra's `sphinx>=9.2` needs 3.13 or later; `UV_PYTHON=3.14` makes
   `check_all.py`'s own `uv venv` pick 3.14.
2. `cargo +1.93 fetch` on `Cargo.toml`, `core/Cargo.toml` and
   `core/py/Cargo.toml`. The check builds with `--offline`, so an empty
   registry fails every Rust step (`no matching package named rayon`).
3. `python3 tools/check_all.py --quick` (under nice) installs the extension
   into the venv (`maturin develop --release`).

## The heavy lock on nash

`tools/heavy_lock.py` shares one host among this account's jobs; it does not
see other users' load. On nash, from `~/.rang-env.sh`:

| Setting | Value | Why |
| --- | --- | --- |
| `RANG_HEAVY_LOCK` | `~/rang-data/locks/heavy` | the default is `/mnt/d/...` on main; on the branch the default off Windows and WSL becomes `~/rang-data/locks/heavy`, so the variable is then redundant |
| `RANG_HEAVY_SLOTS` | 24 | two thirds of the 36 cores; 12 stay free for other users whatever we book |
| `RANG_HEAVY_MEM_GB` | 192 | under 40 % of 503 GB; nice does not protect memory, and an out-of-memory kill could hit another user's job |
| `RANG_HEAVY_NICE` | 19 | new on the branch: `nice -n 19 ionice -c3` for every command `run` starts |

Book honestly as everywhere (`--slots` = threads kept busy, `--mem` = peak
GB). A job wider than one socket (18 cores) crosses the NUMA boundary; for
timing work keep to 16 threads or pin to one node with
`numactl --cpunodebind=0 --membind=0` (`/usr/bin/numactl`).

Exclusive (`heavy_lock.py run -- ...`) means exclusive among our jobs only.
It does not make nash an idle host.

## How to run a job

```sh
ssh gijs@nash.ru.ac.za
cd ~/Github/rang
nice -n 19 ionice -c3 python3 tools/check_all.py --quick      # locks itself
nice -n 19 ionice -c3 python3 tools/heavy_lock.py run --slots 8 --mem 16 -- <command>
python3 tools/heavy_lock.py status
```

Long jobs: `nohup ... > ~/Build/tmp/<date>-<what>/log 2>&1 &`, or a `tmux`
session.

## Labelling timings

Rows in [tool-timings.md](tool-timings.md) from this host name it:
**host nash** (2 x E5-2695 v4, shared, nice 19). They are not idle-host or
exclusive-host timings: other users' jobs run at normal priority and take
cores from ours whenever they want them. Record the load average before and
after each run. Do not compare a nash wall time with one from the Windows/WSL
workstation as a speed result.

## Checks on nash

All at `5bade77` (main), under `nice -n 19 ionice -c3`, through the heavy
lock on nash (`RANG_HEAVY_LOCK=~/rang-data/locks/heavy`). Logs:
`~/Github/rang/outputs/check/` and `~/Build/tmp/20261116-nash-setup/` on nash.

| Run | Wall | Result |
| --- | ---: | --- |
| `check_all.py --quick --slots 16 --mem 32`, empty cargo registry | 22 s | FAIL: every core and extension step (`--offline`, nothing fetched) |
| the same after `cargo fetch`, cold targets | 997 s | FAIL on the gain-hash gate only (archive absent); fmt, ruff, clippy, 23 root and 290 core Rust tests, extension build pass. No pytest: main has no diff, so the quick check selects none |
| `check_all.py --slots 16 --mem 48` (full), warm targets | 683 s | FAIL on the gain-hash gate only; 290 core and 296 core `gpu`-feature Rust tests (no adapter, so CPU paths), pytest 1627 passed, 50 skipped |
| `pytest -q -n 16 -rs` (for the skip reasons) | 126 s | 1627 passed, 50 skipped |

**What the full check lacks on nash.** Not copied, by instruction:

- The gain-hash gate's archive (`RANG_ARCHIVE_OUTPUTS`, on the workstation
  `\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs`): the LUNO slice
  `luno-support-20261029-01/slice` (3.1 GB) and `luno-solve-20261029-02/inputs`
  (2.6 GB), both public S3 downloads (`fetch-luno-*.sh`), plus about 77 MB of
  run products (`tv-response-wsl-20261029-01/clean/{state,backups,trials}`,
  `core-phase2-inputs-20261029-01/arrays.npz`, `luno-solve-20261029-02/solve/gain_flags.npy`).
  About 5.8 GB in all. Without it the gate fails; `RANG_GAIN_HASHES=optional`
  turns that into a skip.
- The 50 pytest skips: archived campaign outputs and oracle runs that live only
  under the workstation's `outputs/` and `D:\rang\outputs` (MS-writer oracle
  MSs `tv-caracal-wsl-20261029-01/original.ms`, `luno-solve-20261029-02/work.ms`,
  the frozen E3 oracle run, E4-E6 oracle runs, the casacore oracle dumps, the
  DF5-O, L5-C, RV1, P5, P6, PC1, A-FLAG and K-fetch runs, CARACal's strategy
  YAMLs), the `meerkat` extra and python-casacore (not in the check's extras),
  `ducc0` and `comrak` (not installed), the O-CASA docker image, the GPU build,
  and three opt-in or Windows-only tests. `test_b1_baselines` still reports the
  fixture missing with `RANG_FIXTURE` set; it looks under `outputs/`.

**Smoke: WSClean and GeMClean on the public fixture.** Scan 9 of
`outer_scans.zip` (SHA256 checked), a fresh copy per run, the settings of
`notebooks/09-cpu-and-gpu.ipynb`: `-size 512 512 -scale 8asec -weight briggs
0.5 -niter 500 -data-column DATA -j 16 -no-update-model-required`. WSClean
3.7 is the system build (`/usr/bin/wsclean`), GeMClean the extension built by
the quick check (`.venv/bin/gemclean`, AVX2 tier). Three repeats, the order
alternating, inside our exclusive lock, `nice -n 19 ionice -c3`, load1
1.6-1.8 before and after. Script and outputs:
`~/Build/tmp/20261116-nash-setup/smoke/` (`run.sh`, `runs.tsv`).

| | wall, s (3 repeats) | peak RSS |
| --- | --- | ---: |
| WSClean 3.7 | 3.33, 2.88, 2.87 | 74 MB |
| GeMClean | 0.97, 0.98, 0.96 | 137 MB |

Both ran 500 components; WSClean spends 2.6 s of its 3.3 s in inversion.
This is a smoke test that both imagers run on nash, not a speed comparison:
the image is tiny, start-up dominates, and the host is shared.

## Open

- The lock change (`RANG_HEAVY_NICE`, the Linux default directory) is on the
  branch `nash-host`; until it is merged, nash's main checkout runs the old
  helper, so `RANG_HEAVY_NICE` does nothing yet and the manual prefix is the
  only protection.
- The full check's archive gate needs the campaign archives
  (`RANG_ARCHIVE_OUTPUTS`), which live on the workstation (`D:\rang`, WSL);
  they are not copied here.
