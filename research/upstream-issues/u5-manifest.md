# U5 posting manifest (2026-11-12)

The coordinator posts these after the owner has seen the list; U5 posted nothing. Each text file has its
`Target`, `Reproduced on` and `Duplicates checked` lines above a `Title:` and a `---`. Post the part
below `---` as the body. Rows 2-23 are issues (none is an MR or PR: on git.astron.nl the account is
external and cannot fork, so the schaapcommon patch is inline); row 1 is an email note and rows 24-25 are
helpdesk tickets, all three for the owner to send.

| # | Host | Project | Title | Text file | Kind |
| --- | --- | --- | --- | --- | --- |
| 1 | email (owner's choice) | Richard Armstrong, SARAO (Obit; fork github.com/richarms/Obit, issues off) | Obit MFImage CLEAN crash: dim[5] in MFMakeResiduals (your ab77437c) | [obit-dconcleanvismf-dim5.md](obit-dconcleanvismf-dim5.md) | note; owner sends or approves |
| 2 | git.astron.nl | RD/schaapcommon | Fit2DGaussianCentred fits only the x >= 0, y >= 0 quadrant of its box (unsigned pixel offsets) | [schaapcommon-beam-fit-quadrant.md](schaapcommon-beam-fit-quadrant.md) | issue, patch inline; if issues are disabled there, gitlab.com/aroffringa/wsclean |
| 3 | gitlab.com | aroffringa/wsclean | -join-polarizations: help and docs say peaks are found in the sum of squares; the default clean finds them in the linear sum | [wsclean-join-polarizations-linear-sum.md](wsclean-join-polarizations-linear-sum.md) | issue |
| 4 | gitlab.com | aroffringa/wsclean | CalculateMsLimits tests the y (v) bound with u | [wsclean-mslimits-v-bound.md](wsclean-mslimits-v-bound.md) | issue |
| 5 | gitlab.com | aroffringa/wsclean | -save-source-list help and component_list.rst do not state its restrictions | [wsclean-save-source-list-help.md](wsclean-save-source-list-help.md) | issue (low priority) |
| 6 | gitlab.com | aroffringa/aoflagger | sumthreshold_masked reads its direction flags from Lua arguments 4 and 5 instead of 5 and 6 | [aoflagger-sumthreshold-masked-args.md](aoflagger-sumthreshold-masked-args.md) | issue |
| 7 | gitlab.com | aroffringa/aoflagger | SumThresholdMissing::horizontal keeps a missing sample in the running sum for the rest of the row | [aoflagger-sumthreshold-missing-xright.md](aoflagger-sumthreshold-missing-xright.md) | issue |
| 8 | gitlab.com | aroffringa/aoflagger | Lua docs: high/low_pass_filter take sigma squared; invert_mask after clear_mask does nothing | [aoflagger-lua-doc-notes.md](aoflagger-lua-doc-notes.md) | issue (docs) |
| 9 | github.com | casacore/casacore | Table files contain uninitialised heap memory (array-file gaps, reserved arrays, MultiFile header blocks); one case is read back as cell values | [casacore-uninitialised-file-bytes.md](casacore-uninitialised-file-bytes.md) | issue (public: no security policy, private reporting off) |
| 10 | github.com | casacore/casacore | IncrementalStMan: re-putting an indirect array in a single-row interval decrements its reference count below zero; the array file then grows | [casacore-ism-refcount-underflow.md](casacore-ism-refcount-underflow.md) | issue |
| 11 | github.com | casacore/casacore | TiledCellStMan: getColumnRange/putColumnRange raise "TSMShape::offset - shapes do not conform" (reads rowpos past the IPosition end) | [casacore-tiledcellstman-column-range.md](casacore-tiledcellstman-column-range.md) | issue |
| 12 | github.com | casacore/casacore | Reopened disk table with a FixedShape MemoryStMan array column: reads raise MSMColumn::findExt and closing the table aborts the process | [casacore-memorystman-fixedshape-reopen.md](casacore-memorystman-fixedshape-reopen.md) | issue |
| 13 | github.com | tmolteno/casacure | Tiled managers on create: a variable-shape column is accepted for TiledColumnStMan, nrow > 0 fails and leaves a broken table; getcoldesc reports StandardStMan for casacore tables | [casacure-tiled-create-descriptors.md](casacure-tiled-create-descriptors.md) | issue |
| 14 | github.com | tmolteno/casacure | measures: UTC to TAI/UT1 returns the input relabelled, and ITRF positions report metres as rad | [casacure-measures-relabel.md](casacure-measures-relabel.md) | issue |
| 15 | github.com | tmolteno/casacure | TaQL: BETWEEN, SELECT without a column list and ORDERBY DESC col are parse errors; rownumbers(table) is missing | [casacure-taql-gaps.md](casacure-taql-gaps.md) | issue |
| 16 | github.com | tmolteno/casacure | Shapes and dtypes of never-written cells: a 3-D column reads as (nrow,), 0-row columns read as int32, addcols stores empty 1-D arrays | [casacure-unwritten-cells.md](casacure-unwritten-cells.md) | issue |
| 17 | github.com | tmolteno/casacure | No LICENSE/COPYING file in the repository or the wheel (LGPL-3.0-or-later declared) | [casacure-licence-file.md](casacure-licence-file.md) | issue |
| 18 | github.com | gaker/celestial-eop-data | build.rs runs `date -u`: the build panics on Windows without a POSIX `date`, and data_timestamp() is the build date | [celestial-eop-data-build-date.md](celestial-eop-data-build-date.md) | issue |
| 19 | github.com | dask/dask | diagnostics.ProgressBar: compute() returns up to `dt` seconds late because _finish joins a thread in time.sleep(dt) | [dask-progressbar-finish-wait.md](dask-progressbar-finish-wait.md) | issue |
| 20 | github.com | ska-sa/katdal | Release request: katdal 0.23 on PyPI fails to import ms_extra (pkg_resources) with current setuptools | [katdal-release-pkg-resources.md](katdal-release-pkg-resources.md) | issue, **optional (owner)**: a release request for a fix already on master; similar fixed-on-master items (carta-python `re.sub`, DP3 names, CASA `six`) were skipped |
| 21 | github.com | CARTAvis/carta-python | Chrome(driver_path=...) fails on Selenium >= 4.10: executable_path is no longer accepted | [carta-python-chrome-driver-path.md](carta-python-chrome-driver-path.md) | issue (repo is busy: post soon) |
| 22 | github.com | CARTAvis/carta-python | Session.close() is repeated by __del__, so an explicitly closed headless session errors at interpreter exit | [carta-python-session-del-double-close.md](carta-python-session-del-double-close.md) | issue |
| 23 | github.com | casangi/casadocs | Flux calibrator models: Stevens-Reynolds 2016 break is 11.1496 GHz, not 11 GHz; Baars entry omits its 1934-638 polynomial | [casadocs-flux-standards-1934.md](casadocs-flux-standards-1934.md) | issue (docs) |
| 24 | email / helpdesk | NRAO CASA (help.nrao.edu, login; or casa-feedback@nrao.edu) | setjy/bandpass report failures only as SEVERE log lines and return normally; gaincal K ignores minblperant; solver messages go to stdout only | [casa-silent-failures.md](casa-silent-failures.md) | helpdesk ticket; owner sends |
| 25 | email / helpdesk | NRAO CASA | casatools 6.7.6.14 manylinux_2_34 wheel does not import on Ubuntu 24.04/26.04 (bundled libssl without its libcrypto); wheel licence metadata contradicts itself | [casa-wheel-packaging.md](casa-wheel-packaging.md) | helpdesk ticket; owner sends |

Before posting:

- **gitlab.com rows 3-8:** the searches first stopped by HTTP 429 were rerun anonymously on 2026-11-12 and found no duplicate (each text's `Duplicates checked` line). Issue comments are not visible anonymously; nearest neighbour WSClean #103 (closed 2022, `-squared-channel-joining`) is cited in row 3.
- **Row 2:** git.astron.nl shows issue pages only when signed in (DP3's too returns 404 anonymously), so whether schaapcommon takes issues is checked when posting; the fallback is WSClean's tracker.
- **Rows 9-12:** run on casacore 3.8.1 (the python-casacore 3.8.1 wheel); v3.8.2 has no wheel, and the cited code is the same at master 9afc669, which is after v3.8.2. Each text says so.
- **Row 9:** casacore has no SECURITY.md and private reporting is off, and the buffer part has been public since PR #1089 (declined in 2022), so it goes in as a public issue.
