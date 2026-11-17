# Licence and acknowledgements

## Software

Since 2026-11-17 the source is under two licences, file by file; each file's
SPDX line says which ({gh}`research/mit-relicense-audit.md`, "Step 1 done: own
code MIT"):

| What | Licence | Why |
| --- | --- | --- |
| ra-ng's own code: every file the audit classes as own original (a) or as reimplemented from papers, documentation or black-box behaviour (c), in `core/`, `python/rang`, `src/`, `tests/`, `tools/` and the research scripts: 441 files, 129,462 lines with the next row | **MIT** ({gh}`LICENSES/MIT.txt`) | The owner wrote it and holds its copyright |
| Translations of permissive upstreams: QuartiCal 0.2.7 (`core/src/solve.rs`, `cal/delay.rs`, `cal/delay_offset.rs`); Tricolour 0.2.1 (`core/src/sumthreshold.rs`, `python/rang/core_flag.py`); codex-africanus 0.4.4 (`core/src/predict.rs`); katdal 0.23 (`python/rang/meerkat.py`); c-blosc 1.21.6 (`core/src/blosc.rs`) | **MIT** for the QuartiCal files (QuartiCal is MIT), **MIT AND BSD-3-Clause** for the others | The upstream licence allows it; the upstream notice stays in the file and in {gh}`THIRD-PARTY-NOTICES.txt` |
| Code translated or derived from GPL or LGPL upstreams (the audit's b-copyleft class; with the next row 64 files, 61,685 lines): the casacore table writer (`ms_write.rs`, `ism.rs`, `multifile.rs`, `tiled.rs`), the ducc0 wgridder (`wgridder.rs`), WSClean's gridder and weights (`grid.rs`, `weights.rs`, `gpu/shader.rs`, `core_grid.py`), GeMClean's radler, aocommon and schaapcommon parts (`gemclean.rs`, `gemclean/mask.rs`, `multiscale.rs`, `stokes.rs`, `input.rs`), the CASA kernels (`cal/apply.rs`, `bandpass.rs`, `crosshand.rs`, `fluxscale.rs`, `reference.rs`, `flag_extend.rs`), `cal_pol.py`, `cal_refant.py`, `formats/sky.py`, `beam_holography.py`, `tests/test_e0_refant_extend.py` | **GPL-3.0-or-later**, with `AND LGPL-3.0-only` (radler), `AND BSD-3-Clause` (codex-africanus regexes in `sky.py`) or `AND SunPro` (fdlibm in `shader.rs`) where the SPDX line names them | The upstream's copyleft licence covers what the translation carries over |
| Code written to rules or formats read in GPL or LGPL source (the audit's c-src class: the MS reader and AipsIO, the CASA calibration rules, the CARACal recipe, the WSClean CLI conventions, `joined.rs`, the killMS and H5parm formats, two CASA-rule test references) and the unclear class d (`ms_schema.rs`) | **GPL-3.0-or-later** (`joined.rs` also `AND LGPL-3.0-only`, `cal/diag.rs` also `AND MIT`) | Kept as they are to be safe until a licensing expert has judged them |
| Files with no SPDX line (the notebooks, examples and documentation; every shipped file has one) | GPL-3.0-or-later, the repository's {gh}`LICENSE` | Not stamped in this step |
| **The distributed package** (the wheels, the sdist and the extension `rang._core`) | **GPL-3.0-only** | It combines the GPL and LGPL parts above with the MIT code. WSClean's sources say "GPL 3" without "or later", and radler is LGPL-3.0-only, conveyed here under GPL version 3 (LGPL-3.0 section 2(b)) |

The per-file list is {gh}`research/results/mit-relicense-audit/spdx.csv`, and
{gh}`tests/test_spdx_headers.py` checks every file's SPDX line against it.
The root crate `rang-sim` is MIT: every file in it is own code. The MIT files
can be reused under MIT on their own; whoever takes a GPL or LGPL file, or
the package as a whole, takes it under that licence.

Contributions are accepted under the licence of the file they change
(inbound = outbound): a change to an MIT file is contributed under MIT, a
change to a GPL file under its GPL line ({gh}`CONTRIBUTING.md`).

The GPL was chosen on 2026-10-29 so that GPL-3 radio-astronomy tools such as
WSClean and AOFlagger could be ported into the core. GPL-2.0-only code cannot
be combined with GPL-3 code, so each upstream's exact licence is checked
before it is ported, and ported code keeps its upstream copyright notices.
New work avoids adding GPL- or LGPL-derived code beyond what a task needs
(owner decision, 2026-11-17).

`python/rang/cal_refant.py`'s `wgs84_to_ecef` is the standard WGS84
geodetic-to-geocentric conversion, which is published formula, not expression.
It follows msutils 1.2.0's order of operations so that `refant: auto` picks the
same antenna as CARACal. msutils' own metadata gives two different GPL versions
(v2 in its LICENSE, 3.0-or-later in setup.py). The conversion is treated as the
standard formula, not as a copyrightable part of msutils (coordinator decision,
2026-11-17). If that view is challenged, the function is rewritten from the
WGS84 definition (NGA TR8350.2) and checked against the same refant tests.

| Ported or bundled | Upstream licence, as the reports record it |
| --- | --- |
| QuartiCal 0.2.7 `complex` solver | MIT; the ported file keeps its notice ({gh}`research/core-phase2.md`) |
| Tricolour 0.2.1 strategies and static masks (`core/src/sumthreshold.rs`, `python/rang/core_flag.py`) | BSD-3-Clause, on the strength of its `LICENSE` file; the masks ship with `TRICOLOUR-LICENSE` ({gh}`research/core-d-tricolour.md`) |
| WSClean 3.6 weights and w-stacking gridder (`core/src/weights.rs`, `core/src/grid.rs` and its WGSL form `core/src/gpu/shader.rs`) | GPL version 3: `gridding/wstackinggridder.h` says "published under the GPL 3 license" and the README "GPL license version 3", neither "or any later version"; Debian's `debian/copyright` records GPL-3.0+ ({gh}`research/core-c-gridder.md`) |
| ducc0 0.42.0 wgridder | GPL-2.0-or-later ({gh}`research/df1-wgridder.md`) |
| SARAO/SKA pointing-offset fit (ska-sdp-wflow-pointing-offset) | BSD-3-Clause ({gh}`research/b1-beam-pointing.md`) |
| codex-africanus 0.4.4 WSClean-format component predict (`core/src/predict.rs`) and two regular expressions of its model parser (`python/rang/formats/sky.py`) | BSD-3-Clause; the translated file keeps its notice, as does {gh}`THIRD-PARTY-NOTICES.txt` |
| katdal 0.23 test helpers, adapted for the synthetic MVF writer (`python/rang/meerkat.py`) | BSD-3-Clause, National Research Foundation (SARAO); its licence text in {gh}`THIRD-PARTY-NOTICES.txt` |
| c-blosc 1.21.6 `blosc_d` and `shuffle-sse2.c` (`core/src/blosc.rs`) | BSD-3-Clause, Francesc Alted and the Blosc Development Team; licence text in {gh}`THIRD-PARTY-NOTICES.txt` |
| fdlibm `k_sin.c`, `k_cos.c`, `e_rem_pio2.c` coefficients (`core/src/gpu/shader.rs`) | Sun Microsystems' permissive notice (SPDX `SunPro`), kept in the file and the notices |
| Tigger 1.8.0 `.lsm.html` writer (`renderAttrMarkup`, `ModelHTML.save`) and its formats (`python/rang/formats/sky.py`) | GPL-2.0-or-later, The MeqTree Foundation and ASTRON, used under GPL-3.0-or-later |
| casacore 3.8.1 storage managers, translated: SSM, the array file, the file buffer, the bucket cache, TSMCube (`core/src/ms_write.rs`), the IncrementalStMan (`core/src/ism.rs`), MultiFile (`core/src/multifile.rs`), the tile shape (`core/src/tiled.rs`); also `Interpolate1D.tcc` (3.7.1, `core/src/cal/apply.rs`) and `MSIter.cc`, `BaseTabIter.cc` (`python/rang/flag_extend.py`) | LGPL-2.0-or-later, Associated Universities, Inc.; each file's notice in {gh}`THIRD-PARTY-NOTICES.txt` |
| CASA `Imager.cc` (GPL-2.0-or-later) and `SpectralIndex.cc`, `SkyCompRep.cc`, `Flux.tcc` (LGPL-2.0-or-later) in `python/rang/calmodels.py`; `CTTimeInterp1.cc` (LGPL-2.0-or-later) in `core/src/cal/apply.rs`; `FlagDataHandler.cc`, `FlagMSHandler.cc` (LGPL-2.1-or-later, with ESO) in `python/rang/flag_extend.py`; casa6 mirror `9269a52` | Associated Universities, Inc.; notices in {gh}`THIRD-PARTY-NOTICES.txt` |
| EIDOS 1.1.2 `recon_par`, re-expressed as a comparison control (`python/rang/beam_holography.py`) | `setup.py` "GNU GPL v3" (Khan M. B. Asad), no notice in the file and no LICENSE in the sdist |
| msutils 1.2.0 `wgs84_to_ecef` (`python/rang/cal_refant.py`, about 20 lines) | `flag_stats.py` has no notice; `LICENSE` is the GPL-2.0 text, the metadata "GNU GPL v2", `setup.py` "version 3 of the License, or (at your option) any later version" (Copyright (c) 2016 SKA South Africa). The statements conflict: under "GNU GPL v2" alone these lines could not be combined with GPL-3.0 code, under `setup.py` they could. **Open, an owner decision** ({gh}`research/v030-review.md` 5.5): keep, ask the msutils authors, or rewrite from the published formula |
| CASA (casa6) calibration and flagging C++: `SolvableVisCal.cc`, `SolveDataBuffer.cc`, `StandardVisCal.cc`, `DJones.cc`, `XJones.cc`, `KJones.cc`, `Calibrater.cc`, `VisCal.cc`, `Jones.cc`, `VisEquation.cc`, `CTPatchedInterp.cc`, `RIorAParray.cc`, `FlagAgentExtension.cc`, read in the mirror `dic-case-studies/casa6` at `9269a52` and followed in the K, G, B, F, polarisation and apply ports (`core/src/cal/`, `rang.cal_*`, `rang.applycal`, `rang.formats.caltable`) and in `core/src/flag_extend.rs` | GPL-2.0-or-later (`Calibrater.cc`), LGPL-2.0-or-later or LGPL-2.1-or-later (`FlagAgentExtension.cc`), each file's own header; Associated Universities, Inc. (and ESO for `FlagAgentExtension.cc`). The LGPL lets a copy be put under the GPL, so all are compatible with GPL-3.0-or-later; each derived file names CASA and the notices are in {gh}`THIRD-PARTY-NOTICES.txt` (checked 2026-11-12, E5 final) |
| casacore measures (`MCDirection.cc`, `MeasMath.cc`, `MeasTable.cc`, `MSDerivedValues.cc`, read at master `3c16927b`, 2026-11-15), followed in `rang.cal_pol.parallactic_angle_casa`: the APP → TOPO → HADEC route, the diurnal-aberration shift, polar motion, the UT → ST polynomial ({gh}`research/e2b-misses.md` 9.13-9.16) | LGPL-2.0-or-later, Associated Universities, Inc.; each file's notice in {gh}`THIRD-PARTY-NOTICES.txt` (checked 2026-11-17, v0.3.0 review B-01). No casacore data table is read or shipped: the Earth orientation is astropy's IERS table (astropy-iers-data, BSD-3-Clause, a dependency, not redistributed) |
| radler `76fe4474` (WSClean 3.7's submodule): the automatic mask, the joined-polarisation and joined-channel peak finding, multiscale CLEAN, the polarisation normalisation (`core/src/gemclean/mask.rs`, `joined.rs`, `multiscale.rs`, `stokes.rs`) | **LGPL-3.0-only** (`// SPDX-License-Identifier: LGPL-3.0-only` in each file read; README "released under the LGPL version 3"); no copyright line in the files. LGPL-3.0 section 2(b) lets a modified copy be conveyed under the GPL, version 3, so these files are `GPL-3.0-or-later AND LGPL-3.0-only` and the parts derived from radler are GPL version 3 only (checked 2026-11-17, B-02) |
| WSClean 3.7 (`4f395b28`) and master `53e25d59` (!1068): beam fitting, visibility count and weight sum, `-pol`, channel grouping, prediction, the theoretic beam (`core/src/gemclean.rs`, `core/src/gemclean/`) | The source files carry no notice; README "released under the GPL license version 3"; `debian/copyright` of wsclean 3.7-3 says GPL-3.0+ with A. R. Offringa's, ASTRON's and Gijs Molenaar's lines (in {gh}`THIRD-PARTY-NOTICES.txt`) |
| aocommon `aa4d6a47` (`polarization.h`, `image.h`) and schaapcommon `b553fd25` (`gaussianfitter.cc`, `spectralfitter.cc`, `reordering.cc`), both WSClean 3.7 submodules | aocommon: no notice in those files, `LICENSE` the GPL version 3; schaapcommon: GPL-3.0-or-later, ASTRON, verbatim in {gh}`THIRD-PARTY-NOTICES.txt` |
| MeerKAT ITRF positions from simms | Facts, not code: see below ({gh}`data/README.md`) |

Crystalball is GPL-2.0-only and is not ported.

Copies of CARACal's flagging strategy (`mk_rfi_flagging_calibrator_fields_firstpass.yaml`,
GPL-2.0) are kept under `research/results/` as run receipts; they ship in neither
the sdist nor the wheels, and {gh}`research/results/CARACAL-NOTICE.md` names them
with CARACal's licence.

Two upstreams state "version 3" without "or any later version": radler
(LGPL-3.0-only, per file) and WSClean's own README ("GPL license version 3",
where Debian's packaging records GPL-3.0+). While GeMClean carries code that
follows radler, the compiled extension `rang._core` can be conveyed under
version 3 of the GPL only, though ra-ng's own code is MIT; the package
metadata says GPL-3.0-only since 2026-11-17 ({gh}`research/v030-review.md`,
B-02).

Behaviour reimplemented from upstream source and documentation, with no
code copied (owner decision E5-33, 2026-11-11,
{gh}`research/e5-prereview.md`):

| Reimplemented | Upstream and its licence |
| --- | --- |
| CARACal 8f7bb363 `manage_antennas.get_refant` (`refant: auto`, `python/rang/cal_refant.py`) | CARACal, GPL-2.0 (its `pyproject.toml` does not say whether only or or-later); follow-up: ask the CARACal authors to confirm GPL-2.0-or-later |
| msutils 1.2.0 `flag_stats.save_statistics`, as `get_refant` uses it (`python/rang/cal_refant.py`) | msutils; GPL (see the `wgs84_to_ecef` row above, which is followed operation by operation) |
| CASA's ported sources | Listed with the ported code above: the calibration and flag-extension ports read CASA's C++ source, so they are translations, not reimplementations of documented behaviour |
| casacore 3.8.1 AipsIO and table formats (`core/src/aipsio.rs`, the reader `core/src/ms.rs`) | casacore, LGPL-2.0-or-later; the formats were read in its sources. The storage-manager writers are translations, listed with the ported code above |
| File formats only, no code: killMS 3.3.0 solutions (`formats/killms.py`; GPL-2.0), losoto 2.7.1 H5parm (`formats/h5parm.py`; GPL-3.0-or-later), Crystalball 0.4.3 and DDFacet 1.0 sky models (`formats/sky.py`) | Formats read in the upstream source, no code translated (the MIT audit's "c-src" class; it names the `sky.py` readers its weakest case; Crystalball is GPL-2.0-only); named in {gh}`THIRD-PARTY-NOTICES.txt` |

The observatory positions in `python/rang/data/casacore_observatories.json`
come from casacore-data 20250826 ({ghdir}`python/rang/data`); like the
antenna tables below they are positions, not code.

The antenna coordinate tables in `data/*.itrf.txt` are copied from simms
(GPL-2.0-only). They hold measured antenna positions (ITRF X, Y, Z, dish
diameter, name, mount) and no code; positions of physical antennas are facts,
which copyright does not cover, so they carry no simms licence obligation and
ship in the package (GPL-3.0-only) with their source recorded in
{gh}`data/README.md`. Only `meerkat.itrf.txt` ships in the sdist, because
GeMClean's simulator compiles it in; the VLA, WSRT and KAT-7 tables feed the
research examples only and stay in the repository (owner decision E5-11,
2026-11-11, {gh}`research/e5-prereview.md`). A byte copy of
`meerkat.itrf.txt` is package data (`python/rang/data/`), so the A1
simulation (`rang.simtruth`, `python -m rang.simtruth_ms`) runs from a wheel
(V3's owner decision 4, {gh}`research/v3-intro-track.md`).

## Data

No raw visibilities or beam maps are committed or redistributed. Fetched
data stay in ignored `outputs/` or in a cache directory the user names.

- **MeerKAT data (SARAO).** The LUNO calibrator observation is used with the
  observer's permission (Ben Hugo, 2026-10-29), recorded as a user decision
  in {gh}`research/big-plan.md`; publications cite the SARAO data usage
  acknowledgement, recorded in {gh}`research/flagging-verdict.md` as:

  > The MeerKAT telescope is operated by the South African Radio Astronomy
  > Observatory, which is a facility of the National Research Foundation, an
  > agency of the Department of Science and Innovation.

  The report notes this wording is to be checked against SARAO's data policy
  before publication.
- **MeerKAT L-band holography beams** (de Villiers 2023, AJ 165, 78; data DOI
  10.48479/wdb0-h061): licence **CC BY-NC 4.0**. rang reads them by HTTP
  range for non-commercial research and never redistributes them; a
  commercial use of products derived from them would need SARAO's permission
  ({gh}`research/b1-beam-pointing.md`).
- **ESO137 target field** (RATT public bucket): licence **CC BY 4.0**, cite
  Ramatsoku et al. (2020) ({gh}`research/b1-beam-pointing.md`).
- **The tutorial fixture** `outer_scans.zip` is a public test file of the SKA
  repository ska-sdp-wflow-pointing-offset (Git LFS), downloaded on demand
  and verified by SHA256, never bundled
  ({gh}`research/measurement-set-inspection.md`).
- **Antenna positions.** The simulation's eight core positions are transcribed from
  Jonas & the MeerKAT Team, PoS(MeerKAT2016)001 ({gh}`data/README.md`).

## Logo

The interferogram mark and the `rang-core` wordmark are the project's own
({ghdir}`docs/logo`).
