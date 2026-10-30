# Radio-astronomy software ecosystem survey for rang (KERN, CASA, CARTA)

Big plan side task, branch `ecosystem-survey` from `5965d37`, 2026-10-30.
Read-only survey: no core code, nothing installed except the worktree's own
check venv. It covers every KERN-10 package, the MeerKAT tools that are not
in KERN, CASA 6.7 and CARTA 6.0. For each tool it gives a verdict for rang
and lists the file formats that the DF-IO decision must cover.

The earlier surveys are not repeated:
- [literature-2024-2026.md](literature-2024-2026.md) covers papers and
  release news;
- [ddfacet-feasibility.md](ddfacet-feasibility.md) covers DDFacet/killMS
  internals;
- `casacure-evaluation.md` (branch `e2-casacure`, protocol frozen, not
  measured) covers casacure;
- [upstream-notes.md](upstream-notes.md) covers the RATT observations.

Where those files already settle a point, this note links to them.

## Method, sources and conventions

- **KERN-10 package list:** the Launchpad PPA source index
  <https://ppa.launchpadcontent.net/kernsuite/kern-10/ubuntu/dists/noble/main/source/Sources.gz>
  (38 source packages, 105 amd64 binary packages), cross-checked against
  <https://kernsuite.info/packages/> (KERN-10 = Ubuntu 24.04 Noble; KERN-9 =
  22.04 Jammy) and the GitHub org `kernsuite-debian` (165 packaging repos,
  listed with `gh api orgs/kernsuite-debian/repos`). Licences for the KERN
  rows are from upstream LICENSE files where present, else from the first
  upstream stanza of `kernsuite-debian/<pkg>/debian/copyright` (the `MIT`
  stanzas in those files cover `debian/*` packaging, not upstream).
- **Upstream metadata:** `gh api repos/<owner>/<repo>` (licence SPDX,
  language, last push), `releases/latest` or tags; PyPI JSON
  (`https://pypi.org/pypi/<name>/json`, latest version, first upload date of
  that version, licence fields, wheel platforms); GitLab API for
  gitlab.com (AOFlagger, WSClean, IDG, SoFiA-2) and git.astron.nl (DP3,
  EveryBeam).
- **Documentation:** casadocs.readthedocs.io (stable = CASA 6.7),
  cartavis.org, carta-python.readthedocs.io, katdal.readthedocs.io, the
  CARACal repository (`caracal/workers/*.py`, `schema/crosscal_schema.yml`),
  and a third-party GitHub mirror of NRAO's casa6 tree
  (`dic-case-studies/casa6`, last pushed 2023-01-20) for CASA source
  headers and the calibration-table schema.
- **All sources were accessed 2026-10-30.** Dates are release dates unless
  marked "push" (last commit pushed to the default branch, from the GitHub
  API). Where the GitHub release, the PyPI version and the KERN version
  disagree, each is given.
- **Unverified** marks a statement taken from memory or from a secondary
  source that was not checked against the primary source.
- **PyPI name collisions found and excluded:** `sourcery` 1.46.0 (an AI
  refactoring tool), `brats` 0.1.14 (Apache, not Harwood's BRATS), `wsclean`
  1.0.0 (2022, not WSClean), `pyxis` 0.2.1 (2011, not ratt-ru/pyxis), and
  `carta` 1.3.3 (author "JaySec", not CARTAvis; carta-python is not on PyPI
  according to its own docs).

**Verdict key.**

| Verdict | Meaning |
| --- | --- |
| PORT | Reimplement in the core. Requires the archive or oracle that validates it. |
| DEPEND | Use as a library. The licence must allow it in a GPL-3-or-later work (LGPL, MIT, BSD, Apache, MPL-2, GPL-3, GPL-2-or-later), and the package must be usable on rang's platforms or as an optional extra. |
| ORACLE | Run only in a pinned container to produce reference outputs. Its licence does not matter. |
| FORMAT | Read and write its files, per the DF-IO decision. |
| IGNORE | Not used, with the reason. |

GPL-2-only code cannot be copied into rang. Reimplementation from the
algorithm is fine. PORT and ORACLE do not depend on the licence.

## Summary

1. **KERN-10 is small.** It has 38 source packages (KERN-9 listed 37)
   under a different mix: CubiCal, PyBDSF, Owlcat, Pyxis and
   21cmfast are gone; CASA (casalite), katsdptelstate, numba and
   ska-sdp-func are new. Most of the RATT stack (QuartiCal, Tricolour,
   dask-ms, codex-africanus, DDFacet, killMS, CARACal) is not in KERN; it
   comes from PyPI.
   - What KERN-10 is good for in rang: a **ready oracle base image**. It
     ships WSClean 3.7, AOFlagger 3.5.0, IDG 1.2.0, casacore 3.7.1,
     python-casacore 3.7.1, MeqTrees 1.11/Cattery 1.8.0, katdal 0.23,
     Obit and CASA 6.7.3 (casalite) as Ubuntu 24.04 debs. That is the
     DF0 container without building anything.
2. **Most of the ecosystem is ORACLE for rang, not DEPEND.**
   - Licence is not the reason. GPL-3 tools could be DEPENDed.
   - Platform is the reason. Almost nothing outside casacure, ducc0 and
     pure-Python packages ships Windows wheels, and rang's live path must
     run natively on Linux, macOS and Windows (X1).
   - The DEPEND list is short:
     - casacure (LGPL-3+, all three platforms; E2 decides);
     - katdal + katsdptelstate (BSD-3, pure Python), as an optional
       `[meerkat]` extra for L3;
     - katbeam (BSD-3, already used);
     - ducc0 (GPL-2+, wheels on all three platforms), as a test-time
       oracle that happens to be a wheel;
     - carta-python (GPL-3), as an optional notebook extra.
3. **CARACal's cross-calibration is CASA, not QuartiCal.** CARACal's
   `crosscal_worker.py` calls `casa_setjy`, `casa_gaincal`,
   `casa_bandpass`, `casa_fluxscale` and `casa_applycal`; `polcal_worker.py`
   calls `casa_polcal`. QuartiCal/CubiCal enter only in self-calibration.
   - So the "matched full CARACal pipeline baseline" in the big plan
     (needed if a campaign turns positive) needs a CASA oracle container.
   - So does any claim that rang's DI calibration matches the MeerKAT
     state of practice.
4. **Flux standard for PKS 1934−638.** In CASA, 1934−638 is covered by
   Stevens-Reynolds 2016 (a single-source standard: Reynolds below 11 GHz,
   Stevens above) and by Perley-Butler 2010, Perley-Taylor 99/95, Perley 90
   and Baars. It is **not** in Perley-Butler 2013 or 2017. The task
   brief's "Perley-Butler 2017 … for 1934" is therefore wrong for CASA.
   - Rang's 14.96 Jy point and the Reynolds polynomial in
     [flagging.md](flagging.md) are the same family as Stevens-Reynolds
     below 11 GHz.
   - Recommendation: PORT the flux-standard evaluation (a few
     polynomials), with `setjy` as the oracle.
5. **CARTA is not a replacement for the notebook plots.** CARTA 6.0
   (GPL-3, 2026-06) has no native Windows build. carta-python needs a
   running backend with `--enable_scripting` plus headless Chrome for
   non-interactive sessions.
   - Keep matplotlib as the default.
   - Add an optional "open in CARTA" helper for large images and cubes.
   - Treat CARTA's IDIA HDF5 schema 0.3 as a write-only FORMAT candidate,
     after FITS.
6. **Top gaps by value for the plan:**
   - B1's beam (holography cubes plus katbeam, already decided);
   - flux standards (PORT, small);
   - CASA caltable read/write (FORMAT, via casacure);
   - katdal/MVF access for L3 (DEPEND now, PORT later);
   - deconvolution (DF5; WSClean and pfb-imaging as oracles);
   - DD calibration (DF4; killMS/DDFacet as oracles);
   - source finding (ORACLE only: PyBDSF);
   - polarisation calibration (ORACLE: CASA polcal; PORT only if a
     protocol needs it).

   The ranked list is in section 5.

## 1. Every KERN-10 package

KERN-10 versions are from the PPA `Sources` index. "Upstream" is the latest
upstream release on 2026-10-30. KERN status: **10** = in KERN-10.

### 1.1 Data access and formats

| Package (KERN-10) | Purpose | Upstream repo | Licence | Lang | Upstream latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| casacore 3.7.1 | CASA table system, MS, measures, images, FITS | github.com/casacore/casacore | LGPL-2.0 ("GNU Library GPL v2", LICENSE file; GitHub reports NOASSERTION) | C++ | v3.8.2, 2026-09-29; push 2026-10-28 | casacore (NRAO/ASTRON/CSIRO) | FORMAT. Read/write MS, caltables and CASA images through casacure (E2) or task E's reader. casacore itself is the ORACLE via python-casacore. |
| python-casacore 3.7.1 | Python bindings to casacore | github.com/casacore/python-casacore | LGPL-3.0 | Python/C++ | v3.8.1, 2026-06-26; wheels Linux only | casacore | ORACLE. Already the comparator for task E. Not DEPEND: no Windows/macOS wheels. |
| casacore-data 20250826 | Measures data (IERS, ephemerides, observatories) | github.com/kernsuite-debian/casacore-data | data files (licence not checked, unverified) | data | KERN snapshot 2025-08-26 | KERN | DEPEND (data), only if the core needs UT1/polar motion. casacure carries a measures subset (E2 reports it). |
| casarest 1.9.2 | Standalone imager/calibrater cut out of old CASA | github.com/casacore/casarest | GPL-3.0 (GitHub); Debian copyright GPL-2.0+ | C++ | v1.10.2, 2026-05-01 | casacore | IGNORE. Superseded by WSClean and CASA for every use rang has. |
| makems 1.5.6 | Create empty MSs from a template (LOFAR heritage) | github.com/ratt-ru/makems | GPL-2.0+ (Debian copyright; no LICENSE file in repo) | C++ | v1.5.6, 2025-08-08 | RATT | IGNORE. The simulated DF field MS is written by rang/casacure (see simms, section 2). |
| katdal 0.23 | MeerKAT MVFv4 data access (RDB + S3 chunk store), `mvftoms.py` | github.com/ska-sa/katdal | BSD-3-Clause | Python | PyPI 0.23, 2024-06-28; push 2026-10-22 (no newer tag) | SARAO | DEPEND now (optional `[meerkat]` extra, L3); PORT the MVF reader later (section 5.3). |
| katpoint 0.10.2 | Coordinates, targets, antenna, pointing and delay models | github.com/ska-sa/katpoint | BSD-3-Clause | Python | PyPI 0.10.3, 2026-09-22 | SARAO | DEPEND for B1 (MeerKAT pointing-model terms and target conventions). PORT only the terms B1 needs. |
| katsdptelstate 1.0.0 | Telescope-state store (Redis/RDB) read by katdal | github.com/ska-sa/katsdptelstate | BSD-3-Clause | Python | PyPI 1.0.0, 2025-07-07 | SARAO | DEPEND (with katdal). |
| rdbtools 0.1.15 | Redis RDB file parser (katsdptelstate dependency) | (no Homepage in the KERN record) | not declared in the KERN record (unverified) | Python | – | – | IGNORE (transitive). |
| katversion 1.3 | Version strings for SARAO packages | github.com/ska-sa/katversion | BSD-3-Clause | Python | push 2026-02-20 | SARAO | IGNORE (transitive). |

### 1.2 Calibration, simulation and modelling

| Package | Purpose | Upstream | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| meqtrees-timba 1.11 | Measurement-equation tree engine (C++ kernel and Python front end) | github.com/ratt-ru/meqtrees-timba | GPL-2.0+ (Debian copyright) | C++/Python | v1.11, 2026-01-08 | RATT | ORACLE only. CARACal's `meerkat_skymodel: true` predicts the 1934 field lsm through MeqTrees (`crosscal_schema.yml`). This is the reference prediction path for L1-M. |
| meqtrees-cattery 1.8.0 | Calibration/simulation frameworks on Timba (Calico, Siamese, FITS-beam interpolation, `pybeams_fits`) | github.com/ratt-ru/meqtrees-cattery | GPL-2.0+ (Debian copyright; GitHub NOASSERTION) | Python | GitHub v1.8.0rc3 2026-01-07; PyPI 1.8.0, 2026-03-17 | RATT | ORACLE (DF3's FITS-beam path and the CARACal lsm prediction). Not PORT: B1 already has a beam path. |
| obit 27JUL20a | Bill Cotton's imaging/calibration package (AIPS heritage) | c6.nrao.edu/~bcotton/Obit.html | GPL-2.0+ (Debian copyright) | C/Python | KERN snapshot 2020-07-27 | NRAO (individual) | ORACLE, conditional. SARAO's continuum imaging pipeline is Obit-based (`ska-sa/katsdpcontim`, Docker builds of AIPS and Obit, push 2026-10-22), so archive-produced MeerKAT images come from Obit. Use only if B1 compares against SARAO's archive images. |
| apsynsim 2.5b | Teaching simulator for aperture synthesis | launchpad.net/apsynsim | GPL-3+ (Debian copyright) | Python | – | individual (I. Martí-Vidal) | IGNORE (teaching). |
| ska-sdp-func 1.2.2 | SKA SDP processing-function library (C/C++/CUDA with Python wrappers) | gitlab.com/ska-telescope/sdp/ska-sdp-func (GitHub mirror ska-telescope/ska-sdp-func, push 2025-03-05) | BSD-3-Clause | C++/CUDA | KERN 1.2.2; current GitLab release not checked (unverified) | SKAO | IGNORE for now. Its contents (reportedly gridders, DFT, RFI and phase-rotation kernels; unverified) are BSD-3, so they may be read and ported freely if DF1/X2 need a second GPU reference. |

### 1.3 Flagging

| Package | Purpose | Upstream | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aoflagger 3.5.0 | SumThreshold RFI flagger (Lua strategies), AOQuality statistics, Python bindings | gitlab.com/aroffringa/aoflagger | GPL-3.0 | C++ | v3.5.0, 2026-01-26; develop push 2026-10-07; PyPI `aoflagger` 3.5.post0 (Linux wheels) | ASTRON / A. Offringa | ORACLE. It is the original SumThreshold, and CARACal's `autoflagger` cab runs it. Use it as a second reference for the task D port on the archived inputs. Not PORT: rang already ports Tricolour's SumThreshold. |

### 1.4 Imaging

| Package | Purpose | Upstream | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wsclean 3.7 | Wide-field imager: w-stacking/wgridder/IDG/w-towers, multiscale, facets | gitlab.com/aroffringa/wsclean | GPL-3.0-or-later | C++ | v3.7, 2026-02-16; push 2026-10-30 | ASTRON / A. Offringa | ORACLE (tasks B, C, I already; DF1, DF5, DF6). Not DEPEND: not a library on Windows. |
| idg 1.2.0 | Image-domain gridding (CPU/CUDA) | gitlab.com/astron-idg/idg | GPL-3.0 | C++/CUDA | tag 1.3.0, 2026-04-02 (the GitLab "release" record still says 0.7, 2020) | ASTRON | ORACLE for DF6 only, through WSClean `-use-idg`. |

### 1.5 Sky models, viewers and logs

| Package | Purpose | Upstream | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tigger-lsm 1.8.0 | Local sky model library: `.lsm.html`, Tigger ASCII, NEWSTAR, BBS conversions (`tigger-convert`) | github.com/ratt-ru/tigger-lsm | GPL-2.0+ (Debian copyright; no LICENSE file in repo) | Python | v1.8.0, 2025-04-01; push 2026-08-01 | RATT | FORMAT. PORT a reader/writer for `.lsm.html` and Tigger ASCII; `tigger-convert` is the round-trip oracle. CARACal's 196-component 1934 model is an `.lsm`. |
| tigger 1.6.1.1 | PyQt sky-model/FITS viewer | github.com/ratt-ru/tigger | GPL-2.0+ (Debian copyright) | Python | v1.6.1.1, 2022-06-06; push 2023-06-15 | RATT | IGNORE (desktop GUI; CARTA covers viewing). |
| kittens 1.4.6 | Utilities shared by Purr/Tigger/MeqTrees | github.com/ratt-ru/kittens | GPL-2.0 | Python | v1.4.6, 2022-01-04 | RATT | IGNORE (transitive). |
| purr 1.5.3 | Data-reduction logbook | github.com/ratt-ru/purr | GPL-2.0 | Python | v1.5.3, 2022-01-04 | RATT | IGNORE. Rang's research notes and archives are its log. |
| pyqt-qwt 1.9.0 | Qwt widgets for PyQt5 (Tigger/MeqTrees GUIs) | github.com/GauiStori/PyQt-Qwt | GPL-2 family (Debian; unverified) | C++/Python | – | other | IGNORE (transitive). |

### 1.6 Pipelines and orchestration

| Package | Purpose | Upstream | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| stimela 2.1.2.1 | Stimela 2 recipe/cab framework (CARACal's engine) | github.com/caracal-pipeline/stimela | GPL-2.0-only (PyPI `license_expression`) | Python | v2.1.4, 2026-04-15 (KERN lags one release); push 2026-10-22 | RATT / caracal-pipeline | ORACLE runner. The frozen QuartiCal/Tricolour recipes already ran under it (history/). Not DEPEND: GPL-2.0-only, Python < 3.14 (stimela#619 filed). |
| scabha 2.1.0rc1 | Stimela 2 helper library (config, cab I/O) | github.com/ratt-ru/scabha (archived 2021); scabha2 archived 2024 | GPL-2.0 | Python | KERN 2.1.0rc1 | RATT | IGNORE (transitive of Stimela). |

### 1.7 Spectral-line and other science

| Package | Purpose | Upstream | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| brats 2.6.3 | Spectral-ageing fits of radio lobes | github.com/JeremyHarwood/BRATS | GPL-3.0 | C | v2.6.3, 2024-05-16 | individual | IGNORE (science product, not calibration). |
| tirific 2.3.11 | Tilted-ring HI kinematic modelling | github.com/gigjozsa/tirific | MIT | C | 2.3.11, 2019-10-31; push 2025-10-06 | individual (G. Józsa, RATT) | IGNORE (HI science). |

### 1.8 Infrastructure packaged for the above

All IGNORE for the core. Each is a transitive dependency of a tool above,
or of TraP, and rang does not need it directly.

| Package | Purpose | Licence | Needed by |
| --- | --- | --- | --- |
| casaconfig 1.3.1 (upstream v1.5.2, 2026-10-01) | CASA runtime data fetcher | Apache-2.0 | CASA; only for a CASA oracle container |
| casalite 6.7.3.21 | Monolithic CASA tarball as a deb | GPL-2.0+ (Debian copyright) | **ORACLE base** for the CASA container (section 3) |
| numba 0.64.0, llvmlite 0.46.0 | JIT | BSD-2 | QuartiCal, Tricolour, codex-africanus. The live rang path no longer needs Numba (P6/P8). |
| sharedarray 3.2.4 | POSIX shared-memory NumPy arrays | GPL-2 (Debian) | DDFacet, killMS |
| polygon3 3.0.8 | 2D polygon operations | not declared (Debian copyright unknown) | DDFacet/killMS facet tessellation (unverified) |
| cityhash 0.4.9 | CityHash/FarmHash bindings | MIT (upstream; GitHub NOASSERTION) | not determined (unverified) |
| pyslalib 1.0.10 | SLALIB wrappers | GPL-2.0+ | MeqTrees, Owlcat (unverified) |
| pymonetdb 1.9.0 (upstream 1.9.1, 2026-07-09) | MonetDB client | MPL-2.0 | TraP transient pipeline |
| tokenize-rt 6.2.0, unittest-xml-reporting 4.0.0 | build/test helpers | MIT / BSD (unverified) | packaging only |

### 1.9 KERN history: packages no longer in KERN-10

Sources: kernsuite.info's KERN-9 tab and the `kernsuite-debian` repos with
their last push.

| Package | KERN status | Where it is now | Rang verdict (details in section 2) |
| --- | --- | --- | --- |
| cubical | KERN-9 only (packaging push 2024-04) | PyPI 1.6.4 (2023-06-06), repo push 2026-10-29 | ORACLE (CARACal selfcal/ddcal still call it) |
| pybdsf | KERN-9 only (2024-09) | PyPI `bdsf` 1.14.1 (2026-06-12), wheels Linux/macOS | ORACLE (source finding) |
| owlcat | KERN-9 only (2024-04) | PyPI 1.8.1 (2026-03-18) | IGNORE (MS utilities) |
| pyxis | KERN-9 only (2024-04) | GitHub v1.7.7, 2025-12-11 | IGNORE (legacy scripting) |
| 21cmfast, omegaconf, future-fstrings | KERN-9 only | PyPI | IGNORE |
| ddfacet | packaging repo only, push 2019-01 | PyPI 1.0.0.0, 2026-06-23 | ORACLE ([ddfacet-feasibility.md](ddfacet-feasibility.md)) |
| dp3 | packaging repo only, 2022-09 | ASTRON v6.6, 2026-05-07; PyPI `dp3` 6.6.0 Linux wheels | ORACLE |
| everybeam | packaging repo only, 2024-01 | ASTRON v0.9.0, 2026-09-24; PyPI 0.9.1 Linux wheels | IGNORE for MeerKAT (no MeerKAT element model checked; unverified) |
| losoto | packaging repo only, 2021-02 | PyPI 2.7.1, 2026-04-29 | FORMAT (H5parm) |
| lsmtool | packaging repo only, 2022-05 | PyPI 1.9.0, 2026-09-25 | IGNORE (BBS sky-model tool; GitHub path 404, PyPI date only) |
| carta, carta-backend, carta-frontend, carta-casacore | packaging repos only, 2021 | CARTA 6.0.0 (section 4) | ORACLE/viewer |
| codex-africanus | packaging repo only, 2020-05 | PyPI 0.4.5, 2026-10-09 | already PORTed (predictor) |
| montblanc | packaging repo only, 2017-11 | PyPI 0.7.4, 2026-01-09 | IGNORE |
| simms | packaging repo only, 2021-01 | PyPI 3.0.2, 2026-07-27 | ORACLE for the empty-MS geometry of the simulated field |
| sourcery | packaging repo only, 2020-06 | GitHub `ratt-ru/sourcery` 404; PyPI name taken by an unrelated tool | IGNORE (unmaintained) |
| karma (kvis) | packaging repo only, 2021-02 | unmaintained (Gooch, ATNF) | IGNORE (CARTA replaces kvis) |
| sagecal, oskar, pymoresane, msutils, dysco, aartfaac2ms, chgcentre, rmextract, lofar, prefactor, tkp, … | packaging repos only, 2018–2021 | various | IGNORE. Not MeerKAT-L-band relevant, or superseded. OSKAR 2.13.0 (BSD-3, 2026-07-23) is noted as a possible second simulator. |

The pulsar, SETI and FRB packaging repos (dspsr, psrchive, presto,
heimdall, turbo-seti, …; last pushed 2018–2019) are out of scope. All are
IGNORE.

## 2. Beyond KERN: the MeerKAT tools that matter

The upstream metadata comes from the GitHub API and PyPI JSON, read
2026-10-30. "Py" is the `Requires-Python` upper bound where one is set;
it matters for rang's 3.10–3.14 matrix.

### 2.1 Data access and formats

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| dask-ms | xarray/dask datasets over MS, zarr and parquet; QuartiCal's I/O | BSD-3 (LICENSE file; GitHub NOASSERTION; PyPI licence field empty except BSD-3 expression) | Python | 0.2.32, 2026-05-18; push 2026-10-20; Py < 3.14 | RATT/SARAO | FORMAT (its zarr export is what the core's ingest reads). Ingest already PORTed (tasks G and E). |
| xarray-ms | xarray backend presenting an MS as MSv4-like datasets/datatree | BSD-3 (LICENSE file; GitHub NOASSERTION) | Python | 0.5.13, 2026-10-20 | RATT/SARAO | IGNORE now. Watch: it is the RATT route to MSv4. |
| arcae | Arrow bindings to casacore; multi-threaded MS reads | BSD-3 | C++/Python | 0.5.8, 2026-10-20; wheels Linux/macOS | SARAO (moved to `ska-sa/arcae`) | IGNORE. casacure (E2) covers the same need natively, with Windows. |
| xradio | NRAO's MSv4 (zarr) schema and converters | BSD-3 | Python | v1.3.0, 2026-10-16; push 2026-10-29 | NRAO (casangi) | FORMAT candidate (MSv4 zarr, "future MS-free interchange"; literature scan section 6). CARTA 6.1 plans xradio-image zarr support (section 4). |
| casacure | Pure-Rust casacore tables, MS, TaQL subset, measures subset | LGPL-3.0-or-later (Cargo.toml) | Rust | crate/PyPI 3.8.35, 2026-10-21; wheels Linux/macOS/Windows | individual (T. Molteno) | DEPEND, pending E2. It is the only MS library with Windows wheels. |
| xova | MS averaging (time/channel, BDA) into a new MS | BSD-3 | Python | 0.1.2, 2022-10-05 | RATT | IGNORE (unmaintained; the brief lists it as QA but it is an averager). |

### 2.2 Calibration

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| QuartiCal | DI/DD Jones solver: complex, diag, phase, amplitude, delay, TEC, RM, crosshand_phase, leakage, feed_flip, parallactic_angle, rotation terms (`quartical/gains/*`) | MIT | Python/Numba | v0.2.7, 2026-06-12; push 2026-10-30; Py < 3.14 | RATT | PORTED (complex 2×2, bit-exact). FORMAT: gain zarr store. The pol terms (crosshand_phase, leakage) are the nearest MIT-licensed polarisation reference (section 5). |
| CubiCal | Older complex-optimisation Jones solver; CARACal's default selfcal/DD solver | GPL-2.0 (GitHub) vs GPLv3 (PyPI classifier): **conflict** | Python/Cython | 1.6.4, 2023-06-06; push 2026-10-29 | RATT | ORACLE only, for a CARACal-matched selfcal baseline. Not DEPEND: licence ambiguous, Python 2-era build. |
| killMS | DD calibration (CohJones/KAFCA) with DDFacet prediction | GPL-2.0 (headers GPL-2-or-later per [ddfacet-feasibility.md](ddfacet-feasibility.md)) | Python/C | 3.3.0, 2026-01-29; Py < 3.13 | saopicc | ORACLE (DF4). FORMAT: npz solutions. |
| DP3 (DPPP) | LOFAR streaming preprocessing; DDECal (scalar/diag/full-Jones, multi-direction); writes H5parm | GPL-3.0 | C++ | v6.6, 2026-05-07 (git.astron.nl; the GitHub mirror's "v5.0, 2020" release is stale); PyPI 6.6.0 Linux wheels | ASTRON | ORACLE (DDECal as a second DD reference, literature scan section 6). FORMAT via H5parm. |
| losoto | H5parm solution inspection, smoothing, plotting | GPL-3.0-or-later | Python | 2.7.1, 2026-04-29 | LOFAR community (F. de Gasperin) | FORMAT (H5parm, the lingua franca of DP3, WSClean `-apply-facet-solutions` and facetselfcal). DEPEND would be legal but pulls in PyTables. PORT the H5parm subset instead. |
| facetselfcal (`rvweeren/lofar_facet_selfcal`) | DI/DD selfcal driver over DP3/WSClean; claims MeerKAT support | **no licence file or licence field found** (pyproject version 21.0.0): all rights reserved by default (unverified legal reading) | Python | no releases; push 2026-10-30 | individual (R. van Weeren) | ORACLE only, for DD selfcal comparisons. Its existence argues against a new DD selfcal driver in rang. |
| katsdpcal | MeerKAT SDP real-time calibration pipeline (K, B, G on calibrator scans; solutions stored in telstate and archived as `sdp.cal` streams) | BSD-3 | Python | no PyPI; push 2026-10-28 | SARAO | ORACLE and reference. Its solutions arrive with every MVF dataset (via katdal's calibration-solution access), so L3 gets SARAO's own K/B/G for free. PORT nothing. |
| CASA gaincal/bandpass/polcal | see section 3 | LGPL-2.0+ headers / "GPLv2" metadata | C++/Python | 6.7.6.14, 2026-08-07 | NRAO | ORACLE (CARACal's crosscal is CASA) |

### 2.3 Flagging

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Tricolour | Numba SumThreshold with CARACal strategies | BSD-3 LICENSE vs "GPLv2/Other" PyPI metadata (filed: tricolour#110) | Python | 0.2.1, 2026-04-01; 0.5.0 rework pending; Py < 3.13 | RATT | PORTED (task D, P3). Re-validate on 0.5.0 (big plan follow-up). |
| AOFlagger develop | as KERN row | GPL-3.0 | C++ | develop push 2026-10-07 (latest commit "SKB-1519 Always use static schaapthreading for Python lib") | ASTRON | ORACLE (section 1.3) |
| Owlcat | MS utilities (`plot-ms`, `flag-ms`, `downweigh-redundant-baselines`) | GPL-2.0+ (Debian) | Python | 1.8.1, 2026-03-18 | RATT | IGNORE. CARACal's `flagms` cab is Owlcat (unverified mapping); rang reads and writes flags itself. |
| CASA flagdata | tfcrop, rflag, clip, quack, shadow, elevation, extend… | see section 3 | C++ | 6.7.6 | NRAO | ORACLE. CARACal's flag worker uses `casa_flagdata` beside Tricolour and AOFlagger. |

### 2.4 Imaging and deconvolution

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| DDFacet | Facet imager with DD Jones, SSD/HMP deconvolution | GPL-2.0 (headers GPL-2-or-later) | Python/C++ | 1.0.0.0, 2026-06-23; Py < 3.13 | saopicc | ORACLE ([ddfacet-feasibility.md](ddfacet-feasibility.md)). FORMAT: DicoModel. |
| pfb-imaging | Preconditioned forward-backward imaging (sparsity/wavelet priors), stimela cabs via hip-cargo | MIT | Python | PyPI 0.0.11, 2026-07-28 (GitHub release v0.0.6 lags); Py < 3.14 | RATT (L. Bester) | ORACLE first; PORT candidate later. MIT allows copying, so it is the deconvolution code rang may lift directly if DF5 wants a convex-optimisation deconvolver rather than CLEAN. |
| ducc0 (wgridder) | Exact w-gridder/degridder, FFT, SHT | GPL-2.0-or-later | C++/Python | 0.42.0, 2026-10-20; wheels Linux/macOS/Windows (GitHub `mreineck/ducc` and gitlab.mpcdf paths not resolved by the API; PyPI only) | MPA (M. Reinecke) | ORACLE (DF1). DEPEND as a test extra is legal and cross-platform. |
| katsdpimager | SARAO GPU spectral-line imager | BSD-3 | Python/CUDA (PyCUDA/OpenCL; unverified) | push 2026-06-09, no releases | SARAO | IGNORE for now. BSD-3 makes it a readable GPU-gridding reference for X2. |
| katsdpcontim (Obit) | SARAO continuum imaging pipeline | BSD-3 (wrapper); Obit GPL-2+ | Python/C | push 2026-10-22 | SARAO | ORACLE, conditional (section 1.2 obit row) |
| breizorro | Binary masks from FITS images (threshold, islands, regions) | GPL-3.0 | Python | 0.2.0, 2025-04-24; Py < 3.13 | RATT | PORT when DF5 needs masks (small: thresholding plus connected components), with breizorro as the oracle. |
| EveryBeam | Beam library for LOFAR/MWA/SKA-Low/OSKAR/ATCA (unverified list) | GPL-3.0-or-later | C++ | 0.9.0 (ASTRON), PyPI 0.9.1 2026-10-21, Linux wheels | ASTRON | IGNORE for MeerKAT. Whether EveryBeam has a MeerKAT element model was not checked (unverified). |

### 2.5 Source finding and sky models

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| PyBDSF | Gaussian decomposition source finder; catalogues in FITS/ASCII/BBS/DS9/kvis/sagecal/star formats (unverified list) | GPL-3.0 | Python/Fortran/C++ | 1.14.1, 2026-06-12; wheels Linux/macOS | LOFAR/ASTRON | ORACLE. FORMAT: `.srl`/`.gaul` FITS or ASCII catalogues (read). DEPEND is legal (GPL-3) but has no Windows wheels. CARACal selfcal uses it (`pybdsm` cab). |
| Aegean (AegeanTools) | Compact-source finder with priorised fitting | **AFL-3.0** | Python | 2.3.5, 2025-07-28 | individual (P. Hancock) | ORACLE only. The FSF treats AFL as GPL-incompatible (secondary sources; FSF page rate-limited on 2026-10-30), so it is not DEPEND. |
| SoFiA-2 | 3D source finder for HI cubes; CARACal line and mask workers | GPL-3.0-or-later | C | v2.7.1, 2026-07-20 (gitlab.com/SoFiA-Admin/SoFiA-2; GitHub archived) | ASTRON/CSIRO/ICRAR | IGNORE (HI). ORACLE if rang ever makes masks for DF5 from cubes. |
| Crystalball | Distributed DFT prediction of WSClean component lists into MODEL_DATA (Serra, Perkins & Smirnov 2022) | GPLv2 (PyPI; "Other/Proprietary" classifier) | Python/Numba | PyPI 0.4.3, 2025-01-29 (GitHub release 0.4.1); Py < 3.13 | RATT/caracal-pipeline | Already PORTED in substance (africanus-style predictor). FORMAT: WSClean `-save-source-list` text, which is its input. ORACLE for L1-M (CARACal's `meerkat_crystalball_skymodel` path). |
| LSMTool | BBS sky-model manipulation | GPL-3.0 (PyPI) | Python | 1.9.0, 2026-09-25 | LOFAR | IGNORE. FORMAT note: BBS `makesourcedb` text is the DP3 sky format. |
| RM-Tools | RM synthesis and QU-fitting | MIT | Python | v1.5.0, 2026-10-21 | CIRADA | IGNORE (polarisation science, not calibration). |

### 2.6 Beams and pointing

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| katbeam | MeerKAT analytic (cosine-taper "JimBeam") beams | BSD-3 | Python | PyPI 0.1, 2020-10-15; repo push 2026-06-01 | SARAO | DEPEND (already used; control model in B1-0) |
| EIDOS | Zernike-fitted MeerKAT/VLA beams from holography; FITS beam cubes | GPL-3 (setup.py) | Python | 1.1.2, 2024-01-24 | RATT | ORACLE/FORMAT. It writes the FITS beam cubes that DDFacet and Cattery read; DF3 needs one. Legal to DEPEND, but stale. |
| SARAO holography cubes | Measured L-band beams (DOI 10.48479/wdb0-h061) | data licence not checked here | data | 2023 | SARAO | B1-0 reference (literature scan section 4.1) |

### 2.7 Pipelines

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| CARACal | MeerKAT end-to-end pipeline (workers: obsconf, flag, crosscal, polcal, selfcal, ddcal, line, mask, mosaic, inspect…) | GPL-2.0 (PyPI "GNU GPL v2"; or-later not stated, unverified) | Python | 1.2.1, 2025-10-28; push 2026-10-13; Py < 3.13 | caracal-pipeline | ORACLE (the matched baseline). Its strategy YAMLs and lsm files are inputs that rang reads (FORMAT). |
| Stimela 2 / cult-cargo | Recipe engine / curated cab images | GPL-2.0-only / MIT | Python | 2.1.4 / 0.2.1 (2026-05-22) | caracal-pipeline | ORACLE runner. cult-cargo's image manifest pins the oracle containers. |
| radiopadre | Jupyter framework for browsing pipeline products, with JS9 and CARTA integration | MIT | Python/JS | v1.2.0, 2023-03-01; push 2026-02-03 | RATT | IGNORE. The D2 notebooks cover rang's needs. Its CARTA launch code is MIT and can be read for section 4's helper. |
| oxkat | Ian Heywood's MeerKAT scripts (CASA crosscal, WSClean, CubiCal/QuartiCal, DDFacet/killMS) | GPL-3.0 | Python | v0.4, 2023-08-21; push 2026-10-08 | individual (Oxford) | ORACLE alternative to CARACal for the matched baseline. It is the other widely used MeerKAT recipe (Heywood 2020 calibrator-model work). |

### 2.8 Visualisation and QA

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| shadeMS | Datashader plots of any MS column against any axis | GPL-2.0-only | Python | 0.5.5, 2026-08-04; Py < 3.13 | RATT (I. Heywood) | IGNORE. Rang's notebook plots read the core's arrays; datashader-style density plots can be done with matplotlib `hexbin`/`imshow` on core aggregates. |
| ragavi | Bokeh plots of CASA/QuartiCal gain tables and visibilities | MIT | Python | 0.5.2, 2020-10-21; push 2026-10-26 | RATT | ORACLE for caltable reading: ragavi reads `VisCal`, `CPARAM`/`FPARAM`, `PARAMERR`, `SNR` and `FLAG`, which confirms the schema in section 3.3. IGNORE as a viewer. |
| CARTA | Image viewer (section 4) | GPL-3.0 | C++/TS | 6.0.0, 2026-06-29 | ASIAA/IDIA/NRAO/UAlberta | optional viewer |
| kvis (karma) | Legacy FITS viewer | Karma licence (unverified) | C | unmaintained | ATNF | IGNORE |
| casaviewer / casaplotms | CASA's image viewer / MS plotter | LGPL classifier | C++ | 2.4.4 (2025-09-29, Linux only) / 2.9.1 (2026-04-27, Linux/macOS) | NRAO | IGNORE (casaviewer is being replaced by CARTA in CASA; unverified). plotms is ORACLE for "what CARACal's inspect worker shows". |

### 2.9 Simulation

| Tool | Purpose | Licence | Lang | Latest / activity | Org | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| simms | Create empty MSs for a given array, pointing and band (wraps CASA `simobserve` or casacore) | GPL-2.0 (GitHub) vs GPL-3.0-only (PyPI): **conflict** | Python | 3.0.2, 2026-07-27; Py < 3.14 | RATT | ORACLE for the DF simulated field's empty MS (independent geometry check). Rang writes the MS itself via casacure. |
| montblanc | GPU RIME simulator (TensorFlow) | GPL-2.0 | Python/CUDA | 0.7.4, 2026-01-09 | RATT | IGNORE (superseded by codex-africanus and Crystalball). |
| codex-africanus | RIME, gridding and DFT kernels (Numba/dask) | BSD-3 (LICENSE; GitHub NOASSERTION; PyPI licence empty) | Python | 0.4.5, 2026-10-09 | RATT | PORTED (predictor). BSD-3, so further kernels (beam cube interpolation, `wsclean_predict`, Zernike beam) may be copied. |
| OSKAR | GPU interferometer simulator with station beams | BSD-3 | C/CUDA | 2.13.0, 2026-07-23 | Oxford | IGNORE now. A second simulator if DF3–DF5 need noise-and-beam-realistic data beyond rang's own predictor. |

### 2.10 Polarisation

Rang has no polarisation calibration. The options:

- **CASA `polcal`.** Leakage `D`/`Df`, cross-hand phase `Xf`/`X`,
  cross-hand delay via `gaincal` `KCROSS`, and `Df+QU`/`Xf+QU` variants
  (unverified list). CARACal's `polcal_worker.py` uses `casa_polcal`,
  `casa_polfromgain` and `casa_setjy`. ORACLE.
- **QuartiCal's `leakage`, `crosshand_phase`, `feed_flip` and
  `parallactic_angle` terms** (MIT). PORT candidates if a protocol needs
  them; they slot into the existing solver.
- **Science-side RM tools** (RM-Tools, BRATS): IGNORE.

The literature scan's recommendation 8 (1934−638's fractional polarisation
below the closure-trace noise) needs a number, not a calibrator.

## 3. CASA

### 3.1 Release, licence and platforms

- **Current release.** CASA 6.7: casatools/casatasks **6.7.6.14** on
  PyPI, first uploaded 2026-08-07. KERN-10's casalite is 6.7.3.21.
  casadocs "stable" describes 6.7.
  - Validated platform: RHEL 8, Python 3.10 (casadocs introduction).
  - macOS Intel support is dropped.
  - macOS 15/26 are in the test table.
  - No Windows build of any kind.
- **Wheels.** casatools 6.7.6.14 ships cp312 and cp313 wheels only:
  `manylinux_2_28`/`2_34` x86_64 and macOS 14/15/26 arm64. There is no
  aarch64 Linux, no Windows and no Python 3.10/3.11/3.14.
  - casatasks is a pure wheel pinned to the same casatools.
  - casaplotms 2.9.1 and casaviewer 2.4.4 are separate wheels; casaviewer
    is Linux only.
- **Licence: inconsistent, recorded rather than resolved.**
  - The casatools 6.7.6.14 wheel METADATA says `License: GPLv2`, but its
    classifier says `GNU Library or Lesser General Public License (LGPL)`.
  - casatasks says LGPL.
  - CASA source files carry the AUI header "GNU Library General Public
    License … version 2 … or (at your option) any later version", which
    is LGPL-2.0-or-later. This was read in `SolvableVisCal.cc` of the
    2023 third-party mirror `dic-case-studies/casa6`, not on NRAO's
    Bitbucket, which requires a login. Unverified as the current official
    statement.
  - Either reading permits DEPEND licence-wise (LGPL; or GPL-2-or-later
    if the headers govern).
- **Verdict: ORACLE.**
  - DEPEND fails on platform: no Windows, two Python versions.
  - It also fails on size: casatools plus casadata runtime data is
    hundreds of MB (unverified).
  - It also fails on the X1 promise that the core runs natively on
    Windows.
  - CASA stays an oracle container. The KERN-10 `casalite` deb or the
    casatools wheels on Python 3.12, in a pinned image, serve as the base.

### 3.2 Tasks relevant to rang's chain

| Task | Algorithm (casadocs 6.7, accessed 2026-10-30) | RATT-stack counterpart and difference | Rang verdict |
| --- | --- | --- | --- |
| `listobs` | MS summary: scans, fields, spws, antennas | `rangtoy` MS reader summaries | IGNORE (core reader suffices). Use as oracle text when a new MS arrives. |
| `flagdata` modes | `manual`, `clip`, `quack`, `shadow`, `elevation`, `tfcrop`, `rflag`, `antint`, `extend`, `unflag`, `summary`, `list`. **tfcrop**: average amplitudes along time into a spectrum, robust piecewise-polynomial fit to the band shape (`freqfit='poly'`, `maxnpieces` 7) and a line in time (`timefit='line'`), flag beyond `freqcutoff` 3σ / `timecutoff` 4σ, up to 5 iterations, then the other axis. **rflag**: AIPS-RFLAG style: sliding-window (`winsize` 3) local RMS of Re and Im per channel in time, thresholds `timedevscale`/`freqdevscale` 5 × median-based noise; `action='calculate'` then `'apply'` replicates the AIPS two-pass method. **extend**: `growtime`/`growfreq` 50 %, `extendpols`. | Tricolour/AOFlagger SumThreshold detects runs of decreasing length with thresholds `χ_i = χ_1 ρ^{log2 i} / i` (ρ = 1.5; Offringa et al. 2010) on background-subtracted data (smoothed by a 2-D filter). tfcrop fits a bandshape and time trend and clips residuals. rflag is a local-RMS detector, with no combinatorial run search. CARACal's flag worker runs tfcrop/rflag (`casa_flagdata`) beside Tricolour and AOFlagger, so a matched CARACal baseline includes them. | ORACLE. A PORT of tfcrop/rflag is cheap (a few hundred lines) but only worth doing if a protocol compares flaggers. The flagging campaign is null, so not now. |
| `setjy` | Model visibilities from a flux standard: Baars, Perley 90, Perley-Taylor 95/99, Perley-Butler 2010/2013/**2017 (default)**, Scaife-Heald 2012 (30–300 MHz), **Stevens-Reynolds 2016** (single source: 1934−638; Reynolds polynomial below 11 GHz, Stevens above), Butler-JPL-Horizons 2010/2012 (solar system), `manual` (`fluxdensity`, `spix`, `reffreq`, `polindex`, `polangle`, `rotmeas`), `fluxscale`. 1934−638 appears in standards 1, 3, 4, 5, 6 and 8 (PB2010, PT99, PT95, P90, Baars, SR2016), **not** in PB2013 or PB2017. PB2013/2017 have time-variable models for 3C48, 3C138 and 3C147. | Rang predicts a 14.96 Jy point or a Reynolds 1994 polynomial ([flagging.md](flagging.md)). CARACal uses `standard='manual'` with its own calibrator table (`utils.find_in_casa_calibrators`) or the lsm/Crystalball model for 1934. LUNO's HISTORY shows `setjy` PB2017 run on 3C 286 only. | **PORT** the standards rang needs (SR2016 and PB2010 for 1934−638; PB2017 for 3C 286, 3C 138 and 0408−65 if used), with `setjy` model visibilities as the oracle: compare per-channel flux against the core's spectral point to 1e-6 relative. Small. |
| `gaincal` | Antenna-based gains, `gaintype` G, T, K (delay), KCROSS, GSPLINE; `calmode` `ap`/`p`/`a`; `solmode` `''` (L2), `L1`, `R`, `L1R` (robust, experimental; `rmsthresh` sequence 7…2.2); `minblperant` 4, `minsnr` 3, `refantmode` flex/strict, `combine`, `solnorm`. "gaincal performs an iterative, steepest-descent chi-squared minimization for its antenna-based gain solution." | QuartiCal (and rang's port) solve the same per-interval χ² with Gauss-Newton on 2×2 complex Jones, using a block-diagonal JHJ, a fixed iteration cap (25 or 50) and a relative-update stop criterion. CASA solves per correlation (G) or polarisation-averaged (T), applies SNR and baseline-count cuts and phase-references to `refant` after solving. Gauge handling and convergence differ, and CASA's robust `R`/`L1` modes have no QuartiCal analogue. | ORACLE. CASA G on 1934−638 is the second DI comparator for L5's convergence study, and it is what CARACal crosscal actually runs. PORT nothing: rang's solver already covers G and T as diagonal terms. |
| `bandpass` | B (channelised) or BPOLY solutions, normalised, with `solint` and `fillgaps` | QuartiCal `complex` with a frequency interval of 1 channel | ORACLE |
| `polcal` | D, Df, X, Xf, D+QU, Df+QU, Xf+QU, Dflls (unverified list) | QuartiCal `leakage`, `crosshand_phase` | ORACLE (section 2.10) |
| `fluxscale` | Transfer the flux scale from a primary to secondaries through G amplitudes; fits a spectral index | no RATT equivalent (CARACal calls CASA) | PORT later if L3 or B1 bootstraps secondary calibrators (small). Oracle: `fluxscale`. |
| `applycal` | Apply caltables (interpolation `linear`, `nearest`, `linearflag`…; `calwt`) | `quartical` apply, rang `correct.rs` (P5) | FORMAT first (read caltables), then PORT the interpolation modes rang needs. Oracle: CASA `applycal` CORRECTED_DATA. |
| `tclean` | Gridders: `standard`, `wproject`, `widefield`, `mosaic`, `awproject`, `awp2`, `awphpg`. Deconvolvers: `hogbom`, `clark`, `clarkstokes`, `multiscale`, `mtmfs` (`nterms` default 2), `mem`, `asp`. Weighting: `natural`, `uniform`, `briggs`, `superuniform`, `radial`, `briggsabs`, `briggsbwtaper`. `usemask='auto-multithresh'`; `parallel` via mpicasa. | WSClean (w-stacking/wgridder, multiscale, joined-channel deconvolution, auto-masking) is the MeerKAT default; DDFacet is for DD imaging. tclean `mtmfs` (Rau & Cornwell) differs from WSClean's joined-channel MF deconvolution with polynomial fits. | ORACLE only, for the `mtmfs` and `asp` algorithms if DF5 ever needs them. WSClean remains the primary imaging oracle. |
| `mstransform` | Split, average, regrid, Hanning, combine spws | xova (averaging) | IGNORE (the core reads what it needs) |
| `plotms` | Interactive/batch MS and caltable plots | ragavi, shadeMS, rang notebooks | IGNORE. ORACLE for "what CARACal's inspect worker shows". |
| `flagmanager` | Save and restore flag versions (`<ms>.flagversions/`) | none in RATT | FORMAT: read and write `.flagversions` if rang must hand flags back to CASA users (low priority). |

### 3.3 The calibration-table format (what rang must read and write)

The schema below was read from the casa6 mirror's
`casatools/src/code/synthesis/CalTables/{CTEnums,CTDesc,NewCalTable}.cc`.
It is the "new-style" table introduced in CASA 3.4; `caltabconvert`
converts older ones.

- **Type.** A casacore table with `TableInfo` type `Calibration`
  (`ME_CALIBRATION`). Its subtype is the `VisCal` name (e.g.
  `"G Jones"`, `"B Jones"`, `"K Jones"`, `"Df Jones"`; ragavi takes the
  first word of `VisCal` as the table type).
- **Main-table keywords.**
  - `ParType`: `"Complex"` or `"Float"`.
  - `MSName`.
  - `VisCal`.
  - `PolBasis`.
  - `CASA_Version`.
  - Subtable links `OBSERVATION`, `ANTENNA`, `FIELD`, `SPECTRAL_WINDOW` and
    `HISTORY` (an MS-like subset).
- **Main columns.**
  - `TIME`, `TIME_EXTRA_PREC`, `INTERVAL`.
  - `FIELD_ID`, `SPECTRAL_WINDOW_ID`, `ANTENNA1`, `ANTENNA2` (the
    reference antenna), `SCAN_NUMBER`, `OBSERVATION_ID`, `ARRAY_ID`.
  - `CPARAM` (complex, shape `[npar, nchan]`) **or** `FPARAM` (float;
    delays, `K` in ns), `PARAMERR`, `FLAG`, `SNR`, `WEIGHT`.
  - Older tables lack `OBSERVATION_ID` and the `OBSERVATION` subtable;
    CASA back-converts them on open.
- **What rang needs.** The table system (casacure or task E) plus
  per-`VisCal` semantics:
  - parameter layout per type: `G` is 2 pols; `B` is 2 pols × nchan;
    `K` is ns; `Df` is leakage;
  - interpolation;
  - the reference-antenna convention.

  The first FORMAT protocol: write a `G Jones` and a `B Jones` table from
  the core's 1934 solutions, have CASA `applycal` (oracle container) apply
  them, and compare CORRECTED_DATA with the core's own correction (P5's
  `correct_stokes_i`) to float32 rounding. Then read CASA-made tables
  (from `gaincal` in the oracle) back into the core. The format has been
  stable since CASA 3.4.

### 3.4 Where CASA's algorithms differ from the RATT stack

1. **Solver.**
   - CASA documents "steepest-descent χ² minimisation" per solution
     interval, per correlation (G) or per polarisation-averaged (T), with
     SNR and baseline-count rejection and optional robust L1/R modes.
   - QuartiCal (rang) uses Gauss-Newton on full or diagonal 2×2 Jones
     with a block-diagonal JHJ.
   - On a strong calibrator both reach the same fixed point to noise.
     Their convergence behaviour and outlier handling differ, which bears
     on L5.
   - Whether CASA's inner loop is plain steepest descent or a
     damped/diagonal-Hessian variant was not read in the source
     (unverified beyond the casadocs sentence).
2. **Flagging.** tfcrop/rflag fit and clip; SumThreshold searches
   combinatorially. In the LUNO HISTORY, SARAO/CARACal ran `flagdata`
   modes beside Tricolour.
3. **Flux standards.** RATT tools take models from lsm/Crystalball
   component lists, or from CASA `setjy` inside CARACal. Only CASA ships
   the standards.
4. **Calibration products.**
   - CASA: caltables, which are per-type, reference-antenna phased and
     interpolated on apply.
   - QuartiCal: zarr gain stores with `gain_time`/`gain_freq` axes and a
     `direction` axis.
   - DP3/WSClean/facetselfcal: H5parm.
   - killMS: npz.

   Rang's FORMAT work must map between these four.
5. **Imaging.**
   - tclean's `awproject`/`mosaic` gridders handle A-terms by AW-projection.
   - WSClean uses IDG or facets.
   - DDFacet uses per-facet Jones.
   - For MeerKAT L-band the community default is WSClean, with DDFacet
     for DD; CASA imaging is rare in MeerKAT papers (unverified, based on
     CARACal and oxkat defaults).

## 4. CARTA

### 4.1 What it is (2026-10-30)

- **Release.** CARTA 6.0.0: GitHub release 2026-06-29; cartavis.org gives
  18 June 2026 as the release date.
  - Backend (C++) and frontend (TypeScript) are both GPL-3.0.
  - Repos: `CARTAvis/carta-backend` and `carta-frontend`, pushed
    2026-10-29.
  - Developed by ASIAA, IDIA, NRAO and U. Alberta (unverified list of
    partners).
- **Platforms (cartavis.org).**
  - Ubuntu 22.04/24.04 and RHEL 8/9 (x86_64, aarch64).
  - macOS 14, 15 and 26 (Intel and Apple Silicon).
  - Docker for unsupported platforms.
  - **No native Windows build** (Windows is only possible through WSL or
    Docker; not stated by cartavis.org).
- **Formats.**
  - FITS, CASA images and MIRIAD (from the CARTA docs and long-standing
    knowledge; cartavis.org's front page does not list them; unverified
    for 6.0).
  - HDF5 with the IDIA schema, which the site singles out as
    "significantly" better for large cubes.
  - xradio-image zarr planned for 6.1.
  - Catalogues with millions of sources render "in seconds"; VOTable and
    FITS tables are unverified for 6.0.
- **Features relevant to rang.**
  - Tiled raster rendering of very large images and cubes.
  - Spatial and spectral profiles, moment maps.
  - Region statistics, contours, catalogue overlays, PV diagrams.
  - Colour blending (new in 6.0, also exposed in carta-python).
  - Pop-out image viewer.

### 4.2 carta-python (scripting)

- **Package.** `CARTAvis/carta-python`: GPL-3.0, Python ≥ 3.10, last tag
  v1.2.0, push 2026-10-25 (Color blending module 2026-08-18). Not on PyPI:
  the docs say install from a checkout, and PyPI `carta` is an unrelated
  package. It requires CARTA ≥ 4.0.
- **Connection.**
  - `Session.interact(frontend_url, session_id)` attaches to an open
    browser session.
  - `Session.start_and_interact` starts a local or SSH-remote backend and
    attaches.
  - `Session.create(Chrome(), url, token)` / `start_and_create` run a
    headless session; only Chrome/Chromium is supported, and it needs the
    `[browser]` extra and a web driver.
  - A self-built backend must run with `--enable_scripting`.
  - Authentication is by `BackendToken` (`CARTA_AUTH_TOKEN`) or a
    controller refresh token.
- **Operations.**
  - `open_image(s)`; set channel, Stokes, centre and zoom.
  - Colourmap, scaling, clip, contours, WCS overlay, colour blending.
  - `rendered_view_data` returns an image that Jupyter displays;
    `save_rendered_view("x.png")` saves one.
  - Regions and spectral profiles are not documented in the quickstart
    (unverified whether the API exposes them).
  - Known limitation: interactive sessions may return a partially
    rendered image.

### 4.3 Should rang's notebooks drive CARTA instead of matplotlib?

**No as a default, yes as an optional helper.**

Reasons against a default:
- No Windows build, against the X1 goal of running natively there.
- A backend process plus headless Chrome is too heavy for CI-executed
  tutorial notebooks (D1 runs them with `nbval`/`papermill`).
- Rendered PNGs from CARTA are not reproducible artefacts the way
  matplotlib figures from core arrays are.
- The D2 plots are mostly 1-D/2-D diagnostics (gains, TV maps, flag
  masks), which CARTA does not show.

Where CARTA wins: inspecting a whole-array dirty image or a cube
(2048 channels) interactively, with profiles, moments and catalogue
overlays. That matters once DF5 makes deconvolved images and B1 looks at
faint emission.

**Integration sketch (proposal, not implemented).**
- An optional extra `[carta]` that installs carta-python from a pinned git
  tag (GPL-3, compatible).
- `rang.notebook.carta.open(path)`:
  - checks for a `carta` executable or the `CARTA_URL` environment
    variable;
  - otherwise prints the CLI command to start one (Linux/macOS) or the
    Docker line (Windows);
  - calls `Session.start_and_interact` and opens the FITS (or HDF5) file
    that rang wrote.
- `rang.notebook.carta.snapshot(path, png)` wraps `save_rendered_view`
  for a static figure.
- Images are written to FITS first (astropy, already used). An HDF5 IDIA
  writer is optional (4.4).
- Tests: skipped unless a backend is present. Nothing in CI depends on it.
- radiopadre's MIT CARTA launcher is the code to read before writing this.

### 4.4 The IDIA HDF5 image schema as a FORMAT candidate

The schema was read in `CARTAvis/fits2idia` (GPL-3.0, C++, push
2026-10-27, last release v0.1.15 2022-06-01), `src/common.h`:
`SCHEMA_VERSION "0.3"`. The paper is Taylor et al. 2020, Astronomy and
Computing 32, 100389.

- **Layout.**
  - Group `0` holds `DATA`, the image in FITS axis order reversed, with
    the FITS header as attributes, plus the attribute
    `SCHEMA_VERSION="0.3"`.
  - `SwizzledData/ZYX` (or `ZYXW` for 4-D) is a spectral-axis-fastest
    copy for fast profiles, hard-linked as `PermutedData`.
  - `Statistics` holds per-channel and per-cube statistics and
    histograms.
  - `MipMaps/DATA/DATA_<n>` holds downsampled pyramids (`-z` adds mipmaps
    along the third axis).
  - All the precomputed datasets are optional; readers must cope without
    them.
- **Cost for rang.**
  - Writing it from Rust needs libhdf5 (the `hdf5` crate links the C
    library). That is a new native dependency on all five wheel
    platforms, which costs X1's "no system libraries" property.
  - Writing it from Python needs h5py, an optional extra.
- **Verdict: FORMAT, write-only, low priority.**
  - Write FITS first.
  - Offer `fits2idia` (or h5py in the `[carta]` extra) for cubes larger
    than a few GB.
  - Reading IDIA files has no use case in rang.
  - Revisit when xradio-image zarr lands in CARTA 6.1. The core already
    writes zarr-adjacent formats without system libraries, so zarr may be
    the better cube format for both CARTA and rang.

## 5. Gaps and recommendations

### 5.1 Rang's missing pieces and which surveyed tool fills each

| Gap | Candidate tools (licence) | Path | Validation (archive/oracle) |
| --- | --- | --- | --- |
| Beam model (B1) | SARAO holography cubes (data), katbeam (BSD-3), EIDOS (GPL-3), Cattery FITS beams (GPL-2+) | DEPEND katbeam; FORMAT read of the holography FITS cubes; PORT cube interpolation (codex-africanus `beam_cube_dde` is BSD-3 and may be copied) | B1-0 protocol (literature scan): holography as reference, katbeam as control; codex-africanus as interpolation oracle |
| Flux standards | CASA `setjy` (LGPL/GPLv2 metadata) | PORT SR2016, PB2010, PB2017 polynomials | `setjy` MODEL_DATA in the CASA oracle; rang's Reynolds values in `flagging.md` |
| CASA caltables | CASA, casacure (LGPL-3+) | FORMAT via casacure (E2) | CASA `applycal` round trip (section 3.3) |
| Native MeerKAT data (L3) | katdal + katsdptelstate (BSD-3), `mvftoms.py` | DEPEND now (`[meerkat]` extra, pure Python, all platforms); PORT the MVFv4 chunk reader later | katdal arrays read side by side; mvftoms MS against the core's reader |
| SARAO's own calibration | katsdpcal solutions in MVF (`sdp.cal`) | DEPEND (via katdal) | compare core K/B/G on the same scans |
| Deconvolution (DF5) | WSClean (GPL-3), DDFacet (GPL-2+), pfb-imaging (MIT), CASA tclean | PORT Hogbom/multiscale (DF5 as planned); pfb-imaging's MIT code if a convex deconvolver is wanted | WSClean/DDFacet on the simulated field, truth known |
| DD calibration (DF4) | killMS (GPL-2), DP3 DDECal (GPL-3), QuartiCal DD (MIT), facetselfcal (no licence) | PORT scalar CohJones (DF4); QuartiCal's MIT DD code is copyable | killMS and DP3 DDECal on the simulated field |
| Source finding | PyBDSF (GPL-3), Aegean (AFL-3.0), SoFiA-2 (GPL-3+) | ORACLE PyBDSF; FORMAT read of its catalogues. No PORT unless a protocol needs a finder in the loop. | – |
| Masks | breizorro (GPL-3) | PORT (small) when DF5 needs it | breizorro on the same FITS |
| Polarisation calibration | CASA polcal, QuartiCal leakage/crosshand terms (MIT) | ORACLE; PORT QuartiCal terms only for a protocol | CASA polcal on 3C 286/3C 138 scans |
| QA plots | ragavi (MIT), shadeMS (GPL-2-only), plotms, CARTA | keep matplotlib (D2); optional CARTA helper | – |
| Sky-model formats | tigger-lsm, Crystalball/WSClean text, BBS, DicoModel | FORMAT (5.3) | `tigger-convert` round trip; Crystalball prediction of the same list |
| Flagging comparators | AOFlagger 3.5 (GPL-3), CASA tfcrop/rflag | ORACLE | task D archived inputs |

### 5.2 Top ten recommendations, ranked by value for the plan's goals

Each item names its licence path and the first protocol to freeze.

1. **CASA oracle container (O-CASA).** casatools 6.7.6.14 on Python 3.12
   in a pinned image (or KERN-10 casalite 6.7.3.21), with WSClean 3.7 and
   AOFlagger 3.5 from KERN-10 in the same Noble base.
   - It is required by the matched CARACal baseline (CARACal's crosscal
     is CASA), the flux standards, caltable I/O and polcal.
   - Licence path: ORACLE.
   - Protocol: run CARACal's crosscal sequence by hand
     (`setjy`/`gaincal`/`bandpass`/`applycal`, CARACal's strategy
     parameters) on LUNO 1934 scan chunk 0 four-station; archive the
     tables and CORRECTED_DATA. Freeze the image digest.
2. **Flux standards in the core (FS1).** PORT Stevens-Reynolds 2016 and
   Perley-Butler 2010 for 1934−638, and PB2017 for 3C 286/3C 138.
   - Licence path: reimplementation from the published polynomials.
   - Protocol: per-channel flux at LUNO's 2048 channels against
     `setjy` MODEL_DATA in O-CASA, to 1e-6 relative.
   - Feeds L1-M, so CARACal's lsm and the SR2016 point can be compared.
3. **CASA caltable FORMAT (DF-IO-CT).** Read and write `G`, `B` and `K`
   tables through casacure (once E2 passes).
   - Licence path: casacure is LGPL-3+ (DEPEND).
   - Protocol: section 3.3's round trip through CASA `applycal`, then
     CASA-made tables back into the core.
4. **katdal for L3 (MK1).** An optional `[meerkat]` extra (katdal 0.23,
   katsdptelstate 1.0.0, BSD-3, pure Python) and a loader from an MVF
   RDB URL into the core's arrays.
   - Use katsdpcal's archived solutions as a free comparator.
   - Licence path: DEPEND.
   - Protocol: on the observer's dataset once it arrives, katdal arrays
     against `mvftoms` MS columns read by the core (exact), and the
     weight product (`weights × weights_channel`; MVFv4 docs) reproduced.
   - PORT the npy-chunk reader (HTTP range fetch already exists) only if
     katdal's dask path is the measured bottleneck.
5. **H5parm FORMAT (DF-IO-H5).** Read and write the losoto/DP3 H5parm
   subset: `solsetNNN/solNNN/{amplitude,phase}000` with `val`/`weight`
   and axes `time,freq,ant,dir,pol` (layout from losoto docs, unverified
   here).
   - This is the format WSClean facet solutions, DP3 and facetselfcal
     share, and the bridge to killMS (`killMS2H5parm`, unverified).
   - Licence path: PORT (h5py in Python first; Rust HDF5 has the libhdf5
     cost noted in 4.4).
   - Protocol: losoto reads the core's file and DP3 `applycal` applies
     it in an oracle.
6. **Sky-model FORMATs (DF-IO-SKY).** Tigger `.lsm.html`/ASCII,
   WSClean/Crystalball source-list text, BBS `.skymodel`, and read-only
   DDFacet DicoModel (pickle; see 5.3).
   - Licence path: PORT.
   - Protocol: CARACal's 196-component `pks1934-638.lsm` read, written
     as WSClean text, predicted by the core and by Crystalball. The
     visibilities must agree to float32, and `tigger-convert` must
     round-trip.
   - Prerequisite for L1-M.
7. **SumThreshold second oracle (A-FLAG).** Run AOFlagger 3.5 with a
   Lua strategy equivalent to Tricolour's first pass on task D's archived
   inputs.
   - Licence path: ORACLE.
   - Report agreement with the port. This answers whether the
     Tricolour-derived port matches the reference implementation, before
     Tricolour 0.5.0 changes the oracle.
8. **CASA gaincal as L5's second DI comparator (L5-C).** In L5's
   protocol, add CASA `gaincal` G/T on the same intervals: held-out
   error, gain-product agreement, cost.
   - Licence path: ORACLE.
   - It tests whether QuartiCal's convergence tail is solver-specific.
9. **pfb-imaging and WSClean as the DF5 oracles (DF5-O).** Freeze both
   on the simulated MeerKAT field before writing Hogbom/multiscale.
   - pfb-imaging is MIT, so its prox operators may be copied if a convex
     deconvolver beats CLEAN at matched cost (the novelty rule).
   - Licence path: ORACLE, then PORT.
10. **Optional CARTA helper (NB-CARTA).** The `[carta]` extra and
    `rang.notebook.carta.open/snapshot` (section 4.3).
    - Licence path: carta-python GPL-3, DEPEND (optional).
    - Protocol: none (tooling). The acceptance is that a whole-array
      dirty image and the LUNO cube slice open from a notebook on Linux,
      and the helper is skipped cleanly on Windows.

Not recommended:
- a CASA DEPEND (platform);
- a source finder PORT;
- Owlcat/shadeMS/xova;
- an IDG or EveryBeam path for MeerKAT;
- Aegean as anything but an oracle (AFL-3.0);
- facetselfcal code reuse (no licence).

### 5.3 File formats the DF-IO decision must cover

| Format | Defined by (version read) | Container | Rang direction | Notes |
| --- | --- | --- | --- | --- |
| Measurement Set v2 | casacore 3.8 (MS v2 note 229) | casacore tables | read (task E), write (casacure, E2) | storage managers: Standard, Incremental, TiledColumn (casacure); Dysco not covered (unverified need) |
| MSv4 | xradio 1.3.0 | zarr | later (watch) | NRAO's successor; xarray-ms is RATT's adapter |
| dask-ms zarr export | dask-ms 0.2.32 | zarr v2 + blosc | read (task G) | `json2` vs `pickle` object columns (upstream-notes) |
| CASA calibration tables | CASA ≥ 3.4 `NewCalTable` | casacore table, `VisCal` subtype | read/write | section 3.3 |
| CASA flag versions | CASA `flagmanager` | `<ms>.flagversions/` tables | write (low priority) | – |
| QuartiCal gain store | QuartiCal 0.2.7 | zarr via `daskms.experimental.zarr.xds_to_zarr`; dims `gain_time`, `gain_freq`, `antenna`, `direction`, `corr` (+ `param_*` for parametrised terms) | read/write | rang already reads it for comparators |
| losoto/DP3 H5parm | losoto 2.7.1, DP3 6.6 | HDF5 (PyTables) | read/write | needs libhdf5 or h5py |
| killMS solutions | killMS 3.3.0 | NumPy `.npz`: `Sols` record array (`t0`, `t1`, `G`), `StationNames`, cluster catalogue; `np.load(..., allow_pickle=True)` in `MergeSols.py` | read/write | pickle-bearing: read with a restricted unpickler, never on untrusted files |
| DDFacet DicoModel | DDFacet 1.0.0.0 | Python pickle of a dict (`Type`, `Comp`, `RefFreq`, `ModelShape`, …; [ddfacet-feasibility.md](ddfacet-feasibility.md)) | read; write only if DDFacet must consume core models | a Rust reader needs a pickle decoder (e.g. `serde-pickle`, unverified for this payload). Unsafe for untrusted files. |
| DDFacet/killMS ClusterCat | DDFacet | NumPy `.npy` record array | read/write | facet node catalogue |
| Tigger LSM | tigger-lsm 1.8.0 | `.lsm.html` (HTML with embedded tags), Tigger ASCII `.txt` (`#format:` header) | read/write | CARACal's 1934 model |
| WSClean source list | WSClean 3.7 `-save-source-list` | text, `Format = Name, Type, Ra, Dec, I, SpectralIndex, LogarithmicSI, ReferenceFrequency, MajorAxis, MinorAxis, Orientation` (unverified header text) | read/write | Crystalball's input |
| BBS sky model | DP3 `makesourcedb`, LSMTool 1.9.0 | text | read | DP3/facetselfcal |
| PyBDSF catalogues | bdsf 1.14.1 | FITS table / ASCII `.srl`, `.gaul` | read | source finding oracle |
| FITS images and beam cubes | FITS 4.0; EIDOS/holography cubes | FITS | read/write (astropy now; core later) | WSClean/DDFacet/CASA `exportfits` all agree on FITS |
| CASA images | casacore images | casacore table (PagedImage) | read (oracle only) | tclean output; CARTA reads it |
| IDIA HDF5 image | fits2idia, schema 0.3 | HDF5 | write, optional | section 4.4 |
| AOFlagger strategies | AOFlagger 3.x | Lua `.lua` (v2 used XML `.rfis`) | read only to run the oracle | rang's strategies stay Tricolour YAML |
| Tricolour/CARACal strategies | Tricolour 0.2.1, CARACal 1.2.1 | YAML | read (task D) | – |
| AOFlagger flags and statistics | AOFlagger | MS `FLAG` column, `QUALITY_*` subtables (aoquality) | FLAG via MS; QUALITY tables ignore | – |
| katdal MVFv4 | katdal 0.23 docs | `.rdb` (Redis dump, telstate keys) + S3 chunk store `<type>/<AAAAA>_<BBBBB>_<CCCCC>.npy` (`correlator_data`, `flags` bitfield, `weights`, `weights_channel`) | read | weights = `weights × weights_channel` (× autocorr power if `need_weights_power_scale`); timestamps synthesised from `sync_time` |
| Stimela/cult-cargo recipes | Stimela 2.1.4 | YAML | read (history only) | frozen recipes |

### 5.4 Oracles for the DF tasks and B1

| Task | Oracle(s) | Container base | Why |
| --- | --- | --- | --- |
| DF0 | KERN-10 Noble image: WSClean 3.7, AOFlagger 3.5.0, casacore 3.7.1, IDG 1.2.0, python-casacore; plus PyPI ducc0 0.42.0, DDFacet 1.0.0.0, killMS 3.3.0 (killMS needs DDFacet v0.9.1 per [ddfacet-feasibility.md](ddfacet-feasibility.md)) | `ubuntu:24.04` + `ppa:kernsuite/kern-10` | one apt line instead of source builds; record the deb versions |
| DF1 exact gridder | ducc0 `vis2dirty`/`dirty2vis` (1 thread), DFT; WSClean `-gridder wgridder` | DF0 | as planned |
| DF2 imaging chains | WSClean 3.7; CASA tclean `standard` as a third reading of weighting conventions (optional) | DF0, O-CASA | – |
| DF3 facets + beams | DDFacet with an EIDOS-generated MeerKAT FITS beam cube; Cattery FITS beam | DF0 | per-facet Jones |
| DF4 DD solver | killMS (DDFacet 0.9.1 pair), DP3 DDECal 6.6 | DF0 + PyPI `dp3` | two independent DD references |
| DF5 deconvolution | WSClean multiscale, DDFacet HMP/SSD, pfb-imaging 0.0.11; PyBDSF for recovered-flux checks | DF0 | truth from the simulated field |
| DF6 facet-IDG | WSClean `-use-idg` (IDG 1.2.0/1.3.0) | DF0 | – |
| DF-IO | CASA `applycal` (caltables), losoto/DP3 (H5parm), `tigger-convert`, Crystalball, killMS `MergeSols`/DDFacet `--Predict-InitDicoModel` (unverified option name) | O-CASA, DF0 | each format judged by its own tool |
| B1-0 beam | SARAO holography cubes; katbeam control; EIDOS Zernike model as a third | none (data) | literature scan 4.1 |
| B1 matched baseline | CARACal/oxkat crosscal in O-CASA; katsdpcal solutions via katdal (L3 data) | O-CASA | the state of practice per the novelty rule |
| L1-M | CARACal's 1934 lsm predicted by MeqTrees (Cattery) and by Crystalball | DF0 + PyPI | two independent predictions of the same model |

## 6. Observations (not filed)

### 6.1 RATT, caracal-pipeline and saopicc (reportable under the user's rule; reproduce on the latest release first)

- **Licence metadata conflicts.**
  - CubiCal: GitHub detects GPL-2.0; the PyPI classifier says GPLv3.
  - simms: GitHub GPL-2.0; PyPI `license_expression` GPL-3.0-only.
  - dask-ms and codex-africanus: a BSD-3 LICENSE text, but an empty
    PyPI licence field (codex-africanus) and GitHub NOASSERTION.
  - shadems, montblanc and crystalball: the "Other/Proprietary"
    classifier beside a GPL licence string.
  - Tricolour is already filed as tricolour#110; do not refile.
  - Same class of issue as #110. One combined issue per repository is
    reasonable if the user wants them filed.
- **Repos without a licence file:** tigger-lsm, owlcat, meqtrees-timba,
  makems (the KERN Debian copyright says GPL-2.0+); tigger and eidos
  declare a licence in `setup.py` only.
- **Python upper bounds blocking 3.13/3.14:**
  - `<3.13`: tricolour, DDFacet, killMS, CARACal, shadems, crystalball,
    breizorro.
  - `<3.14`: QuartiCal, dask-ms, stimela, simms, pfb-imaging.
  - Context for X1. Stimela 3.14 is already filed (stimela#619).
- **ragavi.** The last release is 0.5.2 (2020-10-21) while the repo is
  active (push 2026-10-26). A release request is optional.
- **Stale releases.**
  - pfb-imaging's GitHub release is v0.0.6 while PyPI has 0.0.11.
  - crystalball's GitHub release is 0.4.1 while PyPI has 0.4.3.
  - Cosmetic.

### 6.2 KERN packaging (the user maintains KERN; listed, not filed)

- **Version lag.**
  - casacore 3.7.1 vs upstream 3.8.2 (2026-09-29).
  - python-casacore 3.7.1 vs 3.8.1 (2026-06-26).
  - stimela 2.1.2.1 vs 2.1.4.
  - casaconfig 1.3.1 vs 1.5.2.
  - IDG 1.2.0 vs 1.3.0.
  - numba 0.64.0 vs the 0.67 rang has measured with.
- **Metadata bugs.**
  - The casaconfig `Homepage: ihttps://casa.nrao.edu` has a typo.
  - python-casacore's `Vcs-Browser` points at the dead `anonscm.debian.org`.
  - rdbtools has no Homepage.
- **Not packaged.** The RATT stack that MeerKAT users install from PyPI
  is not packaged: QuartiCal, Tricolour, dask-ms, codex-africanus,
  DDFacet, killMS, CARACal, PyBDSF (since KERN-9).

### 6.3 Non-RATT (for `non-ratt-observations.md`; not reported)

- **casatools 6.7.6.14 wheel metadata is self-contradictory.** It has
  `License: GPLv2` beside an LGPL classifier, and its source headers are
  LGPL-2.0-or-later.
- **casatools ships only cp312/cp313 wheels**: no Python 3.10/3.11/3.14,
  no Windows, no Linux aarch64.
- **The IDG GitLab "latest release" record is 0.7 (2020)** while tags reach
  1.3.0.
- **DP3's GitHub mirror shows a "v5.0, 2020" latest release.**
- **fits2idia's last release is 2022** although the repo is active.
- **The PyPI name `carta` is held by an unrelated GPL-3 package** (author
  "JaySec", 1.3.3, 2023-12-09), while carta-python is not on PyPI. This
  invites confusion and may be worth CARTA's attention (CARTA is not
  RATT; list only).
- **facetselfcal has no licence file.**
- **Aegean is AFL-3.0**, GPL-incompatible per the FSF as quoted by
  secondary sources; the FSF page was not reached.

## For the coordinator

### STATE paragraph

Ecosystem survey (big plan side task; read-only), 2026-10-30
([ecosystem-survey.md](ecosystem-survey.md)).

**What was surveyed.** Every KERN-10 package (38 source packages, Ubuntu
24.04), the MeerKAT tools outside KERN, CASA 6.7.6 and CARTA 6.0 were
assessed. Each got a licence, a release date and a verdict (PORT, DEPEND,
ORACLE, FORMAT or IGNORE).

**Findings.**
- Most of the ecosystem is an ORACLE for rang. Platform rules out
  DEPEND, not licence: almost nothing besides casacure, ducc0 and
  pure-Python packages has Windows wheels.
- CASA ships cp312/cp313 wheels for Linux x86_64 and macOS arm64 only.
- CARTA has no Windows build.
- The DEPEND list is casacure (pending E2), katdal/katsdptelstate (an
  optional `[meerkat]` extra for L3), katbeam, ducc0 as a test oracle,
  and carta-python as an optional notebook helper.
- CARACal's cross-calibration is CASA (`setjy`, `gaincal`, `bandpass`,
  `fluxscale`, `applycal`; `polcal`), not QuartiCal. A matched CARACal
  baseline therefore needs a CASA oracle container.
- In CASA, PKS 1934−638 is covered by Stevens-Reynolds 2016 and
  Perley-Butler 2010, not by Perley-Butler 2013/2017.
- KERN-10 ships WSClean 3.7, AOFlagger 3.5, IDG 1.2, casacore 3.7.1 and
  CASA 6.7.3 as debs, which makes it the DF0 oracle base.

**Recommendations.**
- An O-CASA oracle.
- Flux standards PORTed with `setjy` as the oracle.
- CASA caltable and H5parm FORMATs.
- katdal for L3.
- An AOFlagger second SumThreshold oracle.
- CASA gaincal in L5.
- A format table for DF-IO (22 formats).

### Plan additions (proposed tasks, owner files)

| Id | Task | Owns | After |
| --- | --- | --- | --- |
| O-CASA | CASA 6.7.6 oracle container (+ KERN-10 WSClean/AOFlagger), CARACal crosscal sequence by hand on LUNO 1934 four-station; archive tables and CORRECTED_DATA | `tools/oracles/casa/` (Dockerfile, run script), `research/o-casa.md`, `research/results/o-casa-*.json` | none; DF0 can share the base |
| FS1 | Flux standards SR2016, PB2010, PB2017 in the core, oracle `setjy` | `core/src/fluxstd.rs`, `python/rangtoy/fluxstd.py`, `tests/test_fluxstd.py`, `research/fs1-flux-standards.md` | O-CASA |
| DF-IO-CT | CASA caltable read/write through casacure, `applycal` round trip | `core/src/caltable.rs` or `python/rangtoy/io/caltable.py`, `research/df-io-caltables.md` | E2, O-CASA |
| DF-IO-H5 | H5parm subset read/write, losoto/DP3 round trip | `python/rangtoy/io/h5parm.py`, `research/df-io-h5parm.md` | DF0 |
| DF-IO-SKY | lsm/WSClean text/BBS read/write; DicoModel read with a restricted unpickler | `python/rangtoy/io/skymodel.py` (core reader later), `research/df-io-skymodels.md` | before L1-M |
| MK1 | `[meerkat]` extra: katdal loader into core arrays; katsdpcal solutions as comparator | `python/rangtoy/io/mvf.py`, `pyproject.toml` extra line, `research/mk1-katdal.md` | L3 data |
| A-FLAG | AOFlagger 3.5 Lua strategy vs task D archive | `tools/oracles/aoflagger/`, `research/a-flag-aoflagger.md` | DF0 base |
| NB-CARTA | optional CARTA helper and `[carta]` extra | `python/rangtoy/notebook/carta.py`, `research/nb-carta.md` | P12 (uses the `rang` name) |
| L5 addendum | CASA `gaincal` arm in L5's protocol | L5's own files | O-CASA |

Shared files for the coordinator:
- `upstream-notes.md`: add section 6.1 as "observed, not raised".
- `non-ratt-observations.md`: add section 6.3.
- `tool-timings.md`: add the line below.
- README research index: add one line.

### Tool runs and wall time

| Run | Wall |
| --- | --- |
| PPA `Sources.gz`/`Packages.gz` fetch and parse | < 5 s |
| GitHub API metadata for 75 repos (`gh api`, sequential) | about 3 min |
| PyPI JSON for 62 names (scratch script `pypi.py`) | about 40 s |
| Worktree venv (`uv venv -p 3.14` + editable install), background | 32 s |
| `tools/check-all.sh` (documents only; PASS: 23 + 60 Rust tests, ruff, 631 pytest passed, 3 skipped) | 533 s |

Total session wall time: 2026-10-30 14:29:47 to about 15:07 SAST, about 37 min; the exact end time is
recorded in the commit message. Scratch is in
`~/Build/tmp/20261030-survey/` (index files, parse scripts) and is deleted
at the end.
