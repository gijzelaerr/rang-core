# V8: an open replacement for CASA, a scoping note

Task V8 of [vision.md](vision.md) (section 8). Written 2026-11-12 on branch
`claude/v8-open-casa-a871c6` from `main` `91da8c3`, before E2 and E3 report:
no E2 or E3 acceptance number is used here.

**Status: proposed; nothing built or measured.** Every plan, tolerance and size
below is a proposal. The inventory states what `main` has at `91da8c3`, each
mark taken from the status line of the note cited. CARACal facts were read at
master `8f7bb363` (2026-09-14) on 2026-11-12. Where a fact was not confirmed,
the text says "not checked". The v0.2.0 critical path (E2 to E6) is not
touched: every piece below starts after v0.2.0 unless the owner says otherwise
(decision 1).

Owner direction, 2026-11-12, verbatim: "fuck casa, they make it impossible to
contribute. even now, years later. we should not even try. lets make the world
a better place by making a better CASA that is way more transparant and open to
contributions. lets replicate casa but make it better".

## 1. Recommendation in one paragraph

Grow `rang-core` task by task towards the CASA tasks that a MeerKAT continuum,
polarisation and time-series user actually runs, in the order CARACal's shipped
MeerKAT strategies call them, each port gated against CASA 6.7.6.14 run as an
oracle binary and never against CASA's source. The calibration core already
stands near CASA parity (C2a-C2e, C3a, C4, C6, C7, FS1/FS2), and imaging stands
at WSClean parity (G-series, DF1-DF2), which is the MeerKAT state of the art. So
**the largest gap is flagging**: CARACal calls `flagdata` more than any other
task (23 call sites in its workers), its crosscal `A` step and the full-Stokes
calibrator flagger are `flagdata mode='tfcrop'`, and rang replaced tfcrop with
its Tricolour port (C1 O1). The first three pieces are `flagdata` tfcrop, the
deterministic `flagdata` modes with `summary`, and `listobs`. All three are
ports with parity as the goal. None of them is novelty. Being better than CASA is
measured on transparency (receipts, oracles, documented numerics), on
contribution (public PRs, CI), on correctness (CASA's bugs become rang's tests)
and on cost and platforms, each item with a metric (section 4). CASA stays an
oracle in WSL and containers, and nothing goes back to NRAO.

## 2. Inventory: CASA tasks and tools against rang at `91da8c3`

Marks: **parity** means done at parity against CASA (or against the named oracle
where CASA is not the reference), with any post-hoc change labelled in its note.
**Partial** means part of the task exists, or its gate was not met as frozen.
**Missing** means nothing. "Oracle" is what the rang gate compared against.

### 2.1 Data in and out

| CASA | What rang has | Note, gate | Oracle | Mark |
| --- | --- | --- | --- | --- |
| `importasdm` | nothing. MeerKAT delivers MVFv4 and MS (via katdal), never ASDM | – | – | missing; not needed for MeerKAT |
| `importuvfits`, `exportuvfits` | nothing | – | – | missing (V6's FITS-IDI is the VLBI need) |
| MVFv4 to arrays (katdal, not CASA) | the `[meerkat]` extra, MVFv4 loader into `(row, channel, corr)` arrays | [mk1-katdal.md](mk1-katdal.md): (a), (b), (d) exact on a synthetic archive; (c) not runnable | katdal's own writers | partial (no public MVFv4 archive) |
| MS read (`ms`, `tb` tools) | Rust reader: Standard, Incremental, TiledShape, TiledColumn managers; zarr | [core-e-ms-reader.md](core-e-ms-reader.md), [sliced-read.md](sliced-read.md) | casacore | parity for those managers |
| MS write, new columns, `FLAG` | Rust table writer, write-back with flag backup | [w1-writeback.md](w1-writeback.md), [e3-table-writer.md](e3-table-writer.md) to [e6-table-writer-final.md](e6-table-writer-final.md), [ms-lock-windows.md](ms-lock-windows.md) | casacore, CASA, WSClean read-back | parity |
| calibration tables | read and write K, G, B, Df, T; bytes equal to CASA's except masked gaps | [dfio-formats.md](dfio-formats.md) (DF-IO) | CASA `applycal` bit-identical on rang's tables | parity |
| `flagmanager` | `.flagversions` save and restore | [dfio-formats.md](dfio-formats.md) (restored by `flagmanager`), `python/rang/formats/flagversions.py` | CASA `flagmanager` | parity for save and restore; `list`, `delete`, `rename` not checked |
| `concat`, `virtualconcat` | nothing | – | – | missing |
| `clearcal`, `delmod` | none as a command; W1 adds columns, G6 writes `MODEL_DATA` | [w1-writeback.md](w1-writeback.md), [g6-predict.md](g6-predict.md) | – | missing (small) |
| `importfits`, `exportfits` | GeMClean writes FITS directly; no CASA image (PagedImage) read or write | [g8-wheel.md](g8-wheel.md) | WSClean FITS | partial: FITS only |

### 2.2 Inspection

| CASA | What rang has | Note, gate | Oracle | Mark |
| --- | --- | --- | --- | --- |
| `listobs` | the reader's metadata, used inside `rang-core config check` (preflight) and `research ms`. No summary command | [w2-commands.md](w2-commands.md), [w4-unsupported.md](w4-unsupported.md) | – | missing as a task |
| `flagdata mode='summary'` | flag statistics in the notebooks (`python/rang/notebook/flags.py`); no command | – | – | partial (no per-axis summary, never compared with CASA's) |
| `plotms`, `plotcal`, `plotbandpass` | notebook plots only | [d2-notebook.md](d2-notebook.md) | – | missing (CARACal uses shadeMS and ragavi, not CASA, for most plots) |
| `imstat`, `imhead` | image statistics inside the G-series comparison scripts, no command | [g4-masks.md](g4-masks.md), [g7-defaults.md](g7-defaults.md) | WSClean | missing as a task |
| viewer | CARTA from a notebook | [nb-carta.md](nb-carta.md) | – | not CASA's to replace (CARTA is open) |

### 2.3 Flagging

| CASA `flagdata` mode | What rang has | Note, gate | Oracle | Mark |
| --- | --- | --- | --- | --- |
| `extend` | `core/src/flag_extend.rs`, run as `calibrate.polcal.extendflags` | [e0-refant-extend.md](e0-refant-extend.md): FLAG bit-identical to CASA on every case; rule coverage met only by a post-hoc case | CASA `flagdata` | parity |
| `tfcrop` | nothing. C1 O1 replaced it by the Tricolour port in the A step; O2 left it out on the Xf table | [c1-calibration-chain.md](c1-calibration-chain.md) O1, O2; [c2e-calibrate.md](c2e-calibrate.md) ("not comparable by design") | – | **missing** |
| `rflag`, `clip`, `antint` | nothing (Df's `clip` key is a solution clip, not `flagdata clip`) | – | – | missing |
| `manual` (antenna, spw/channel, frequency ranges, uvrange, field, scan, timerange), `autocorr` | `flag.static_masks` (Tricolour's two masks), `flag.fields` | [core-d-tricolour.md](core-d-tricolour.md) | Tricolour | partial: masks only, no CASA selection |
| `shadow`, `quack`, `elevation`, `unflag` | nothing | – | – | missing |
| automatic RFI (not CASA) | Tricolour 0.2.1 port, flag for flag on four controls; SumThreshold kernel against AOFlagger 3.5 | [core-d-tricolour.md](core-d-tricolour.md); [a-flag-aoflagger.md](a-flag-aoflagger.md) (kernel level; against the shipped binary not met as frozen, an AOFlagger defect, filed as aoflagger#45) | Tricolour, AOFlagger | parity with Tricolour; partial with AOFlagger (kernel, not the `firstpass_QUV` strategy) |

### 2.4 Calibration

| CASA | What rang has | Note, gate | Oracle | Mark |
| --- | --- | --- | --- | --- |
| `setjy` | PB2010, Baars, SR2016, `manual` ≤ 1.6e-14 relative, MODEL_DATA bit-identical in float32; PB2017 4 of 20 sources regular, 16 opt-in; `.lsm` through Crystalball | [fs1-flux-standards.md](fs1-flux-standards.md), [fs2-casarundata.md](fs2-casarundata.md), [c3a-models.md](c3a-models.md) (every frozen comparison passes) | CASA `setjy`, Crystalball | parity for MeerKAT's calibrators; PB2013, Scaife-Heald, solar-system and image models missing |
| polarised models (`setjy` with `polindex`, `polangle`, `rotmeas`) | tabular 0 ulps, `spix` 2 ulps | [c7a-polmodels.md](c7a-polmodels.md) | CASA | parity |
| `gaincal` G (`ap`, `p`, `a`) | class A against QuartiCal met; against CASA the slice met first time; A1 met after two post-hoc fixes, but solution `TIME` misses 0.01 s by up to 0.054 s on RFI-flagged scans, and `combine='scan'` differs by about 1 % | [c2a-gain.md](c2a-gain.md) | CASA `gaincal`, QuartiCal 0.2.7 | partial |
| `gaincal` K | as `delay_and_offset`: C2b's fourteen CASA cases pass after three labelled post-hoc changes | [c2b-delay.md](c2b-delay.md), [c2c-bandpass.md](c2c-bandpass.md) | CASA, QuartiCal | parity, post hoc |
| `gaincal` T, GSPLINE, `solmode` L1/R | nothing (T is read and applied, not solved) | [dfio-formats.md](dfio-formats.md) | – | missing |
| `bandpass` B (`fillgaps`, `solnorm`) | B met; the chain K, G, B met on the composite, not term by term | [c2c-bandpass.md](c2c-bandpass.md) | CASA | parity on the composite; BPOLY missing |
| `fluxscale` | class B and C met, `fluxd` and F tables bit-identical on 10 of 12 frozen and 3 of 4 held-out cases after two post-hoc ports; fit errors at `fitorder=2` up to 2.6e-5 against 1e-6 | [c2d-fluxscale.md](c2d-fluxscale.md) | CASA | partial |
| `polcal` Xf, Df; `gaincal` KCROSS; Gpol | P, class T and C met; class B and chain not met as frozen; wired bit-identical to the library, χ within 0.003° of CASA's chain; Gpol class B 0.108° against 0.1° on LUNO | [c6-polterms.md](c6-polterms.md), [c6w-polwire.md](c6w-polwire.md), [e2-average-freq.md](e2-average-freq.md) | CASA `polcal`, `gaincal` | partial |
| `polcal` D, Dflls, Xfparang+QU, Df+QU; `polfromgain` | nothing (CARACal's polcal worker calls all of them in its other strategies) | – | – | missing |
| refant `auto` | CARACal's `get_refant`, reimplemented | [e0-refant-extend.md](e0-refant-extend.md) | CARACal | parity where CARACal's function runs |
| `applycal` | K, G, T, B, Df in memory; MS write-back, `calwt`, field maps; polarisation apply | [c4a-apply.md](c4a-apply.md) (class C not met on every case), [c4b-apply-ms.md](c4b-apply-ms.md) (frozen run failed; held-out passed after three post-hoc ports), C7b in [c6w-polwire.md](c6w-polwire.md) | CASA `applycal` | partial (held out met, frozen not) |
| solve pre-averaging | `calibrate.average_time`, `average_freq` | [e2-average-time.md](e2-average-time.md), [e2-average-freq.md](e2-average-freq.md) | CASA | parity except Gpol |
| `smoothcal`, `gencal`, `fringefit` | nothing (`fringefit` is V6's first piece) | [v6-vlbi-scope.md](v6-vlbi-scope.md) | – | missing |
| self-calibration (CASA's `gaincal` loop, CARACal's CubiCal) | `rang-core selfcal`: solves equal QuartiCal's; full-loop truth gate not met (model absorption) | [c5-selfcal.md](c5-selfcal.md), [c5b-selfcal-masks.md](c5b-selfcal-masks.md) | QuartiCal | partial |

### 2.5 Data manipulation

| CASA | What rang has | Note, gate | Oracle | Mark |
| --- | --- | --- | --- | --- |
| `split`, `mstransform` (field, scan, spw selection; `timeaverage`, `chanaverage`; `datacolumn`; `keepflags`; `docallib`) | in-memory only: scan selection (W6), averaging inside the solves, `image.average_channels`, `data.memory_limit_gb` chunking; no new MS is written | [w6-imaging-inputs.md](w6-imaging-inputs.md), [w3-chunking.md](w3-chunking.md) | CASA (solves only) | missing as a task |
| `mstransform` `regridms`, Doppler, `hanning`, `combinespws` | nothing | – | – | missing (spectral line) |
| `initweights` (`wtmode='ones'`) | `data.weights: uniform`, in memory, not written | [w6-imaging-inputs.md](w6-imaging-inputs.md) | – | partial |
| `statwt` | nothing | – | – | missing |
| `uvsub` | nothing as a command (`MODEL_DATA` is written, G6) | [g6-predict.md](g6-predict.md) | – | missing (small) |
| `uvcontsub` | nothing | – | – | missing (spectral line) |
| `fixvis`, `phaseshift` | nothing | – | – | missing |

### 2.6 Imaging and image analysis

| CASA | What rang has | Note, gate | Oracle | Mark |
| --- | --- | --- | --- | --- |
| `tclean` (standard and w-projection gridders; Högbom, multiscale; MFS spectral fit; masks; Stokes IQUV; weighting; taper; uv range; model write-back) | GeMClean: exact wgridder, Briggs weighting, multiscale, joined channels with spectral fits, FITS and automatic masks, IQUV and joined polarisations, `MODEL_DATA`, the restoring beam as WSClean 3.7 fits it | [df1-wgridder.md](df1-wgridder.md), [df2-wgridder-speed.md](df2-wgridder-speed.md), G2-G9 ([g2-memory.md](g2-memory.md) to [g9-stokes.md](g9-stokes.md)): G3 one held-out MFS bound failed, G4 restoring beam and two mask items not met as frozen, G9 held-out C, D, E not met as frozen | **WSClean 3.7**, not `tclean` | partial: at WSClean parity, never compared with `tclean` |
| `tclean` `mtmfs`, `mosaic`, `awproject`, cubes in LSRK | nothing | [ecosystem-survey.md](ecosystem-survey.md) 3.2 | – | missing |
| `widebandpbcor`, `impbcor` (primary beam) | research beam models only (katbeam, holography) | [katbeam-pointing.md](katbeam-pointing.md), [beam-model-selection.md](beam-model-selection.md) | – | missing as a task |
| `imfit`, `immath`, `imsubimage`, `imregrid`, `imsmooth` | the restoring-beam fit only | [g7-defaults.md](g7-defaults.md) | WSClean | missing |
| `ft`, `predictcomp` | component predictor, `MODEL_DATA` predict | [g6-predict.md](g6-predict.md), [c3a-models.md](c3a-models.md) | WSClean `-predict`, Crystalball | parity |

### 2.7 Tools (the `casatools` layer)

| CASA tool | What rang has | Note | Mark |
| --- | --- | --- | --- |
| `measures` (`me`) | parallactic angle (astropy, geodetic) and CASA's frame as `calibrate.polcal.frame: casa`; observatory positions from casacore-data; no frame-conversion API, no UVW computation | `python/rang/measures.py`, [b1-2-identifiability.md](b1-2-identifiability.md), [c6-polterms.md](c6-polterms.md) | partial |
| `imager` (`im`), `simulator` (`sm`) | `gemclean`; simulated truth MSs with seeds (MeerKAT layouts) | [a1-simtruth.md](a1-simtruth.md) | partial |
| `calibrater` (`cb`) | the Python functions `rang.cal_*` and `rang-core calibrate` | [c2e-calibrate.md](c2e-calibrate.md) | partial (as 2.4) |
| `table` (`tb`), `ms` | the Rust reader and writer; Python wrappers | as 2.1 | parity for MS and calibration tables |
| `image` (`ia`), `coordsys` (`cs`) | FITS via astropy in Python | – | missing (CASA image tables) |
| `msmetadata` (`msmd`) | the reader's metadata, not a public API | – | partial |

### 2.8 Time series

CASA has no pulsar or FRB tasks; its time-domain path is `tclean` per interval
and `plotms`. V1 ([v1-timeseries-scope.md](v1-timeseries-scope.md)) proposes
P1, residual 8 s snapshot light curves against WSClean `-intervals-out` and an
exact DFT. Nothing in V8 replaces that; a CASA user's snapshot imaging maps to
V1's P1 when it exists.

## 3. Priority: what MeerKAT users need first

Evidence: the CASA cabs called in CARACal's workers at `8f7bb363`, and which
workers its three shipped MeerKAT configurations enable
(`meerkat-defaults.yml`, `meerkat-continuum-defaults.yml`,
`meerkat-fullStokes-continuum-defaults.yml`).

| CASA task | Call sites (workers) | Enabled in the shipped MeerKAT configs |
| --- | ---: | --- |
| `flagdata` | 23 (flag 11, polcal 10, crosscal 1, polimg 1) | all three: `flag_autocorr`, `flag_spw` (frequency ranges), `flag_mask` with `uvrange`, `flag_shadow` (full Stokes); `flag_rfi` with `flagger: tfcrop` (full Stokes) or AOFlagger `firstpass_QUV.rfis` (the other two); crosscal `A` is `tfcrop` (in `KGBAKGB` of `meerkat-defaults.yml`); polcal `extendflags: true`, `tfcrop` and `clip` on the cross-hand tables |
| `gaincal` | 11 (polcal 8, crosscal 3) | all three |
| `polcal` | 10 | full Stokes |
| `applycal` | 7 | all three |
| `mstransform` | 5 (transform 4, line 1) | all three: `split_field` of calibrators and of the target with `otfcal` (`docallib`), optional time and channel averaging |
| `setjy` | 5 | all three (`meerkat_skymodel: true`) |
| `listobs` | 3 | all three (`obsconf`) |
| `fixvis` | 3 | not in the shipped configs (prep option) |
| `importfits`, `exportfits`, `imregrid` | 4, 2, 2 | mask worker, disabled in all three |
| `plotms` | 2 | `inspect` (most plots are shadeMS and ragavi) |
| `clearcal`, `concat`, `bandpass`, `fluxscale`, `fringefit`, `polfromgain`, `clean` | 1 each | `bandpass`, `fluxscale` in all three; `clean` only in the line worker; `fringefit` as crosscal term `S` |
| `initweights` | through `casa_script` | all three (`prep.specweights: uniform`) |

Self-calibration and imaging in all three configs are CubiCal and WSClean, not
CASA; `uvcontsub`, `statwt` and Hanning smoothing are not called by name
anywhere in the workers (the line worker's `douvcontsub` is an `mstransform`
option). That puts **`tclean` low** for MeerKAT continuum: WSClean is what
MeerKAT users run, and GeMClean already gates against it.

Order of the missing and partial pieces (MeerKAT first, LOFAR noted):

1. **`flagdata tfcrop`**: CARACal's A step, its full-Stokes calibrator
   flagger and its polcal table flagging; C1 O1 is the largest departure from
   CARACal in rang's chain. LOFAR: AOFlagger, not tfcrop.
2. **Deterministic `flagdata` modes and `summary`**: `manual` with CASA's
   selection syntax, autocorrelations, `shadow`, `quack`, `elevation`,
   `unflag`; every shipped config uses some of them.
3. **`listobs`**: in every config, and the first thing a CASA user types.
4. **`split`/`mstransform` to a new MS**: field, scan and channel selection,
   time and channel averaging, `datacolumn`, with calibration on the fly.
   Needed at MeerKAT's 4096 and 32768 channels to cut volume. LOFAR:
   averaging and multi-subband concatenation are also DP3's job (V7).
5. **`polcal` D, Dflls, Xfparang+QU, Df+QU and `polfromgain`**: CARACal's
   strategies for calibrators with unknown polarisation.
6. **`initweights` and `statwt` written to the MS; `uvsub`; `clearcal`;
   `fixvis`/`phaseshift`; `concat`**: small, used occasionally.
7. **Primary-beam correction** (`widebandpbcor`): needed for science-grade
   fluxes off axis; MeerKAT beams are katbeam or EIDOS (holography), and LOFAR
   needs EveryBeam (V7 decision 3).
8. **Image analysis** (`imstat`, `imfit`, `immath`, `imsubimage`): CARACal
   uses aimfast and PyBDSF, not CASA; useful as a small Python layer.
9. **Inspection plots** (`plotms`-like): CARACal uses shadeMS and ragavi, which
   are open; a wrapper, not a port.
10. **Spectral line** (`uvcontsub`, Doppler regridding, cubes) and **CASA image
    tables**: out of continuum scope; after an owner decision.
11. **`importasdm`, `importuvfits`, `fringefit`, `gencal`**: not MeerKAT
    (VLA, ALMA, VLBI); `fringefit` belongs to V6.

## 4. What "better" means, measurably

All proposed; none of these is measured yet. Each item gets its metric and the
oracle or check that decides it.

| Axis | What rang promises | Metric | How it is checked |
| --- | --- | --- | --- |
| Transparency | every result has a receipt and an oracle; the numerics are written down | every task marked "parity" in section 2 names a research note with a frozen tolerance, an oracle and a result archive; every command run writes a receipt (W4-1) | a CI test over a task table (proposed `docs/casa-tasks.md`) that fails when a "parity" row has no note or no archive |
| Transparency | deliberate differences from CASA are public | a docs page lists each one with its reason and test | page exists; each entry links a test |
| Contribution | anyone can contribute: PR route ([CONTRIBUTING.md](../CONTRIBUTING.md), [docs/contributing.md](../docs/contributing.md)), task procedures ([docs/agents/](../docs/agents/index.md)) with skill wrappers, CI (`tests`, `docs`, `wheels`) on every pull request | first outside pull request merged; median time to first review; CI green on Linux and Windows for every merged PR | GitHub history. CASA has no public tracker: U5's tickets needed a login at help.nrao.edu |
| Correctness | a CASA bug found becomes rang's test, not behaviour rang copies | each CASA defect in [casa-silent-failures.md](upstream-issues/casa-silent-failures.md) and [casa-wheel-packaging.md](upstream-issues/casa-wheel-packaging.md), and the casadocs error of [casadocs-flux-standards-1934.md](upstream-issues/casadocs-flux-standards-1934.md), has a rang test that fails if rang behaves the same way | `pytest`; the docs page lists the difference |
| Cost | speed and memory | wall time and peak RSS against CASA on the same host and data, `-j1` and `-j16`, in [tool-timings.md](tool-timings.md) | measured per task; a claim of "materially lower" only from a frozen protocol (AGENTS.md) |
| Platforms | native Windows, Linux, macOS (x86-64 and arm64) | the five wheel platforms of [g8-wheel.md](g8-wheel.md) pass each new task's tests | `wheels` CI. CASA ships no Windows wheels (U5, skipped list) |
| Install | a Python API without a monolithic install | `pip install rang-core` size and dependency count against `casatools`+`casatasks`+`casarundata` | measured once (not measured yet); U5 row 25: CASA's manylinux_2_34 wheel does not import on Ubuntu 24.04/26.04 |

**Novelty rule (AGENTS.md).** A reimplementation of a CASA task is not novelty,
and a win against CASA alone is not one either when CASA is not the state of
the art for that job. For MeerKAT imaging the state of the art is WSClean (and
DDFacet for DD), and for MeerKAT gain solves it is QuartiCal: beating `tclean`
or `gaincal` claims nothing. Therefore:

- **Parity is the goal** for every task in section 3: `flagdata`, `listobs`,
  `split`/`mstransform`, `polcal` modes, `initweights`, `statwt`, `uvsub`,
  image statistics. A port that also runs faster records the times as resource
  measurements, not as a claim.
- **Where rang must beat the state of the art to claim anything:** flagging
  quality at matched cost against AOFlagger and Tricolour (the null F1-F3
  record says this is hard), calibration quality against QuartiCal and CASA at
  matched cost, imaging against WSClean (GeMClean is faster than the fastest
  WSClean setting on the speed run's sets at `-j 16`, by 1.05-2.91 ×, but uses
  2.0-3.6 × WSClean's memory on the pilot; no novelty claimed:
  [gemclean-speed.md](gemclean-speed.md), [g2-memory.md](g2-memory.md)).
  Each goes through [propose-and-measure](../docs/agents/propose-and-measure.md).

## 5. CASA's role from now on

- **An oracle binary only.** CASA 6.7.6.14 runs in WSL or in the pinned image
  `rang-o-casa:6.7.6.14` ([o-casa.md](o-casa.md)), as now. It is never a
  contribution target: no reports, tickets, patches or mail to NRAO.
- **U5 rows 24 and 25** (the two helpdesk tickets) are marked "not sent, owner
  decision 2026-11-12: no contributions to CASA" in
  [u5-manifest.md](upstream-issues/u5-manifest.md) and
  [u5-upstream.md](u5-upstream.md). Their texts stay as the record of CASA's
  defects that rang tests against (section 4). Row 23, casadocs#205, was
  already filed on 2026-11-12; whether it stays open is decision 4.
- **Licence.** rang is GPL-3.0-or-later. CASA is distributed under the GPL
  (per the brief); the exact version and terms are **not checked**:
  [docs/licence.md](../docs/licence.md) says "CASA's licence not checked", and
  U5 row 25 found the wheel's licence metadata contradicts itself. So:
  - reimplement from behaviour (the oracle's outputs), CASA's documentation and
    the papers, as FS1, C2a-C2d and C4 did;
  - copying or translating CASA source needs the licence check E5-33 used for
    CARACal and msutils first: read the licence file at the pinned commit,
    decide "translated" or "reimplemented", and record it in
    `docs/licence.md`;
  - that check is already owed: `core/src/flag_extend.rs` follows
    `FlagAgentExtension::computeAntennaPairFlags` "operation by operation"
    (`docs/licence.md` line 33). Decision 5.
- **Deliberate differences go in a docs page** (proposed
  `docs/casa-differences.md`, with the first piece). Entries known today:
  Tricolour in place of tfcrop in the A step (C1 O1, until piece 1 lands);
  Df's `min_data_fraction` (rang's rule, off by default); KCROSS's `refined`
  estimator option; `calibrate.polcal.frame: rang`; rang's FS2 opt-in list for
  PB2017's 16 irregular sources. Each U5 CASA defect becomes an entry once its
  test shows which way rang goes. One is open: whether rang's K applies
  `minblperant` (C2b matched CASA's flags and refant rule, so rang may share
  CASA's behaviour; **not checked**).

## 6. Shape and naming

**Packages.** `rang-core` grows: every task in section 3 needs the same reader,
writer, chunking, receipts and Rust kernels, and the five-wheel CI already
covers it. Split a package off only when it brings a dependency `rang-core`
must not carry: plotting (shadeMS-like inspection with its plotting stack) as
`rang-inspect` or an extra, LOFAR's EveryBeam (V7), spectral-line cubes. Do not
call anything "CASA" in a package or command name; ra-ng stays the name, and
"CASA task X" appears only in the mapping (decision 6).

**Commands and API.** rang's model is one config and stage commands
(`rang-core flag`, `calibrate`, `apply`, `image`, `selfcal`, `run`); CASA's is
one call per task with many keywords. Proposed, both:

1. New stage verbs where a task is a stage (`rang-core listobs MS`,
   `rang-core flag` with CASA-mode sections, `rang-core split`).
2. A thin compatibility layer, `rang.tasks`, whose functions take CASA's
   keyword names (`flagdata(vis=..., mode='tfcrop', ...)`) and translate them
   to rang's config. Any keyword or value rang does not implement is refused
   with a clear error (the W4 rule), never ignored, and every call writes a
   receipt.

Mapping (to live in the migration doc; "proposed" rows do not exist yet):

| CASA task | rang | State |
| --- | --- | --- |
| `listobs` | `rang-core listobs` | proposed (piece 3) |
| `flagdata` `tfcrop` | `rang-core flag` with `flag.flagger: tfcrop` | proposed (piece 1) |
| `flagdata` `manual`, `shadow`, `quack`, `elevation`, `unflag`, `summary` | `rang-core flag` sections; `rang-core flag --summary` | proposed (piece 2) |
| `flagdata` `extend` | `calibrate.polcal.extendflags` | exists |
| `flagmanager` | `rang.formats.flagversions`; `flag.write` with backup | exists |
| `setjy` | `calibrate.model.source: setjy` (`standard`), `manual`, `lsm` | exists |
| `gaincal` G, K, KCROSS; `bandpass`; `fluxscale`; `polcal` Xf, Df | `calibrate.*.terms` with `type: G, K, B, F, Gpol, KCROSS, Xf, Df` | exists |
| `applycal` | `rang-core apply` | exists |
| `split`, `mstransform` | `rang-core split` | proposed (priority 4) |
| `tclean` | `rang-core image` / `gemclean` (WSClean-style options) | exists (WSClean parity) |
| `ft` | `image.write_model`, `rang.core_model.write_model_data` | exists |
| `exportfits` | not needed: FITS is written directly | exists |

**Migration doc** (proposed `docs/casa-migration.md`, with piece 3): the
mapping above; how a CARACal or CASA script becomes one `rang-core` config,
worked on the LUNO 1934−638 slice; the differences page; what is refused and
why. It is written when the first command it describes exists, so it never
documents something that is not there.

## 7. First three pieces (proposal outlines, to freeze later)

All three are ports with parity as the goal and claim no novelty. All run after
v0.2.0 (E6) unless the owner moves piece 3 earlier: it reads only, adds one
command and touches no code E2 or E3 uses (decision 1). Data stays on
`D:\rang`; CASA runs in `rang-o-casa:6.7.6.14`. Before freezing, each reads
CASA's documentation for its task (casadocs 6.7) and checks the behaviour on a
probe MS, not CASA's source (section 5).

### Piece 1: `flagdata mode='tfcrop'`

- **Hypothesis.** A Rust tfcrop gives CASA 6.7.6.14's flags on visibilities
  and on calibration tables (CARACal's settings: `timecutoff=4`,
  `freqcutoff=3`, `ntime='60s'`, `combinescans`, `usewindowstats='both'`,
  `datacolumn` `corrected`, `CPARAM`), within the tolerance below, at no more
  than CASA's wall time and memory.
- **Oracle.** CASA `flagdata` 6.7.6.14.
- **Data.** Development: A1 simulated truth with injected RFI
  ([a1-simtruth.md](a1-simtruth.md)) and the LUNO 1934−638 slice
  ([o-casa.md](o-casa.md)); CARACal's Xf table from the C6 runs. Held out,
  opened once after the development gate passes: one LUNO scan not used in
  development, and the ESO137 primary scan.
- **Gate (proposed).** Per cell, FLAG equal to CASA's on ≥ 99.99 % of cells per
  case, and every differing cell attributed to a test value within 1e-6
  relative of its cutoff (float order), as A-FLAG attributed its differences;
  zero unattributed cells. Flag fractions per baseline within 1e-4 absolute.
  Wall time and peak RSS against CASA at `-j1` and `-j16`, recorded.
- **Then.** Put tfcrop back in the A step as an option and rerun C2e's
  comparison of the chain with CASA's A, which C1 O1 made "not comparable by
  design"; whether it becomes the default is an owner decision after the
  measurement.
- **Size.** Three to four agent sessions (docs and protocol 1; kernel and
  wiring 1-2; runs and write-up 1); about 1,000 lines of Rust and Python;
  heavy-lock time under an hour.

### Piece 2: the deterministic `flagdata` modes and `summary`

- **Hypothesis.** `manual` (antenna, spw with channel and frequency ranges,
  uvrange, field, scan, timerange, `autocorr`), `shadow`, `quack` (all four
  `quackmode`s), `elevation`, `unflag` and `summary` give CASA's flags and
  counts exactly.
- **Oracle.** CASA `flagdata`; CASA's selection-syntax documentation for the
  parser.
- **Data.** A synthetic MS from rang's writer with edge cases at every
  selection boundary (channel edges, frequency on a channel boundary, a
  shadowed pair, scans shorter than `quackinterval`, elevation through the
  limit); the LUNO slice; CARACal's three configs' flag sections as the case
  list. Held out: the SKA pointing-scan MSs of
  [measurement-set-inspection.md](measurement-set-inspection.md).
- **Gate (proposed).** FLAG bit-identical on every case; `summary` counts
  equal; a selection rang does not support is refused before anything is
  written (the W4 rule). `elevation` and `shadow` depend on measures:
  differences allowed only for cells within 1e-6° of the limit (shadow:
  1e-6 m), counted and listed.
- **Size.** Two to three sessions; about 800 lines, mostly Python (the
  selection parser) over a small Rust kernel; light, no heavy lock.

### Piece 3: `listobs`

- **Hypothesis.** `rang-core listobs MS` reports what CASA's `listobs` reports
  (observation, scans with times and fields, field directions, spectral
  windows, sources, antennas with positions) from rang's reader, and in JSON
  for agents.
- **Oracle.** CASA `listobs` (its `listfile` text and returned record).
- **Data.** The MSs already used: LUNO slice, A1, the SKA pointing scans, an
  E2-converted MS's metadata (read only, after E2 is done).
- **Gate (proposed).** Every value in CASA's returned record equal (times to
  1 ms, directions to 1e-3 arcsec, frequencies to 1 Hz, counts exactly);
  text layout not compared.
- **Size.** One to two sessions; about 400 lines of Python; light. It fits
  before v0.2.0 if the owner wants it there.

## 8. Owner decisions

1. **When.** All three pieces after v0.2.0 (recommended), or piece 3
   (`listobs`, read-only, one command) alongside E2-E6 as a light task.
2. **Order.** Pieces 1-3 as in section 7 (flagging first), or another order
   from section 3 (for example `split` before `listobs`).
3. **tfcrop in the A step.** After piece 1, CASA's tfcrop as the A step's
   default (CARACal's behaviour) or kept as an option with Tricolour the
   default (C1 O1 today).
4. **casadocs#205** (U5 row 23, filed 2026-11-12 on a CASA project): leave it
   open, or withdraw it under "no contributions to CASA".
5. **Licence.** Commission the CASA licence check now (it is already owed for
   `flag_extend.rs`), or only before the first port that would read CASA
   source; and whether ports read CASA source at all, or only its behaviour
   and documentation.
6. **Shape.** `rang-core` grows (recommended), new packages only for heavy
   dependencies; and whether to build the CASA-keyword layer `rang.tasks`
   (section 6) or stage verbs only.
7. **Scope edge.** Whether spectral line (`uvcontsub`, Doppler regrid, cubes)
   and CASA image tables are in scope at all, or left to CASA and other tools.

## 9. Sources (read 2026-11-12)

- CARACal master `8f7bb363876f5f0daecbf2167c36bb597c7e5160` (2026-09-14),
  cloned blob-less into the session scratchpad and deleted: `caracal/workers/*.py`
  (cab calls counted with `grep -ohE '"cab/[a-z_0-9]+"'`; per-worker counts),
  `crosscal_worker.py` `RULES` (A = `flagdata tfcrop`, S = `fringefit`),
  `prep_worker.py` (`initweights` through `casa_script`), `transform_worker.py`
  (`mstransform` keys), `schema/flag_schema.yml` (`flagger` enum: aoflagger,
  tricolour, tfcrop), and the three MeerKAT sample configurations.
- rang notes cited in sections 2-7, read at `main` `91da8c3`; CASA task list
  and verdicts from [ecosystem-survey.md](ecosystem-survey.md) section 3.2
  (casadocs 6.7, accessed 2026-10-30); CARACal's chain from
  [c1-calibration-chain.md](c1-calibration-chain.md).
- U5 texts: [casa-silent-failures.md](upstream-issues/casa-silent-failures.md),
  [casa-wheel-packaging.md](upstream-issues/casa-wheel-packaging.md).
- No CASA source was read for this note, and no CASA task was run.

## 10. For the coordinator

- Branch `claude/v8-open-casa-a871c6`: this note; `vision.md` section 8 (the
  owner's words, dated) and a V8 row in section 7; a README line; U5 rows 24-25
  marked "not sent, owner decision 2026-11-12: no contributions to CASA" in the
  manifest, `u5-upstream.md`, both CASA texts' status lines and
  `non-ratt-observations.md`. Nothing built.
- STATE paragraph: "V8, 2026-11-12 (proposed; [v8-open-casa.md](v8-open-casa.md)):
  owner direction to build an open CASA replacement. Inventory of the CASA tasks
  MeerKAT users run against rang at 91da8c3: calibration near CASA parity,
  imaging at WSClean parity, flagging the largest gap (CARACal's 23 `flagdata`
  call sites; tfcrop replaced by Tricolour in C1 O1). First pieces proposed:
  `flagdata` tfcrop, the deterministic `flagdata` modes with `summary`,
  `listobs`, all ports, after v0.2.0. CASA stays an oracle binary; the two U5
  helpdesk tickets will not be sent. Seven owner decisions."
- Plan line: "V8 done 2026-11-12 (`v8-open-casa.md`): scoping only; seven
  owner decisions."
- Checks run: docs link check of the changed files; the full
  `python -m rang.check` was not run (research and docs text only; the host is
  E2's).
