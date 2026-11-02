# U4: upstream findings filed, Tricolour #114 rebased (2026-11-02)

Task U4 of [big-plan.md](big-plan.md): file the upstream findings the owner approved on
2026-11-02, each reproduced first on the latest release, and rebase the owner's
ratt-ru/tricolour#114. Status: implemented, measured and filed. Everything under the owner's
account (gijzelaerr); commits as Gijs Molenaar <gijsmolenaar@gmail.com>, no trailers. Texts:
[upstream-issues/](upstream-issues/). Scripts: [u4-upstream-files/](u4-upstream-files/).
Host: WSL2 Ubuntu, Python 3.12.15 (Tricolour 3.13), fresh uv venvs from public PyPI on
`D:\rang\scratch\u4`, all deleted afterwards. Logs: `outputs/u4-20261102-01/logs/`.

## Results

| # | Finding | Reproduced on | Issue or PR | Notes |
| --- | --- | --- | --- | --- |
| 1a | Tigger: `ASCII.save` writes a multi-term spectral index as a list repr its loader skips; `BBS.save` writes radians and the list into `SpectralIndex:0` | astro-tigger-lsm 1.8.0; `master` 11131bec has the same lines | [tigger-lsm#55](https://github.com/ratt-ru/tigger-lsm/issues/55) | source A dropped by both loaders; `BBS.load` also reads radians back unconverted |
| 1b | Tigger: `ModelHTML.load` uses `eval` on `mdlval` | 1.8.0 and `master` | [tigger-lsm#56](https://github.com/ratt-ru/tigger-lsm/issues/56) | public: no security policy found (below); checked with `1+1+1` only; suggests `ast.literal_eval` |
| 2 | Crystalball: `import_from_wsclean` fails on SpectralIndex lists of different lengths | 0.4.3, NumPy 2.5.4; `master` 21213bcc same | [crystalball#83](https://github.com/caracal-pipeline/crystalball/issues/83) | equal lengths load |
| 3a | pfb-imaging: `[full]` pairs xarray ≥ 2026.4 with zarr < 3 | 0.0.11: xarray 2026.9.0, zarr 2.18.7; real `pfb init` fails; passes with `xarray<2026.4` | [pfb-imaging#390](https://github.com/ratt-ru/pfb-imaging/issues/390) | `main` 4cbbf625 resolves the same pair |
| 3b | pfb-imaging: `kclean` cannot load `libtbb.so.12` in a plain venv | 0.0.11, with a narrower cause (below) | **not filed** | `kclean` is removed on `main`; text and cause in [pfb-imaging-kclean-tbb.md](upstream-issues/pfb-imaging-kclean-tbb.md) |
| 4 | Tricolour: release note for the `uvrange` change in 0.5.0, with CARACal's `0~550` question | 0.2.1 and `367ff54` (head of `0.5.0-dev`): 700 m baseline 1700 against 0 channels | [tricolour#115](https://github.com/ratt-ru/tricolour/issues/115) | request, not a defect |
| 5 | QuartiCal #455: L5-C's result | no rerun; archived L5-C numbers | [comment](https://github.com/ratt-ru/QuartiCal/issues/455#issuecomment-6577475036) | L5-C's text verbatim; no earlier comments on the issue |
| 6 | killMS: `MergeSols.py` pickle in the working directory, `allow_pickle=True` | v3.3.0 = `master` 350f22c, DDFacet logger stubbed | [killMS#28](https://github.com/saopicc/killMS/issues/28) | public: no security policy found; harmless marker only; says that `driver()` overwrites the file just before reading |
| 7a | casacure: fixed-shape string array written by casacore cannot be read | 3.8.36, python-casacore 3.8.1 | [casacure#24](https://github.com/tmolteno/casacure/issues/24) | also FixedShape without Direct; issue, not PR: the fix couples read, write and existing tables |
| 7b | casacure: `getcol` on a ragged column returns the first row's shape | 3.8.36 | [casacure#25](https://github.com/tmolteno/casacure/issues/25), [PR #27](https://github.com/tmolteno/casacure/pull/27) | fix and regression test, gate below |
| 7c | casacure: smaller notes (`getvarcol` numbering, `iscelldefined`, MemoryStMan, MultiFile, cp310 macOS wheel) | 3.8.36 | [casacure#26](https://github.com/tmolteno/casacure/issues/26) | left out: see below |
| 8 | Tricolour PR #114 rebased onto `0.5.0-dev` | head c1000f1 on `367ff54` | [tricolour#114](https://github.com/ratt-ru/tricolour/pull/114) | mergeable, CI 4 of 4 pass, flags bit-identical on RV1's check |

Nothing on the list failed to reproduce. 3b reproduces, but not with DF5-O's cause.

## Duplicates and security policies

Every repository's issues were listed first (open and closed, plus searches on the key terms).
No finding was already reported. Near neighbours, all different: tigger-lsm #42 (BBS `file`
NameError, closed), crystalball #3, #31 and #42 (closed), pfb-imaging #334 (dask-ms 0.3.0
notice), casacure #8 (defaults by design), #18 (TiledDataStMan, open), #19 (`getcell` conformance),
#23 (`info`, open).

Security policies, checked before filing 1b and 6, 2026-11-02: tigger-lsm and killMS have no
`SECURITY.md`, GitHub's community profile lists none, `ratt-ru/.github` and `saopicc/.github` do
not exist, private vulnerability reporting is disabled on both, and the READMEs mention nothing.
So nothing asked for private reporting, and both went in as public issues as the owner
approved. Contributing rules: GitHub's community profile lists a file only for Tricolour
(`CONTRIBUTING.rst`, read; nothing in it conflicts); the others have none.

## Corrections to earlier notes

- **DF5-O's `kclean` cause.** A plain venv is not enough to fail: `set_envs` followed by a
  parallel region selects `tbb` with no `LD_LIBRARY_PATH`. `core/kclean.py` calls
  `numba.set_num_threads` at line 77, one line before `set_envs`, whose `ctypes` load is what
  numba needs. In that order the error appears; swapped, it does not
  (`pfb_repro_tbb_order.py`). The real `pfb kclean` fails at line 77 and passes with
  `LD_LIBRARY_PATH`. `main` removed `kclean`, so it was skipped as fixed.
- **casacure fixed-shape strings.** T1 said Direct; FixedShape without Direct fails too. The cause
  is a layout difference: casacore stores no `[ndim][dims][flag]` header for these cells.
- **casacure wheels.** macOS x86_64 is deliberately not built (README), so it is not reported.
  The cp310 macOS arm64 wheel is a real gap against the README.
- **#25 was edited after filing.** The first body wrote with `valuetype="float"` and had not been run
  in that form; casacure's `putcell` refuses it (new observation 3 below). The snippet now uses a
  double column, was run on both backends (`casacure_ragged_snippet.py`) and gives the stated output.

## casacure PR #27

`column_to_python` now refuses cells of different non-empty shapes with `RuntimeError`, as casacore
does; empty cells stay exempt (#8). New test fails on released 3.8.36, passes on the branch and on
python-casacore 3.8.1. Gate as CI: `cargo fmt --check`, `cargo clippy --workspace --all-targets --
-D warnings`, `cargo test --release --workspace`, `PYTHONPATH=tests/shim pytest tests/` 471 passed,
41 skipped, 3 xfailed (Rust stable 1.99.1, fixtures from `tests/make_fixtures.py`). Fork
gijzelaerr/casacure created for it; branch `getcol-ragged-raises`, 419e7f4.

## Tricolour PR #114

Rebased onto `0.5.0-dev` `367ff54`: 2f476ad became c1000f1, one commit, modes unchanged. The one
conflict was `tests/test_flagging.py`; both tests are kept. The kernel takes #112's casts by the
rebase, so the second signature goes.

- `pytest -m "not acceptance"` with the CI's test group and extras: 59 passed, 2 skipped. `ruff
  check` and `ruff format --check` clean.
- RV1's check (`examples/oracle_tricolour_050.py oracle`, four controls, cold Numba cache) into
  `outputs/u4-20261102-02`, compared with RV1's T1 (`rv1-20261030-12`) in `outputs/u4-20261102-03`:
  `t3_identical_to_t1: true` (every stage array, the intensity and the final flags),
  `t1_identical_to_021: true`, `t4_one_signature: true` (`_get_flags_impl` holds 1). The result's
  overall `identical` reads false only because T0 and T2 were not rerun here.
- Pushed to the PR's own head branch only, with
  `--force-with-lease=lanes-frequency-axis:2f476ad…` from Windows. PR state after the push:
  open, MERGEABLE, CLEAN; Code Quality and Tests 3.11, 3.12, 3.13 pass.

## Timings

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-11-02 | `uv venv` + install, per tool | public PyPI, on D: | tigger 17.2 s, crystalball 18.2 s, casacure 15.8 s, pfb `[full]` 79.7 s | 46, 56, 39, 164 MB | |
| 2026-11-02 | `pfb init`, `[full]` closure as resolved | DF5-O `field.ms` | 117.0 s | 484 MB | fails on `zarr_format` |
| 2026-11-02 | `pfb init`, `xarray<2026.4` | same | 96.5 s | 491 MB | exit 0 |
| 2026-11-02 | `pfb grid`, 256 px | same | 223.9 s | 620 MB | exit 0 |
| 2026-11-02 | `pfb kclean`, plain venv | same | 54.4 s | 463 MB | exit 1, threading layer |
| 2026-11-02 | `pfb kclean`, `LD_LIBRARY_PATH=<venv>/lib` | same | 179.0 s | 791 MB | exit 0 |
| 2026-11-02 | Tricolour PR venv install | `0.5.0-dev` + PR, Python 3.13 | 54.3 s | 105 MB | |
| 2026-11-02 | Tricolour `pytest -m "not acceptance"` | rebased head | 31.3 s (warm) | 400 MB | 59 passed, 2 skipped; a first run without `zarr` took 123.5 s and stopped on the import |
| 2026-11-02 | `oracle_tricolour_050.py oracle` | 4 controls, rebased head, cold | 39.9 s | 735 MB | oracle total 30.2 s |
| 2026-11-02 | casacure `cargo fmt` + `clippy` | fix branch | 29.5 s | 428 MB | |
| 2026-11-02 | casacure `maturin develop --release` | fix branch | 57.4 s | 576 MB | |
| 2026-11-02 | casacure `cargo test --release --workspace` | fix branch | 52.5 s | 980 MB | |
| 2026-11-02 | casacure `pytest tests/` (shim) | fix branch | 55.8 s | 246 MB | 471 passed |
| 2026-11-02 | `bash tools/check-all.sh` | this branch | 998.1 s (includes lock wait) | 2.11 GB | overall PASS; pytest 824 passed, 19 skipped. A first run (877.0 s) failed at collection: the briefed venv extras lack scipy; rerun with `.[pointing,beam,test,imaging,formats]` |

## Kept and deleted

Kept (ignored): `outputs/u4-20261102-01/logs` (220 KB: installs, freezes, repro logs, `timings.txt`),
`outputs/u4-20261102-02` (98 MB, T3 arrays on the rebased head), `outputs/u4-20261102-03` (12 KB,
comparison), `outputs/u4-20261102-check-all.log` (and `-check-all-1-no-scipy.log`). Deleted and checked absent:
`D:\rang\scratch\u4` (all clones, venvs and tables). Stays: fork gijzelaerr/casacure and its branch.

## For the coordinator

**New observations, not filed: not on the approved list.** Each needs the owner's say.

1. **Tigger does not import from a fresh install.** `uv pip install astro-tigger-lsm` (1.8.0)
   pulls meqtrees-cattery 1.8.0 → purr 1.5.3 → PyPI `kittens` 0.1.2, an unrelated package ("sending
   friendly images of kittens to a target") that installs a top-level `Kittens` over
   astro-kittens 1.4.6. Here it won: `import Tigger` failed, first on `requests`, then on
   `config.get("mogreet", ...)`. Its `__init__` reads `~/.kitten.conf` and `/etc/kitten.conf`, and it
   has send code for api.mogreet.com. It failed on import here, sending nothing. Purr most likely
   means astro-kittens. Reporting it to Purr looks worth it. The U4 venv removed `kittens` and
   reinstalled `astro-kittens`, which #55's environment line reflects. `tools/formats-oracle`
   locks both packages: **check `sky.lock` and `qc.lock`**, which pin `kittens==0.1.2`.
2. **casacure writes fixed-shape string tables casacore cannot read.** python-casacore 3.8.1 raises
   on both (`casacure-write2.log`). Related to #24, whose text says only that casacure's writer
   stores the header.
3. **casacure: `valuetype="float"` on a variable-shape column.**
   `makearrcoldesc("V", 0.0, ndim=1, valuetype="float")` gives a column where `putcell` raises
   `array cannot be stored in column V (valueType float)` for float32 and float64, and `getcol`
   returns scalars. A double column works. Fixed-shape float columns are covered by casacure's own tests.
4. **Tigger with NumPy 2 scalars.** `ASCII.save` writes `np.float64(20.0)` into the shape columns when
   the model holds NumPy scalars. Other DF-IO notes (`.lsm.html` hash-seed order, `SyntaxWarning`s)
   were not on the list and were not rechecked.

**Not filed.** 3b, as above: the owner may still want it against 0.0.x; the text is ready. Per the
brief: DF5-O items 3 and 4, Tricolour input-flag growth, DDFacet pins, the data-store notes.

**Lines for `research/upstream-prs.md`** (a new section "After U4"):

- Tricolour rows as lanes: tricolour#114 rebased onto `0.5.0-dev` by U4, head c1000f1: CI 4 of 4 pass, mergeable, flags bit-identical to `367ff54` on RV1's four controls, one `_get_flags_impl` signature.
- casacure `getcol` on ragged columns: [casacure#25](https://github.com/tmolteno/casacure/issues/25), [PR #27](https://github.com/tmolteno/casacure/pull/27). Tests: new test fails before, passes after; `pytest tests/` 471 passed; cargo fmt, clippy, test pass.

**Lines for `research/upstream-notes.md`** (a new section "Upstream status after U4 (2026-11-02; `u4-upstream.md`)"):

- Tigger 1.8.0: **filed** ratt-ru/tigger-lsm#55 (ASCII and BBS save) and #56 (`eval` in `ModelHTML.load`, public: no security policy).
- Crystalball 0.4.3: **filed** caracal-pipeline/crystalball#83.
- pfb-imaging 0.0.11: **filed** ratt-ru/pfb-imaging#390 (`[full]` closure, also on `main`). `kclean`/TBB **not filed**: the cause is `set_num_threads` before `set_envs` in `core/kclean.py`, and `kclean` is gone on `main`; `upstream-issues/pfb-imaging-kclean-tbb.md`.
- Tricolour: **filed** ratt-ru/tricolour#115 (`uvrange` release note); #114 rebased to c1000f1, mergeable, CI green.
- QuartiCal #455: L5-C comment **posted**.
- killMS 3.3.0: **filed** saopicc/killMS#28 (public: no security policy).
- casacure 3.8.36: **filed** tmolteno/casacure#24, #25, #26; **PR** #27 (ragged `getcol` raises).
- New, not filed: PyPI `kittens` shadows `astro-kittens` through purr, so a fresh Tigger does not import; casacore cannot read casacure's fixed-shape string tables; casacure refuses `putcell` on a variable-shape `valuetype="float"` column; Tigger `ASCII.save` writes `np.float64(...)`.

**STATE paragraph:**

> U4, upstream findings filed (big plan), 2026-11-02 (implemented; measured;
> [u4-upstream.md](u4-upstream.md)). Filed from the owner's list, each reproduced on the latest
> release: tigger-lsm#55, #56; crystalball#83; pfb-imaging#390; tricolour#115; killMS#28; casacure#24,
> #25, #26 with PR #27; the L5-C comment on QuartiCal#455. `eval` and pickle went in as public issues:
> neither repository has a security policy. Not filed: pfb `kclean`/TBB, which reproduces on 0.0.11 but
> is caused by the call order in `core/kclean.py` (DF5-O's plain-venv wording was too broad), and
> `kclean` is gone on `main`. Tricolour #114 is rebased to c1000f1: mergeable, CI 4 of 4, flags
> bit-identical to `367ff54` on RV1's four controls, one kernel signature. New and not filed, for the
> owner: PyPI `kittens` shadows `astro-kittens` through purr, so a fresh Tigger does not import, and
> casacore cannot read casacure's fixed-shape string tables.

**Research-index line** (already added to `research/README.md`, section "Upstream reporting", so the
index test passes):

> - [U4, findings filed](u4-upstream.md): ten filings on Tigger, Crystalball, pfb-imaging, Tricolour, QuartiCal, killMS and casacure, a casacure PR, and tricolour#114 rebased and green.

**Tool-timings rows:** the table above.

**To watch:** casacure#27, #24, #25, #26; tricolour#114 (now reviewable), #115; pfb-imaging#390; tigger-lsm#55, #56; crystalball#83; killMS#28. `research/big-plan.md`: "U4 done 2026-11-02 (`u4-upstream.md`)".
