# MIT relicensing audit of rang-core

2026-11-17. Read-only audit; no code changed. Base: main `41bc3efb`. The notice
additions of branch `v030-fix` (`07875d43`, unmerged when this was written: casacore measures, radler,
WSClean 3.7, aocommon, schaapcommon) were read and are taken into account. Not
legal advice: section 7 asks for a licensing expert before the final step.

**Question (owner, 2026-11-17).** What has to happen to relicense rang-core
from GPL-3.0-or-later to MIT?

**Answer in one paragraph.** The owner wrote all 1,555 commits
(`git shortlog -sne`: one identity; no co-author trailers in any message), so
everything he wrote himself can be relicensed by him. That is 100,723 of the
172,388 shipped source lines (58 %), plus 8,520 lines translated from
permissive upstreams (QuartiCal, Tricolour, codex-africanus, katdal, c-blosc),
which stay usable under MIT if their notices are kept. **31,734 lines in 25
files are translations of GPL or LGPL code** (about 14,400 lines actually
derived). Another 25,556 lines in 32 files reimplement rules or formats read in
GPL or LGPL source (not clean-room), and 2,130 lines of copied schema strings
are unclear. The blockers are, in order of size:
1. the casacore table writer (4 files, 6,760 derived lines, LGPL-2.x-or-later);
2. the ducc0 wgridder (3,550, GPL-2.0-or-later, no BSD option);
3. WSClean's w-stacking gridder and weights (1,650, GPL-3);
4. GeMClean's radler, aocommon and schaapcommon parts (1,270, LGPL-3.0-only and GPL-3);
5. five CASA calibration kernels, the CASA flag extension and one test (850, LGPL-2.x-or-later).

An MIT-only rang-core without them has no imager and no Measurement Set
writes. The cheapest sound route:
- first, ask ducc0's and ASTRON's authors for permission;
- meanwhile, rewrite the small CASA and CARACal pieces clean-room;
- keep the casacore table writer under LGPL-2.1-or-later as a marked module, because its byte identity cannot survive a clean room;
- move whatever is still GPL into an optional GPL package;
- have the last step checked by a licensing expert.

The end state of that route is "MIT AND LGPL-2.1-or-later" plus an optional GPL
package, not MIT only. MIT only also needs a clean-room table writer.

**Effort:**
- **With both permissions and the LGPL writer module:** about 3-4 weeks of agent work, plus the time the replies take.
- **Fully clean-room:** 12-17 weeks of agent work, or about 7-10 weeks elapsed with independent sessions in parallel; the wgridder sets the pace.

## 1. File-level classification

### Method

The scope is every source file that ships in the sdist or the wheels:
- `core/src`, `core/py/src` and `src`;
- `python/rang`;
- `tests` (shipped in the sdist);
- `tools/check.py` and `tools/wheel/`, the only tools the sdist keeps (`pyproject.toml` `exclude`).

That is 392 files and 172,388 lines (`.rs`, `.py`, `.sh`).

Five read-only reviews each read one area's code, the research notes that
record its port and `git log --follow`, and checked structural correspondence
against the upstream at the named commit where it mattered:
- imaging;
- GeMClean;
- calibration;
- flagging and table IO;
- the rest of the Python and the tests.

The two findings that contradict the repository's own wording were
cross-checked here against the upstream sources:
- **`ism.rs` `get_split` against casacore v3.8.1 `tables/DataMan/ISMBucket.cc` `ISMBucket::getSplit`.** The early return for `nr <= 2`, the loop condition `cumLeng[i-1] < rowLeng[i] + totLeng - cumLeng[i] && i<nr-1`, the `diff` update and the step back are the same. The file says "nothing is copied".
- **`bandpass.rs` `fill_gap_array` against casa6 `9269a52` `StandardVisCal.cc` `BJones::fillChanGapArray`.** The variables `ich`, `ch1`, `ch2`, `dch`, `a0`, `da`, `p0`, `dp` and `fch`, the control flow and the comments ("Advance to first unflagged channel") are the same. The file says CASA "is not copied".

Two statements in the files were read on rang's side only; the area reviews
checked them against the upstream:
- `wgridder.rs:3540`, the KernelDB rows "verbatim from `src/ducc0/math/gridding_kernel.cc`";
- `grid.rs:2-10`, "A Rust translation of … `gridding/wstackinggridder.cpp`".

Classes:

| Class | Meaning |
| --- | --- |
| a | Own original: no upstream code followed. A file that cites WSClean or CASA as an oracle is not derived. |
| b-permissive | Translated from an MIT or BSD upstream: fine under MIT if its notice is kept. |
| b-copyleft | Translated or derived from a GPL or LGPL upstream: structure, names, constants or loop order carried over. Blocks MIT. |
| c-src | Own code and decomposition, written to rules or a format read in GPL or LGPL **source** ("nothing is copied"). Not clean-room; lower risk than b; for the expert to judge. |
| c | Reimplemented from papers, documentation or black-box behaviour only. Fine under MIT. |
| d | Unclear. |

A mixed file counts whole under its most restrictive class; the "derived" column
estimates the lines that actually follow upstream code. The per-file table
(path, lines, class, upstream, licence, upstream files, derived lines) is
[results/mit-relicense-audit/files.csv](results/mit-relicense-audit/files.csv),
written by
[results/mit-relicense-audit/classify.py](results/mit-relicense-audit/classify.py),
which also prints the totals below.

### Totals per class

| Class | Files | Lines | Derived lines (est.) |
| --- | ---: | ---: | ---: |
| a | 317 | 100,723 | 0 |
| b-permissive | 8 | 8,520 | 5,935 |
| b-copyleft | 25 | 31,734 | 14,365 |
| c-src | 32 | 25,556 | 1,048 |
| c | 9 | 3,725 | 0 |
| d | 1 | 2,130 | 2,130 |
| **total** | **392** | **172,388** | 23,478 |

By area:
- **`tests`:** 32,470 lines. All own, except three files that transcribe CASA loops or rules as test references (123 derived lines).
- **`tools`:** the shipped 1,040 lines are all own.
- **`src`:** the root crate rang-sim, 2,870 lines, all own.

### Totals per upstream (b-copyleft, c-src and d only)

| Upstream | Licence | Class | Files | Lines | Derived (est.) |
| --- | --- | --- | ---: | ---: | ---: |
| casacore (table storage managers: `ms_write.rs`, `ism.rs`, `multifile.rs`, `tiled.rs`) | LGPL-2.0-or-later / 2.1-or-later | b-copyleft | 4 | 9,832 | 6,760 |
| casacore measures (`cal_pol.py`) | LGPL-2.0-or-later | b-copyleft | 1 | 1,503 | 70 |
| ducc0 0.42.0 wgridder | GPL-2.0-or-later | b-copyleft | 1 | 4,824 | 3,550 |
| CASA casa6 (calibration, flag extension) | LGPL-2.0/2.1-or-later | b-copyleft | 7 | 3,846 | 847 |
| WSClean 3.6/3.7 | GPL-3.0 ("version 3", see 3.2) | b-copyleft | 4 | 2,616 | 1,650 |
| radler 76fe4474 | **LGPL-3.0-only** | b-copyleft | 2 | 2,383 | 1,020 |
| schaapcommon (gemclean.rs, input.rs) | GPL-3.0-or-later | b-copyleft | 2 | 4,118 | 89 |
| Tigger (`formats/sky.py` writer) | GPL-2.0-or-later | b-copyleft | 1 | 1,155 | 170 |
| EIDOS 1.1.2 | GPL-3.0 | b-copyleft | 1 | 654 | 24 |
| aocommon | GPL-3.0 | b-copyleft | 1 | 539 | 165 |
| CARACal / msutils | GPL-2.0 | b-copyleft | 1 | 264 | 20 |
| casacore (MS reader, AipsIO, table.dat) | LGPL-2.0-or-later | c-src | 5 | 4,883 | (format) |
| casacore (MS v2 schema strings) | LGPL-2.0-or-later | d | 1 | 2,130 | 2,130 |
| CASA (calibration rules) | GPL-2.0+/LGPL-2.0+ | c-src | 13 | 6,992 | 193 |
| CARACal 8f7bb363 (recipe, defaults) | GPL-2.0 | c-src | 5 | 6,317 | 370 |
| WSClean (CLI behaviour, predict, rules) | GPL-3.0 | c-src | 5 | 5,535 | 385 |
| radler (joined.rs) | LGPL-3.0-only | c-src | 1 | 988 | 60 |
| schaapcommon (spectral.rs) | GPL-3.0-or-later | c-src | 1 | 362 | 40 |
| killMS 3.3.0 (format) | GPL-2.0 | c-src | 1 | 188 | 0 |
| losoto 2.7.1 (H5parm layout, `formats/h5parm.py`) | GPL-3.0-or-later | c-src | 1 | 291 | 0 |

Permissive (b-permissive):
- QuartiCal 0.2.7, MIT: 3 files, 4,799 lines;
- Tricolour 0.2.1 and katsdpsigproc, BSD-3-Clause: 2 files, 2,101 lines;
- katdal 0.23: 640 lines;
- c-blosc 1.21.6: 720 lines;
- codex-africanus 0.4.4: 260 lines.

### The b-copyleft files

Evidence is quoted from the file or note. Line ranges are those of the derived
functions.

| File | Lines | Upstream | Derived and evidence |
| --- | ---: | --- | --- |
| `core/src/ms_write.rs` | 6,607 | casacore 3.8.1 SSM, StManArrayFile, FilebufIO, BucketCache, TSMCube | ~3,830 (L927-4754). :2262 "step for step as `SSMStringHandler`"; e3-table-writer.md:274-279 calls the FilebufIO copy "a replica". The rest (lock, headers, TableWriter) is c-src |
| `core/src/ism.rs` | 2,170 | casacore 3.8.1 ISMBase, ISMBucket, ISMColumn, ISMIndex | ~2,100. :7 "The IncrementalStMan of casacore 3.8.1, step for step"; `get_split` and `split` keep casacore's loop and locals. The header's "nothing is copied" (:19) is wrong |
| `core/src/multifile.rs` | 793 | casacore MultiFile, MultiFileBase | ~600. Methods 1:1 (`packIndex`, `unpackIndex`, `addFile`, `flush`) |
| `core/src/tiled.rs` | 262 | casacore TiledStMan::makeTileShape, TSMCube::adjustTileShape | ~230. Same locals in order, same literals, same six-phase loop |
| `core/src/flag_extend.rs` | 345 | CASA FlagAgentExtension.cc (LGPL-2.1+) | ~125. :8 "as `FlagAgentExtension::computeAntennaPairFlags`" |
| `core/src/wgridder.rs` | 4,824 | ducc0 0.42.0 `wgridder_impl.h`, `gridding_kernel.{h,cc}`, `gl_integrator.*` | ~3,550, of which the 939 KernelDB rows (L3540-4491) are verbatim; own additions (tiles, pools, SIMD dispatch) ~900 |
| `core/src/grid.rs` | 1,093 | WSClean 3.6-1 `wstackinggridder.cpp` and others | ~850. Functions map 1:1 (`makeKaiserBesselKernel`, `WToLayer`, `AddDataSample`, `projectOnImageAndCorrect`) |
| `core/src/weights.rs` | 764 | WSClean 3.6 `imageweights.*`, 3.7 tapers; schaapcommon `reordering.cc` | ~560. :18 "A Rust translation of the weighting path of WSClean 3.6" |
| `core/src/gpu/shader.rs` | 301 | WSClean, through grid.rs | ~180. WGSL forms of `AddDataSample` and `projectOnImageAndCorrect`; also fdlibm constants (Sun, permissive) |
| `core/src/gemclean/multiscale.rs` | 1,829 | radler `multiscale_algorithm.cc`, `subminor_loop.cc`, `multiscale_transforms.h` | ~800. `shape_function` is `MakeShapeFunction` line for line, f32 kept to match bits; `run_multiscale_masked` follows `ExecuteMajorIteration` |
| `core/src/gemclean/mask.rs` | 554 | radler `Radler::Perform`, `gain_calculations.h`; aocommon `image.h` | ~220. Radler's variable names and break-out order; the MAD constant copied |
| `core/src/gemclean/stokes.rs` | 539 | aocommon `polarization.h` `ParseList`; radler `image_set.h`; schaapcommon | ~165. aocommon's parser state machine and error wording |
| `core/src/gemclean.rs` | 3,069 | schaapcommon `gaussianfitter.cc`; WSClean `FitBeamSize` | ~65 (L1964-2015), plus ~150 c-src. The rest (lazy exact Högbom, tiles, stop rule) is own |
| `core/src/gemclean/input.rs` | 1,049 | schaapcommon `reordering.cc` | ~24 (`stokes_cell`). Not named in the v030-fix notice |
| `core/src/cal/fluxscale.rs` | 622 | CASA SolvableVisCal.cc `fluxscale`; casacore LSQFit | ~350. CASA's names (`mgref`, `MGOK`, `lowbound`) and branches |
| `core/src/cal/reference.rs` | 368 | CASA `applyRefAnt`, `verifyConstraints` | ~185. Step for step, including the recursive restart |
| `core/src/cal/bandpass.rs` | 163 | CASA StandardVisCal.cc `fillChanGapArray` | ~90. Same variables and comments. The header's "CASA is not copied" is wrong |
| `core/src/cal/apply.rs` | 1,604 | CASA RIorAParray `trackPhase` | ~30 fragment; the rest c-src |
| `core/src/cal/crosshand.rs` | 454 | CASA KJones `DelayFFT::searchPeak` | ~27 fragment; the rest c-src |
| `python/rang/cal_pol.py` | 1,503 | casacore measures (`MCDirection.cc`, `MeasMath.cc`, `MeasTable.cc`, `MSDerivedValues.cc`) | ~70 (`parallactic_angle_casa`). v030-fix notice: "a translation of the steps and constants" |
| `python/rang/core_grid.py` | 458 | WSClean `makeKaiserBesselKernel` | ~60, a test reference ("Direct NumPy transcription") |
| `python/rang/formats/sky.py` | 1,155 | Tigger `renderAttrMarkup` and `ModelHTML.save` | ~170 (L466-637), plus ~400 c-src readers (Tigger, Crystalball, DDFacet, killMS) and two codex-africanus regexes |
| `python/rang/beam_holography.py` | 654 | EIDOS `recon_par` | ~24, a comparison control only |
| `python/rang/cal_refant.py` | 264 | msutils `wgs84_to_ecef` ("operation by operation"); CARACal `get_refant` (c-src) | ~20 |
| `tests/test_e0_refant_extend.py` | 290 | CASA FlagAgentExtension.cc | ~40 (`casa_cube`, "CASA's loops … loop by loop") |

### The c-src files: what to judge

These files keep their own decomposition and follow a format or rules read in
the source:
- **Calibration (CASA):** `applycal.py`, `cal_*.py`, `calmodels.py`, `formats/caltable.py`, `cal/diag.rs`, `cal/leakage.rs`, `caltable.rs`.
- **Recipe and defaults (CARACal):** `core_pipeline.py`, `core_config.py`, `cal_chain.py`, `cal_apply.py`, `cal_selfcal.py`.
- **Table format (casacore):** the reader `ms.rs`, `aipsio.rs`, `ms_desc.rs`, `ms_create.rs` and `formats/_aipsio.py`.
- **Other formats:** `formats/killms.py` (killMS) and `formats/h5parm.py` (losoto's sdist read, `dfio-formats.md:37`).
- **GeMClean behaviour (WSClean):** `gemclean/cli.rs`, `gemclean/predict.rs`, `gemclean/spectral.rs`, `gemclean/joined.rs`.
- **Tests (CASA rules in NumPy):** two files.

Copyright protects expression, not formats, algorithms or parameter values. On
that basis most c-src code is defensible. Non-literal copying of structure is
the open risk. Two files are the weakest:
- **`joined.rs`:** its v030-fix header already says `AND LGPL-3.0-only`.
- **The ~400 c-src reader lines of `sky.py`.**

`gemclean/cli.rs` reproduces WSClean's option names and defaults. That is an
interface. Its help text is the owner's own wording: a 5-gram comparison with
`commandline.cpp` found one shared error phrase (cli.rs:383).

### Class d: `core/src/ms_schema.rs`

The file holds 2,130 lines (789 string literals) of MS v2 and CASA NewCalTable
column names, comments and keywords. They are copied from `table.dat` files
written by casacore 3.8.1 and CASA 6.7.6, so that rang's tables are byte
identical. This is interface data needed for interoperability. Its copyright
weight is low but not zero (the comments are casacore's prose). This is for
the expert.

## 2. Data and other assets

| Asset | Ships in | Origin and licence | Under MIT |
| --- | --- | --- | --- |
| `python/rang/data/4k_lband_meerkat.staticmask`, `4k_uhfband_meerkat.staticmask` | wheel, sdist | Byte copies from Tricolour 0.2.1, BSD-3-Clause (NRF/SARAO), with `TRICOLOUR-LICENSE` | Fine; keep the licence file |
| `python/rang/data/casacore_observatories.json` | wheel, sdist | 57 observatory positions from casacore-data 20250826, via `me.observatory()`; its README says casacore-data's own licence was not checked | Positions are facts. Check casacore-data's licence, or regenerate from primary sources |
| `python/rang/data/meerkat.itrf.txt`, `data/meerkat.itrf.txt` (`include_str!` in `gemclean/sim.rs:42`) | wheel, sdist | Verbatim copy from simms (GPL-2.0-only), commit `ad6d0a4a`; treated as facts (owner decision E5-11) | The facts argument is unchanged, but the file is a verbatim copy of a GPL-2.0-only file. Regenerating it from SARAO's published antenna positions removes the question |
| `python/rang/data/README.md`, `data/README.md` | wheel, sdist | Own text | Fine |
| `data/kat7`, `vla-c`, `wsrt.itrf.txt` | repository only | simms (GPL-2.0-only) | Not shipped; mark in the repository |
| Logo (`docs/logo/`) | documentation site | The project's own (`docs/licence.md`) | Fine |
| `docs/`, `notebooks/`, `formal/` | not in the sdist | Own; `docs/cli.md` is generated from cli.rs's own help | Fine |
| Network weights (F2, F3) | not shipped | Not in git or the package; F3 used LUNO data (SARAO; observer's permission) and ESO137 (CC BY 4.0) | Nothing to do now |
| `tests/data/` (31 files) | sdist | Outputs produced by the owner running rang or the oracles (CASA, python-casacore, xradio) on own or public inputs; none copied from an upstream test suite | Fine |
| CARACal strategy YAMLs (GPL-2.0) under `research/results/` | repository only | Verbatim copies, several | If the repository's `LICENSE` becomes MIT, mark these as GPL-2.0 or remove them |
| MeerKAT holography beams (CC BY-NC 4.0), LUNO, ESO137 | never redistributed | `docs/licence.md` | Unchanged |

## 3. Dependencies

### 3.1 Licences

The crate licences were read from `cargo metadata` of `core/py` (resolved,
non-dev, x86_64-pc-windows-msvc). The PyPI licences were read from installed
package metadata or from the PyPI JSON API for the pinned versions.

| Dependency | Where | Licence | An MIT rang-core may depend on it? |
| --- | --- | --- | --- |
| 34 crates of the default build (all platforms): pyo3 0.30.1, numpy 0.30.0, rayon, rustfft 6.4.1, ndarray, num-complex and others | statically linked into `rang._core` | MIT OR Apache-2.0 (25), Apache-2.0 OR MIT, MIT/Apache-2.0, BSD-2-Clause (numpy crate), Apache-2.0 WITH LLVM-exception (target-lexicon, build only), Unicode-3.0 (unicode-ident) | Yes |
| feature `gpu`: wgpu 30.0.1 and the rest (127 crates in all, all platforms) | statically linked | MIT/Apache-2.0 variants, Apache-2.0, MIT, Zlib, ISC, BSD-2-Clause | Yes |
| numpy | required | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Yes |
| PyYAML 6 | required | MIT | Yes |
| astropy (pyerfa, astropy-iers-data) | required | BSD-3-Clause | Yes |
| `plot`, `notebook`: matplotlib, pandas, ipywidgets, ipykernel, jupyterlab, nbformat, nbconvert | extras | PSF-based (matplotlib), BSD-3-Clause | Yes |
| `test`: pytest, pytest-xdist, pytest-timeout | extra | MIT | Yes |
| `pointing`: jax, scipy | extra | Apache-2.0, BSD-3-Clause | Yes |
| `beam`: katbeam 0.1 | extra | Modified BSD | Yes |
| `beam`: eidos 1.1.2 | extra, lazy import | GPL-3.0 | Yes as an optional dependency (rang does not ship it), but the user's combined program is GPL. Simpler to drop it from the extra: EIDOS is a comparison control only |
| `recipes`: stimela 2.1.4 | extra | **GPL-2.0-only** | Yes (separate tool; rang imports nothing from it). Keep it optional |
| `meerkat`: katdal 0.23, katsdptelstate 1.0.0 (python-lzf, rdbtools) | extra | BSD (Modified), BSD-3-Clause, BSD, MIT | Yes |
| `msv4`: xarray, zarr, numcodecs | extra | Apache-2.0, MIT, MIT | Yes |
| `formats`: h5py | extra | BSD-3-Clause | Yes |
| `casacure`: casacure 3.8.35 | extra (read-only oracle) | LGPL-3.0-or-later | Yes: a dynamically imported Python module. The LGPL is about modifying casacure, not about using it |
| `carta`: requests, simplejson, selenium; carta-python installed by commit | extra | Apache-2.0, MIT OR AFL-2.1, Apache-2.0; carta-python GPL-3.0 | Yes, as for eidos: optional, lazily imported, not shipped |
| `mcp`: mcp 2.3 | extra | MIT | Yes |
| `docs`: sphinx 9.2, furo, myst-nb, papermill | extra | BSD-2-Clause, MIT, BSD-3-Clause (myst-nb: blank on PyPI, from its repository, not re-read here), BSD | Yes |
| Oracles in tests only: ducc0 0.42.0, python-casacore 3.8.1, WSClean, CASA, QuartiCal, AOFlagger | not dependencies | GPL-2.0-or-later, LGPL-3.0, GPL-3, GPL/LGPL, MIT, GPL-3 | Running them as oracles is unaffected |

**The dependency side does not block MIT.** Every linked crate is permissive
(`cargo metadata` without a platform filter, with and without `gpu`).
The copyleft packages are optional extras that rang does not redistribute.

### 3.2 Notice gaps found on the way

These are worth fixing now, under the GPL, whatever the decision. BSD and MIT
notices must be kept under MIT too.

- **`core/src/blosc.rs`:** follows c-blosc 1.21.6 `blosc_d` and `shuffle-sse2.c` (BSD-3-Clause). There is no notice, and its SPDX line says GPL only.
- **`python/rang/meerkat.py`:** says "adapted from katdal 0.23's test helpers" and its SPDX line says BSD-3-Clause. The BSD text is in neither the file nor `THIRD-PARTY-NOTICES.txt`.
- **`python/rang/core_flag.py`:** follows Tricolour (`load_mask`, defaults), but its SPDX line says GPL only.
- **`core/src/gpu/shader.rs`:** carries fdlibm constants (Sun's permissive notice) with no notice.
- **`python/rang/formats/sky.py`:** Tigger (GPL-2.0-or-later) and two codex-africanus regexes, with no notice for either.
- **`gemclean/input.rs`:** absent from the v030-fix schaapcommon notice. Also not in the notices:
  - `calmodels.py` (CASA `Imager.cc`, casacore components);
  - `apply.rs` (casacore `Interpolate1D`, CASA `CTTimeInterp1.cc`);
  - `flag_extend.py` (casacore `MSIter`, CASA `FlagDataHandler`);
  - `killms.py` (killMS, GPL-2.0);
  - `h5parm.py` (losoto layout).
- **msutils:** PyPI says "GNU GPL v2"; `docs/licence.md` says "licence not checked".
- **WSClean 3.6's `gridding/wstackinggridder.h`** says "published under the GPL 3 license" (no "or later"). `grid.rs:13` and the notices say WSClean's files carry no notice.
- **Contradictory headers:** `ism.rs`, `bandpass.rs`, `reference.rs` and `fluxscale.rs` say "nothing is copied" or "CASA is not copied", but their code is a structural translation. The notices are right for the CASA files and missing for the casacore storage managers, whose headers should say "translated".

## 4. Per derived component: options, cost, and what MIT-only loses

Four routes exist for each component:
- **(P) Permission:** a permissive licence or a written grant from every copyright holder.
- **(R) Clean-room rewrite.**
- **(G) Optional GPL package:** move the component into a separately installed package, say `rang-core-gpl`, a second crate and wheel that registers itself with rang-core.
- **(L) Keep under the LGPL:** possible only for LGPL upstreams.

**Clean-room caveat for every R.** The owner, and every session that read the
upstream (all the porting sessions, this audit), cannot be the author. The
research notes that list "the rules as read in the source" (c2a §1, c2d §0.1,
core-e-ms-reader, g4/g5 §1, e5-table-writer-rest) cannot be the specification
as they stand. A defensible clean room has two parties:
- **A specification writer.** They may read the source, but they write down only behaviour, formats and published equations. A second person checks that text for expression.
- **An implementer.** They never saw the upstream or rang's port.

The oracle gates stay valid: testing against an upstream binary as a black box
is allowed. An agent session can implement only if it has no access to the
upstream source or to rang's port. Whether a model that may have seen
WSClean, casacore or ducc0 in training counts as clean is a question for the
expert (section 7).

### 4.1 casacore table writer: `ms_write.rs` (part), `ism.rs`, `multifile.rs`, `tiled.rs`

- **Upstream:** casacore 3.8.1, LGPL-2.0/2.1-or-later. The copyright holder named in the files is Associated Universities, Inc.; casacore is maintained by its community on GitHub (`casacore/casacore`).
- **What it does:**
  - every MS write: FLAG, CORRECTED_DATA and MODEL_DATA write-back, flag versions, CASA caltables;
  - `default_ms` and `create_table`;
  - the ISM, big-endian and MultiFile tables.
- **Today's gates:**
  - 20 of 21 frozen cases byte-identical to casacore 3.8.1 (`research/e6-table-writer-final.md`);
  - python-casacore and casacure read every table;
  - `tests/test_core_ms_write.py`, `test_e4_table_create.py`, `test_e5_table_writer_rest.py`, `test_e6_table_writer_final.py`, `test_t1_casacure_oracle.py`.
- **P:** permission from AUI. This touches the standing decision not to approach CASA or NRAO (owner decision, 2026-11-12); AUI is NRAO's operator. Owner decision.
- **L:** keep these files under LGPL-2.1-or-later inside an otherwise MIT package. The package is then licensed "MIT AND LGPL-2.1-or-later".
  - The extension links the files statically. The LGPL's relinking condition is met because the full source is published, but that needs checking.
  - Users who embed rang-core in closed code must then honour the LGPL for those files.
  - This is the cheapest legal route. It is not "MIT only".
- **R:**
  - Spec sources: AIPS++ Note 229 (MS v2), casacore's Tables documentation (doxygen: storage managers, `table.dat`), and the files casacore writes, read as data.
  - **No public document specifies the ISM bucket split, the BucketCache slot history or FilebufIO buffering.** A clean-room writer cannot pass the byte-identity gate. It can pass "casacore, python-casacore and CASA read it back exactly".
  - Size: 3,000-5,000 lines, for SSM and Tiled writers only (ISM and MultiFile read-only, or written in a simpler layout).
- **G:** the writer moves to the GPL package. An MIT-only install could not write any MS unless python-casacore (LGPL-3) is used as an optional backend.
- **MIT-only loses:** every MS and caltable write, and so `rang-core calibrate`, `apply`, `flag` write-back and `run`.

### 4.2 ducc0 wgridder: `wgridder.rs`

- **Upstream:** ducc0 0.42.0, `42ce8ab5`. Licence lines read verbatim at that tag:
  - `wgridder_impl.h`, `gridding_kernel.{h,cc}` and `gl_integrator.{h,cc}`: "GNU General Public License … either version 2 of the License, or (at your option) any later version", with no BSD alternative.
  - `fft.h` alone is `BSD-3-Clause OR GPL-2.0-or-later`. In rang that covers only `good_size_complex`, about 40 lines.
  - ducc's README says only the FFT component is also BSD.
  - **So ducc0's BSD option does not cover the wgridder.**
- **Copyright holders:** Max-Planck-Society, Martin Reinecke and Albert M. W. Yau (2026 lines). Contact route: the ducc issue tracker (github.com/mreineck/ducc, gitlab.mpcdf.mpg.de/mtr/ducc) or the author address in the sources. Reinecke already dual-licenses the FFT, so a request has a precedent. MPG as an employer may have to agree. No message drafted.
- **What it does:**
  - the exact gridder and degridder under all of GeMClean: invert, predict, the simulator and the stop-rule bound;
  - `clean_certified`, `clean_major`, `prox_solver` and `gridder_gram`;
  - light-curve snapshots, and the campaign's `wgrid`.
- **Gates:**
  - `research/df1-wgridder.md` criteria 1-5: agreement with ducc0 to 1e-12-1e-14 of the peak, adjointness ≤ 1e-12, thread-independent SHA256;
  - `test_kernel_table_is_ducc0s`, which pins the copied KernelDB, so a rewrite breaks it by design;
  - df2a speed gates; `test_core_wgridder.py`, `test_df2b_wgrid.py`, `test_df2c_campaign_gridder.py`.
- **R:**
  - Spec sources: Arras et al. 2021 (A&A 646, A58); Barnett, Magland & af Klinteberg 2019 (the ES kernel; FINUFFT, Apache-2.0, as a permissive reference); Ye et al. 2022.
  - Re-optimise the kernel parameters (β, e0 per support and oversampling) from the published error criterion instead of copying KernelDB. Keep ducc0 as the black-box oracle (`pip install ducc0`).
  - Size: 2,500-3,500 lines, most of it performance work to regain the df2 speed.
  - Gate: df1 criteria 1-3 at the same tolerances, df2a speed within a frozen margin.
- **G:** possible, but then the MIT package has no imager.
- **MIT-only loses:** the whole imager: GeMClean, every CLEAN and prox solver, and light curves. **This is the decisive component.**

### 4.3 WSClean w-stacking gridder and imaging weights: `grid.rs`, `gpu/shader.rs`, `weights.rs`, `core_grid.py`

- **Upstream:** WSClean 3.6/3.7. README "GPL license version 3"; `wstackinggridder.h` "GPL 3"; Debian records GPL-3.0+.
- **Copyright holders:** A. R. Offringa and ASTRON. The Debian copyright file also lists "2014-2016 Gijs Molenaar". The GeMClean review took this to be probably for the packaging, which the owner can confirm. If he wrote any of the translated WSClean code himself, that part needs no permission.
  - schaapcommon: ASTRON, GPL-3.0-or-later.
  - aocommon: GPL-3, no file notice.
- **Contact:** André Offringa and ASTRON's R&D group (gitlab.com/aroffringa/wsclean, git.astron.nl/RD). No message drafted.
- **What it does:**
  - `grid.rs`: the `wstack` dirty image and PSF that match WSClean, the GPU gridder (X2), and the frozen C/I/K replays.
  - `weights.rs`: natural, uniform and Briggs weights, the rank filter, tapers and Stokes I formation for GeMClean, `core_weights`, light curves and the campaign.
- **Gates:**
  - `research/core-c-gridder.md` run -05: within 6.1e-7 of the peak on 15 jobs;
  - `research/core-b-weighting.md`: bit-identical `IMAGING_WEIGHT_SPECTRUM` on 19 runs;
  - the g4 taper gates; `test_core_grid.py`, `test_core_weights.py`, `test_x2_gpu.py`.
- **P:** ask ASTRON and Offringa. This covers WSClean, radler, aocommon and schaapcommon at once (section 4.4).
- **R:**
  - **Gridder:** Offringa et al. 2014 (MNRAS 444, 606), Kaiser-Bessel gridding (Jackson et al. 1991; Beatty et al. 2005) and the WSClean docs. 700-900 lines plus the shaders.
  - **Weights:** Briggs 1995 and the WSClean weighting docs; the tapers are textbook. 300-400 lines.
  - Bit identity has to be re-earned as a black box.
- **G:** the w-stacking gridder alone could move to the GPL package at little cost: it is a replay and oracle path, and the wgridder is the production one.
- **MIT-only loses:** without `grid.rs`, the WSClean-matching w-stacking path and the GPU gridder. Without `weights.rs`, all weighting, and so GeMClean.

### 4.4 GeMClean parts from radler, aocommon and schaapcommon: `multiscale.rs`, `mask.rs`, `stokes.rs`, `gemclean.rs` (beam fit), `input.rs` (`stokes_cell`)

Radler is **LGPL-3.0-only**. That already makes the extension GPL-3.0-only
today (v030-review B-02).

The LGPL route (L) is open for the radler parts. LGPL-3.0 lets a modified copy
stay under LGPL-3.0, so `multiscale.rs`, `mask.rs` and `joined.rs` could be an
LGPL-3.0-only module with no permission needed. Their GPL fragments still need
permission or a rewrite first:
- aocommon's MAD constant and `ParseList` in `mask.rs` and `stokes.rs`;
- WSClean's `CalculateMsLimits` and theoretic beam in `multiscale.rs`;
- schaapcommon in `gemclean.rs` and `input.rs`.

L for GeMClean therefore costs the ~350 GPL lines rather than the ~1,300.

| Part | What it does | Gate | R: spec and size | MIT-only loses |
| --- | --- | --- | --- | --- |
| Multiscale (radler) | `-multiscale` and its options: extended emission | g5-multiscale gates B, C1 against WSClean 3.7; unit tests `shapes_have_radlers_sides_and_unit_sum` and others | Cornwell 2008; Offringa & Smirnov 2017 (MNRAS 471, 301); the WSClean docs; 800-1,000 lines | Extended-source imaging |
| Auto-mask state machine (radler, aocommon) | `-auto-mask`, `-abs-auto-mask`, `-auto-mask-nmiter` | g4-masks gates S and M | Offringa & Smirnov 2017 §3; the continued-loop gain has to be re-derived as a black box; 250 lines | Auto-masking (`-fits-mask` stays) |
| `-pol` parser and Stokes formation (aocommon, schaapcommon, radler) | `-pol`, `-join-polarizations`, Stokes I weights `min(4w_XX, 4w_YY)` | g9-stokes C, D, E; G2/G3 identity hashes | The Stokes relations (Hamaker, Bregman & Sault 1996); the WSClean `-pol` docs; 200 lines | In practice all imaging from linear feeds |
| Restoring-beam fit (schaapcommon, WSClean) | BMAJ, BMIN, BPA | g7-defaults gate B: 1e-3 relative, 0.1° | Levenberg-Marquardt (Moré 1978); box rule and quadrant behaviour as a black box; 120 lines | The beam that matches WSClean |
| c-src: cli.rs, predict.rs, spectral.rs, joined.rs | WSClean conventions | g3, g6, the CLI tests | Restate as documented behaviour; joined.rs's ~60 radler-flow lines rewritten (100 lines) | Nothing if restated |

Permission for these parts comes from ASTRON and Offringa, as in 4.3. The rewrite totals 1,500-1,800 lines.

### 4.5 CASA calibration and flag-extension kernels

Upstream: casa6 (mirror `9269a52`, 6.7.6.14), LGPL-2.0/2.1-or-later, copyright
Associated Universities, Inc. (and ESO for FlagAgentExtension). Permission (P)
conflicts with the owner's standing no-NRAO decision. The LGPL route (L) is as
in 4.1 and needs no permission.

This audit still recommends R for these parts, for three reasons:
- they are small (about 1,100-1,300 lines);
- CASA fidelity can be re-earned by probes, as V8b did;
- every file left under L keeps the package from being MIT only.

L is the no-cost fallback for any part whose rewrite misses its gate.

| Part | What it does | Gate | R: spec and size | MIT-only loses |
| --- | --- | --- | --- | --- |
| `fluxscale.rs` (350) | the F step: secondary flux bootstrap and spectral fit | c2d: bit-identical on 10 of 12, fluxd to 3.9e-4; `test_cal_fluxscale.py` | CASA fluxscale task docs and weighted least squares in log-log; CASA quirks (the median rule above 100 values) as a black box; 300 lines | F in `rang-core calibrate` |
| `reference.rs` (185) | CASA flex and strict refant, minblperant, minsnr | c2a class B (products 4e-6); `test_cal_gain.py`, `test_c2e_calibrate.py`, `tools/gain_hash_gate.py` | gaincal and bandpass docs; 150 lines | CASA-identical referencing (`casa_rules=True`, the default); QuartiCal referencing stays |
| `bandpass.rs` (90) | fillgaps for B | c2c part 2: 8 of 8 exact | bandpass docs (linear interpolation of amplitude and phase); 60 lines | `fillgaps > 0` (CARACal's default is 0) |
| `apply.rs`, `crosshand.rs` fragments (57) | phase tracking in interpolation; the KCROSS peak | c4a/c4b class C; c6 | documented behaviour; 50 lines | ulp-level CASA match |
| `flag_extend.rs` (125) and `test_e0_refant_extend.py` (40) | `flagdata(mode='extend')`, the polcal extend step, tfcrop `extendflags` | e0 gate 2: FLAG bit-identical to CASA 6.7.6.14 | casadocs flagdata extend, and probes as V8b did; 150-250 lines | The extend mode |
| `cal_pol.py` `parallactic_angle_casa` (70, casacore measures) | CASA-frame parallactic angle for `parang=True` | `tests/data/pa_casacore.json`, 2e-7 rad (e2b 9.13-9.16) | IERS conventions and the casacore measures documentation; 70 lines | The CASA frame; frame `rang` (astropy) stays, up to ~7e-6 rad different |
| c-src calibration rules (CASA, CARACal; ~560 lines) | the order of the chain, defaults and interpolation rules | c2e, c6w, c5 | Restate from the CASA task docs and caracal.readthedocs.io; 300-400 lines of rewording | Nothing if restated |

The rewrite totals about 1,100-1,300 lines. Fluxscale and refant need fresh CASA probes.

### 4.6 Small items

| Part | Upstream | Best route | Size | MIT-only loses |
| --- | --- | --- | --- | --- |
| `formats/sky.py` Tigger HTML writer (170) and c-src readers (~400) | Tigger GPL-2.0-or-later (licence and code compared at Tigger's master; the note names 1.8.0, not re-checked); Crystalball, DDFacet, killMS GPL-2.0 | R from format samples, with Tigger as a black box | 150 + 400 | Writing `.lsm.html`; the readers if not rewritten |
| `beam_holography.py` `_reconstruct` (24) | EIDOS GPL-3.0 | Drop (comparison control) or R from Asad et al. 2021 | 24 | Nothing for users |
| `cal_refant.py` `wgs84_to_ecef` (20) | msutils GPL-2.0 | R from NIMA TR8350.2 | 10 | Nothing |
| `core_grid.py` `kernel_reference` (60) | WSClean | R from Jackson et al. 1991, or drop the test reference | 60 | Nothing |
| Two CASA-rule test references (83) | CASA | Delete them; keep the CASA archive comparisons | 0 | Nothing |
| `ms_schema.rs` (d) | casacore and CASA schema strings | Expert opinion; if needed, regenerate from AIPS++ Note 229 and from tables as data | 0 to 2,130 | Byte identity of `table.dat` |
| casacore format reader (c-src) | casacore format | Keep (format, not expression), or restate `core-e-ms-reader.md` as a format spec and have it checked for expression | 0 to 3,000 | Every MS read, if dropped |

## 5. Recommended sequence

| Step | What | Effort (agent time) | Depends on |
| --- | --- | --- | --- |
| 0 | Fix the notice gaps of 3.2 under the GPL now (c-blosc, katdal, core_flag, fdlibm, Tigger, africanus, input.rs, calmodels, apply, flag_extend.py, killMS, losoto, msutils; WSClean "version 3"; the headers that say "nothing copied") | 0.5 day | none |
| 1 | Owner decisions (section 6); engage the licensing expert to review this audit before any rewrite | owner, 1-2 weeks of calendar time | 0 |
| 2 | Requests for permission (owner writes them): ducc0 (Reinecke, MPG, Yau) for the wgridder port; ASTRON and Offringa for WSClean, radler, aocommon and schaapcommon | owner; calendar time unknown (weeks) | 1 |
| 3 | While waiting: clean-room rewrites of the small items (4.5, 4.6, the c-src restatements), each with its existing oracle gate re-run and a proposal note frozen first | ~2,000-2,500 lines; 2-3 weeks | 1 |
| 4 | Table writer: decide L (LGPL module, 1-2 days of marking), R (non-byte-identical writer, 3-5k lines, 3-4 weeks) or G | 1-2 days or 3-4 weeks | 1 |
| 5 | Imaging: for what step 2 does not grant, R of the wgridder (2.5-3.5k lines, 4-6 weeks), the weights (1 week) and the GeMClean parts (1.5-1.8k lines, 2-3 weeks), or L for radler (4.4); or move the w-stacking gridder to the GPL package (G) | 0 to 7-10 weeks | 2 |
| 6 | Restructure if G is used anywhere: a `rang-core-gpl` crate and wheel, registered by entry point, with the rest of rang-core refusing those options with a message that names the package | 1 week | 4, 5 |
| 7 | The relicensing step itself, checked by the expert first:<br>- `LICENSE` (MIT text);<br>- SPDX lines in 392 files and `tests/test_spdx_headers.py`;<br>- `pyproject.toml` `license`;<br>- the three `Cargo.toml` `license` fields;<br>- `CITATION.cff`, `docs/licence.md`, `THIRD-PARTY-NOTICES.txt` (permissive notices kept), `CONTRIBUTING.md`, README;<br>- the repository's GPL files under `research/results/` and `data/` marked or removed;<br>- the directories this audit did not classify, because they do not ship, but which a repository-level `LICENSE` would cover: `tools/oracles/` (`aoflagger/st_bridge.py` follows AOFlagger 3.5, GPL-3.0), `tools/e2e/`, `history/`, `examples/`, `core/examples/`, `notebooks/`. Audit them the same way, or scope the new `LICENSE` to the package and mark the rest | 1-2 days (plus 2-3 days for that audit) | 3-6 |

**Effort, in agent work.** Steps 3, 4 and 5 can run in parallel in independent sessions.
- **With permissions for ducc0 and ASTRON, plus the LGPL writer module:** about 3-4 weeks (steps 0, 3, 4 L, 7), plus the time the replies take.
- **Fully clean-room:** 12-17 weeks (step 3: 2-3; step 4 R: 3-4; step 5 R: 7-10), or about 7-10 weeks elapsed in parallel.

Clean-room implementers must be sessions or people that have not read the
upstream or rang's port (section 4).

**Recommended route.**
1. Step 0 now.
2. Ask ducc0 and ASTRON (2).
3. Rewrite the CASA and CARACal pieces clean-room (3). This is small, and CASA permission is excluded by the owner's earlier decision.
4. Keep the casacore writer under LGPL-2.1-or-later as a marked module (4, L), since byte identity is a measured feature no clean room can keep.
5. Whatever ASTRON or ducc0 decline goes to `rang-core-gpl` first (G), then into a clean-room rewrite as time allows.

The package then becomes "MIT AND LGPL-2.1-or-later", with an optional GPL
package. True MIT-only requires step 4 to be R.

## 6. Owner decisions

1. **Target:** MIT only; MIT with an LGPL-2.1-or-later module (the casacore and CASA translations); or MIT plus an optional GPL package.
2. **Byte identity of the MS writer:** keep it (needs L, or AUI's permission) or give it up for a clean-room writer.
3. **Permission requests:** whether to ask ducc0's authors (and MPG) and ASTRON/Offringa, and who writes the messages. This audit drafts none.
4. **CASA and casacore (AUI):** does the standing no-NRAO decision (2026-11-12) exclude asking AUI? If so, CASA parts are R or L only.
5. **Clean-room authorship:** who implements (a contributor who has not read the sources, or fresh agent sessions with no upstream access), and whether the training-data caveat is acceptable. Ask the expert.
6. **What may be dropped instead of rewritten:**
   - the EIDOS control;
   - the Tigger HTML writer;
   - the killMS, DDFacet and Crystalball readers;
   - the w-stacking gridder (to the GPL package);
   - the CASA-rule test references.
7. **Timing:** release v0.3.0 under the GPL as planned (with B-01/B-02 resolved; radler makes the extension GPL-3.0-only), and relicense in a later minor version.
8. **The expert:** whom (for example the Software Freedom Conservancy) and when: before step 3, or only before step 7.
9. **Factual data files:** regenerate `meerkat.itrf.txt` and `casacore_observatories.json` from primary sources (SARAO, IERS and observatory publications) instead of relying on the facts argument.

## 7. Prior releases, AI-assisted code, expert check

**Prior releases.** v0.2.0 and every earlier tag and PyPI upload stay under
GPL-3.0-or-later. Whoever received them keeps that licence for those
versions. A relicence applies from the version that carries the new `LICENSE`.
The same holds for the GPL-derived files: until each is replaced or permitted,
any release that contains it is GPL. v0.3.0, if released before the relicence,
is GPL too. Because radler is LGPL-3.0-only, the extension in v0.3.0 is
GPL-3.0-only in effect (B-02).

**AI-assisted code, in brief.**
- **US:** the Copyright Office (2025 report, Part 2) treats material generated by AI without sufficient human authorship as not protected. Human selection, arrangement and modification can be protected.
- **EU and the Netherlands:** protection requires the author's own intellectual creation, which points the same way.
- **Consequences for this relicence:**
  1. The owner can license whatever copyright he holds. A permissive grant over parts that are not protected does no harm.
  2. **It does not help with derived code.** The upstream's copyright persists in whatever expression a translation carries over, whoever or whatever made the translation.
  3. A clean-room rewrite by an agent is judged by what it copies, not by who typed it. The model's training data is the open question in section 4.

This is a summary, not advice.

**Expert check.** Have the final relicensing step reviewed by a licensing
expert before it is pushed, for example the Software Freedom Conservancy
(which advises free-software projects on licensing and relicensing) or a
lawyer who works with FOSS licences. Questions for them:
1. **Static linking of LGPL modules.** Can LGPL-2.1-or-later translations of casacore and CASA stay under the LGPL inside an MIT package whose Rust extension links them statically, and what must the wheel provide for relinking?
2. **c-src code.** Are the 25,556 lines written to rules read in GPL and LGPL source acceptable as they stand, or must some be rewritten?
3. **`ms_schema.rs`.** Is the copied schema text protectable?
4. **Clean room.** What counts as clean-room when the implementer is a language model?
5. **Optional GPL extras.** Is "MIT core, optional GPL package and optional GPL extras (eidos, stimela, carta-python)" sound?
6. **Wording.** What should the new `LICENSE` and notices say?

## 8. For the coordinator

- **Done:** this note; [results/mit-relicense-audit/](results/mit-relicense-audit/) (`files.csv`, `classify.py`). No code changed.
- **Cross-checks against upstream source made here:** `ism.rs` `get_split` (casacore v3.8.1) and `bandpass.rs` `fill_gap_array` (casa6 `9269a52`). The other upstream comparisons are the area reviews'.
- **Base and sources:** base `41bc3efb`. The notices read from `v030-fix` (`07875d43`) are not on main yet; when v030-fix merges, the notice gaps of 3.2 are what remains. They fit the same release (step 0).
- **Owner decisions:** the nine in section 6. Decisions 1, 2 and 4 decide most of the cost.
- **Upstreams fetched:** ducc0 0.42.0, WSClean 3.6, schaapcommon and aocommon headers, read at their tags on GitHub and GitLab; casa6 `9269a52` sources were fetched into a session scratchpad (not kept). Licence metadata came from PyPI JSON for the pinned versions.

## Owner decision, 2026-11-17

"ok never mind about the license, too much work for now. lets rewrite things when we are done."

- rang-core stays GPL-3.0-or-later. v0.3.0 and the releases after it ship under the GPL.
- The relicensing route in this note (permission requests, clean-room rewrites, an LGPL writer module and an optional GPL package) is deferred until the roadmap work is done. Nobody has been asked for permission.
- Until then, new work avoids adding GPL- or LGPL-derived code beyond what a task needs. It prefers permissive upstreams and reimplementation from papers, so the later rewrite does not grow.
- The notice gaps found here are fixed now under the GPL, on branch `v030-fix`.

## Owner decision, 2026-11-17 (later the same day)

"maybe we should MIT the parts of the code we can to avoid future work, keep
the parts that need to be GPL or LGPL that license for now, we will sort that
out in the future." This supersedes the first decision above for ra-ng's own
code; the rest of the route stays deferred.

## Step 1 done: own code MIT (2026-11-17)

Branch `mit-own`, from main `11fdd993` (v030-fix merged, package metadata
GPL-3.0-only). Only SPDX lines and licence prose changed; no code.

**Rule.** Classes a and c of `files.csv` get `MIT`. Class b-permissive gets
`MIT AND <upstream>`: `MIT AND BSD-3-Clause` for Tricolour, codex-africanus,
katdal and c-blosc; `MIT` alone for the three QuartiCal translations,
because QuartiCal is MIT (the notice stays in each file;
`test_quartical_translations_keep_the_mit_notice`). Classes b-copyleft, c-src
and d keep their lines unchanged. When in doubt, a file stays GPL.

**Re-checked on the new main.** The four headers v030-fix corrected
(`ism.rs`, `bandpass.rs`, `fluxscale.rs`, `reference.rs`) are b-copyleft and
stay GPL. The class-a files v030-fix changed (`core_cli.py`,
`core_writeback.py`, `lightcurve.py`, `tools/check_all.py`) gained own code
only.

**Outside the audit's scope.** 112 header-bearing files do not ship
(`tools/oracles/`, the other `tools/` scripts, research scripts,
`core/tests/`, `docs/_extra/`). Their heads and upstream mentions were read
one by one. Six stay GPL (the `HELD` list in
[results/mit-relicense-audit/spdx.py](results/mit-relicense-audit/spdx.py)):
- `tools/oracles/aoflagger/st_bridge.py`: AOFlagger 3.5's `SumThresholdMissing`, transcribed;
- `tools/oracles/aoflagger/posthoc/s1_values.py`: Tricolour's kernel and AOFlagger's semantics re-chained;
- `tools/oracles/aoflagger/tricolour_dump.py`: re-chains Tricolour's flagger step for step (d);
- `tools/oracles/casa/crosscal.py`: CARACal's `crosscal_worker.py` calls, line by line (c-src);
- `tools/oracles/w3b/angles_memory.py`: a verbatim copy of an older `applycal._field_angles` (c-src);
- `docs/_extra/interferometer/index.html`: embeds the simms-copied MeerKAT positions (d).

**Licence prose.** 32 MIT files said "Licensed under the GNU General Public
License, version 3 or (at your option) any later version" in a comment; that
line now names the MIT License and `LICENSES/MIT.txt`. The QuartiCal and
codex-africanus translations said "part of Rang (GPL-3.0-or-later)"; now
"(MIT)".

**After the change** (every tracked file with an SPDX line; the list is
[results/mit-relicense-audit/spdx.csv](results/mit-relicense-audit/spdx.csv),
written by `spdx.py`):

| Class | SPDX line | Files | Lines |
| --- | --- | ---: | ---: |
| a | `MIT` | 424 | 117,208 |
| c | `MIT` | 9 | 3,725 |
| b-permissive (QuartiCal) | `MIT` | 3 | 4,799 |
| b-permissive (BSD) | `MIT AND BSD-3-Clause` | 5 | 3,730 |
| b-copyleft | `GPL-3.0-or-later` | 22 | 27,824 |
| b-copyleft | `GPL-3.0-or-later AND LGPL-3.0-only` | 3 | 2,931 |
| b-copyleft | `GPL-3.0-or-later AND BSD-3-Clause` (`sky.py`) | 1 | 1,160 |
| b-copyleft | `GPL-3.0-or-later AND SunPro` (`shader.rs`) | 1 | 313 |
| c-src | `GPL-3.0-or-later` | 32 | 24,043 |
| c-src | `GPL-3.0-or-later AND LGPL-3.0-only` (`joined.rs`) | 1 | 991 |
| c-src | `GPL-3.0-or-later AND MIT` (`cal/diag.rs`) | 1 | 1,154 |
| d | `GPL-3.0-or-later` | 3 | 3,269 |
| **MIT or MIT AND BSD** | | **441** | **129,462** |
| **GPL or LGPL** | | **64** | **61,685** |

The class counts include the 112 unshipped files (106 of them class a), so
they differ from the shipped-only totals of section 1.

**Stamped (coordinator follow-up, same day).** The 170 shipped files that had
no SPDX line now have one. 167 are class a (most of `tests/` and
`core/py/src`): `MIT`. Three transcribe CASA and stay GPL, with HELD entries:
`tests/test_e0_refant_extend.py` (b-copyleft, `FlagAgentExtension.cc`'s
loops), `tests/test_cal_fluxscale.py` and `tests/test_a3_casa_phase_weights.py`
(c-src, CASA rules in NumPy): `GPL-3.0-or-later`. `tests/test_v030_fix.py`,
own code added after the audit, is `MIT` too. Every shipped file now carries
an SPDX line.

**Licence files and metadata.** `LICENSES/MIT.txt` (Gijs Molenaar and the
ra-ng contributors, 2026) is new and ships in the wheel and the sdist
(`license-files`); `LICENSE` stays the GPL-3.0 text. `pyproject.toml`,
`core` and `core/py` stay `GPL-3.0-only`: the combined package is GPL while
the GPL and LGPL parts are in it. The root crate `rang-sim` is `MIT` (all
seven files class a). `CITATION.cff` names only the package licence and is
unchanged.

**Test.** `tests/test_spdx_headers.py` checks that every tracked SPDX line is
listed in `spdx.csv` with the same expression, that the expression fits the
class (a, c: `MIT`; b-permissive: `MIT` first and only permissive terms; the
rest: a GPL term and not `MIT` first), and that no file `files.csv` marks
b-copyleft, c-src, d or non-MIT b-permissive carries a bare `MIT`.
A file not yet listed passes if its line is bare `MIT` (new own code is MIT by
the owner's rule); with any other line it fails until it is added to
`spdx.py`'s `HELD` with its class. `test_a_bare_mit_on_a_derived_file_fails`
shows a bare `MIT` on a derived file is caught.

## Update 2026-11-26: the provenance register

The owner, 2026-11-26: "keep track of the license per file or code piece so we
can decide which ones to rewrite later". Owner decisions the same day
(research/STATE.md): radler-derived code stays as it is and is rewritten
later; msutils was GPL-2.0-or-later up to 3.0.0 (Apache-2.0 from 3.1.0).
Branch `licence-register`. Only the register, licence lines and licence prose
changed; no code behaviour.

**The register.** [results/mit-relicense-audit/files.csv](results/mit-relicense-audit/files.csv)
is now edited by hand and is the source of truth. `classify.py` no longer
writes it from a table of its own: it checks coverage, refreshes `lines`
(`--lines`) and prints the totals and the candidates below. Two columns are new:
- `piece`, the derived functions or sections, so a rewrite can be chosen per piece;
- `decision`, the owner's decision for that row.

**Scope.** Every tracked `.py`, `.sh`, `.rs`, `.cc` and `.wgsl` file under
`python/rang`, `core/src`, `core/py/src`, `src` and **all of `tools/`**, plus
the audit's 158 rows for `tests/`. New tests are not required to have a row.
The scope is wider than section 1's 392 shipped files (`tools/` was only
`check.py` and `wheel/`), so the totals here are not comparable with section 1.

**Enforced.** `tests/test_licence_register.py` and `tools/prepush_check.py`
(standard library, part of the one-second pre-push check) refuse a file in
scope without a row, and a row without a file. The test also requires each
derived row to name its upstream, licence, upstream files and piece. Own new
code is one line: `<path>,<lines>,a,-,-,-,0,-,-`.

**Rows added since d4b13e9b (2026-11-17).** 173 files had no row: 26 shipped
and 147 in `tools/`. Each one's head, its upstream mentions and the research
note it cites were read.
- Class a: 166 files. These include the F4/F5 flaggers, `learned_interp.rs`, `diag_stream.rs`, `cal_stream`, `core_spool`, `watch`, `msv4`, `msv4_flags`, `solver_flags.py`, `flag_residual.py`, every binding in `core/py/src`, and every new `tools/` script (the DD1-DD10, ts-p2/p3, multinode and chunk-task drivers call WSClean, QuartiCal and CASA as oracles; nothing is transcribed). The five `tools/` files that `spdx.py` holds as GPL keep their classes.
- **b-permissive (QuartiCal 0.2.7, MIT, notice present):**
  - `core/src/flag_residual.rs`: `flags_quartical`, the `mad_flags` port, about 140 lines;
  - `core/src/cal/diag_dd.rs`: the direction-dependent `diag_complex` and `phase` kernels, about 600 lines. Its helpers copied from `diag.rs` are QuartiCal's; the CASA SNR part is not among them.
  - `test_quartical_translations_keep_the_mit_notice` now covers both.
- **c (documentation or format), MIT:**
  - `core/src/reweight.rs` and `python/rang/reweight.py`. The statwt rules they follow are in casadocs' statwt page: `(v_r + v_i)/2`, divisor N, and WEIGHT as the median of WEIGHT_SPECTRUM. casa6's source was read only to confirm them.
  - `core/src/learned.rs`: the field numbers of `onnx.proto`, an Apache-2.0 interface.

**Reclassified.** `python/rang/meerkat.py` goes from b-permissive to **d**.
Its `KNOWN_RFI_L_*` lists (issue #59) are oxkat `421d14c5`'s `config.py`
L-band lists, copied with their order and comments (checked against oxkat at
that commit). oxkat is GPL-3.0, and so is the SARAO MeerKAT Cookbook that
they cite. They are facts (frequency ranges). Under the same rule as the simms
positions in `docs/_extra/interferometer/index.html`, the file is now
`GPL-3.0-or-later AND BSD-3-Clause`. Its notice is in THIRD-PARTY-NOTICES.txt,
and `test_ported_files_name_the_upstream_licence_too` pins it.

**Header and prose fixes.**
- 17 MIT files (16 bindings in `core/py/src`, and `core/src/f4flag.rs`) still said "Licensed under the GNU General Public License, version 3 or (at your option) any later version" in a comment. They now name the MIT License, as Step 1 did for 32 files.
- `cal_refant.py`, `docs/licence.md` and THIRD-PARTY-NOTICES.txt record the msutils settlement. The four radler files carry "rewrite later (owner 2026-11-26)" in `decision`.

**Changed files whose class stands.** Since d4b13e9b, own code was added to
GPL files. The pieces that follow upstream rules are named:
- `apply.rs` `calwt_scale`, after CASA `calcWtScale`;
- the calwt opt-ins in `cal_gain.py`, `cal_pol.py` and `cal_apply.py`;
- `cal_delay.py`'s refantmode flex and `zero_start`, for which KJones.cc was read (a deviation from CASA, own logic);
- `multiscale.rs`'s dropped-scale rule;
- `wgridder.rs` and `cli.rs`'s `RANG_GEMCLEAN_TRACE` lines (gemclean-57, own).

None changes a class. Their derived-line estimates are kept, since the
additions are c-src rules, not transcriptions.

**Totals** (`classify.py`; the register, including the `tests/` rows):

| Class | Files | Lines | Derived lines (est.) |
| --- | ---: | ---: | ---: |
| a | 480 | 132,879 | 0 |
| b-permissive | 9 | 10,482 | 6,445 |
| b-copyleft | 27 | 32,766 | 14,555 |
| c-src | 34 | 28,047 | 1,192 |
| c | 12 | 4,888 | 0 |
| d | 3 | 3,182 | 2,510 |
| **total** | **565** | **212,244** | **24,702** |

Without `tests/`, the five directories hold 407 files and 179,204 lines. Of
them, 61 files and 63,210 lines are in the copyleft classes (b-copyleft, c-src
and d; five of these files are oracle tools).

**Rewrite candidates, per piece** (copyleft classes; derived lines from the
register; cost from section 4 unless marked new):

| Piece | Files | Derived | Upstream | Licence | Cost | Decision |
| --- | --- | ---: | --- | --- | --- | --- |
| SSM, StManArrayFile, FilebufIO, BucketCache, TSMCube writers; IncrementalStMan; MultiFile; tile shapes | `ms_write.rs`, `ism.rs`, `multifile.rs`, `tiled.rs` | 6,760 | casacore 3.8.1 | LGPL-2.0/2.1-or-later | L 1-2 days, or R 3-5k lines, 3-4 weeks (4.1) | - |
| ducc0 wgridder and KernelDB | `wgridder.rs` | 3,550 | ducc0 0.42.0 | GPL-2.0-or-later | R 2.5-3.5k lines, 4-6 weeks, or permission (4.2) | - |
| MS v2 and NewCalTable schema strings (data) | `ms_schema.rs` | 2,130 | casacore 3.8.1, CASA 6.7.6 | LGPL-2.0-or-later | expert opinion; 0 to 2,130 (4.6) | - |
| w-stacking gridder; WGSL shader; imaging weights and tapers; `kernel_reference` | `grid.rs`, `gpu/shader.rs`, `weights.rs`, `core_grid.py` | 1,650 | WSClean 3.6/3.7 | GPL-3.0 | gridder 700-900 lines plus shaders; weights 300-400 lines, 1 week (4.3) | - |
| multiscale; auto-mask; `-pol` and Stokes; joined flow | `multiscale.rs`, `mask.rs`, `stokes.rs`, `joined.rs` | 1,245 | radler 76fe4474, aocommon aa4d6a47, WSClean 3.7 | LGPL-3.0-only; GPL-3.0 | 1.5-1.8k lines with the schaapcommon parts, 2-3 weeks (4.4) | **rewrite later (owner 2026-11-26)** |
| CASA kernels: fluxscale, refant rules, fillgaps, trackPhase, KCROSS peak, extend | `fluxscale.rs`, `reference.rs`, `bandpass.rs`, `apply.rs`, `crosshand.rs`, `flag_extend.rs` | 807 | casa6 9269a52 | LGPL-2.0/2.1-or-later | about 1,100-1,300 lines with the CASA rules below (4.5) | - |
| WSClean CLI behaviour, predict, Stokes I and angle rules (c-src) | `gemclean/cli.rs`, `gemclean/predict.rs`, `core_model.py`, `core_weights.py`, `correct.rs` | 385 | WSClean 3.6/3.7 | GPL-3.0 | restate as documented behaviour (4.4) | - |
| CARACal recipe, defaults and worker order (c-src) | `core_pipeline.py`, `core_config.py`, `cal_chain.py`, `cal_selfcal.py`, `cal_apply.py`, `cal_refant.py` `get_refant` | 370 | CARACal 8f7bb363 | GPL-2.0 | restate, 300-400 lines of rewording (4.5) | - |
| Tigger HTML writer; sky-model readers | `formats/sky.py` | 170 (+ ~400 c-src) | Tigger, Crystalball 0.4.3, DDFacet 1.0, killMS 3.3.0 | GPL-2.0(-or-later) | 150 + 400 (4.6) | - |
| restoring-beam fit; `stokes_cell`; spectral conventions | `gemclean.rs`, `input.rs`, `spectral.rs` | 129 | schaapcommon b553fd25, WSClean 3.7 | GPL-3.0-or-later | 120 lines (4.4) | - |
| CASA-rule test references | `tests/test_e0_refant_extend.py`, `test_cal_fluxscale.py`, `test_a3_casa_phase_weights.py` | 123 | casa6 | LGPL | delete; 0 (4.6) | - |
| CASA calibration rules (c-src) | `cal_gain.py`, `cal_delay.py`, `cal_bandpass.py`, `cal_fluxscale.py`, `applycal.py`, `calmodels.py`, `flag_extend.py`, `cal/diag.rs` SNR, `cal/leakage.rs`, `caltable.rs`, `formats/caltable.py` | 110 | CASA | GPL-2.0+/LGPL-2.0+ | part of the 300-400 lines of rewording (4.5) | - |
| `parallactic_angle_casa` | `cal_pol.py` | 70 | casacore measures | LGPL-2.0-or-later | 70 lines (4.5) | - |
| `EidosBeam._reconstruct` | `beam_holography.py` | 24 | EIDOS 1.1.2 | GPL-3.0 | drop, or 24 lines (4.6) | - |
| oxkat L-band RFI lists | `meerkat.py` `KNOWN_RFI_L_*` | 20 | oxkat 421d14c5 | GPL-3.0 (facts) | new: about 20 lines, re-sourced from primary allocations (ITU, GNSS operators) and checked against #59's flagged fraction | - |
| `wgs84_to_ecef` | `cal_refant.py` | 20 | msutils 1.2.0 | **GPL-2.0-or-later** (owner 2026-11-26) | 10 lines from NIMA TR8350.2 (4.6) | licence settled |
| MS reader, AipsIO, table.dat, H5parm, killMS formats (c-src) | `ms.rs`, `aipsio.rs`, `ms_create.rs`, `ms_desc.rs`, `_aipsio.py`, `h5parm.py`, `killms.py` | 0 (format) | casacore 3.8.1, losoto 2.7.1, killMS 3.3.0 | LGPL-2.0-or-later, GPL | keep (format), or restate (4.6) | - |
| oracle tools (not shipped): AOFlagger and Tricolour bridges, CARACal crosscal calls, the old `_field_angles` | `tools/oracles/aoflagger/*` (3), `casa/crosscal.py`, `w3b/angles_memory.py` | 464 | AOFlagger 3.5, Tricolour 0.2.1, CARACal 8f7bb363, CASA | GPL | new: none needed for the package; mark or keep under GPL (step 7) | - |

The shipped pieces sum to about 17,600 derived lines. The largest four make up
14,090 of them: the casacore writer, the ducc0 wgridder, the schema strings,
and the WSClean gridder and weights.

**For the coordinator.**
- `files.csv` is a single file that every branch adding a source file now touches, so expect merge conflicts in it. Resolve them by keeping both rows (the rows are sorted by path).
- A branch that was in flight before this one merges goes red until it adds its rows.
- `meerkat.py` flipping to GPL makes the known-RFI preset the cheapest rewrite candidate.
