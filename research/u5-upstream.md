# U5: upstream findings prepared for filing, non-RATT included (2026-11-12)

Task U5. On 2026-11-12 the owner approved, in chat, "Report the bugs errors and fixes where you can", which widens
the reporting rule to non-RATT projects. Status: **reproduced and written; nothing posted.** This
session's permission settings refused `gh issue create`, and the coordinator then set the route: the
coordinator posts after the owner has seen the list. The list is
[upstream-issues/u5-manifest.md](upstream-issues/u5-manifest.md): 25 texts. 22 are for public trackers
(GitHub 15, gitlab.com 6, git.astron.nl 1), 2 are CASA helpdesk tickets and 1 is a note to Richard Armstrong
about Obit.

Method as U4 ([u4-upstream.md](u4-upstream.md)): latest release or default-branch head first, duplicate
search over open and closed issues and PRs/MRs, security policy checked for security-like items. Five
reproduction agents (astron, casacore, casacure, pyeco, casa), each told to post nothing. Scripts:
[u5-upstream-files/](u5-upstream-files/) (one folder per group). Logs (ignored): `outputs/u5-20261112-<group>/logs/`.
Hosts: native Windows 11 and WSL2 Ubuntu 26.04, plus the local `rang-wsclean-native:3.7` and
`rang-obit:dc26694` images. Fresh uv venvs from public PyPI on `D:\rang\scratch\u5` or `/dev/shm`, all
deleted afterwards. "Run on X" below means executed; "read at Y" means confirmed in source at that sha (rows 4, 8, 17 and 18 are source reads only). The issue or MR links are filled in by the coordinator after posting; the Target column names the tracker.

## To file (25 texts)

| # | Finding | Reproduced on | Target | Notes |
| --- | --- | --- | --- | --- |
| 1 | Obit `MFMakeResiduals` reads `dim[5]` past `dim[MAXINFOELEMDIM=5]`; MFImage CLEAN segfaults at the first residual | run on bill-cotton/Obit master dc26694 (V5: crash rc 139; patched rc 0, fluxes within 2e-4); lines 1088, 1115 re-read at dc26694 | note to Richard Armstrong (owner's choice), [obit-dconcleanvismf-dim5.md](upstream-issues/obit-dconcleanvismf-dim5.md) | his fork richarms/Obit (issues off) has the same fix, ab77437c on `fix/mfbeam-stokes-multigpu`, 2026-10-20, not on bill-cotton master; bill-cotton/Obit has issues on but none ever filed |
| 2 | schaapcommon `Fit2DGaussianCentred`: `size_t` offsets, so the fit sees the x ≥ 0, y ≥ 0 quadrant only (also the circular fit); β Jacobian sign wrong | run: built against schaapcommon 35f91f8, fits identical with the other three quadrants zeroed or set to 0.5; patched build responds. Whole box on S1 13.58″ × 9.47″ against 13.88″ × 8.34″ (G7 §13) | git.astron.nl RD/schaapcommon, patch inline | present since WSClean 3.0; WSClean master pins 35f91f8 |
| 3 | WSClean `-join-polarizations`: help and docs say sum of squares; default clean sums linearly | run on 3.7 (two-source simulation picks the linear-sum peak); read at master 486d0f5 (`subminor_loop.cc:49,179`, Radler 703c1bd) | gitlab.com aroffringa/wsclean | `-no-fast-subminor` path squares (G9 §8) |
| 4 | WSClean `CalculateMsLimits` tests the y bound with `u` | read at master 486d0f5 `msprovidercollection.cpp:28` (v3.7 `:27`) | gitlab.com aroffringa/wsclean | introduced by the v3.5 refactor (MR !717); v3.4 used v. Feeds `max_baseline`, hence the beam-fit box of row 2 |
| 5 | WSClean `-save-source-list` restrictions (channels-out > 1 needs spectral fitting; Stokes I only; niter > 0) not in help or docs | run on 3.7; read at master (`settings.cpp:378-395`) | gitlab.com aroffringa/wsclean | low priority, doc |
| 6 | AOFlagger `sumthreshold_masked` reads Lua args 4, 5 for the direction flags (checks 5, 6) | run on 3.5.0 (`(true,false)` runs both, `(false,true)` runs x only); read at master 811f8e0 `functionswrapper.cpp:319` | gitlab.com aroffringa/aoflagger | shipped strategies pass `true, true`, unaffected |
| 7 | AOFlagger `SumThresholdMissing::horizontal`: xRight on a missing sample stays in the sum; plus VerticalStacked zero padding (the y half) | run on 3.5.0: 504 of 504 cells flagged with the missing hot sample at x = 1, 2 of 504 at x = 10; padding 4 cells in 40 columns | gitlab.com aroffringa/aoflagger | affects shipped strategies; one-line fix |
| 8 | AOFlagger docs: filter "sigma" is a variance; `invert_mask` after `clear_mask` is a silent no-op | read at master 811f8e0; 3.5.0 (A-FLAG deviation 1) | gitlab.com aroffringa/aoflagger | docs |
| 9 | casacore writes uninitialised heap memory into table files: `table.fNi` gaps, `StManArrayFile::putRes` reserved arrays (read back as cell values after an ISM recreate), `MultiFile::writeHeader` (4,194,079 bytes vary), `writeRemainder` | run on python-casacore 3.8.1 wheel (casacore 3.8.1) under `MALLOC_PERTURB_`; read at master 9afc669 | github casacore/casacore | casacore 3.8.2 (latest) has no python-casacore wheel; code unchanged at master 9afc669, after 3.8.2. No SECURITY.md, private reporting off; PR #1089 (2022, declined) made the buffer part public; the text proposes zeroing tails only |
| 10 | casacore ISM: re-putting a single-row indirect array decrements its refcount below zero; file then grows (20 puts, 16 records against 10) | run on 3.8.1; read at 9afc669 | github casacore/casacore | cause differs from E5's note (`handleRemove` on the same offset) |
| 11 | casacore TiledCellStMan ranged getcol/putcol raise `TSMShape::offset` (reads `rowpos` past its end) | run on 3.8.1 | github casacore/casacore | ranged `getcol` fails too, not only `putcol` |
| 12 | casacore MemoryStMan FixedShape array column in a reopened table: `findExt` on read, SIGABRT on close | run on 3.8.1 | github casacore/casacore | zeros on reopen are documented; the abort is not |
| 13 | casacure: TiledColumnStMan accepted for a variable-shape column; tiled create with nrow > 0 fails and leaves a broken table; `getcoldesc`/`getdminfo` misreport managers; DEFAULTTILESHAPE [2,4,8] stored as [2,4,8192] | run on casacure 3.8.41 (latest), python-casacore 3.8.1 reference | github tmolteno/casacure | E2 items 1, 5 plus two new |
| 14 | casacure measures: UTC→TAI/UT1 returns the input relabelled (TAI off by 37 s, UT1 0.13 s); ITRF metres labelled rad | run on 3.8.41; read at de45b5d `measures.rs:272-274` | github tmolteno/casacure | E2 item 3 |
| 15 | casacure TaQL: BETWEEN, bare SELECT FROM, ORDERBY DESC, `rownumbers(table)` | run on 3.8.41 | github tmolteno/casacure | E2 item 6 |
| 16 | casacure never-written cells: 3-D FLAG_CATEGORY reads `(nrow,)` bool; 0-row columns read int32; `addcols` writes defined empty 1-D cells | run on 3.8.41 | github tmolteno/casacure | E2 item 7, E3 twelfth item, one new |
| 17 | casacure: no LICENSE/COPYING in the tree or the wheel | read at de45b5d; 3.8.41 wheel | github tmolteno/casacure | E2 item 8 |
| 18 | celestial-eop-data `build.rs` runs `date -u`: Windows build panics; `data_timestamp()` is the build date | read at v0.1.33 b7678d9 `build.rs:36-41`; Windows panic measured on 0.1.12 (E2), not rerun | github gaker/celestial-eop-data | crates.io stops at 0.1.12 |
| 19 | dask `ProgressBar._finish` joins a thread in `time.sleep(dt)` | run on dask 2026.8.0 (latest): dt = 20 gives 20.00 s for a 1 s task; read at main b4cc5c5 `progress.py:108-129` | github dask/dask | fix: `threading.Event` |
| 20 | katdal 0.23 (PyPI, 2024-06-28) fails at `mvftoms.py` import on `pkg_resources` | run on 0.23 with setuptools 84.2.1, Python 3.13; fixed on master 84432ef (closes #379) | github ska-sa/katdal | release request; **optional for the owner** (fixed on master, as the skipped carta-python, DP3 and CASA items are) |
| 21 | carta-python `Chrome(driver_path=...)` passes `executable_path`, gone in Selenium ≥ 4.10 | run on dev c33914d, Selenium 4.52.0: TypeError | github CARTAvis/carta-python | |
| 22 | carta-python `Session.__del__` repeats `close()` | run on dev c33914d with stubs: two calls each | github CARTAvis/carta-python | |
| 23 | CASA docs: SR2016 break at 11.1496 GHz, not 11 GHz; Baars entry omits its 1934−638 cubic | run on 6.7.6.14 (latest): 11.0 GHz uses the low piece, 2.10811 Jy against 2.11267 (0.22 %); read at casa6 90e9d3d `FluxStdsQS2.cc:202-204` | github casangi/casadocs | |
| 24 | CASA silent failures: `setjy` returns `{}` with MODEL_DATA unchanged (default PB2017 on 1934−638 without tables), unknown names 1 Jy; bandpass with a missing table returns normally; gaincal G returns a `solve_tables` entry it never wrote; K ignores `minblperant`; solver messages on stdout only; G/T drop the frequency part of `solint` without a warning | run on 6.7.6.14 on a self-built simulated MS; read at casa6 90e9d3d (`Imager.cc:5066-5076`, `Calibrater.cc:3852-3861`, `VisCalSolver2.cc:265,466`) | NRAO helpdesk (login) or casa-feedback@nrao.edu | CASA has no public tracker; owner sends. Also notes casatasks 6.7.6.14 no longer imports from a fresh install (`six`, fixed on master 4fce2abe, unreleased) |
| 25 | CASA wheels: manylinux_2_34 bundles AlmaLinux 9's libssl 3.2.2 without its libcrypto (fails on Ubuntu 24.04 and 26.04); licence metadata contradictory, no licence file, stale classifiers | run on 6.7.6.14 (Ubuntu 24.04.5 container, Ubuntu 26.04) | NRAO helpdesk | cause corrected from O-CASA's note: not Ubuntu-24-specific |

## Skipped, with reasons

| Item | Reason |
| --- | --- |
| zarr/numcodecs pickle filter | already fixed: GHSA-jqc8-qjfv-5m6r (2026-10-20), numcodecs 0.15.2/0.16.6/0.17.1 refuse it; zarr 3.4.2 adds opt-in `allow_unsafe_pickle_decode`. Run: 0.15.1 unpickles, 0.15.2 raises |
| blosc partial-chunk reads; LUNO chunk layout | feature request; data layout, not software |
| WSClean wide natural-weighting beam (DF5-O 4) | not the quadrant bug (that moves axes 1-14 %, this is 60 %): the natural PSF plateau dominates any unit-peak least-squares fit in the box; by design |
| WSClean read-only MS opened read/write (DF5-O 1) | by design: fails only with `-no-reorder` and `-mgain` < 1, where MODEL_DATA is the only place to keep the model; run on 3.7, 5 arms |
| WSClean `-store-imaging-weights` double write; `-j 4` not bit-reproducible; log does not state precision; padding 1.2 aliasing; `-threshold` deprecation | performance only; thread-order rounding; cosmetic; documented behaviour (×2) |
| DP3: more than one FIELD row refused | by design, explicit error (`MsReader.cc:771` at v6.6) |
| DP3: NUL-padded antenna names | already fixed: schaapcommon 35d32ee1 (2026-10-02), in DP3 master f65029b2 today, not released yet |
| DP3: GLib and measures for a DI applycal | packaging: libglib is on the manylinux2014 allow-list; MsReader looks up the observatory for non-LOFAR telescopes |
| KERN `aoflagger` module path | KERN is the owner's own packaging, not upstream |
| casacore `TiledCellStMan::setShape` with unflushed tiles | by design: a shape change discards the old values; only unreferenced bytes differ |
| casacore `table.dat` rewrite per lock release; bucket-cache scratch bytes; MultiHDF5 timestamps; CASA cal-table group names | write cost, no correctness issue; deterministic unreferenced bytes of the same table; libhdf5 behaviour; CASA's, not casacore's |
| python-casacore N-D string `getcell` dict, uChar→uint16, Int64 keywords, DEFAULTTILESHAPE | deliberate (built in `PycArray.cc`, tested in `tConvert.py`); type mapping; not verified; round-trips raw |
| casacure FixedShape from a given shape | fixed in 3.8.38 (8018519) |
| casacure SIGBUS on a file truncated after open | mmap semantics (exit 135); not security-like |
| casacure Windows/macOS wheels untested in CI | opinion |
| casacure `addcols` rebuilds the StandardStMan | documented (#22, 3.8.35 CHANGELOG); could go in as an enhancement if the owner wants |
| casacure TiledDataStMan, MemoryStMan, MultiFile | duplicate #18 (open); #33, #34 closed (MultiFile error now names the container) |
| katsdptelstate `[rdb]` needs sdist-only python-lzf, rdbtools | third-party packages; builds and round-trips on Linux |
| carta-python PyPI name `carta` | duplicate: #143 checklist, open PR #184 |
| carta-python `re.sub` count positional | fixed on dev c174344 (#161), unreleased |
| carta-python `preexec_fn=os.setpgrp` | POSIX only by its classifiers; CARTA has no Windows build |
| CARTA backend `openFile` absolute directory | by design: paths are relative to the backend's root (`Casacore.cc:24-30`, carta-python docstrings) |
| CARTA image does not enable scripting; SwiftShader | scripting is opt-in (`enable_scripting = false`); headless-Chrome matter |
| cityhash: no cp314 wheels | duplicate: escherba/python-cityhash#100 (open); master has 3.14 support |
| wgpu DX12 `SHADER_F64`; naga rejects `active` | documented (Vulkan only, `features.rs`); `active` is a WGSL reserved word |
| maturin launcher on Windows; uv "too many temporary files" | Windows locks running executables (near-duplicate uv #11134); cause unclear, worked around |
| CASA: seconds `solint` drift | not reproducible on a regular 8 s grid (16 s lands on pair centres; 12 s is a 12 s grid) |
| CASA: float32 compiled coefficients; Df linear approximation; B/Df interpolation; no Windows wheels; casaconfig SEVERE notices | by design or documented; opinion |
| losoto, ducc0, JAX and OpenBLAS thread pools, Crystalball licence, katbeam, katsdpsigproc, SARAO holography, wgpu memory query | no defect; documented defaults; known behaviour handled on rang's side; informational |
| ESO137 / LUNO data notes (C1, B1-2, B1-3) | data, not software |

New observations made while reproducing, not written up: WSClean's `-reorder` help says reordering happens only in
channel-imaging mode, but 3.7 also reorders for `-mgain` ≠ 1, four or more polarisations, BDA and facets
(`settings.cpp` `determineReorder`); python-casacore `tablehelper._format_cell` discards its `reshape` result;
Ubuntu casacore-data 20250826 now triggers "TAI_UTC seems out-of-date" in CASA.

## Follow-ups on U1-U4

Checked 2026-11-12 (`gh search issues/prs --author gijzelaerr`, every comment read). No reply from us is due:

- casacure: all U4 filings fixed and released in 3.8.38 (#24 and #28 by 8018519, #25 by our PR #27 merged as f1e7454,
  #29 by f75c21c); #26 split by the maintainer into #31-#35, all closed. Rerun of the U4 scripts on 3.8.41: still fixed.
- QuartiCal #452 fixed in #456, our test comment already posted; #453 acknowledged; no 0.2.8 release yet.
- pfb-imaging #390, #391: the maintainer will close them with 0.1.0 (latest on PyPI 0.0.11).
- Tricolour #111 closed by #112; #114 merged 2026-11-05; #110, #113, #115 wait for 0.5.0 (latest 0.2.1).
- purr PR #40 and caracal #1708: only the CI bot's "verify this patch" (admin action, not ours).
- No comments on tigger-lsm #55-#57, crystalball #83, killMS #23-#28, DDFacet #73-#77, stimela #619/#620.

## Timings

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-11-12 | dask ProgressBar repro, dt = 20 | 1 s task | 20.4 s | – | native Windows; venv + install 6.4 s |
| 2026-11-12 | katdal 0.23 venv + install; `mvftoms.py --help` | – | 17.7 s; 0.55 s | – | WSL |
| 2026-11-12 | casacure + python-casacore venvs; all probes | – | 4.1 + 6.3 s; 0.01-0.12 s each | – | WSL `/dev/shm` |
| 2026-11-12 | python-casacore 3.8.1 venv; `MALLOC_PERTURB_` sets (fNi, MultiFile, MultiFile 4 KiB) | – | 7.4 s; 6.7, 4.3, 3.5 s | – | WSL; casacore blob-less clone 11.3 s |
| 2026-11-12 | casatools/casatasks 6.7.6.14 venv, 2_34 and 2_28 wheels | – | 22.2, 21.3 s | – | WSL |
| 2026-11-12 | `repro_casa.py` (simulated MS + all CASA probes) | self-built MS | 8.2, 8.3 s | 274, 272 MB | WSL, two runs |
| 2026-11-12 | schaapcommon beam-fit repro, compile + run | Docker `rang-wsclean-native:3.7` | 5 s each (2) | – | |
| 2026-11-12 | WSClean 3.7 read-only MS runs | 64 MB MS, 5 arms | 6 s, 12 s | – | Docker |
| 2026-11-12 | AOFlagger 3.5.0 probes | synthetic | about 1 s each | – | |

No job needed the heavy lock (all under a minute, under 1 GB); one CASA attempt queued behind an exclusive
job and was stopped.

## Kept and deleted

Kept: texts in `research/upstream-issues/` (25 plus the manifest), scripts in `research/u5-upstream-files/`
(169 KB), logs in `outputs/u5-20261112-{astron,casa,casacore,casacure,pyeco}/logs/` (ignored, 450 KB).
Deleted: every venv and clone under `D:\rang\scratch\u5` and `/dev/shm`.

## For the coordinator

- Nothing is posted. Post from [the manifest](upstream-issues/u5-manifest.md) after the owner has seen it; rows 1,
  24 and 25 go by email or helpdesk and the owner sends them; rows 3-8 need the rate-limited GitLab duplicate
  searches rerun first.
- Obit: Richard Armstrong already has our fix in his fork (ab77437c); the note confirms it and asks about its
  route to Bill Cotton's master.
- casacore row 9 goes in public: no private route exists and the buffer part has been public since #1089.
- Lines for `research/upstream-notes.md`: "Upstream status after U5 (2026-11-12; `u5-upstream.md`): 25 texts
  prepared, none posted; manifest `upstream-issues/u5-manifest.md`; all U4 casacure filings fixed in 3.8.38."
- STATE paragraph: "U5, upstream findings prepared (2026-11-12; reproduced, not posted; [u5-upstream.md](u5-upstream.md)).
  The owner's approval widened reporting to non-RATT projects. 25 texts (Obit note to Richard Armstrong, schaapcommon,
  WSClean, AOFlagger, casacore, casacure, celestial-eop-data, dask, katdal, carta-python, casadocs, two CASA helpdesk
  tickets), each reproduced on the latest release or confirmed at the default-branch head, the rest of the non-RATT
  backlog skipped with reasons. The coordinator posts from the manifest after the owner has seen it."
- Plan line: "U5 done 2026-11-12 (`u5-upstream.md`): texts and manifest ready; posting is the coordinator's."
- Not run: the full `python -m rang.check` (the commit adds research files only). Ran ruff check and ruff format on
  `u5-upstream-files/`, `py_compile` on its Python scripts, and the docs tests (13 passed; one unrelated failure,
  `test_e5_decisions::test_a_run_without_run_stages_runs_the_whole_chain`, an extension ImportError from the main
  checkout's venv not built for this worktree).
