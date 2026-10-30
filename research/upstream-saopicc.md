# Upstream issues and pull requests for DDFacet and killMS (big plan task U3, 2026-10-30)

Task U3 of [big-plan.md](big-plan.md): file the `saopicc` findings of the DDFacet/killMS
feasibility study ([ddfacet-feasibility.md](ddfacet-feasibility.md), section "Upstream
observations") after the user allowed `saopicc` reports on 2026-10-30, with pull requests where
the fix is small and certain. Model: task U2, [upstream-prs.md](upstream-prs.md). Per-finding
records: [upstream-issues/](upstream-issues/) (`killms-*`, `ddfacet-*`). Scripts:
[upstream-saopicc-files/](upstream-saopicc-files/) (they refer to the session's scratch paths;
the logic is what matters). All issues and PRs under gijzelaerr; commits as Gijs Molenaar
<gijsmolenaar@gmail.com>, no trailers.

**Versions checked.** Latest releases equal current `master` in both repositories: DDFacet
v1.0.0.0 = `master` 2fe05ab4 (also = cyriltasse/DDFacet `master`, where development PRs are
merged; compare API: 0 ahead, 0 behind); killMS v3.3.0 = `master` 350f22c. Every finding was
re-checked on these commits. Host: WSL2 Ubuntu 26.04, GCC 15.2.0, Python 3.12.15, load high.

## Summary

| # | Finding | Issue | PR | Tests | CI |
|---|---|---|---|---|---|
| 1 | killMS does not build with GCC 14+ (`Gridder.c:309-310`) | [killMS#25](https://github.com/saopicc/killMS/issues/25) | [killMS#26](https://github.com/saopicc/killMS/pull/26) | build fails before (13.4 s), builds after without CFLAGS; `_pyGridder` imports; disassembly of `Gridder.c` identical before/after | no GitHub CI (Jenkins, private); no checks |
| 2 | killMS 3.3.0 vs DDFacet 1.0.0.0 `AsyncProcessPool` API | [killMS#27](https://github.com/saopicc/killMS/issues/27) | none: port touches 10 modules; options in the issue | data-free reproduction: `AttributeError` / `ImportError` | – |
| 3a | DDFacet classifier GPLv2 vs "or later" headers | [DDFacet#73](https://github.com/saopicc/DDFacet/issues/73) | [DDFacet#74](https://github.com/saopicc/DDFacet/pull/74) | sdist `PKG-INFO` has `GPLv2+` | no checks |
| 3b | killMS classifier, same | [killMS#23](https://github.com/saopicc/killMS/issues/23) | [killMS#24](https://github.com/saopicc/killMS/pull/24) | sdist `PKG-INFO` has `GPLv2+` | no checks |
| 4 | DDFacet: MS with data in another field, error names no fields | [DDFacet#75](https://github.com/saopicc/DDFacet/issues/75) | [DDFacet#76](https://github.com/saopicc/DDFacet/pull/76) | new unit test fails before / passes after; `nosetests DDFacet.Tests.FastUnitTests` 35 OK before, 36 OK after; `DDF.py` before/after | no checks |
| 5 | DDFacet Hogbom diverges to `inf` with >1 facet | [DDFacet#77](https://github.com/saopicc/DDFacet/issues/77) | none: cause not found in the time box | reproduced on synthetic data (point source) in 2 min; 1 facet converges | – |

Fork branches: gijzelaerr/killMS `gcc15-incompatible-pointer-types` (26af26e),
`licence-classifier-gplv2plus` (fbfdbf6); gijzelaerr/DDFacet `licence-classifier-gplv2plus`
(fbd2521f), `selection-field-hint` (4c1794e3). All four PRs open and mergeable at filing; no
reviewers requested, no auto-merge. Duplicate searches (`gh issue list/pr list --search`, both
saopicc repos, and cyriltasse/DDFacet for Hogbom): none found.

## 1. killMS on GCC 14+ (filed, PR)

[killms-gcc14-pointer-types.md](upstream-issues/killms-gcc14-pointer-types.md). `pyGridderPoints`
declares the two `PyArg_ParseTuple` `O` outputs as `PyArrayObject *`; GCC 14 made
`-Wincompatible-pointer-types` an error (porting notes checked). With the workaround the verbose
build shows exactly two such diagnostics (lines 309, 310) and no other GCC 14 error category, so
the one-line declaration change is the whole fix. PyPI has only the 3.3.0 sdist, so
`pip install killMS` fails on Ubuntu 26.04 today.

## 2. killMS against DDFacet 1.0.0.0 (filed, no PR)

[killms-ddfacet-app-api.md](upstream-issues/killms-ddfacet-app-api.md). Broader than the study's
note: besides `_init_default()`, the global `APP` is gone (ten killMS modules import it, three of
them fail at import) and `init()` now returns a pool and takes `requested_worker_cpus`, not
`affinity`. Correction to the study: `51a1d352` only re-adds an already commented-out file;
the removal is 11a616f2 (2026-04-30), after de2fc174 (2022) stopped calling it at import, and
reached the release through cyriltasse/DDFacet#912. The issue offers a port sketch or a
`DDFacet < 1.0` pin. The rang conclusion stands: a killMS oracle needs DDFacet < 1.0, and
`DDFacet==0.9.1` itself does not install on GCC 15 (its dependency astlib 0.13.2 fails on C23
prototypes; `CFLAGS=-std=gnu17` did not help through uv), so DF0 needs an older compiler or a
container.

## 3. Licence classifiers (filed, two PRs)

[ddfacet-killms-licence-metadata.md](upstream-issues/ddfacet-killms-licence-metadata.md).
README and headers: "version 2 ... or (at your option) any later version"; classifier: GPL-2.0-only.
Recounted on master (git-tracked `.py/.c/.cc/.cpp/.h/.hpp`): DDFacet 168 of 350 files without a
header (21 empty `__init__.py`), killMS 17 of 90 (3 empty) — the study's 173/78 used another
file set. Headers were mentioned only as a note; none added. Worded so the maintainers can say
GPL-2.0-only is intended instead.

## 4. `--Selection-Field` (filed, PR)

[ddfacet-selection-field.md](upstream-issues/ddfacet-selection-field.md). Correction to the
study's wording: the skip is logged, not silent; the gap is that neither message names the
fields present. The PR adds the `FIELD_ID/DATA_DESC_ID` pairs and the selection options to the
`ClassMS.ReadMSInfo` skip message (one function), with a unit test; `ClassDaskMS` is unchanged
and the PR says so.

## 5. Hogbom (reproduced on synthetic data, filed)

[ddfacet-hogbom-facets-divergence.md](upstream-issues/ddfacet-hogbom-facets-divergence.md). On the
slice geometry with `DATA` = 1 Jy at the phase centre, the study's 3×3-facet Hogbom command
diverges to `inf` (overflow at `ClassModelMachineHogbom.py:184`) in the first minor cycle; with
UVW ×30 (2.2 km) it still diverges (8.3e15 Jy); with one facet it converges (0.047 then 0.0022 Jy).
So it is a facet-related Hogbom defect, not the compact PSF. Cause not identified (PSF facet
selection suspected and labelled unverified in the issue). Time box: started 14:30, reproduced
14:31, three runs done by 14:39.

## Tool timings (for `tool-timings.md`)

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | `git clone` DDFacet, killMS | GitHub | 10.8 s | – | |
| 2026-10-30 | `uv pip install ./DDFacet` (v1.0.0.0) | source | 80.2 s | 874 MB | Python 3.12.15 |
| 2026-10-30 | `uv pip install DDFacet==0.9.1` | PyPI | 4.3 s | 72 MB | **failed**: astlib 0.13.2 on GCC 15; retries with CFLAGS 0.9-1.0 s, failed |
| 2026-10-30 | `uv pip install --no-deps ./killMS` (3.3.0) | source | 13.4 s | 68 MB | **failed**: `Gridder.c:309` |
| 2026-10-30 | same with `CFLAGS=-Wno-error=incompatible-pointer-types` | source | 13.3 s | 76 MB | built |
| 2026-10-30 | `uv pip install ./DDFacet ./killMS` (fix branch, no CFLAGS) | source | 132.7 s | 874 MB | built |
| 2026-10-30 | `gcc -c Gridder.c` before/after + `objdump` | one file | seconds | – | disassembly identical |
| 2026-10-30 | `uv build --sdist` licence branches | DDFacet, killMS | 0.9 s, 1.8 s | – | `GPLv2+` in PKG-INFO |
| 2026-10-30 | new `TestClassMSSelection` (pytest) | 3-row MS | 0.5-0.8 s | 106 MB | fails before, passes after |
| 2026-10-30 | `nosetests DDFacet.Tests.FastUnitTests` | 35 / 36 tests | 19.4 s / 17.9 s | 351 MB | OK / OK |
| 2026-10-30 | `DDF.py` dirty, default field 0 | LUNO slice copy, 128 px | 5.4 s (before), 2.2 s (after) | 296 / 279 MB | exit 1 both; new message after |
| 2026-10-30 | `DDF.py` dirty, `//F1` and `--Selection-Field 1` | same | 6.7 s, 6.6 s | 445 MB | exit 0 |
| 2026-10-30 | `DDF.py` Hogbom 3×3 facets, synthetic point source | slice geometry, 2048 ch, 512 px | 101.7 s | 8.9 GB | diverges to inf; CPU 299 % |
| 2026-10-30 | same, UVW ×30 | same | 104.2 s | 9.0 GB | diverges (8.3e15 Jy) |
| 2026-10-30 | same, 1 facet | same | 273.1 s | 21.5 GB | converges; CPU 71 % |
| 2026-10-30 | rang worktree venv (`uv venv -p 3.14` + editable install) | worktree | see check-all section | – | |

## Scratch deleted

`~/Build/tmp/20261030-saopicc/` (DDFacet and killMS clones, venvs `venv-ddf100`, `venv-ddf091`,
`venv-kmsfix`, sdists, `objcmp/`, `field/`, `hogbom/` MS copies and images, logs). Everything
needed is in `upstream-saopicc-files/` and on the fork branches. Forks gijzelaerr/DDFacet and
gijzelaerr/killMS stay (they hold the PR branches).

## For the coordinator

- **Lines for `upstream-notes.md`** (new section "Upstream status after task U3"):
  - killMS GCC 14+: **filed** saopicc/killMS#25, **PR** #26 (one-line declaration fix,
    identical object code).
  - killMS vs DDFacet 1.0.0.0: **filed** saopicc/killMS#27 (global `APP`, `_init_default`,
    `init()` signature all changed via cyriltasse/DDFacet#912); no PR, port or `<1.0` pin left
    to the maintainers.
  - Licence classifiers: **filed** saopicc/DDFacet#73 and saopicc/killMS#23, **PRs** #74 and
    #24 (`GPLv2+`); missing headers (168 and 17 files) noted only.
  - DDFacet field selection: **filed** saopicc/DDFacet#75, **PR** #76 (skip message names the
    fields present; unit test).
  - DDFacet Hogbom: **filed** saopicc/DDFacet#77 (diverges to inf with more than one facet on a
    synthetic point source; one facet converges).
- **STATE paragraph.** "Big plan task U3, 2026-10-30 (implemented; measured): filed
  saopicc/killMS#23, #25, #27 and saopicc/DDFacet#73, #75, #77; opened killMS#24, #26 and
  DDFacet#74, #76 (no GitHub CI on either repository). Latest releases equal `master` in both.
  The DDFacet Hogbom failure seen on the LUNO slice reproduces on a synthetic point source in two
  minutes and depends on the facet count, not the compact array (one facet converges; 3×3 diverges
  to inf even with 2.2 km baselines): DF0/DF5 oracles should use one facet or reject `nan`
  models. killMS still needs DDFacet < 1.0, and DDFacet 0.9.1 does not install on GCC 15
  (astlib), so the killMS oracle needs an older toolchain. Report: `research/upstream-saopicc.md`."
- **Timing rows**: the table above.
- **Open items**: watch killMS#24, #26 and DDFacet#74, #76 (no CI, review only); answer
  questions on #27 (port vs pin) and #77 (cause unknown; a follow-up could bisect the PSF facet
  selection); `research/README.md` could link this report.
