# Rang research state

DF1 exact gridder (big plan; [df1-wgridder.md](df1-wgridder.md)),
2026-10-30 (implemented; measured): a Rust port of ducc0 0.42's wgridder
(`core/src/wgridder.rs`, `ffi_wgridder.rs`, `core_wgridder.py`), f32 and f64,
both directions, ducc0's 939-row kernel table and a thread-free kernel
choice. All five gated criteria pass as frozen: against a float64 DFT ≤ 10 ε
(worst 4.0e-5 at f32 1e-4, 4.1e-8 at f64 1e-7), against ducc0 ≤ ε
(1e-12–1e-14 in f64 away from the field edge; up to 1.7e-10 in the outermost
pixels of a 0.3 rad field, cause not identified), adjoint to 4.2e-13,
bit-identical at 1–16 threads, kernel table and choices equal to ducc0's.
Item 0 of the DDFacet study is attributed: the core w-stacking image's 19 %
difference from the DFT on the LUNO slice is aliasing of WSClean's
Kaiser–Bessel kernel at padding 1.2 (reproduced to 98.9 % by an aliasing
prediction; 2.1e-5 at padding 2 with kernel 15) plus a pixel mis-map in the
study's search; no defect in `grid.rs`, which reproduces WSClean faithfully,
aliasing included. Through the exact gridder the C/I/K images move by 19–32 %
of the peak at the edge and 0.3–0.6 % inside; task I's response fractions move
by up to 0.036 (no sign changes); the campaigns' held-out decisions do not
depend on the images. Cost: 0.13–0.16 s per four-station image at 16 threads
(w-stacking 0.38–0.41 s, ducc0 0.06 s), but 3.7–4.4× slower than ducc0 per
visibility on one thread, so whole-array use needs the gridding loop
optimised first (DF2). The K replay could not be re-measured because the task
K fetch copy was deleted (re-fetchable).

P7 architecture (big plan wave 2), 2026-10-30 (implemented; measured;
[p7-architecture.md](p7-architecture.md)): the ctypes path and the
import-time cargo build are gone; the root crate's kernels (TV, projector and
survey with the P4 eigensolver, the pointing toy) live in the extension;
`tests/test_core_backends.py` is extension-against-archive (golden archive
recorded under both old backends, identical bytes); every C function has
`catch_unwind` (a panic returns an error code instead of aborting); the GIL is
released around kernels (two predictor calls overlap, 0.92–1.12× one call;
rayon's shared pool still serialises concurrent solver calls); the Tricolour
pack/unpack is parallel (24–32 ms → 4.5–5 ms at 16 threads, flags identical);
`solve_complex` takes bool or uint8 flags without a copy; the static masks
ship as package data. Wheel-only acceptance: a wheel from
`tools/wheel/build.py` installed with cargo absent reproduces every archived
verdict (phase 1/2 validators, section 6, the actions/B/C/D/E/I comparators,
task F, K precondition, trend, signal, the notebooks), 58 arrays and 60 FITS
HDUs byte-equal. Native Windows: 622 passed, 43 skipped with reasons, 0
failed; the libm-based kernels differ from Linux by at most 2.6e-15 relative,
so the golden test is exact on Linux x86_64 and tolerant elsewhere.
`RANG_CORE_LIB` and `rangtoy.build()` no longer exist; `core.library()` and
`backend_name()` remain as compatibility names meaning the extension.

Big plan task A1 (RFI-band audit), 2026-10-30 (implemented; measured;
explanation only; [a1-rfi-audit.md](a1-rfi-audit.md)). Reran the Tricolour
port with per-step stages on L1 and L2, reproducing the archived additions,
splits and invalid-prediction counts exactly. The station-bins the CARACal
first pass empties are exactly the campaigns' lost gain bins: 691 on 1934−638
and 122 on 1830−211. All of them are in static-mask blocks, 682/691 and
122/122 on the GNSS carriers (1176, 1207, 1268, 1279 MHz); none is in
1304–1498 MHz. They are the long-baseline residue (median 5 training samples,
99.6 % already input-flagged) that SumThreshold removes; mild and a mask-free
first pass empty the same blocks, they persist over all dumps, and the
strategy also flags 99 % of the held-out cells there. RFI excision as
intended; supports U2's not filing. Proposal for L4, L1-M and C1:
pre-register dropping the emptied bins' held-out samples, computed after the
split and before any solve (0.02 % of held-out samples), with the
matched-sample rule as fallback. One question for the CARACal and Tricolour
maintainers (in `upstream-notes.md`): the first pass's all-baseline static
mask is discarded by the next replace-semantics step.

Ecosystem survey (big plan; read-only), 2026-10-30
([ecosystem-survey.md](ecosystem-survey.md)): every KERN-10 package (38
source packages, Ubuntu 24.04), the MeerKAT tools outside KERN, CASA 6.7.6
and CARTA 6.0 assessed with licence, release date and a verdict (PORT,
DEPEND, ORACLE, FORMAT, IGNORE). Most of the ecosystem is an ORACLE for rang;
platform rules out DEPEND more than licence (almost nothing besides casacure,
ducc0 and pure-Python packages has Windows wheels; CASA ships cp312/cp313
wheels for Linux x86_64 and macOS arm64 only; CARTA has no Windows build).
CARACal's cross-calibration is CASA (`setjy`, `gaincal`, `bandpass`,
`fluxscale`, `applycal`, `polcal`), not QuartiCal, so a matched CARACal
baseline needs a CASA oracle container (O-CASA, on the KERN-10 base that
ships WSClean 3.7, AOFlagger 3.5, IDG 1.2 and casacore 3.7.1). CASA's PKS
1934−638 flux standards are Stevens-Reynolds 2016 and Perley-Butler 2010, not
Perley-Butler 2017 (FS1 ports them with `setjy` as oracle). Proposed: CASA
caltable and H5parm formats, katdal as an optional `[meerkat]` extra for L3,
AOFlagger as a second SumThreshold oracle, CASA `gaincal` as a second
comparator in the solver protocol, a 22-format table for DF-IO and the oracle
per planned task. KERN packaging lag and metadata issues are listed for the
user (KERN is the user's own).

QuartiCal issue 452 fix verified, 2026-10-30
(`upstream-issues/quartical-qp-jhj-weights.md`): PR ratt-ru/QuartiCal#456
(merged into v0.2.8-dev as d54c46b) gives the ANTENNA2 side the transposed
weights in the shared solver loop and fixes complex, leakage, rotation,
rotation_measure and crosshand_phase at once, with a test over all 14 terms.
On scan 9 with a four-fold YX weight asymmetry the old code converged 67 % of
intervals and flagged 81.5 % of antenna-intervals; the fixed code converges
98.8 % and flags 39.0 %, as with unit weights. Rang's `qp_weights=transposed`
matches the fixed QuartiCal to 1.5e-14 on three weightings, so the opt-in is
the upstream fix; `archived` matches 0.2.7 to 2e-14. Native MeerKAT weights
carry about 15 % XY/YX asymmetry, so once 0.2.8 is the reference,
`transposed` is the compatible default and the archived comparisons need
re-validation (the dev branch also restructures the solver loop and
references the complex term by default). Result posted on #452.

E2 casacure evaluation (big plan), 2026-10-30
([casacure-evaluation.md](casacure-evaluation.md)): casacure 3.8.35 (Tim
Molteno's pure-Rust casacore tables, LGPL-3.0-or-later) reads all 173 task E
oracle columns column-exactly through Python and through the Rust crate (Rust
1.93), on Linux and natively on Windows, little- and big-endian; in-place
writes and default-manager MS creation read back exactly in python-casacore.
But it accepts a TiledColumnStMan request for a variable-shape column and
writes an MS casacore cannot open (W1(b) failed as frozen), relabels epoch
conversions without converting, crashes with SIGBUS on a file truncated under
its mapping, ships no licence file, and has one maintainer at 36 releases in
33 days. Verdict as frozen: (c), do not adopt; extend task E's reader into
rang's own writer (E3, E4, E5) and keep casacure as an optional pinned second
oracle that also runs on Windows and macOS. `core_ms` passed its first
big-endian test on the way. The eleven casacure defects are listed in
`non-ratt-observations.md` (casacure is outside the reporting decision).

Big plan task U3 (saopicc upstream), 2026-10-30 (implemented; measured;
[upstream-saopicc.md](upstream-saopicc.md)): filed saopicc/killMS#23, #25,
#27 and saopicc/DDFacet#73, #75, #77; opened killMS#24, #26 and DDFacet#74,
#76 (no GitHub CI on either repository). Latest releases equal `master` in
both. The DDFacet Hogbom failure seen on the LUNO slice reproduces on a
synthetic point source in two minutes and depends on the facet count, not the
compact array (one facet converges; 3×3 diverges to inf even with 2.2 km
baselines): DF0/DF5 oracles should use one facet or reject `nan` models.
killMS still needs DDFacet < 1.0, and DDFacet 0.9.1 does not install on GCC 15
(astlib), so the killMS oracle needs an older toolchain.

L5 solver science (big plan wave 3), 2026-10-30 (implemented; measured; no
default changes; [l5-solver-science.md](l5-solver-science.md)): the core
solver gains run-time options through `RANG_SOLVE_OPTIONS` (default = archived
QuartiCal 0.2.7, bit-identical: task F checks at 1/4/8 threads, phase 2
validator, K precondition, K's and L1's `original` gains hashes): the issue 452
qp weight fix, gauge-invariant product and loss stop tests, safeguarded
Anderson acceleration of the two-step Gauss–Newton map, per-interval freeze,
and a per-iteration trace (`RANG_SOLVE_TRACE`). Measured on the fixture, the
four-station slice, 32 stations and the whole array (56 stations): the weight
fix changes no held-out error (≤ 8e-9 relative); no stop criterion beats the
50 cap on all sets (the frozen selection, cap 8, fails the fixture by 3.9e-3);
Anderson m = 3 reaches the 0.99 criterion at 27 / 21 / 65 / 65 iterations
where plain needs 55 / 91 / > 300 / > 300, with the same held-out error and
fixed point where the plain run converged, and at the cap of 50 lifts the
array's converged fraction from 0.833 to 0.982 at equal cost. As frozen no
default changes; `qp_weights=transposed,anderson=3` is the documented opt-in;
a future default protocol would pair it with a cap of 70 against a converged
plain reference. Archive `results/l5-solver-science.json`.

P5 memory (big plan wave 2), 2026-10-30 (implemented; measured;
[p5-memory.md](p5-memory.md)): one copy of the cube. Tiles decode straight
into the final arrays (strided Rust decode, mmap), the split runs in row
blocks with one lexsort, the base solves' outlier scores come from the fused
pass over baseline groups and are kept sparse, additions are stored as
indices, and gain correction plus the Stokes I reader run in Rust
(`core/src/correct.rs`, extension bindings `blosc_decode_span_rows_strided`
and `correct_stokes_i`) into reused buffers. Every identity gate passes: K's
precondition masks and the four-station replay identical (images
bit-identical); the whole-array run equals the unmodified driver on all
1,820 non-timing fields (three dirty images within 3.1e-11 of the peak) and
L1's archive on every non-image field. Whole-array peak 12,997 → 10,406 MiB
(159 → 128 B per cell, −20 %; L1's "12.46 GB" was MiB); the pre-registered
≤ 115 B per cell is missed, the gridder's per-group copies and the Tricolour
stage planes now set the peak (for P2/P3/P7). An image takes 13–15 s instead
of 5–10 min on the parallel kernels.

L2 PKS 1830−211 campaign (big plan wave 3), 2026-10-30 (implemented;
measured; null). The gain-TV-guided flagging campaign ran on the whole array
for LUNO's gain calibrator PKS 1830−211 (MAIN_2, the whole 80 s scan: 56
stations, 1,540 baselines, 126 M cells) under two model arms fixed in the
protocol: the stored MODEL_DATA with its 1e-3 cross-hand terms, and a scalar
point at the phase centre predicted by the core with a power law fitted to
the short-baseline data (α = +0.22). 877 MB of DATA and UVW were fetched
whole in 137 s; the L2 driver (`rangtoy.core_campaign_1830`) replays K on
four stations and reproduces the archived survey. Under the scalar model the
four-station survey is fully identified except 15 tree bins; under the
stored model it is status 6 everywhere. Criteria 4 and 6 fail as frozen (the
Tricolour arms leave held-out samples unpredictable; the stored model
converges on 5 % of intervals, the scalar on 94 %). The pre-registered
matched headline is null under both models (TV policy against first pass
0.99977 and 0.99969); every TV-guided mask is rejected; the cost is not
comparable on the parallel kernels as measured on a contended host (TV chain
4.6–5.9× the first pass). Verdict null. Archive
`results/luno-1830-campaign.json` ([luno-1830-campaign.md](luno-1830-campaign.md)).
What L4 can now say: gain-TV-guided flagging is null on both LUNO
calibrators at four-station and whole-array scale under a matched
state-of-the-art comparator and pre-registered rules; what could still change
the answer is native flags and weights (L3), a converged solver (L5) and the
field model (L1-M).

DDFacet/killMS feasibility (big plan; 2026-10-30; study, no core code;
[ddfacet-feasibility.md](ddfacet-feasibility.md)). DDFacet 1.0.0.0 (about
106 k lines of Python, 8.5 k C/C++, GPL-2-or-later headers) does w-projection
per facet with Voronoi tessels, BDA and per-facet 2×2 Jones; most of its
code is deconvolution heuristics. killMS 3.3.0's CohJones is LM over a
per-antenna, all-direction Jacobian. Recommendation: no faithful port; keep
DDFacet and killMS as pinned external oracles. Instead DF1, an exact
gridder/degridder porting the ducc0 wgridder algorithm (GPL-2-or-later),
facet-free, validated against the ducc0 wheel at one thread and a DFT (ducc0
matches a DFT to 1.2e-5 of peak at epsilon 1e-4 and 8.7e-8 at 1e-7 on the
LUNO slice, in 0.04–0.27 s); then facets as shifted sub-images with per-facet
Jones, a scalar CohJones and Hogbom/multiscale, against DDFacet/killMS on a
simulated MeerKAT target field (DF3–DF5, after B1 says what it needs); DF6
facet-IDG on `wgpu` after X2 with WSClean 3.7 as oracle. B1 keeps
per-component beams in the DFT predictor: away from facet nodes a
facet-constant beam errs by 13–50× a 30″ pointing signal at 9–100 facets.
Found on the host: killMS 3.3.0 does not build on GCC 15 without a flag and
does not run on DDFacet 1.0.0.0; DDFacet HMP on the 37 MB slice peaks at
8.9 GB; the core w-stacking image differs from a DFT on the slice by 19 % of
peak (1.6 % on the PSF), unattributed, to be resolved in DF1 (item 0).

Cross-platform (big plan X1), 2026-10-30 (implemented; measured on native
Windows and Linux; CI not yet run; [x1-crossplatform.md](x1-crossplatform.md)).
The core, the root crate and the PyO3 extension build natively on Windows
with Rust 1.93.1 (MSVC) and maturin with no source change, and the extension
exports the C ABI. The backend tests pass on Windows (10 passed, 1 skipped).
Of the full suite, 529 tests pass on Windows, 17 fail and 3 modules do not
collect, all from POSIX assumptions (`resource`, `st_blocks`, symlinks, path
separators, console encoding), listed for P7/P9/P12. The task D Tricolour
comparator ran natively on Windows on the archived inputs: criteria 1–4
exact, all 56 arrays byte-identical to Linux; criterion 5 fails as frozen
only because the receipt hashes `str()` paths with backslashes. `wheels.yml`
now builds and tests manylinux x86_64 and aarch64, macOS arm64 and x86_64,
and win_amd64 wheels with cargo absent, and publishes to PyPI by trusted
publishing on `v*` tags (the project name at the tag is still `rangtoy`
until P12). `tools/wheel/build.py` and `test.py` build and test the native
wheel without docker; `.cargo/config.toml`'s v3 target is scoped to x86_64.

Big plan task U2 (upstream fixes), 2026-10-30 (implemented; measured): filed
stimela#619, tricolour#113 and QuartiCal#455; opened stimela#620,
tricolour#112 (merged), tricolour#114 and caracal#1708 (approved). No PRs for
QuartiCal #452/#453 and Tricolour #110 by maintainer direction. Rows-as-lanes
in Tricolour 0.5.0-dev: 1.3–2.1× with bit-identical flags. QuartiCal 0.2.7
defaults on scan 9: 46–54 % of intervals converged at the 25-iteration cap,
chi-squared settled by 10–15; the slow tail is not gauge drift (a
gauge-invariant stop rule would not stop earlier). The CARACal first-pass
station-bin loss reproduces on scan 9 but is whole-channel excision, not
filed. Report: `research/upstream-prs.md`.

D2 notebook tooling (big plan, documentation track), 2026-10-30
(implemented; measured; no science claim). `rangtoy.notebook` gives plain
plot and table functions over the core wrappers (`data`, `survey`, `flags`,
`gains`, `image`, `experiment`) and an ipywidgets steering layer (`steer`);
five tutorial notebooks in `notebooks/` teach the data and the
identifiability rank first, Tricolour step by step, gains/gauge/TV, imaging,
and the flagging experiment with its null results read from the archives.
The fixture loader reproduces the archived split and baseline solve to ten
figures without casacore; the LUNO survey reproduces 389/43/592 and the
decision replay reproduces task K's calls exactly. On a host at load 46–61,
notebooks 01–04 ran in 9–37 s each, 05 in 66 s with its LUNO replay, and all
five on the fixture alone in 48 s together; the new tests take 78 s. Wish
list (progress hook in `fetch_slice`, POSIX-only `resource` import in
`core_campaign`, TV and normals kernels outside the wheel, amendment 1 calls
missing from the L1 archive) in [d2-notebook.md](d2-notebook.md); the
`[notebook]` extra holds the dependencies.

P10 test-suite speed (big plan wave 2), 2026-10-30 ([p10-tests.md](p10-tests.md)):
a `tests/conftest.py` caps OpenBLAS/OMP/MKL at one thread and XLA's CPU
backend at one intra-op thread, and builds the pointing references once per
session. The caps are defaults, and the caller's environment wins.
`test_blocked` computes its dense audit once, and one validation check moved
to the thinned rows. The 555 test ids are unchanged and all pass. In the
matched A/B pair under load 26, full pytest went from 672 to 223 s wall and
from 6,031 to 188 CPU-s: `test_pointing` 584 → 146 s, `test_blocked` 40 →
19 s, `test_beams` unchanged (31 s). On an idle host the cap is estimated to
cost about 1.5–2.5× wall; `OPENBLAS_NUM_THREADS` overrides it.
`tools/check-all.sh` now takes a host-wide lock so suites queue instead of
overlapping. The day's load averages of 55–98 came from up to seven
concurrent suites whose BLAS pools busy-waited on each other.

Literature scan (big plan, read-only), 2026-10-30
([literature-2024-2026.md](literature-2024-2026.md)). arXiv, release APIs and
changelogs were surveyed for 2023–2026-10 across calibration, RFI, imaging,
beams and pointing, mathematics and software; every source was accessed
2026-10-30, most papers at abstract level. The strongest finding for the
active experiment is calibrator model completeness: Heywood et al. (2020)
show a point model of PKS 1934−638 imparts 0.2–0.5 % structured amplitude
errors at MeerKAT, and CARACal ships a 196-component 1934 field model; K and
L1 solved against a 14.96 Jy point, so part of the gain structure that TV
measures may be model error (task L1-M). Other recommendations: safeguarded
Anderson acceleration after the #452 fix (theory only, no radio precedent);
a closure-invariant (GL(2,C) gauge-free) comparator arm (C1), which isolates
exactly the non-antenna-factorable part gain TV cannot see; the SARAO
holography cubes and the SARAO/SKA pointing-offset fit as B1's reference
beam and baseline. Dropped: diffusion priors, robust PCA RFI separation,
ephemeris flagging as a method, an IDG port, a DDFacet rewrite (DDFacet is
maintained, v1.0.0.0 2026-06-23; WSClean 3.7 ships w-towers and facet-IDG).

P6 frozen Python hot spots (big plan wave 2), 2026-10-30 (implemented;
measured; [p6-python-hotspots.md](p6-python-hotspots.md)): the trend track's
candidate generation is ported to `core_trend.generate_candidates` (geometry
built once per case by prefix sums and one `np.nonzero` per row group, scores
vectorised with a bitwise-checked emulation of NumPy's pairwise sum), and the
signal track's `train_signal_guard`, `inverse_tangent` and
`corrected_intensity` are ported into `core_signal.py` with `cond`/`inv` once
per run of identical gain matrices. Frozen modules untouched. Trend results
and checkpoints byte-equal, signal results equal apart from wall times, both
comparators pass with identical counts through the switched drivers (the
`rang-core trend` and `signal` commands now use the ports). Trend 3.1× faster
(34.5 → 11.2 s minimum, claimed); signal `cond`/`inv` CPU 13.1 → 0.8 s per run
but no wall gain measurable in the frozen A/B at falling load (not claimed;
most signal time is now the survey eigensolver, P4). S1's premise that most
trend tiles are rejected by count was wrong: 60 % are admissible.

P4 survey eigensolver (big plan wave 2), 2026-10-30 (implemented; measured;
[p4-eigen.md](p4-eigen.md)): the anchored-response kernel's two 32 × 32
eigenproblems per call now use Householder tridiagonalisation + implicit QL
(`linalg::eigen_ql`) instead of classical Jacobi; Jacobi stays for the
pointing toy and the A/B. All 13,989 `anchored_response` calls of the
section 6 / phase 2 / LUNO surveys and the signal and prospective stages
replay with identical statuses and ranks; every archive comparator passes as
before (389 / 43 / 592, LUNO solved and support surveys leaf for leaf, signal
and prospective comparators); the smallest margin to the 1e-10 rank cutoff
over all bins is 7.3e7 above and 1.6e5 below. Under load 18–32: survey block
0.84 → 0.34 s, 1.7 → 0.35 ms per call, section 6 pass excluding decode
2.0 → 1.3 s (its `8_cost` criterion passes again at load 18–22), signal stage
67 → 50 s (minimum), 79 → 53 s (median).

L1 whole-array LUNO campaign (big plan wave 1), 2026-10-30 (implemented;
measured; null). The gain-TV-guided flagging campaign ran on the whole of
LUNO 1934−638 row chunk 0 on the core: 53 stations, 1,378 baselines, 342 M
cells, local whole tiles, no fetch. The array driver
(`rangtoy.core_campaign_array`) reproduces K's run bit for bit on four
stations and caps memory at 12.5 GB by row-block reimplementation (K's driver
would have needed about 88 GB). The run took 2 h 08 min on a shared host
before the P1–P3 kernels were merged. Frozen criteria 2, 4 and 6 fail as
frozen: the derived FLAG_ROW covers 571 input-flagged rows, convergence is
0.83 at the 50-iteration cap (0.98 on four stations), and the headline is
undecidable because the Tricolour first pass flags every training sample of
some station-bins, so the comparator's held-out loss is unavailable.
Amendment 1 (committed before the run) adds matched-sample calls, which are
null on every pair (TV policy against first pass: MSE ratio 0.99943, residual
RMS 0.9954); the policy selects a 21-cell unguided mask and rejects every
TV-guided mask; cost comparable (1.85). Diagnosed post hoc: the 1934−638
MODEL_DATA is a 14.96 Jy point about 1.5″ off the phase centre. The result is
null at both four-station and array scale. Archive
`results/luno-array-campaign.json` ([luno-array-campaign.md](luno-array-campaign.md)).
Next: L2 (1830−211) and L3 (native flags) for the L4 verdict; the array
solve's convergence goes to the wave 3 solver protocol.

P2 gridder (big plan wave 2), 2026-10-30 (implemented; measured): the
w-stacking gridder buckets samples by w-layer once, grids dirty image and PSF
in one pass, runs the layers in parallel with rayon and an ordered sum, and
uses `rustfft` at WSClean's exact padded size. One four-station image:
5.8 s → 0.80 s on one thread, 0.53–0.61 s at 4–16 threads on a loaded host;
task C, I and K comparators pass with unchanged margins (dirty 6.11e-7, PSF
4.17e-7 of peak against WSClean); images differ from the old FFT's by 2e-15
of the peak and are identical at any thread count. Whole array: about 3–6 s
per image (estimate). Consequence: archived image SHA256s (task K's
`results/core-k-luno-campaign.json`, S1's profile equality) no longer match
a rerun by design; checkers compare pixels or metrics within task A's
tolerances. `rustfft` picks AVX/SSE/scalar at run time, so images may differ
at 1e-15 between hosts and between the local v3 build and the wheel
([p2-gridder.md](p2-gridder.md)).

P1 solver and fused pass (big plan wave 2), 2026-10-30 (implemented;
measured): the ported QuartiCal solver runs each (time bin × frequency bin)
interval on rayon in epochs of 8 iterations with a serial,
iteration-by-iteration replay of the global stop test, and the fused pass
sweeps row blocks in parallel with a serial fold of the order-dependent sums
and per-interval normals. Every product is bit-identical to the single-thread
code at 1, 2, 4, 8 and 16 threads (task F checks, phase 1 and 2 validators, K
precondition, a 45-process sweep including early-stop settings); LUNO solve
0.252 → 0.047 s (5.4×) and fused pass 0.027 → 0.007 s at 8 threads under load
14–26; the fixture's 5.5× is measured but below the frozen claim rule at that
load. Thread count: `RAYON_NUM_THREADS` (default all logical CPUs, so
concurrent campaign processes should set it). QuartiCal's swapped qp weights
(issue 452) are reproduced unchanged; fixing them is a science protocol
([p1-solver.md](p1-solver.md)).

P3 SumThreshold (big plan wave 2), 2026-10-30 (implemented; measured): the
Tricolour port runs in parallel over baselines (rayon, `RAYON_NUM_THREADS`)
with per-worker scratch and a vectorised, lane-grouped box filter and
frequency-axis SumThreshold; flags bit-identical (task D comparator 5/5 at 1
and 16 threads, K additions hashes at 1–16 threads, every per-step window
identical to the unmodified port). K first-pass 1.65 → 0.55 s on one thread
and 0.14–0.16 s on 8–16; D controls 9–12×. Whole-array chunk 0 first pass
estimated about 7 min → 25–50 s. The serial packing in `ffi_flag.rs` is now
13–20 % of a 16-thread call (for P7). Archive `results/p3-sumthreshold.json`
([p3-sumthreshold.md](p3-sumthreshold.md)).

P8 history (big plan wave 2), 2026-10-30 (`p8-history.md`): the 23 frozen
`tv-flagging*` recipes, `tools/flagging/` (8 Dockerfiles, wrappers, fetch
scripts, preflight, locks) and the six recipe-only modules
`flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}` with
their tests moved to `history/` by `git mv`, byte-identical (70 files, 6,258
lines; 3 wrapper and recipe test functions cut there too). Live tree 267 → 197
files and 59,145 → 52,772 lines; recipes 30 → 7; pytest 739 → 555 tests.
check-all passes; S1's live-chain suite reproduces every archived verdict and
the K replay hash for hash, except section 6's wall-time cost criterion under
shared load (2.6 s and 7.9 s against a 2 s limit, load 14–20; a post-hoc A/B
shows the pre-move tree failing it the same way at load 26–46). Re-running a
frozen campaign is done from `43dc3c7` or its recorded commit with the pinned
images (`history/README.md`). The pinned `rang-flagging*:local` images are no
longer used by any live chain and may be pruned (user item).

Wheel (big plan W1), 2026-10-30 (implemented; measured locally; CI run
started by the merge push). `rangtoy-0.1.0-cp310-abi3-manylinux_2_28_x86_64.whl`
(821 kB, built in the pinned manylinux_2_28 container with Rust 1.93.1 and
maturin 1.16.0, auditwheel-clean, nothing grafted) installs from public PyPI
on clean CPython 3.10–3.14 and runs the extension backend with no cargo;
backend tests pass and task J's archive run reproduces through the wheel
(task I included) with arrays and images identical on every version and JSON
leaves identical on NumPy 2.5 (last-bit differences on 3.10/3.11 follow their
older NumPy). aarch64 cross-builds by zig but was not run. NumPy is now a
declared dependency (a bare install was broken). The wheel does not carry the
root crate's TV kernel, the Tricolour static masks or the archive drivers'
checkout paths. Wheels are built with the baseline ISA (`RUSTFLAGS` overrides
the local `x86-64-v3` config). Publication is a user item ([wheel.md](wheel.md));
open: the distribution name (`rangtoy` or `rang`) before the first upload.

Simplification review S1 (big plan wave 1), 2026-10-30 (measured; no code
changed). Every archived chain was re-run and reproduces its archived outcome
(29 timed steps plus the phase 1 and 3c-a validators, the fetch checker and
the backends comparator; the offline task K replay matches the archived gains,
dirty images and PSFs hash for hash). The core runs one thread per stage:
87 % of the K chain's samples are in Rust, under 1 % in Python glue, and 15 of
16 hardware threads stay idle (the host is 8 physical cores with SMT). The six
K images are 67 % of the non-fetch time and 83 % of each image is the
hand-written Bluestein FFT. Peak memory is about 0.87 kB per visibility cell
against 84 B of inputs, so the whole-array chunk (100.9 M cells) would need
about 88 GB as the K code is written. Thin LTO plus `x86-64-v3` code
generation cut instructions by 22 % with bit-identical results (applied on
main as P0). The 50-iteration solver cap is not convergence: held-out MSE
settles within 2e-5 by 12 iterations, but gain products move 1.3e-3 between
50 and 91 iterations, so changing the cap is a science protocol. The test
suite's time is 98 % in three pointing modules (JAX/XLA and dense algebra,
145 threads). Wave 2 tasks P0–P11 are cut in `simplification-review.md`
section 4 with owner files and archives; P1, P2, P3 and P8 start first.

Task U1 (big plan), 2026-10-30 (done). Every RATT observation in
`upstream-notes.md` was checked against its latest release (QuartiCal 0.2.7 and
v0.2.8-dev, Tricolour 0.2.1 and 0.5.0-dev, dask-ms 0.2.32). Four issues were
filed: QuartiCal #452 (the qp normal equations use swapped XY/YX weights,
verified against QuartiCal's own kernel), QuartiCal #453 (HISTORY row),
Tricolour #110 (non-TTY ProgressBar adds up to 300 s per run, the source of the
archived 302 s runs) and Tricolour #111 (integer `spike_width_time` causes a
second compilation). Nine observations were closed with reasons in
`research/upstream-issues/`. The Tricolour licence question is settled:
0.5.0-dev declares BSD-3-Clause. Non-RATT items are in
`research/non-ratt-observations.md`. Implication for the core: the phase 2
solver port reproduces QuartiCal bit-for-bit and therefore carries the #452
weight swap; wave 2's solver task should fix it as a validated deviation
(same fixed point, fewer iterations expected when w_XY ≠ w_YX).

Big plan started, 2026-10-30 (user decisions in chat; [big-plan.md](big-plan.md)).
Four lines of work run in parallel from here: a simplification and
optimisation review of the whole chain (then its implementation), the
science continued to a settled verdict (whole-array LUNO campaign first),
upstream issues filed on RATT software only, and a distributable Linux
wheel. The coordinator merges waves without waiting for the user.

Licence decision, 2026-10-30 (user, in chat): the LUNO data may be used and
upstream software may be rewritten in the core. The observer's permission
(Ben Hugo, 2026-10-29 15:36 SAST) is the basis and publications cite the
SARAO data usage acknowledgement. Earlier "provisional pending licence"
labels on LUNO results are history; their other caveats (processed weights,
unlogged model origin, four stations) stand. Raw visibilities are still
never committed or redistributed.

Core task K (wave 2), 2026-10-30 (implemented; measured; provisional). The
first real-data campaign on the LUNO PKS 1934−638 four-station slice ran
entirely on the core (`rangtoy.core_campaign`): range fetch (752.8 MB, 74.2 s,
every byte hash-equal to task G's archive), Rust decode (0.36 s), the frozen
seed-7 split, six arms solved with the core's QuartiCal port (0.32 s each), the
Tricolour first-pass and mild strategies ported in task D (1.55 s and 0.89 s),
the frozen TV policy loop (1.7 s) and corrected-data Briggs dirty images
(3.9 s each); 110 s and 461 MB in all, criteria 1–7 pass as frozen after the
section 6 precondition reproduced the archives. Outcome: a null result by the
pre-registered rule on every pair. The TV policy selects no flag (each of the
six candidates raises the fixed-support TV and the validation MSE); the
first-pass strategy adds 128 of 94,047 training cells to a slice already
70.10 % flagged and moves the held-out test MSE by 6e-5 relative and the
point-source residual RMS by 4e-5; dirty peak 14.925 Jy/beam against the
14.940 model in every arm; cost comparable (TV chain 2.00 s against 1.54 s,
ratio 1.30). Labelled post-hoc: one checker-only path fix after the first
check call failed; the run is untouched. Caveats: SARAO's written licence
confirmation is pending (observer permission in chat 2026-10-29 15:36 SAST;
no visibilities redistributed); WEIGHT_SPECTRUM is a QuartiCal product and the
1934−638 model origin is unlogged, so every χ² and MSE is conditional; four
stations make the dirty image sidelobe-dominated (the frozen 9×9 PSF box sits
inside the main lobe); PKS 1830−211 was not run. Archive
`results/core-k-luno-campaign.json` (`core-k-luno-campaign.md`). Next: a
whole-array run and the native-flag run once the observer's data arrive;
1830−211 needs a model decision.

Core task J (wave 2), 2026-10-29 (implemented; measured; criteria 1–7 pass
as frozen). The core is packaged as the PyO3 extension `rangtoy._core`
through maturin (`core/py`, pyo3 0.30.1 and numpy 0.30.0, abi3-py310; the
`pyproject.toml` backend is now maturin): each of 17 functions and the
`MsTable` class is a second door into the same C function with NumPy arrays
borrowed in place, `core/src` unchanged. Every wrapper uses the extension
when importable and ctypes otherwise (`RANG_CORE_BACKEND`, `RANG_CORE_LIB`).
Through the extension the phase 2, section 6, actions, B, C, D, E and I
comparators reproduce their archives with every number equal to the ctypes
precondition; `examples/compare_core_backends.py` finds 94 files, 4,544 JSON
leaves, 60 npz arrays and 60 FITS HDUs identical. Timings: first kernel call
under 1 ms against 28–32 ms through ctypes, per-call cost otherwise equal;
the extension buys packaging and a typed boundary, not speed. Found and
fixed: `tools/check-all.sh` never failed on a failing pytest (now it does;
the Rust test steps were fixed the same way at the merge). Not done: a
distributable manylinux wheel and the container update. Archive receipts
under `outputs/core-j-20261029-*` (`core-j-packaging.md`). Next: task K once
the licence answer is in.

Core task I (wave 2), 2026-10-29 (implemented; measured). The imaging track
replays on the core (`rangtoy.core_imaging`, `rang-core imaging`,
`recipes/core-imaging.yaml`): the fifteen archived jobs are imaged from the
checkpoints with `core_ms`, `core_weights` and `core_grid` and the unedited
`flagging_imaging` algebra, no WSClean, container or python-casacore. Against
`results/gain-tv-next-imaging.json` and the host reproduction: weight sums
1.4e-15, dirty 6.1e-7 and PSF 4.2e-7 of peak, template fluxes 1.4e-7, response
fractions 1.3e-7 (82 % of task A's 1.6e-7), closures 7.4e-9 Jy/beam, 532 exact
fields; 62 s for the family (about 2.5× single-threaded WSClean inversion).
Criterion 8 failed as frozen on its git clause because the operator edited
tracked files during the run (not the driver); the first Stimela run failed as
frozen because Stimela 2.1.4 raises "There is no current event loop" on Python
3.14, and passes after a labelled environment step on a 3.13 venv. Archive
`results/core-i-imaging-replay.json` (`core-i-imaging-replay.md`). Next: task
J (PyO3/maturin packaging), then task K once the licence answer is in.

Wave 1 merged, 2026-10-29 (implemented; measured). The eight parallel
sessions of `core-parallel-plan.md` ran in WSL worktrees on branches
`core/<slug>` from `9e12326` and were merged onto main one at a time in the
order G, H, A, B, C, D, E, F (F last because it edits existing kernels), with
each task's "For the coordinator" section applied in the merge commit. Every
branch passed `tools/check-all.sh` once on its own (51–53 min each while eight
suites shared the 16 cores). Next: wave 2 (I imaging replay on the core, J
PyO3/maturin packaging, K the LUNO campaign, which needs the licence answer).

Core task A, 2026-10-29 (implemented; measured): WSClean approximation
sensitivity, 19 variants × 15 archived imaging jobs (kernel 5–9, oversampling
511–2047, w-layers 1–256) in 552 s; all gated criteria pass. Proposed phase 4
tolerances at one tenth of the smallest adjacent movement: dirty-image L∞
8.8e-6 of peak, PSF L∞ 2.8e-6, template flux 4.7e-6 relative, response
fraction 1.6e-7 absolute, weight sums 1e-9 (`core-a-imaging-sensitivity.md`).

Core task B, 2026-10-29 (implemented; measured): `core/src/weights.rs`
(`rangtoy.core_weights`) ports WSClean 3.6-1 Briggs, uniform and natural
imaging weights and Stokes I formation, bit-identical to WSClean's
`-store-imaging-weights` on all 19 oracle runs (`core-b-weighting.md`).

Core task C, 2026-10-29 (implemented; measured): `core/src/grid.rs`
(`rangtoy.core_grid`) ports the w-stacking gridder (Kaiser–Bessel 7, 1023×,
w-layers, PSF, normalisation, FITS orientation). The frozen run failed because
the reading missed WSClean's default `-padding 1.2`; after the labelled
post-hoc fix the core matches WSClean's dirty images and PSFs on all fifteen
jobs to at most 6.1e-7 of the peak, inside task A's 8.8e-6
(`core-c-gridder.md`).

Core task D, 2026-10-29 (implemented; measured): Tricolour 0.2.1 treated as
BSD-3-Clause (LICENSE file; the `GPLv2` metadata string is unaccompanied),
Crystalball GPL-2.0-only and not ported. `core/src/sumthreshold.rs`
(`rangtoy.core_flag`) reproduces the four archived CARACAL controls flag for
flag (run `-02`, after one post-hoc fix of the `flag_nans_zeros`
accumulation); 4.2 s CPU per first-pass strategy against 1.2 s warm Numba plus
74 s compilation. Archive `results/core-d-tricolour.json`
(`core-d-tricolour.md`). The licence reading awaits confirmation by SARAO.

Core task E, 2026-10-29 (implemented; measured): `core/src/ms.rs`
(`rangtoy.core_ms`) reads casacore tables stored with StandardStMan and
TiledStMan column-exactly against python-casacore on all 173 oracle columns of
the fixture and LUNO Measurement Sets; python-casacore is still needed to
write tables and for the oracle (`core-e-ms-reader.md`).

Core task F, 2026-10-29 (implemented; measured): solver and blosc decoder
faster with bit-identical results against the phase 2 and section 6 oracles
(solver 1.5× fewer instructions and 1.7–1.8× faster at quiet load, decoder
4.6× fewer instructions and 3.0–3.3× faster); the rank survey is a null
result because its cost is the root crate's Jacobi eigensolver, not the core
(`core-f-performance.md`).

Core task G, 2026-10-29 (implemented; measured): the LUNO four-station slice
fetched with HTTP range requests (`rangtoy.core_fetch`), 751.8 MB in 74.5 s
against 4.87 GB in about 679 s whole-tile, all bytes hash-equal to the
archive (`core-g-http-fetch.md`).

Core task H, 2026-10-29 (implemented; measured): five core-native Stimela
recipes (`recipes/core-*.yaml`) and `rang-core` (`python -m rangtoy.core_cli`)
reproduce the phase 3 archives through Stimela and directly, in a venv without
QuartiCal; two criteria failed as frozen (wall-time digests, docstring text)
and pass under labelled post-hoc rules (`core-h-recipes.md`).

Core section 6 prototype, 2026-10-29 (implemented; measured). Run as frozen
from the LUNO zarr tiles with no MS (`examples/prototype_section6.py`, checker
`examples/check_section6.py`): a Rust blosc decoder (`core/src/blosc.rs`,
`rangtoy.core_zarr`) matches numcodecs on all 68 chunks and reads only the
needed blocks (512 of 3136). Run `-01` failed criterion 8 (2.86 s excluding
decode, 299 MB); after implementation fixes with unchanged criteria, run `-02`
passes all eleven (1.67 s, 140 MB; gains equal QuartiCal to 3.3e-16; survey
389/43/592). Archive `results/core-section6.json`. Next: phase 4.

Core phase 3c-b, 2026-10-29 (implemented; measured: all gated criteria pass
as frozen). The signal track runs on the Rust core (`rangtoy.core_signal`):
9 solves in 34.5 s, prediction by the core predictor, injection and complete
sky in memory. 261 exact fields equal, floats within 1.7e-11 against
`results/gain-tv-next-signal.json` and the host reproduction. Archive
`results/core-phase3c-b.json`. Phase 3 gate covered: core drivers for
injections, actions, trend, prospective and signal reproduce their archives,
with qualifications (trend only under post-hoc 3b; injections and actions
needed post-hoc comparator steps). The frozen recipes still call QuartiCal.
Lesson: five of eight frozen runs needed a post-hoc step, three of which a
comparator run on archive versus host reproduction would have exposed; future
protocols require that precondition. Next: the section 6 prototype as frozen
(zarr ingest, no MS), then phase 4.

Core phase 3c-a, 2026-10-29 (implemented; measured). `core/src/predict.rs`
ports the WSClean-format component predictor of codex-africanus 0.4.4 (BSD
notice kept). Against a once-only africanus oracle
(`outputs/core-phase3c-oracle-20261029-01`) it is bit-identical on the response
pair, the 5153-component SARAO catalogue and a 64-component stress set. The
frozen run `-01` failed one criterion through a validator error (wrong source
list for the NumPy templates); the corrected rerun `-02` passes all. Archive
`results/core-phase3c-a.json`. Next: 3c-b, the signal track (freeze a UVW
export of the prepared cases first).

Core phase 3 trend chain test, 2026-10-29 (implemented; measured). Seven
core-solved baselines, written as a mirror of the concurrent suite
(`examples/build_core_trend_mirror.py`), are consumed by the unedited trend
module (hash equal to the archive). 875 exact fields match; criterion 3 failed
as frozen on the reference-antenna slopes (rounding zeros, at most 6e-19 rad/s);
post-hoc criterion 3b (scaled by each axis's largest slope) passes at 8.4e-14.
Archive `results/core-phase3-trend.json`. Phase 3: injections, prospective,
actions and trend done; signal track remains (needs the Rust predictor).

Core phase 3 actions stage, 2026-10-29 (implemented; measured). The actions
stage runs on the Rust core (`rangtoy.core_actions`) in 9.2 s with 17 solves;
it passes as frozen against `results/gain-tv-actions.json` (floats 6.6e-15,
differences 1.8e-11). Against the host reproduction the frozen comparator
flagged 14 float metadata scores as exact; a labelled post-hoc rule passes.
Archive `results/core-phase3-actions.json`. Phase 3 overall: in progress
(injections, prospective, actions done; trend chain test and signal remain).

Core phase 3b, 2026-10-29 (implemented; measured: all gated criteria pass as
frozen). The prospective track runs on the Rust core
(`rangtoy.core_prospective`, `examples/run_core_campaign.py`) in 32.8 s with
54 solves; every decision equals the archive and the host reproduction;
floats agree to 1.4e-14. Run `outputs/core-phase3b-20261029-01`, archive
`results/core-phase3b.json`. Next: phase 3c (signal track) needs a Rust
point/Gaussian predictor, which is also the predictor step of phase 1.

Core phase 3, 2026-10-29 (implemented; measured). The injection campaign
runs on the Rust core (`rangtoy.core_workflow`, `rangtoy.core_injections`,
`examples/run_core_injections.py`) from the prepared host reproduction, with
no MS and no container: 49 solves in 25 s against 296 s. Frozen run
`outputs/core-phase3-20261029-01`: every compared field passes (858 exact, 928
floats to 1.3e-14, 54 distances to 1.5e-14), all six selections equal the
archive, but the frozen comparator reported 18 archive-only per-case fields as
missing. Post-hoc run `-02` adds them and passes against the archive and the
host reproduction. Archive `results/core-phase3.json`. Next: phase 3b, the
prospective and signal tracks.

Core phase 2, 2026-10-29 (implemented; measured: all eight frozen criteria
pass). `core/src/solve.rs` ports the QuartiCal 0.2.7 complex solver (MIT notice
kept). Run `outputs/core-phase2-20261029-01`: gain flags identical on fixture and
LUNO; gains within 1.4e-15 and 3.3e-16; 50 iterations and converged fraction
0.9833234067897558 as QuartiCal; losses and TV within 4e-16; LUNO rank survey
389/43/592 exact. LUNO solve 0.77 s; load+solve+fused 0.94 s, 96 MB (QuartiCal
28.3 s cold, 3.6 s warm, 633/382 MB). Inputs exported once from the LUNO MS to
`outputs/core-phase2-inputs-20261029-01`. Archive `results/core-phase2.json`.
Next: phase 3, the policy loop and campaign tracks on the core.

Core phase 1, 2026-10-29 (implemented; measured: criterion 4 failed as
frozen; post-hoc 4b passes in `outputs/core-phase1-20261029-02`, archive
`results/core-phase1.json`). `core/` is a new GPL Rust crate with
a fused pass (residuals, split losses, robust scores, antenna-diagonal normal
blocks) behind ctypes (`python/rangtoy/core.py`). Frozen run
`outputs/core-phase1-20261029-01`: residuals agree with the archive to 5.7e-14 Jy,
split losses to 2e-15, scores to 2e-14, diagonal blocks exactly; criterion 4
failed on b (4.9e-11 against 1e-13) because b cancels at the optimum. See
`core-phase1.md`.

Licence and port decision, 2026-10-29 (user, in chat): rang is now
GPL-3.0-or-later (`LICENSE`, Cargo and Python metadata). The user asked to work
down the port plan in `stack-consolidation-feasibility.md` section 9, starting
with phase 0 and phase 1, Rust for performance and Python for interfaces.
Open: whether Tricolour and Crystalball are GPL-2-only, which would block
translating their code into a GPL-3 core (phase 5 only).

Stack-consolidation feasibility study, 2026-10-29 (written study, no code,
no scientific change): `stack-consolidation-feasibility.md`, linked from the
README. Verdict: partially feasible; fuse the inner loop in one Rust core, keep
MS tables, strategy flaggers and WSClean external. New measurements (logged in
`tool-timings.md`): QuartiCal on the LUNO slice is 28.3 s cold versus 3.6 s with
a warm Numba cache, with gains equal to 2e-14 relative; decoding the DATA tiles
expands 2.72 GB to 3.28 GB to keep 12.6 MB. Prototype acceptance criteria are
frozen in the study. Section 9 adds a phased single-framework port plan with
before/after step counts (about 6× fewer for the five-track campaign). Run directory
`outputs/stack-feasibility-20261029-01`.

LUNO solved-gain follow-up, 2026-10-29 (provisional; protocol `487208b`).
A four-station casacore MS was built from row chunk 0 of 1934−638 scan 2
(1070–1497.8 MHz, 192 rows × 2048 channels), and QuartiCal 0.2.7 was run with
the frozen pipeline command (G complex, 2×32, 50 iterations). Chi-squared fell
from 73.75 to 0.27, 98.3% of intervals converged, flags were unchanged, and
gains were flagged exactly on unsupported station-bins. Rank at the solved
gains is identical to identity and random gains: 389 fully identified bins
(status 0) and 43 tree-shaped underidentified bins (status 3). This is the
declared expected consistency result. Run `outputs/luno-solve-20261029-02`,
archive `results/meerkat-luno-solved.json`, report `flagging-luno-solved.md`.
Tool timings are now logged in `tool-timings.md`, and upstream observations in
`upstream-notes.md`. QuartiCal's roughly 24 s per-container Numba JIT dominates
small solves, because the image's cache lives in `/tmp`.

LUNO answers from the observer, 2026-10-29 (WhatsApp, Ben Hugo):
- 15:36 SAST: "you can use it. Just cite the Sarao data usage acknowledgement".
- 15:37 SAST: "weight spectrum would have been modified by quartical" and
  "Sigma spectrum should have the original inverse variances".

- 15:38 SAST: "I can make a full resolution dataset available to you" and "The
  zarr files I think was a subset".

Recorded in
`flagging-luno-candidate.md`. No data, weights or flags were changed on the
strength of the chat. The running solved-gain follow-up (`flagging-luno-solved.md`,
frozen in `487208b`) keeps its frozen WEIGHT_SPECTRUM inputs. A SIGMA_SPECTRUM
weight variant would need its own protocol after a numeric check.

LUNO continuation, 2026-10-29: the user chose to continue with the LUNO
calibrators while the licence and native weights are unconfirmed (Ben Hugo asked
the same day; no answer yet). All LUNO results are provisional, and no
visibilities are redistributed. The processed-support survey protocol is frozen
in `flagging-luno-support.md` before any tile download (commit `807eb52`).
Measured, provisional: on 3.22 GB of row chunk 0 (1070–1497.8 MHz, stations
m000–m003, 2×32 grid):

- **1934−638 (scalar model):** 389 of 432 supported bins are fully identified
  (116,805 of 117,556 TRAIN cells). All 43 failures are tree-shaped support
  graphs. A post-hoc audit with the original `anchored_response(H,0,0,0)`
  call gives status 0 on the 389 and status 3 on the 43. The frozen call
  `(H,0,H,0)` was mis-specified: it zeroes the retained curvature and returns
  status 4. The first push wrongly reported "432/432 agree".
- **1830−211:** the model has about 1e-3 cross-hand terms, so the scalar U(2)
  condition does not apply (145 over-rank bins and 15 tree failures; native
  status 6 on all 160).
- **Model origin:** neither surveyed model has a logged origin. `setjy` named
  only 3C 286, and a `clearcal` with `addmodel` on field 2 would have reset the
  1830−211 model.
- No-data bins are the RFI-masked roughly 1150–1311 MHz and 1471–1498 MHz
  channels. Antennas m031, m040 and m044 have no TRAIN support.

Results are identical at identity and at the seed-20261029 random gain point.
Run directory `outputs/luno-support-20261029-01`; archive
`results/meerkat-luno-support.json`.

LUNO provenance, 2026-10-29 (text metadata only; no data changed). The stores'
OBSERVATION/FIELD/HISTORY strings, which are `json2`-encoded so no pickle is
involved, give project `20210818-0008`, observer `B Hugo` and target field
`Moon`. The Moon was 44′–149′ from the stored target direction during the track.
HISTORY holds 923 calibrator and 124 target rows, all CASA 5.6 records from
2022-09-10 to 2022-11-02: 25 `applycal` with `calwt=True`/`calflag`, four manual
`flagdata`, `setjy` (Perley-Butler 2017, 3C 286 only) and `clearcal`. FLAG,
WEIGHT_SPECTRUM and MODEL_DATA are therefore processing products, so the all-four-weight
support is not native evidence. The stores were published 2024-11-29 as
AfriCalim 2024 workshop data (`africalim/resources` QuartiCal recipes, likely
source of `CORRECTED_DATA_QCAL`). No licence was found. The workshop's
Polcal-Primer notice for its UHF Moon data says SARAO-owned, teaching use,
MeerKAT data policy 4.2.2.2. Research use needs confirmation from SARAO or the
observer; a question was sent to the "Hout boys" WhatsApp group 2026-10-29
~13:06 SAST, with no reply recorded. Run `outputs/luno-text-20261029-01` via
`tools/flagging/fetch-luno-text.sh` plus `examples/decode_luno_text.py`
(60 objects, 27,237 bytes), archived in `results/meerkat-luno-provenance.json`;
details in `flagging-luno-candidate.md`. Gain-bin support was later measured
provisionally (above).

Second public candidate, 2026-10-29 (metadata plus one bounded numeric tile;
no calibration). `LBAND_LUNO_CALIBRATORS.zarr` in the anonymous RATT bucket:
56 antennas, 20 scan groups, 3C 286 / PKS 1934−638 / PKS 1830−211 by
`PHASE_DIR`, a 14,218 s track. `WEIGHT_SPECTRUM` is positive in all four
correlations, and 1,735,448 tile cells are all-four supported (ESO137: 0).
Probe `outputs/luno-probe-20261029-01` (repeated in `-02`, all 50 object hashes
equal), via `tools/flagging/fetch-luno-probe.sh` plus
`examples/decode_luno_probe.py`, archived in
`results/meerkat-luno-candidate.json`; report `flagging-luno-candidate.md`.
Open before any use: licence/citation terms (no documentation found), whether
weights/flags/model are native or processing-derived (923 HISTORY rows not
decoded), and TRAIN gain-bin support on the calibrator scans.

New host setup, 2026-10-29 (no scientific runs, no code changes):
Windows 11 workstation using WSL2 Ubuntu 26.04 (x86_64, 16 cores, 30 GiB RAM),
checkout `~/Github/rang` on the Linux filesystem, Docker 28.3.3 inside WSL.
Python 3.14.4 venv from public PyPI with the recorded pins (JAX/JAXlib 0.11.1,
NumPy 2.5.3, pytest 9.1.1, Ruff 0.16.7). All checks pass: 654 Python (no skips),
19 Rust, release build, Clippy `-D warnings` and `cargo fmt` under Rust 1.93.1,
Ruff lint+format, `git diff --check`. Stable Rust 1.99 Clippy adds
`chunks_exact_to_as_chunks` on `src/projector.rs`/`src/response.rs`. Those
sources are hashed in result receipts, so they stay unchanged and checks pin 1.93.
Native Windows Python ran 614/654: all 40 failures are POSIX-only guard tests
(symlink privilege, `st_blocks`, bash paths, cp1252 output), so Windows is
documented as unsupported rather than weakening the guards.
`rang-flagging:local` rebuilt natively as linux/amd64
(`sha256:124ee3a09bbcf7f933a7280a24bc4e36f3c82db1910f33d78d09c96d09e55be6`).
Offline smoke check: QuartiCal 0.2.7, Stimela 2.1.4, python-casacore 3.8.1 and
the Rust kernel library load; the pilot recipe parses with `stimela doc`.
The other container images (sky, comparators, imaging, next) are not rebuilt.

Data restore, 2026-10-29. The original `outputs/` tree from the previous Mac
host was deleted and no copy exists. Every raw output, prepared input,
backup and run tree named below in this file is therefore gone (for example
`outputs/flagging-backups/*`, `outputs/tv-injections-pilot-01/`,
`outputs/tv-response-20260924-precision-01/`, `outputs/tv-caracal-clean-01/`). The tracked compact archives, receipts and
recipes remain the record. Wrappers that take those directories as sources need
their producing stages rerun into fresh namespaces first. Re-fetched inputs, each
verified against the recorded hash:
- `outputs/ska-pointing/outer_scans.zip`: upstream Git LFS object
  `https://gitlab.com/ska-telescope/sdp/science-pipeline-workflows/ska-sdp-wflow-pointing-offset/-/raw/main/tests/data/outer_scans.zip`,
  45,452,147 bytes, SHA256 `d4dae56f…144f`, equal to the LFS pointer oid.
- `outputs/flagging-sky-inputs/fitted.PKS1934.LBand.wsclean.cat.txt`: SHA256
  `b277bc6d…1fb9`, 5153 components (CC BY-NC 4.0, not redistributed).
- `outputs/flagging-next-data-wsl-20261029/primary-zmetadata.json`: SHA256
  `68fdb7f4…bbaa`. Its acquisition `outputs/tv-public-acquired-wsl-20261029-01`
  matches all 75 archived objects in bytes, SHA256 and ETag (884,609,513 bytes).

Prepared clean/contaminated input rebuilt with the unchanged frozen recipe:
`bash tools/flagging/run-injections.sh outputs/tv-injections-wsl-20261029-01`
(seed 19, strengths 3/10, three patterns, 50 iterations; exit 0, 296 s versus
400 s archived). Compared with `results/gain-tv-injections.json`: all selected
policies, flag counts, integers and strings identical; every non-timing float
agrees within 6.3e-15 relative. The kernel library hash differs because
`src/lib.rs` gained later kernels after that archive. Only timings and
archive-only summary fields otherwise differ. Use this directory, not the lost
`tv-injections-pilot-01`, as the prepared-input source for later wrappers.

Later stages rerun on this host, 2026-10-29, into fresh namespaces with frozen
code/settings. Each result is compared field by field with its tracked archive.
Exact fields cover integers, booleans, strings, mask IDs and policy selections.
Paths, timings, input/image/kernel digests and archive-only summary fields are
excluded. Only rounding-level float differences remain:

| Stage (archive) | Fresh run | Exact fields | Worst float rel | Wall time |
| --- | --- | --- | --- | --- |
| Actions (`gain-tv-actions.json`) | `tv-flagging-actions-wsl-20261029-01` | 61 equal | 7.6e-11 (differences of near-equal TVs) | ~6 min |
| CARACAL native (`gain-tv-caracal.json`) | `tv-caracal-wsl-20261029-01` | 99 equal | 4.5e-14 | 1265 s |
| Response (`gain-tv-response.json`) | `tv-response-wsl-20261029-01` | 461 equal | 3.8e-12 (closure residuals ~1e-17 Jy excluded) | 96 s |
| Concurrent suite (`gain-tv-concurrent.json`) | `tv-concurrent-wsl-20261029-01` | all branches complete, no failures | see branches | 445 s |
| Balanced, 7 cases (`gain-tv-balanced.json`) | `.../experiments/<case>` | 2829 action fields, 21 selections equal | 9.6e-15 | |
| Signal (`gain-tv-signal.json`) | `.../experiments/signal` | 287 equal | 2.8e-9 | |
| Transfer (`gain-tv-transfer.json`) | `.../experiments/transfer` | 262 equal | 3.3e-12 forecasts; coefficient 11 and train bias are ~1e-21/1e-19 zeros | |
| Public pilot (`meerkat-public-pilot.json`) | `.../experiments/public` | 56 equal | exact | |
| Uncertainty (`gain-tv-uncertainty.json`) | `.../experiments/uncertainty` | 180 rows equal | 2.1e-12 | |

Only time-burst seed 105 selects a non-null mask, identically for residual and
TV, as archived. Provenance HEAD/conditional GET reran into
`tv-provenance-head-wsl-20261029-01` and `tv-provenance-acquired-wsl-20261029-01`:
85 objects, 15,672 bytes, as recorded. Receipt SHA256 values differ only
through embedded finish times; per-object hashes were not archived.
CARACAL strategy sources re-fetched at revision `8f7bb363` into
`outputs/caracal-strategy-inputs-8f7bb363/`: all nine files match
`results/caracal-strategies.json` in SHA256 and size.
Images rebuilt natively: sky, comparators, parallel, response and next.
`tools/flagging/imaging/Dockerfile` uses a BuildKit heredoc `COPY`, so imaging
and next-imaging need buildx. This host uses the official buildx v0.37.2 user
plugin (`~/.docker/cli-plugins`, release checksum verified):
`docker buildx build --load --platform linux/amd64 -f tools/flagging/<d>/Dockerfile -t rang-flagging-<d>:local .`
for `imaging` then `next-imaging`.

| Stage (archive) | Fresh run | Exact fields | Worst float rel | Wall time |
| --- | --- | --- | --- | --- |
| Corrected imaging (`gain-tv-next-imaging.json` raw_result) | `tv-next-imaging-wsl-20261029-01` | 652 equal except allocated bytes | 2.2e-15 over 394 science floats | 36 s |
| Five-track trend (`gain-tv-next-trend.json`) | `tv-next-wsl-20261029-01/experiments/trend` | 1016 equal | 1.9e-15 | 436 s (whole campaign) |
| Prospective (`gain-tv-next-prospective.json` projection) | `.../prospective` | 1909 equal except allocated bytes | 1.5e-11 | |
| Signal guard (`gain-tv-next-signal.json`) | `.../signal` | 412 equal except allocated bytes | 1.7e-11 | |
| Provenance inspection (`gain-tv-next-provenance.json`) | `.../provenance` | 939 equal | exact | |
| In-campaign imaging (`gain-tv-next-imaging.json`) | `.../imaging` | 652 equal except allocated bytes | 2.2e-15 | |

The paired dirty-image figure `dirty-response.png` is byte-identical to the
archived one (SHA256 `8e2951ef…9c40`). FITS and whole-MS backup digests differ
because those files embed per-run headers and copies. Excluded: near-zero
values below 1e-12 (template cross-terms, pixel-MSE floors) and float64→complex64
rounding audits. The provenance inspection matching exactly also validates the
re-fetched provenance content. Unlike the original 2026-09-24 master
(imaging CLI failure, no gather), this fresh `run-next.sh` completes all five
tracks and the top-level gather with the corrected code. That is a
reproduction of the corrected strategy, not a new scientific result; no
threshold, setting or source changed. Every stage of the published five-track
evidence chain is now reproduced on this host from re-fetched public inputs.

FINAL CHECKED PUBLICATION READY2026-09-24 10:24UTC:
654Python(no skips)/19RustPASS,releasebuild/Clippy-Dwarnings/cargoformat,
fullrepoRufflint+format,91Pythoncompiles/62strictJSONarchives,
10embedded auditprogramSHA+compile checks,6exactrawprojections,
combinedarchive everylinkedarchive/audit/reportSHA exact, figureSHA and full
gain-supportsurveyartifact exact; allshellsyntax+working/stagedwhitespace gate.
Historical123action/native13helper/signal-transfer-public archive checksPASS.
Rootreadonlyverification confirms all5original source trees unchanged and
original master result stillabsent; currentcorrectedtopStimela2dryrunPASS.
Allruntimecode/testfiles unchanged since e3cab8c, allowned reports frozen.
Final prepublicationbackup:
`outputs/flagging-backups/20260924-five-track-final-audited/code.tar.gz`,
SHA256`5cd0be66f706e6201510bfb83e22054bec1cb012a1346dea9fc934b2058b4197`.
72GiBfree/8GiBreserve, nocleanup. Publish combined measuredindex
`research/results/gain-tv-next.json` +readable report/figure/recipe handoff
under Gijs/gmailidentity; noagent/coauthor/generated attribution.

ALLFIVE MEASURED+INDEPENDENTLYAUDITED~10:20UTC. Readable finalhandoff:
`research/flagging-next-summary.md`, plan`flagging-next-results.md`, indexed
README/findings and explicitStimela2 researchrecipe`recipes/tv-flagging-next.yaml`.
Originalmaster4/5exit1/noresult remains; final summary composes fouroldbranches
+fresh03exit0,neverclaimsoriginalgather. Image03independent419/419PASS incl
independentnativeUVW/Fourier/Gaussian/spectral-oracle/exactonceunitpayload.
Prior02audit409numericPASS+2semanticFAIL and initial23preservationPASS retained
separately. Fourotheraudits562trend/2355prospective/558signal/657provenancePASS;
separateall-binrank1751PASS. No extraQC;63newQC+30completedWSCinversions of
15distinctphysicaljobs(15invalidbasis02+15correct03)+oneCLIparsefailzeroFITS.
No novelSOTA/nativecost/independenttransfer/certifiedflaggerclaim. Absolute
signalguardabstains;56maskonlyunguardedobjective/knowninjectiondiagnostic.
Nextgates: prospectivelyfrozen support-awaregrid+modelcontrols, independently
observed supported/provenancedMeerKATLbanddata, matchednativeimage/costvsSOTA.
Finalfullchecks+strictcombinedreceiptverification/stagedwhitespace/publicpush
follow after owned finalimageaudit/reportfiles arefrozen. Runtimecodeunchanged
sincee3cab8c. Current73GiBfree,8GiBreserve;nofilesdeleted.

CORRECTED03IMAGINGCOMPLETE10:16:45UTC/sourcee3cab8c:
rawoutputs/tv-next-imaging-20260924-03,15inversions/0QC,64secondsStimela.
RawresultSHA`1dd4f4617483296635307c6f3fd32d05165e88788e7f10410969af61c7932838`.
Referencefit59.999996/119.999990mJy/pixelMSE3.46e-17 matchesintendedfamily.
Omittedpairedknown-template dirtyresponse49.17/77.57%, complete99.69/98.65%;
same9169TEST/PSFs/nativeweights; imageclosure3.81e-8<unchanged1e-6.
AllinternalpreservationchecksPASS; independent03semantic+numeric auditpending.
30completedWSCleaninversions of15frozenphysicaljobs(15failedfamily02+15fresh03),
oneinitialCLIparsefailure/zeroFITS,63actualnewQC unchanged. PublicfigPNG is
identical02/03(itshowsnonunitpairedimages,notbasisfits),SHA8e2951... recorded.
Final mainreadablehandoff research/flagging-next-summary.md; commonarchive and
finalcheckedpublicpush follow independentimageaudit, no oldmastergathercreated.

Readonly gain-supportsurvey COMPLETE/frozen:1751/1751PASS,all3cases287/288
TRAIN-supportedbinsidentified (608no-data),73718/73720TRAINcells99.997287%.
Only2cells/bin811one0–2edgeunderidentifiedrank8required12. No cell discard,
grid/gauge/threshold change or QC. Exactcode/command/nativecf61/sourcehashes
andall864nativecrosschecks archived in gain-tv-next-gain-support.json; report
flagging-next-gain-support.md. This quantifiesfirstcertificateobstacleonly;
fixingrankswouldnotproveabsoluteTnearidentityorskyadequacy.
Currentpublicsourcee3cab8c(actual03currentlyrunning), raw02retainedsemanticFAIL.

Corrected unit-spectrum source checkpoint fullchecksPASS~10:15UTC:
654Python(no skips),19Rust,release/Clippy/cargoformat,fullrepoRufflint+format,
91Pythoncompiles,59strictJSONarchives,5exactrawprojections(including02FAIL),
embedded auditprogramsha/compile,allwrapperbashsyntax+fresh03namespacegate.
47imagingtargetedtests include ACTUALtemplateproducer independentzeroUVW
spectra/exactonceconsumer/doublelawcounterexample. No threshold/settings or
Quarticalgainchanges. Backupbeforechecking:
`outputs/flagging-backups/20260924-next-imaging-spectral-fix/code.tar.gz`,
SHA256`1cb20ad613a45377094d720db0f31e3737b4cc8fc3fb3221edd99f959c863d80`.
Checked stagedwhitespace gates sourcecommit/push thenfresh03measurement.

IMPORTANT02SEMANTICFAIL~10:13UTC: independent imaging audit409numeric+
preservationchecksPASS but2scientificfamilychecksFAIL. Saved
response/spectral-templates.npz already includes alpha-.5/-.9, and02runner
multiplies spectra aSECONDtime; unitbasis haswrongalpha-1/-1.8. Keepall02raw
products/ratios labeledscientificallyinvalidmatched-family, publicrawarchive
`gain-tv-next-imaging-invalid-basis.json`. Nonunitvisibility/imageclosure,
source/backups/nativecols/flagsguardsremainvalid; don'treport02intendedfamily
fluxratios. Rootdraftnotpublished; semanticerrorcaughtbeforepublication.
Authorizeonlyduplicate-factorremoval+provenanceunitregression and separately
fresh03imaging-onlyretryafterfullchecks/sourcecommitpush; all15physicaljobs,
settings/weights/closures/budgets/gainsunchanged,0newQC.

FRESH IMAGING SUCCESS10:08:16UTC/source84d15b3:
`outputs/tv-next-imaging-20260924-02`,15actualWSClean inversions,0newQC,
rawresultSHA`aa6d6f89eb47d9dc7f19af7dd8e27a4170deb27fa1d99eaae200d4c82d2adce4`.
All internal source/runtime/tool/nativecols/wholebackup guardsPASS; image
independent audit underway. Fullraw+frozenconfigprojection+figureSHA archived.
MatchedPSFs/commonTEST9169, omittedcompact/extendeddirtyresponse49.30/76.21%,
truth-complete99.67/98.67%; closuremax3.809691406786442e-8Jy/beam<fixed1e-6.
RejectedCARACALfirstpassloses1357TEST/differentPSF. Figure is pairedknown-sky
dirtydifference, not cleaned scienceimage; niter0alsoemitsunused-imageFITS.
Combined report `research/flagging-next-summary.md` distinguishes measured
prototype/uncertifiedsciencepolicy/future independent-observation cost gates.
Original master remains4/5/no gather; completecampaign summary references
fouroriginalbranches+one separatelyfreshretry,nevermutatesoldoriginalgraph.
Public checked checkpoint84d15b3 uses Gijs/gmailidentity/noattributiontrailers.

Scoped extra readonly TRAIN-curvature rank survey is being performed to quantify
the measured support bottleneck, not retune guards/flag troublesomecells. New
separate gain-support report/archive only;9QCsignalresult remains immutable.

Compatibility/confirmed-results checkpoint checks PASS2026-09-24~10:08UTC:
650Python(no skips),19Rust,releasebuild,Clippy-Dwarnings,cargoformat,
full-repository Rufflint+format,91Pythoncompiles,57strictJSONarchives,
four exactrawprojections, embedded auditprogram SHA/compile/allbashsyntax,
real pinned WSClean parser and separate Stimela dryrun/23YAMLparses.
Readonly wrapper review removes an unnecessary writable fixed NumBacache mount;
all imaging temporary caches use tmpfs, preventing symlink/source alias risks.
An initial zsh unmatched tools/*.sh glob stopped the final syntax step; rerun
uses rg-selected existing wrappers under bash and passes. No failing check
authorizes a commit; staged whitespace remains a final gate.

Next checked checkpoint2026-09-24~10:05UTC: prospective independent audit
2355 predicates PASS, signal558/558 complete readonly recovery PASS, zero
additional QC. Prospective physics selects the full-union reference choice in
all3 cases, zero missed benefit; clean/107 nochange,10956 flags known-patch
recall9.40%. Forecasts improve descriptive RMSE over negative-flag-cost-only
by4.5–8.6x; no measured runtime/SOTA or trend-ranking advantage claimed.
Signal guard remains unavailable/UNCERTIFIED at bin811: two TRAIN cells,
one0–2 baseline,2active stations/rank8 versus required12. Sky completeness,
not the selected56flagmask, dominates paired compact/extended recovery.

Imaging CLI compatibility fix changes only4 option spellings; fixed physical
settings,15jobs,budgets/closure tolerances unchanged. Actual pinned parser
preflight now passes before copying/mutating any MS.43 imaging unit tests;
650 total Python/19Rust pass. Full-repository Ruff detected3 pre-existing
Markdown example-format discrepancies; mechanical formatting applied before
rechecking. First Stimela readonly validation failed on its dependency-file
write at a readonly cwd; rerun isolates deps/logs in tmpfs and passes.
Dedicated fresh retry uses `bash tools/flagging/run-imaging.sh
outputs/tv-next-imaging-20260924-02 outputs/tv-response-20260924-precision-01
outputs/tv-caracal-clean-01`, after checked source commit/push. Original failed
master/first imaging remain immutable; no repeated63QC, no fabricated gather.
Current73GiB free space,8GiB reserve; no cleanup/deletion performed.
Pre-compatibility checkpoint backup:
`outputs/flagging-backups/20260924-next-imaging-compatibility/code.tar.gz`,
SHA256`10c089244cd604a56db81680a10dd4c292a36eee22f4f97697a04d6b8eb681ff`.

Original five-branch run finished09:56:33UTC:4/5 branches succeed; imaging fails
retained CLI parsing error, so NO top-level result/gather and no claim that the
original graph completed. Prospective branch finishes54 realQCs (3 baselines+
51 masks), signal9;63 actual new QCs total. All4 completed branch internal
preservation guards pass. Prospective independent artifact audit is next.

First measured checkpoint local checks PASS:646 Python(no skips)/19 Rust,
release build/Clippy/format/lint, Python compilations,53 strictJSON archives,
new exact raw projections and shell syntax. Backup before this checkpoint
`outputs/flagging-backups/20260924-five-track-first-measured/code.tar.gz`,
SHA256`2eea3cbbc88698bb8931b7894db9da9c44da0cc469df9256efd43801679ec937`.
Checked staged whitespace must gate the public commit. Original implementation
snapshot remains intact for historical audit after the CLI fix.

Five-track measured checkpoints2026-09-24~09:54UTC:
trend28 replay branch completed,562/562 independent checks pass; all21 added
smooth-phase comparisons preserve detrended ranked masks, while17 change raw-TV
ranking. Primary objective unchanged; no flags/QC in this saved-gain diagnostic.
Provenance85 objects/505strings/21HISTORY rows extracted,657/657 independent
checks pass; records one CASA split datacolumn=all/keepflags/width1/timebin0s,
not proof of DATA/sigma convention. Conversion/calibration gates remain false.
Exact compact archives/new audit reports are indexed under next-* in research.

Signal branch completes9 actualQCs and full9169commonTEST; independent numerical
audit pending. Unguarded seed10956-cell mask objective1.2495729266458455 confirms
the frozen forecast; absolute-signal guard selects no-change UNCERTIFIED because
baseline TRAIN curvature is underidentified at bin811, native_status3. No T or
absolute near-identity error is available there; do not mislabel this a numeric
signal-rejection threshold result. Paired omitted-sky signals still attenuate.

Imaging first invocation failed before any FITS: WSClean3.6 rejects legacy
`-datacolumn`; source/copies/checkpoint/logs retained, not exportable. Pinned
binary help and full proposed-command `-dry-run` verify four compatible names:
`-data-column`, `-wstack-nwlayers`, `-abs-mem`, `-no-min-grid-resolution`.
These preserve the frozen physical settings, not threshold/precision retuning.
Other branches continue under unchanged source freeze; prospective clean/107
reference masks complete, seed109 ongoing. Top-level graph has NOT succeeded.
Fix-forward source checkpoint and separately fresh imaging run follow only
after active calibration ends; no duplicate QC required.

Trusted implementation tar extracted into sibling `frozen-code` below
`outputs/flagging-backups/20260924-five-track-implementation` for independent
historical replay after the CLI fix. All92 captured /workspace runtime source
paths exactly match that snapshot (93rd receipt is immutable Linux native).

ACTIVE EXECUTION2026-09-24~09:45UTC, source checkpoint
`ec2f17d1dad5f4de65311db19db6daaf1aa4fc2a` pushed and clean. Actual offline
top-level recipe launched via `bash tools/flagging/run-next.sh`:
root `outputs/tv-next-20260924-01`, logs sibling `-logs`, finalimage5da4... .
Inputs prepared/actions-01, historical/concurrent-20260924-01,
response/precision-01, CARACAL/clean-01 and fresh metadata acquisition below;
all five pre-existing sources have explicit OS-read-only bind mounts.
Fresh clean/107/109 inputs construct first, then five isolated branches,
three scatter processes (<=2 QC workers and one imager). No source-runtime edits
are permitted during this freeze. Parallel owners independently audit raw
guard, prospective/provenance and trend/imaging outputs without rerunning QC.

Metadata HEAD85 completed09:43:24UTC:15,672 total bytes, maximum546 bytes,
82 string chunks plus3 numeric HISTORY, fixed origin/schema/unique allowlist,
zero MAIN requests. Separate root and independent-agent checks passed.
Complete HEAD SHA256`92d18475723e6e1ef2586a4a90bf382b0beb4391fd2ae9b55a1626b6ebc41029`,
path `outputs/tv-provenance-head-next-20260924-01`.
Only then conditional GET85 acquired all15,672 bytes; exact ETags/lengths/SHA
receipts validated before offline inspection. Acquisition complete SHA256
`3dc7fd843cb570778a4527349c6cb576aebcf927ee49823eab43097c530b65fc`,
path `outputs/tv-provenance-acquired-next-20260924-01`.
First host invocation lacked PYTHONPATH and made no requests/files; retry with
`PYTHONPATH=python` succeeded. No publisher pickle has been unpickled.

Five-track source checkpoint verification2026-09-24 09:42UTC PASS:
646 Python tests(no skips),19 Rust tests, release build, Clippy-Dwarnings,
Rust/Ruff formatting and lint,91 in-memory Python compilations,49 strictJSON
archives, all15 shell-wrapper syntax checks, top-level Stimela2 dry-run and23
YAML parses. Historical123 action records and13 helper hashes rechecked exact.
Pre-checkpoint backup `outputs/flagging-backups/20260924-five-track-implementation/code.tar.gz`,
SHA256`fade4c26a80fd5619b2f4538ea58e1721e310de53ba046de1e0fe94a956991a0`.
Source checkpoint is ready for public commit/push before new scientific runs.

Final campaign runtime ready2026-09-24: signed WSClean3.6-1 child installed51
new Debian packages,27,171,224 downloaded bytes (25.91MiB), all signed-metadata
size/SHA matches and pre-existing package identities unchanged. Signed package
receipt SHA256`de9be2c0562412103ef099ca579b120d5db361eb62e5babd44068dac395d1f0a`.
Final corrected-kernel overlay avoids repeating those downloads; campaign image
`sha256:5da4c1b754ddc3a43f57b5cb7f4d8b7bf9aa182c53eeac5c4ac0fb6208ac1d22`,
Linux native SHA256`cf61db3728a1bb1e1a8bc66ec738d80a102f636185dd527e11a1f6290c530a84`.
Top-level Stimela2 dry-run and all23 recipe YAML parses pass; prepared casacore
source validates on OS-read-only mount. Full exact dependency/keyring/repository
receipts: `research/results/gain-tv-next-runtime.json`.

Cross-review fixed overflowed coordinate spacings, full helper/runtime closure,
missing residual replay ranking, TRAIN geometry and input/source/cardinality
guards before measurement.39 imaging,83 provenance,34 prospective,22 signal,
17 campaign,6 trend and26 independent trend-review tests now exist. An interim
full test invocation collected new campaign tests while they were still being
finalized:3 failures (source predispatch guard, fixture locks, absent host YAML)
were fixed, not ignored. Final full check is running; no scientific runs yet.

Five-track implementation progress2026-09-24:
new Rust trend kernel, Python trend/prospective/input/parallel interfaces and
six new Stimela2 recipes exist; parallel owners implemented signal guards,
inert native-metadata extraction and fifteen fixed WSClean diagnostics.
Initial full suite556 Python tests passes without skips;19 Rust tests, release
build, Clippy-Dwarnings and Rust format pass. Extra cross-review regressions
are still being finalized before the checked source checkpoint.

Separate kernel overlay built and verified: image
`sha256:ec2d4f2acec9fe39c07e5725d38342aaf330e825ca2bbbd2f23a9e544be77f2c`,
Linux nativeSHA256`70aeda3cebd3e571eed1a3a62573f5556786830ae3b3386cd5aee9a77e4c34df`,
new `rang_trend_slopes` export present. Build's Rust compilation was offline;
Docker contacted its registry for pinned base metadata/authentication.
Original response image102767... retained. Signed-snapshot WSClean child build
is running under256MiB new-deb cap; no scientific runs/HEAD/GET launched yet.
All48 historical JSON archives,123 balanced actions and13 frozen Python helper
hashes independently rechecked unchanged. New measurements remain pending.

Five-track start backup (before new Rust implementation):
`outputs/flagging-backups/20260924-five-track-start/code.tar.gz`,
SHA256 `28a1a055c8c26eb2eff28809bc89fb4a66f556519c5f9c92848a1a450aaf96cb`.
Historical macOS native library copied beside it before rebuilding;
SHA256 `9d4b8105c06e946db797f5f0538c215b866af380f087b2b007f4b603f7cd9a02`.
Old Linux image/native library remain unchanged. New replay and candidate
measurements require new namespaces and checked source/runtime freezes.

Updated 2026-09-24.

## Current continuation and routing

New user-requested five-track execution2026-09-24 after pushed`166350c`:
[frozen results campaign](flagging-next-results.md). Root trend/prospective,
parallel signal guard/provenance/imaging owners active in disjoint NEW files.
New seeds107/109, no oldmeasurementretuning; immutable flags/nativecolumns,
8GiBreserve, checkedboundedoutputs, at most2QCworkers+singleimager. Estimated
1–3hour firstauditedprototypecycle, notpromise; independentdata/imaging/cost
qualitygates still required. No newscience outcome yet. Save exactsource/image
receipts beforeactual runs; original102767solverimage/rawoutputs retained.

Latest measured response: 2026-09-24 08:51:35UTC, checked pushed source `1f53a17`.
`outputs/tv-response-20260924-precision-01` COMPLETE: all ten QuartiCal controls
and final source/native-column/received FLAG/FLAG_ROW restoration audits pass.
Start with [reportable findings](flagging-findings.md), then
[response measurements](flagging-response.md) and
[full compact controls](results/gain-tv-response.json).
Raw result SHA256:
`e7ee791ba0f8ca1f1775c49348dd2e4a51c9fe9e29b77a7e4cda2cfd29215083`.

- All9,169 TEST samples shared, zero loss; fits rank2/condition1.92390.
- Fine omitted-sky positive response: compact51.00%/extended74.19%, versus
  complete diagnostic99.96%/98.92%; negative pairs agree closely.
- Total=direct+adaptation closes within8.253e-15Jy; gain adaptation absorbs
  about29.5/31.0mJy in the positive omitted fine arm without added flags.
- Coarsening raises omitted response only to52.4%/76.2%, while clean validation
  MSE is31.678 versus25.206 (fine), despite normalized polarTV0.03393 versus
  0.14744. LowerTV is not calibration quality.
- Complete control uses truth and known evaluation spectra/positions/extents;
  no images, confidence intervals, independent transfer or SOTA claim.

Independent [input/gain/response audit](flagging-response-verification.md) is complete:
602/614 initial passes,12 retained exact-identity failures;24/24 separately
qualified roundoff checks and30/30 backup/training-holdout boundary checks pass.
Full predicates and all three read-only programs:
`research/results/gain-tv-response-audit.json`, SHA256
`8e46288057230a9efb6d62c8c8203b368334bbe44c11b222532d76d745b58468`.
The same native
calibration inputs/protocol reproduce all ten prediction losses exactly; nine
gain products are bit-identical, clean fine differs by≤3.141e-16 and its shared
normalization differs by one ulp. Do not claim all gains are bit-identical.
Fresh allocated blocks889081856bytes including directories (~0.828GiB), checked
1.5GiB budget/reserve8GiB retained, not an OS quota. Runtime image102767... and
Linux libraryf764... have full receipts below/in the compact archive.
Original failed run remains untouched/not exportable. Ten failed+ten fresh QC
invocations=20 actual invocations of ten frozen controls, not independent replicates.

Final local checks:419Python/17Rust (no skips), release build, Clippy
`-D warnings`, Rust/Ruff lint/format,78 in-memory Python compiles,14 wrapper
syntax checks,48 strict JSON parses and whitespace pass. Three fresh Stimela2
prevalidations and recovered-image pip check pass. Root projection checks23
for the full response raw result/receipts pass;11752 projection predicates also
pass across123 influence rows/492 phase-action rows/28 baselines/configs/58
mask IDs/missing outcomes. Historic `8836e85` source receipts are not rewritten.
All21 targeted archive regressions pass, including exact-failure retention and
eight independent fit reconstructions. Final claims review verifies all response
percentages/mJy/25.7% underfit and retains one-observation/known-family limitations;
phase wording distinguishes equivariant predictions from invariant residual magnitudes.
The publication commit is the Git commit containing this entry; preceding
checked push `1f53a17`. No runtime/settings tuning followed these measurements.
Formatting fix-forward after local measured commit`52f0b8e`: the staged
whitespace check found two trailing blank lines in the new audit files, but its
nonzero status did not stop that commit. Remove only those blanks and update
their SHA256 receipts; JSON values/report content/raw runs are unchanged. Never
rewrite the commit: publish this explicitly checked fix-forward too. The current
Git commit contains the normalized receipts; no data or solver rerun is needed.
Final code/report snapshot, taken before adding its own receipt:
`outputs/flagging-backups/20260924-reportable-signal-final/code.tar.gz`,
SHA256`4f43c78b78f3499224aa93006ffb0e36dba55cc2ebbe45c5088b5b28ff08c381`. All old snapshots and both raw
response trees remain retained; no research-agent cleanup was performed.
Normalized fix-forward snapshot before adding its own receipt:
`outputs/flagging-backups/20260924-reportable-signal-format-final/code.tar.gz`,
SHA256`2b8e500717b97307d5907262883e7cae304507ce3e66fd3656d10cd28d15d201`. Repeat full checks include
unchanged audit JSON/report content versus`52f0b8e`, refreshed byte hashes and
an explicitly gated staged-whitespace check before the fix-forward commit.

Next discriminating experiment: freeze an estimated instrumental-trend/noise
specificity control and establish independently supported native data/noise
provenance before transfer or broad training. Keep actual guarded QC confirmation
after surrogate candidate triage, signal-preservation/support safeguards, and
the pinned full CARACAL controls. The current prototype is not a validated final
flagger or a matched quality/cost novelty result. The85-object textual metadata
plan remains design only, with no new metadata acquisition/parser/conversion.

### Earlier checkpoints (preserved chronology)

Measured native-derived controls2026-09-24 08:42UTC after pushed`8836e85`:
`outputs/tv-influence-20260924-host-01` and
`outputs/tv-equivariance-20260924-host-01` COMPLETE; source/runtime guards pass.
Compact`research/results/gain-tv-{influence,equivariance}.json` curated,
`research/flagging-findings.md` synthesizes mechanisms and limitations.
Physical local response covers120/123old counterfactuals; seed105matchedRMSE
8.5694e-5 vsknownflagcost6.2254e-4=7.26ratio. No TEST/truth inforecasts, no newQC.
Median canonicaldGrelativeerror8.32%,cosine.99690; threepredictedpositive
actions actuallybeneficial, but frozen.1truststep rejectsbesttimeburst105mask.
Recommendedactualbenefit.00034731 vsbest.00076859, regret.00042128.
Allseven cases reuseoneobservation; not independenttransfer/SOTA/speedclaim.
Smoothphase replay520from130existinggainproducts: residualMSEinvariant≤3.41e-13,
predictionerror≤5.96e-15Jy; cleanpolarTV.14744→.27750. Fiveoldsetdecisionsflip,
no unmeasuredrerankedmaskselected. Independentphaseaudit12006predicates passes.
The user confirmed Docker cleanup to recover disk, explaining missingimages;
no cleanup byresearchagents. Derivedpaths ranhostPython3.14.7/NumPy2.5.3,
notpretendedsameLinux image; runtime/native hashes held. Solver-onlylockedbase
recovered, newactualimage`sha256:55487b9fb3140df8b0f7fb9a31148ec4bb7db348a3f33930b6efe00a5d3851b8`,
sameLinuxlibrarySHA`f764ed8f215a6b22db5b511fcefae6398f9ff52c0a1b851d914f66452d235a8f`.
ResponseactualtenQCs finished but evaluationstrictclosure failed;
`outputs/tv-response-20260924-recovered-01` retaineduntouched(.827GiBallocated).
Independentprecisiondiagnosis confirmed all eightarms; differencecomplex64
rounding causes3.18–3.51e-9Jyclosure, castBEFOREsubtract128gives6.88–8.25e-15Jy.
Fixfrozen27targettests, samecalDATA/models/flags/weights/grids/threshold1e-10.
Failedtreeunchanged; doc`research/flagging-response-precision.md`.
Fresh`outputs/tv-response-20260924-precision-01` pending checked launch;
no currentfluxclaim. TenfailedQCs plus tenplannedretryQCs are separate actual
invocations, not20independentcontrols. Physicalindependentaudit4620passes.
Metadata-onlyfuturehostversionreceipts/phaseconfigwordingsplit do not change
measurednumericmethods; original8836e85config/modulehashes remain archival.
Freshintermediatechecks405Python/17Rust(no skips),releasebuild,Clippy-Dwarnings,
Rust/Rufflint/format,77Pythoncompiles,allwrapper syntax,46strictJSONparses,
old123action/rawarchive exactreconstruction/all13oldmodulehashes andwhitespace pass.
Newarchive numericalregressions7pytestcases pass. Solver-onlyresponseDockerfile
nowrequiresjustbaseimage; actualofflinebuild/pipcheck passes,
tagID`sha256:102767125ea2fe1f7fc000738cb16e28d1e967188c227a583d27293596fb2d95`.
Snapshot before adding thisreceipt:
`outputs/flagging-backups/20260924-reportable-measured-intermediate/code.tar.gz`,
SHA256`372c75634821b80ab46615ae99cc73d17ee6f08ee6971f58ae73c7a2a25f4390`.
Currenthostfree109GiB, reserve8GiBretained; no bulkdownloads/fulltoolsrebuild.
Bounded85objectstring/HISTORY plan recorded ONLY asdesign, no acquisition/parser.

Continuation2026-09-24 after pushed`9f25601`: user requests persistent research
until reportable findings and regular checked intermediate commits. New freezes:
`research/flagging-reportable.md`, `research/flagging-equivariance.md`.
Parallel: Rust local actionresponse, ten-solve complete/omitted-sky/grid controls,
smoothreceiverphaseTV replay and supported-data/partial-Jones gauge review.
Implementation checkpoint2026-09-24 08:29UTC: all three new numerical paths
are implemented and frozen. Separate executable nativeStimela2 recipes/wrappers:
`tv-flagging-response`, `tv-flagging-equivariance`, `tv-flagging-influence`.
Actual ten-QC/replay/forecast outcomes still pending, not implied by unit tests.
New response image reuses pinned tool environments and rebuilds only Rust:
`sha256:9a26a19f1b89768e2aa7bb84dad2e4b1e674ed9a847ab2bd026d2f0be759f79a`,
LinuxlibrarySHA256`f764ed8f215a6b22db5b511fcefae6398f9ff52c0a1b851d914f66452d235a8f`.
All three recipe dryruns, native symbols and three environment pipchecks pass.
Root independently regenerated the supported-data diagnostics in the pinned
image:341 numeric leaves match, retained at
`outputs/meerkat-supported-data-regenerated-20260924-01.json`.
Report`research/flagging-supported-data.md`, archive
`research/results/meerkat-supported-data-candidates.json`, reproducible read-only
`examples/diagnose_native_support.py`. NativeSIGMA supports allfour products
but its convention/provenance is NOT validated; zeroXY/YX storedweights cannot
be silently repaired. Only60/61nativeantennaIDs have received-unflaggedcross
support; ID21staysunsupported. Parallelhand-only scalar-sky likelihood has
independent rowU(2)xU(2) freedoms; common-rightpolar gaugealone fails to make
fullJonesTV identified. No data/parser acquisition or partialJones solve here.
Old measuredoutputs/modules protected; fresh runnames only.
Fresh implementation precommitchecks:396Python tests(no skips),17Rust tests,
releasebuild,Clippy-Dwarnings,Rust/Rufflint/format,76Pythonbytecompiles,
allwrapper shellsyntax,42researchJSONparses andGitwhitespace pass.
Snapshot before adding this receipt:
`outputs/flagging-backups/20260924-reportable-implementation/code.tar.gz`,
SHA256`2dc0918a469f4ff200086e0aee45650f9d559c47d1bf4c8dbdeedcb974ccb84d`.
Disk15GiB/reserve8GiB, response checkedbudget1.5GiB, derivedtracks256MiB each;
reservations/checkpoints are not OSquotas. No cleanup/bulk acquisition. Pre-start
backupSHA/path inprotocol; designs precede implementations/measurements.

Latest measured checkpoint, 2026-09-24 07:18:30UTC: the five-track Stimela2
suite completed all ten scatter branches and the dependent transfer fit, with
three workers. Implementation commit `1739d48` is pushed. Raw run:
`outputs/tv-concurrent-20260924-01`; entry recipe
`recipes/tv-flagging-concurrent.yaml`. All13 frozen module hashes and the prepared
source/acquisition boundaries are unchanged. Result/archive curation and
read-only verification are complete; no source retuning.

Compact evidence: `research/results/gain-tv-concurrent.json`,
`gain-tv-balanced.json`, `gain-tv-signal.json`, `gain-tv-transfer.json`,
`meerkat-public-pilot.json`; the acquisition and standalone gain controls keep
their historical archives. Seven balanced cases require130 actual full-Jones
diagnostic solves. Only time-burst seed105 selects flags: residual58/58 known
injected additions,10.1045% recall; TV113/136 known injected,19.6864% recall,
23 outside known injection. Objectives1.2496526895/1.2492314087 versus1.25;
random and every other case retain no change. Outside-injection additions are
not proven false positives on unlabeled DATA. This is not a robust TV advantage.

Paired signal track:16 diagnostic solves plus native MAD flag generation;
commonTEST9169/9169, no lost support. Residual/TV retain no extra flags. The
conditional omitted-source fits recover only15.34% compact/9.31% extended
reference flux, but BOTH fitted spectral indices hit the-5 lower bound.
Report boundary-constrained diagnostics, NOT astrophysical slopes or images.
NativeMAD adds960TRAIN cells, worsens objective1.2874921193. WSClean absent.

Grouped fitted model:35TRAIN/34VAL/36TEST actual guarded labels, seed groups
101/103/105, penalty0.1, optimism margin0.00108005734. All six recommendations
are no-change, missing the time-burst105 benefit0.0007685913. A post-hoc known
flag-cost-only predictor is much closer than a TRAIN-mean constant: do not imply
broad transferable improvement. Every case reuses one four-antenna observation.

Public numeric inspection is complete, not conversion/calibration: both scans
retain61antennas/16complete integrations/30256rows/128channels1070–1096.541MHz.
Received FLAG fractions80.4890%/80.2970%; DATA/model finite. Native XY/YX
WEIGHT_SPECTRUM is identically zero, leaving zero eligible full-four-correlation
cross cells in the current protocol. NEVER substitute row WEIGHT=1, clear flags
or cherry-pick a nicer epoch to force acceptance. This does not prove the data
uncalibratable under a separately justified partial-support/gauge protocol.
Safe string/native-MS conversion, representative full-support calibration,
independent observation transfer, images and mature-method cost/quality wins
remain outstanding. Source FLAGS/DATA/all four native weight/SIGMA columns are
protected; intentional simulation writes affect backed-up working copies only.

Latest full local checks:323Python tests(no skips),14Rust tests,releasebuild,
Clippy,Rust/Ruff lint/format,bytecompile,allwrapper syntax,41researchJSON parses,
exact archive/raw-result reconstruction andallthreecontainer pipchecks pass.
Actual recipe execution completes; Gitwhitespace passes before measured commit.
Suite allocated6.9GiB/free disk15GiB at07:22UTC, reserve8GiB retained/no cleanup.
The frozen6GiB allowance was a forecast, not a hard cap; check capacity afresh.
Read-only audit routing: `research/results/gain-tv-concurrent-audit.json`.
Separate counts:108prepared,2303balanced numerical/artifact,1297new compact
archive integrity,1255standalone/1257integrated gain-control,680transfer,
32+6+17signal artifact/replay checks all pass; counts are not scientific wins.
Final source/archive snapshot before adding its receipt to the handoff:
`outputs/flagging-backups/20260924-concurrent-measured-final/code.tar.gz`,
SHA2568fdaecdbf429a8d052d2ebe1bb4f7af676b7998e74a89520a3949ff4ca3fc419.
Next: source-preservation/identifiability guards on a new frozen validation
protocol, a genuinely supported representative dataset, then matched native
accuracy/cost experiments. Never tune new settings to the seed105 outcome.

## Historical checkpoints (superseded statuses)

Latest2026-09-24 07:10UTC: allfive modules/recipes implementedandstable;
fullchecks323Python/14Rust(no skips),releasebuild,Clippy,Rust/Rufflint/format,
bytecompile,allwrappersyntax,35JSONarchives,whitespace andallthreecontainer
pipchecks pass. Master/public/signal actualrecipe dryruns pass. Integratedactual
Stimela scatter3 started07:08:54UTC at`outputs/tv-concurrent-20260924-01`;
sixfresh backed-up cases staged, firstthree fullJones branches active, results
pending. Masterfreezes13sourcehashes andimage beforecases/solves; donotedit
runtime modules untilfinish orretainfailure andchoosea newrun.

Gain-only diagnostics measured180controls separately at
`outputs/tv-uncertainty-controls-01`; trackedcompactarchive
`research/results/gain-tv-uncertainty.json`. Legitimate smoothdelaygains mayhave
muchhigherrawTV thanflatnoisy gains. Detrending/noiseexcess isconditional
synthetic guidance only, notrealQC uncertainty orRFIclassificationvalidation.
Publicreceipts independentlyverified75boundedobjects/884609513bytes; first
entireFLAGchunk80.4068%flags, retainednegativefinding, no clearing/cherrypick.
Trackedacquisition `research/results/meerkat-public-ingestion.json`; fullnumeric
inspectionandMSconversion/calibration/transfer remainpending. Publicreader34
tests includereceipttotal/headers/statbounds beforepayloadread; reviewissueclosed.
Disk13GiB/allocatedsuite1.3GiB asof07:10UTC, reserve8GiB/no cleanup.
Checkedimplementation backup
`outputs/flagging-backups/20260924-concurrent-implementation/code.tar.gz`,
SHA2568d68fed79cc9171dec7322a2de40b98670ca4c03ef30dc031956ba2090a5a5bb.

User requests allfive next workstreams concurrently. Checked hardeningcheckpoint
`5377902` is pushed and worktree initiallyclean. Pre-outcome protocol/routing:
`research/flagging-concurrent.md`. Geometry-balanced search, uncertaintyTV,
bounded61antenna numeric ingestion, pairedscience signals and groupedtransfer
model implementedinparallel with separatefile ownership. Startdisk17GiB;
reserve8GiB, no cleanup, maxthree actualsolverworkers. Frozenfreshinjection
seeds101/103/105 are train/validation/test fortransfer, strongtimeburst/antlocal.
No newmeasurements yet. Backup/path/SHA inprotocol; originalflagsalwaysprotected.

Bounded publicacquisition nowcomplete: `outputs/tv-public-acquired-20260924-01`,
75numericBloscobjects/884609513bytes(843.63MiB), MAIN_0/MAIN_1tile8firstrowchunk,
metadatarepin+HEAD/GET exactETag/length+SHA256 eachobject. ReceivedFLAG/FLAG_ROW
andWEIGHT/WEIGHT_SPECTRUM/SIGMA/SIGMA_SPECTRUM allacquired unchanged; no
CORRECTED_DATA orobject/picklestringdecoded. Offlineinspection/calibrationnotyet.
Newpublicreader34tests/masterorchestrator8tests pass, bothrecipes actualoffline
dryruns pass. Balancedsearch17tests anduncertainty/transfer21tests pass; source
filesstable. Masterrecipe scatter3, transferwaitsforactualbalancedlabels;
`recipes/tv-flagging-concurrent.yaml`. Signalmodule nowstable/16tests pass.

Complete measured checkpoint `94369a0` pushed to origin/main after196Python/
14Rust and full local checks, public user identity/no co-authors. Separate
read-only artifact verification is now complete:318predicates pass across all
seven structured states/14exports/101solves and four native controls. Includes
all present weight/SIGMA columns, exact source reconstruction, frozen ranks,
actual Rust TV/support/scale, source boundaries and selections. Record
`research/results/gain-tv-artifact-audit.json`; no measurement-blocking issue.

Fix-forward hardening after review: new stdlib host preflight resolves run/log/
prepared/strategy paths before any cache,log orDocker writes, rejects nested/
escaped sources and reused/dangling logs, and reserves logs with exclusivemkdir.
Both actual wrappers have invalid-call regression tests and fresh offline
recipe dry-runs pass. Diagnostic objective rejects nonfinite/negative inputs;
all98published action/native scores remain exactly unchanged under new guards.
These fixes do not relabel old runs as new-code measurements. Full new checks
pass before commit/push:222Python/14Rust(no skips),releasebuild,Clippy,Rust/Ruff
lint/format,bytecompile,allwrapper shell syntax,33research JSON parses and
whitespace. Both hardened wrappers pass fresh offline recipe dry-runs; only
valid/invalid-call hardening, no retuned science. Pre-commit code/archive backup
`outputs/flagging-backups/20260923-preflight-hardening/code.tar.gz`,
SHA2561ab43731d4d195dbb7631f737eebb3b1e9812668ff5c20acca56296444f438c8.

Completed native/structured measured checkpoint, superseding pending entries
below. Four unmodified CARACAL native controls finish19:19:11UTC with all source/
original-mask/DATA/weight audits passing. First-pass controls~36% exceedbudget
and lose support; mild controls~0.90–1.00% retain support but worsen objective,
TV and val/test prediction. Report/archive `research/flagging-caracal.md` and
`research/results/gain-tv-caracal.json`; no native policy selected.

All seven unchanged frozen structured controls complete19:26:27UTC,101actual
QuartiCal solves. Both rank23,329identicalmasks/top8 each; all112ranked slots
are single-baseline actions, neverglobal/star. Both nochange on unmodified,
both narrowband, weaktimeburst/antenna-local. Strongtimeburst residual rank
selects11known-injected samples(2.89%recall),objective1.249904895/test−0.01985%;
TV rank choosesnone. Strongantenna-local TVrank selects8outside known injection,
objective1.249931062/test−0.00949%,zero injectionrecall; notprovenfalsepositives.
All source/export/originalflags/rows/DATA/weights/TRAIN-only audits pass.
Report/archive `research/flagging-structured.md`/`research/results/gain-tv-structured.json`.
No independent transfer, signal/image/SOTA or robustTV-guidance advantage.

After all measurements, rename only audit key no_truth_read→
no_truth_decoded_or_used_for_selection: provenance hashes label-file bytes but
does not decode/use them in decisions. Raw measured audits remain annotated;
archive verifies exact measured source reconstruction by one literal replacement
against every recorded SHA. Numerical protocol unchanged. Recipe logger fix
validated in fresh native/structured dry-runs and five actual isolated-log runs.
Firsttwo structured outer logs retained in
`outputs/flagging-backups/20260923-structured-shared-logs/`; neveruse forcostclaims.

Fresh full checks after the audit-wording change pass:196Python/14Rust(no skips),
releasebuild,Clippy,Rust/Ruff lint/format,bytecompile,allwrapper shell syntax,
32research JSON parses and whitespace. Both new recipes prevalidate locally;
four native and seven structured controls executed, no CI used as test runner.
Final code/archive backup
`outputs/flagging-backups/20260923-caracal-structured-final/code.tar.gz`,
SHA2560d0b03fbe0dce04372a2976dca9c13ca6d22db16a5f756beb810ca7959c7e82a.
Independent agent read-only review
already passed51actual checks for native+firsttwo structured states, recomputed
rankings/TVsupport/exports; extension toremainingfive ongoing. Next: calibrated
coherence/aggregate or group-balanced proposals, uncertainty-awareTV and signal
preservation; representative61antenna primary acquisition remains proposedonly.

Native implementation/partial-results/data provenance checkpoint `9a454fc` was
pushed to origin/main using the public user identity, no co-author trailers.
All local tests passed before commit, including187Python tests once the parallel
pure generator was present; the committed native implementation itself has179.

Structured matched-search implementation and recipe now have17pure tests;
clean and strong time-burst frozen experiments started19:17UTC in
`outputs/tv-structured-clean-01/` and `outputs/tv-structured-timeburst-01/`.
Both rankings have identical23,329mask families and top8budgets; shared masks
reuse one actual solve. Only single whole-rectangle proposals, no trimming or
unions; original flags/rows/DATA/weights remain protected. Source/truth/test
selection rules and module hashes are recorded before baseline solves.
Pre-run backup `outputs/flagging-backups/20260923-structured-native/code.tar.gz`,
SHA2565c76acfb44355ebd43d139c6a15f3ae45357d5a7af3aff70811d883728e5a75e.
Measured results pending; do not claim a new model or quality improvement.

Integration finding: top-level recipe static log paths override the wrapper's
global `-s opts.log.dir`, so these first two structured controls share Stimela's
outer logs/profiling. Actual copiedMS/config/frozen masks/QC logs/checkpoints are
isolated per run; no scientific-state collision. Preserve shared outer logs and
do not use their profiling as timings. Removed only the recipe's fixed log-dir
default (no algorithm/module change); validate wrapper-selected unique paths in
a fresh dry-run before commit. Native CARACAL's single outer run is unaffected
by this parallel collision but receives the same logging fix for future runs.

Handoff/rules/CARACAL source checkpoint3d561d1 pushed toorigin/main; no agent
attribution or Spotify identity. New native verification module/recipe/wrapper
implemented, measurements pending. It compares operational and artificial
holdout-masked input flags under unmodified first-pass/mild CARACAL YAMLs.
Installed Tricolour0.2.1 polynomial cycles can discard starting masks, so neither
control is advertised as unseen-holdout policy evaluation. Actual gain solves
always preserve every originalflag/row. The new implementation passed all local
checks and179Python/14Rust tests; native measurements are separately recorded.

Native default CARACAL verification started in `outputs/tv-caracal-clean-01/`:
first-pass and mild strategies × operational/holdout-masked inputs, full native
CLI withoneworker, no network, protected copies and recorded engine/mask hashes.
Baseline reproducesTV0.1474368701/validation25.20612260. Source code frozen for
this run, pre-runbackup `outputs/flagging-backups/20260923-caracal-native/code.tar.gz`.
Full new suite already passed14Rust/179Python tests(no skips), releasebuild,
Clippy,Rust/Ruff lint/format,bytecompile andshellsyntax. Both first-pass controls
completed successfully and preserved persisted original flags/rows/DATA/weights,
but propose36.207%/36.133% extra training flags, lose fixed TV support and have
unavailable validation losses. Both are rejected; no policy is chosen. Partial
archive `research/results/gain-tv-caracal-progress.json` explicitly records2of4
controls and final source audit pending. Full-strategy mild controls ongoing.
Verified non-TTY Dask progress logger adds~300seconds per native CLI call;
do not misidentify the sleeping timer as deadlock or use it as kernel timing.

Representative public data identified: `research/flagging-public-data.md` and
`research/results/meerkat-public-primary-metadata.json`. Metadata/nine numeric
chunks only, no visibility downloads or pickle decoding. Actual primary archive
has61antennas/eightscans/fullLband/XX,XY,YX,YY and supplied MODEL_DATA/nativeweights.
A proposed one-tile DATA/model/FLAG/weight acquisition would fetch353.48MiB
compressed; current~21GiB disk requires strict capacity/backups accounting.
Flag/model provenance, occupancy and support remain unverified. Closure-based
cross-check is now documented as a proposed hypothesis, not an implementation.

Structured TRAIN-only multiscale candidate generation is proceeding in parallel
with the native verification under the earlier user authorization. Root owns
integration/recipes/results; injection-controls agent owns only the new pure
candidate module/tests. Frozen residual and TV-conditioned scoring/top8 budgets
must be archived before any actual gain re-solves. No structured result yet.

Native implementation/partial-results/public-data checkpoint pre-commit checks:
release build,14Rust/179Python tests(no skips),Clippy,Rust/Ruff lint/format,
bytecompile,all wrapper shell syntax,30research JSON archives and all three
container pip checks pass. Actual native recipe prevalidation/execution is
underway on protected copies. Backup
`outputs/flagging-backups/20260923-caracal-progress-commit/code.tar.gz`,
SHA25688047647948a3b53cdf3b7d9dda2230637291cea43d1c3b0454b885c4b5c8472.

The verified baseline/follow-up commits35e763b/f782921 were pushed to origin/main
at the user's request on2026-09-23. Both author and committer are
Gijs Molenaar <gijsmolenaar@gmail.com>; no co-author/agent attribution or Spotify
email occurs in those commit messages. Attribution prohibitions and durable
handoff routing are explicit in rootAGENTS.md. Start with `research/README.md`.

The user additionally requested CARACAL strategy verification and regular pushes
of checked progress so astronomers can follow along. Official CARACAL revision
8f7bb363876f5f0daecbf2167c36bb597c7e5160 strategy/flag-worker inspection completed:
polarisation-mode fullTricolour passes/staticmasks/polynomial residual handling
are not the reduced StokesI kernel comparator. AO firstpass_Q usesStokesQ.
Report `research/flagging-caracal.md`; full native strategy measurements pending.
Current documentation/routing/rules checkpoint passed14Rust/171Python tests,
releasebuild,Clippy,Rust/Ruff lint/format,bytecompile and28archive JSON parsing.

Continuation: investigate structured multiscale baseline/antenna-shared flagging
actions without injection-truth inputs, keeping the original TV/validation/flag
budget and all original flags. Frozen proposed scope, hypotheses and primary
prior-art links: `research/flagging-next.md`. Implementation/results pending.
Pre-edit backup `outputs/flagging-backups/20260923-structured-start/code.tar.gz`,
SHA256a421d417394d256ac8024752a796f45cf46cb97ab1d091bc0f9f66fd7a9f92cb.
Current handoff/rules/planning/source-inspection changes have fresh local checks;
their checkpoint will be pushed before further implementation. Larger structured
and CARACAL verification experiments require their own measured archives/checks.

## Active flagging experiment (2026-09-23)

The user requested a model for MeerKAT flagging trained on the TV norm of
QuartiCal full complex 2x2 gains, guided by TV maps, delivered as a Stimela2
recipe. Preserve every original observatory flag and back up as work proceeds.
The clean initial revision is `39eeb53`; code and raw archive backups are in
`outputs/flagging-backups/20260923-initial/`. The existing real public SKA scan-9
fixture is the first intuition dataset. Plan and provenance are recorded in
`research/flagging.md`. An isolated public-PyPI QuartiCal 0.2.7/Stimela 2.1.4
Linux environment has been built and tested. Earlier pointing results remain valid
under their documented assumptions.

Checkpoint: complete Stimela2 pilot in `outputs/tv-flagging-pilot-03/` selected
no additional flags. Baseline gauge-fixed TV 0.1476474, raw TV 0.2701043,
validation weighted MSE 25.20588. Six nonempty proposals increased TV and none
beat no-change. This version used unwhitened policy features; test MSE was
unavailable due to unsupported baseline predictions. Original flags/data
digests survived. Archive the null result. Final strategy now whitens features,
reserves sparse-bin training data before solving, reports invalid prediction
counts and masks unsupported plot bins. Final pinned-environment replay pending.
Full local checks passed 14 Rust and 112 Python tests before the latest
sparse-bin regression addition; rerun appropriate verification after changes.

Second complete pinned-environment pilot `outputs/tv-flagging-pilot-04/` passed:
73,720 train / 9,115 validation / 9,169 test samples; zero invalid predictions.
Gauge-fixed TV 0.14743687, raw TV 0.26732583; validation MSE 25.20612, test MSE
24.91961. Five nonempty proposals raised TV; no additions selected. Original
flags and final DATA array verified unchanged. Latest suite passed 113 Python
tests before the final telescope/band guard regression. User explicitly
reaffirmed MeerKAT L-band only; OBSERVATION identifies MeerKAT, project
20230103-0005. Preparation now enforces MeerKAT and nominal 856–1712 MHz channels.
Final scope-guarded recipe replay: `outputs/tv-flagging-pilot-06/`, passed.
The scope-guard startup caught a casacore string-list `.tolist()` assumption;
explicit NumPy conversion fixed it. No original observation was modified.

Final flagging checkpoint (2026-09-23): recipe implements prepare/train/report,
QuartiCal full complex 2x2 inner solves, Rust masked Frobenius TV with fixed
support/scale, unpolarized polar-gauge handling, noise-weighted TV-conditioned
outlier policy, original-flag lower bounds, per-write backups, flag budget,
fixed validation and test checks, and explicit MeerKAT L-band metadata guards.
Final run reproduced the prior no-change result, with zero invalid predictions,
test MSE ratio 1.0, all 1,074,094 original flag cells/rows and final DATA preserved.
Results/provenance archived in `research/results/gain-tv-flagging.json`;
method and limitations in `research/flagging.md`; recipe `recipes/tv-flagging.yaml`.
Verification passed release build, 14 Rust/114 Python tests (no skips), Clippy,
Rust/Ruff lint/format, byte compilation, dependency and whitespace checks, and
the full pinned container recipe. Final backup is
`outputs/flagging-backups/20260923-final/`. This checkpoint is the baseline for
the user-requested commit before parallel follow-up work.
No flagging/imaging improvement or native-performance advantage established.
Next scientifically relevant checks: accurate L-band calibrator sky,
RFI/signal injection controls and matched established flagger comparisons.

User authorized parallel follow-ups and a commit of all current flagging work.
Four workstreams: injection/oracle controls, SARAO multi-component sky,
QuartiCal MAD/Tricolour comparators, and measured patch-action TV benefit.
Each must use fresh isolated outputs and writable MS copies. The learned-policy
scientific assessment depends on the controls, even if implementation proceeds
in parallel. Detailed proposed scope and references are in `research/flagging.md`.
Fresh pre-commit verification passed: release build, 14 Rust and 114 Python
tests, Clippy, formatting/lint, container build/dependency consistency, research
JSON parsing and the complete Stimela2 replay in
`outputs/tv-flagging-precommit-01/`. Replay reproduced no additions, TV
0.14743687, test MSE ratio 1.0 and preservation audits. Pre-commit code backup:
`outputs/flagging-backups/20260923-precommit/code.tar.gz`, SHA256
`ab9a0c849041a418a6abce788a25f4dcac1d336883b2ffe2e1516ff4004b4c01`.
No follow-up quality improvement is yet measured.

Parallel execution checkpoint: baseline committed as `35e763b` under
`Gijs Molenaar <gijsmolenaar@gmail.com>`; no push requested/performed. Three
delegated workstreams own injection, calibrator-sky and comparator modules,
recipes, tests and reports; root owns action-benefit and suite integration.
Individual branches use fresh copied MS and isolated compatible tool venvs.
Crystalball's psutil requirement conflicts with Stimela; Tricolour's legacy
Numba requirement conflicts with QuartiCal. Separate `/opt/sky` and
`/opt/tricolour` environments resolve these without altering the base solver.

Action branch completed `outputs/tv-flagging-actions-01/`: 16 disjoint
counterfactual patch re-solves, 10/3/3 train/validation/test actions, seed29.
Fifteen removals increased fixed-support TV. One validation-action removal
lowered TV0.172% but worsened validation/test MSE0.117%/0.177%; this illustrates
that smoother fitted gains do not necessarily predict held-out data better.
Ridge model test-action MSE2.971197e-6 exceeds constant-control1.670672e-6;
selected no additions. Original flags/data/source/copy audits passed. Compact
archive `research/results/gain-tv-actions.json`, report `research/flagging-actions.md`.
Parallel Stimela2 recipe `recipes/tv-flagging-parallel.yaml` prevalidates under
installed2.1.4 with native `for_loop.scatter=4`; full concurrent execution is
not yet verified. Suite image successfully combines the two separate venvs
and passes all three pip checks. Injection, sky and comparator pilots remain
in progress; retain their checkpoints and do not claim scientific improvement.

Further parallel checkpoint: all six injection cases passed, 49 actual solves.
Strong time-burst injection-only oracle improves currentobjective1.25→1.24873479
while proposalpolicy choosesnochange. Oracle is evaluation-only. Three-sky
control passed: fullcatalog improves val/test MSE~1.20%/~0.98% vs officialprimary
but slightly raises TV. Clean and strongnarrowband comparatorpilots passed with
nochange; packaged Tricolour dilation expandsrandomholdoutholes and is retained
as negativecontrol, explicit holdout-safe settings tested separately.
Root actionpilot on copiedtimeburst completed16 re-solves, source/flags/DATA
audits passed, nochange; predictor testMSE9.546514e-7 vsconstant9.397650e-7.
Full suite is running native scatter4 in `outputs/tv-flagging-parallel-01/`;
sky and action branches complete, comparator/injection branches ongoing.
Review found generic preparedDir trust/nesting safety gaps; new original-state
and split validation helper is being added before commit. Trusted measured
inputs are consistent and no original flags/data were lost. All follow-up
findings remain local/uncommitted pending integration checks.

Final parallel checkpoint (supersedes the in-progress entries above): all four
native Stimela2 scatter workers completed in
`outputs/tv-flagging-parallel-01/`, 18:21:29–18:28:32 UTC, no failures. Individual
and concurrent pilots reproduce the negative findings summarized in
`research/flagging-parallel.md` and `research/results/gain-tv-parallel.json`.
No flagging/imaging superiority or native-performance advantage established.
The strong time-burst evaluation-only oracle improves the guarded objective;
current proposals and ridge action learning still select no-change. Fullsky
predicts held-out data somewhat better while slightly increasing gain TV.

Prepared-input safety integration completed: actual original flags/rows and
native weights are authoritative, saved/work data and metadata must agree,
eligible splits must be disjoint and manifest channels/count/grid coherent.
Nested source/output paths are rejected before creating outputs. Fresh gated
action and comparator Stimela smokes passed. Final helper
SHA2568c1878cdaa3259ca2e5416b78df2a89544a87cea86aa1b47099eaf4b3d96e8ab
independently audited 24 completed prepared inputs read-only, including every
concurrent branch/case; source/original digests, final DATA/native weights and
original flags passed. An in-memory original-flag tampering probe was rejected.
The original scientific runs predate these new guards and remain versioned,
not silently relabeled as reruns of the strengthened implementation.

Fresh full local verification: release build,14Rust/171Python tests(no skips),
Clippy,Rust/Ruff lint/format,byte compilation,shell syntax,27result JSON archives
and whitespace checks passed. All dependency environments and containers were
built/checked locally; no CI used as a test runner. All six final Stimela recipe
schemas passed dry-runs without touching real data. Final backup directory:
`outputs/flagging-backups/20260923-parallel-final/`. The follow-up checkpoint
contains code and compact measured findings; raw MS/catalog/gain outputs stay
ignored, never added to Git.
Baseline commit35e763b is local; no push requested or performed.
Next discriminating scientific work is broader coherent action proposals and
independent MeerKAT L-band observation/image/signal-recovery checks, not an
assumed neural-network or TV-only solution.

## Earlier pointing checkpoint

Handoff documentation supersedes the historical in-progress entries below:
`research/status.md` is the current scientific assessment and
`research/development-roadmap.md` specifies the next go/no-go experiment.
The antenna-beam work was committed and pushed as `2b5211a`.
README smoke testing found complex gains could not be serialized by
`examples/pointing.py`; real/imaginary arrays now preserve these outputs and
an end-to-end CLI regression covers the failure. Both README examples run;
the seed-7 joint antenna-width campaign converged in all eight cases.
Final verification passed: release build, 12 Rust and 107 Python tests with no
skips, Clippy, Rust/Ruff formatting, Ruff lint, byte-compilation and whitespace
checks. All 20 result JSON archives parse and handoff local file links resolve.
Verified environment and smoke results are recorded in `research/status.md`.
This checkpoint includes the documentation, export fix and regression test;
next research work is the roadmap's focused algorithm comparison, not a novelty
claim. Generated outputs and local environments remain ignored and uncommitted.

## Historical checkpoint log

Entries below describe their state at the time, not outstanding current work.

- Antenna-beam checkpoint full verification passed: release build,12Rust tests,106Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks. This includes the relative/common uncertainty split and existing solver paths. Ready to commit; continue after checkpoint.

- Component-wise coverage replay completed: omitted antenna widths relative17.0%, common41.3%, total26.3%; jointwidth relative95.7%, common85.4%, total89.4%. Mean median relative std0.868 vs0.899arcsec: bias removal, not interval inflation. Same12noise/fixedtruth71, correlated coordinates; no precise coverage guarantee. Replay archived separately (`antenna-beam-coverage-components.json`), not counted as new independent trials. Report `antenna-beam-widths.md` and README linked; latest full checks running after uncertainty split. Next independent adequacy/signal-recovery validation; no novelty or measured-data calibration claim.

- Heterogeneous-beam result archived in `results/antenna-beam-widths.json`: 168fit configurations (144three-seed stress/prior +24fixed-truth noise). Ignored widths relative6.30–9.26arcsec/test2.60–3.98; sharedwidthalone6.33–9.19/test2.60–3.99; inferredrelativewidthσ.03 gives0.79–1.10/test1.049–1.051, widthRMSE2.33e-4–3.55e-4. σ.003 comparable; overconfidentσ.0003 leaves3.17–4.36arcsec/test1.43–1.72. All converge. Twelve-noise truth71 total-pointing95%coverage26.28% omittedwidth vs89.43% fittedwidth; relative-widthcoverage94/96, fluxratio34/36 fitted vs28/36 omitted. Correlated coordinates/one truth, no precise confidence claims. Full checks passed12Rust+106Python before newest uncertainty-output split.
- New follow-up: return marginalized relative and common pointing standard deviations separately from total physical-pointing std. Replaying both12noise pilots with split coverage diagnostics; full tests need rerun after this change. This avoids conflating robust relative pointing with weak shared-mode inference. No commit yet for antenna-beam work.

- Relative antenna-width inference passed noiseless combined recovery; all6 three-seed heterogeneous-beam/prior campaigns finished (144fits). Inferred contrasts recover width deviations to about2–3e-4 log width and restore~1arcsec pointing in initial0.03prior results. Stronger-prior controls0.003/0.0003 retained. Twelve-noise fixedtruth71 coverage campaign with joint antenna widths finished; paired omitted-antenna-width coverage run and full checks running. Do not equate this matched-family inference with novelty: BIRO already precedes joint pointing/beam inference. New docs/archive pending; no commit until full checks pass.

- Heterogeneous-beam continuation: 1% pre-demean antenna log-width scatter yields roughly8–9arcsec relative pointing errors despite correct quadratic spectral gains; a shared-width fit does not fix it. Known-per-antenna oracle control completed. Added inferred zero-mean log-width deviations (N−1 orthonormal contrasts) plus optional shared width, avoiding a redundant common width parameter. Full prior Jacobian uncertainty now includes marginal relative antenna-width std. Combined common-pointing/shared-width/relative-width noiseless test and finite differences passed (15 beam tests). First inferred-width campaign running/completing; prior sensitivity0.003 and0.0003 (default0.03) running. New code/results uncommitted; no full checks yet.

- `811bed9` chromatic/polynomial checkpoint pushed. Continuing gate1: optional known per-antenna scalar log-width corrections in tabulated beam predictor, with common-width and shape callbacks retaining them. Example injects independent demeaned antenna width errors using a separate reproducible seed stream; optional explicitly labelled known-beam oracle control. Targeted uniform-width equivalence, autodiff/finite-difference locality and input-validation tests plus first0.01scatter campaign running. No heterogeneous-beam recovery result claimed yet; new changes uncommitted.

- Chromatic/polynomial checkpoint verified: release build,12Rust tests,100Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks all passed. Degree0/achromatic equivalence, polynomial joint noiseless recovery with time-varying spectral phase+amplitude, and invalid option combinations covered. Prior-art boundary explicitly linked to Yatawatta2015 frequency-smooth distributed calibration; no polynomial novelty claim.

- Gate2 follow-up now168 archived fits across7 campaigns, all converged. Degree1 gain model + fitted spectra uses192 total parameters vs312 independent-channel, with linear-truth relative0.726–1.038arcsec/test1.016–1.039. Added quadratic truthscale0.5 breaks degree1 (relative4.75–6.28arcsec/test17.2–32.4); degree2 restoresrelative0.724–1.065/test1.043–1.047 with252params, channelbaseline0.754–1.090/test1.059–1.065. This is expected matched-family compression, not novelty; priors differ across parameterizations. Archive `research/results/chromatic-gains.json`, report `research/chromatic-gains.md`. Expanded noiseless time-varying chromatic phase+amplitude tests and invalid-option controls passed46 targeted tests; new degree0 equivalence test/full checks pending. Continue with independently validated model adequacy and out-of-family beams/bandpasses, not claims from inadequate baselines.

- Gate2 chromatic-truth campaign completed72 fits, all converged. Achromatic joint fit: relative18.9–26.4arcsec, held-out whitened mean square543–619. Independent channel gains restore relative0.759–1.094arcsec and test1.054–1.065. Adding spectral-index priors0.1 changes relative little but common error grows from0.20–0.29arcsec to0.70–1.46arcsec (matched beam, commonprior0.5arcmin). These are assumed linear spectral log-gain slopes, not measured bandpasses. Results in ignored outputs/*commonprior0.5*chromatic1*.
- Implemented optional gain_frequency_degree Chebyshev log-gain coefficients (degree+1 rather than one coefficient per channel, tensor time-spline basis). Independent coefficient priors explicitly differ from independent-channel priors. Returns frequency-labelled gains and basis metadata. No state-of-the-art or novelty claim. Noiseless joint recovery tests expanded; targeted checks and24fit linear-degree+spectral-prior campaign running. Changes uncommitted.

- `f270342` committed and pushed with structured projection benchmarks and public-MS reader. Continuing gate2: `examples/relative_pointing.py` now injects optional smooth frequency-dependent log-gain slopes (linear frequency coordinate around1.3GHz per0.4GHz), independent of fitted gain flexibility. Optional spectral-index priors added to joint-flux/gain-only cases and prediction uses fitted spectra. Three-seed campaigns running: achromatic fit, per-channel fit, per-channel+spectral priors, all with commonprior0.5arcmin and true slope scale1. New script changes uncommitted; no conclusions yet.

- Checkpoint verification passed: release build,12Rust tests,91Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks. Digest-pinned public-PyPI Docker reader build and actual read-only archive inspection also passed. No raw observation files or upstream source downloads are committed.

- Ready-to-checkpoint: public-MS inspector/container verified; structured projector and internal Rust layout optimized. Final isolated scaling run (after tests completed) archived:64-size full NumPy0.1525s/312.2MiB, grouped NumPy0.0621s/133.5MiB, grouped Rust0.1713s/134.0MiB; rank634, Gram relativeerror<5e-16. No full-array geometry, sky/beam simulation or end-to-end calibration in this matrix benchmark. Full checks passed12Rust+89Python before two additional empty-shared projector tests; final rerun pending. Continue afterward with realistic gain/beam mismatch, not another claim based only on kernel speed.

- Scaling continuation: synthetic gain-incidence matrices at8/16/32/64 antennas and4 channels, isolated workers and whole-process peakRSS. Found poor row-major access in Rust QR. Internal column-major storage plus four-lane dot accumulation cuts64-size grouped Rust median1.359s→0.173s; NumPy/Accelerate still~0.062s. Shared/target derivatives random: not a MeerKAT observation or calibration benchmark. Exact Gram/rank checks pass~5e-16. Five-repeat final campaign underway; native full checks running after added scale/remainder tests. Important correction: NumPy uses Apple Accelerate, so OPENBLAS_NUM_THREADS=1 does not establish single-thread execution. Record environment and backend, not an unmeasured thread count.

- Active continuation: `fdf5883` pushed after full checks (11 Rust, 73 Python). Frequency-blocked gain elimination now implemented and tested against dense information, including exact gauge/flux-anchor controls. An additional regression caught and fixed promotion of already-eliminated shared nuisance round-off to rank. Five warmed repetitions: dense median1.520s, time-blocked Rust0.178s, frequency-blocked Rust0.153s, frequency-blocked NumPy0.151s. Same information to~2.6e-11 absolute. Ordinary structured elimination, not a novel algorithm or competitive-calibrator benchmark. New full checks pending.
- Public SKA MeerKAT `outer_scans.zip` inspected via network-disabled, read-only amd64 casacore container using public PyPI wheels; host ARM/macOS reader unavailable. Archive SHA256 d4dae56f7ad1bb4a49ab8c4a3846871d5b8ebb4b731ee958cb9f1baf3306144f, 45,452,147 bytes, five MS (not six), four antennas m000–m003, J1939-6342, 4096 channels856–1711.791MHz, 42–47% flags. All POINTING.ANTENNA_ID values0; antenna-major timestamps match upstream reshape, but physical label assignment not independently established. TARGET/SOURCE_OFFSET tagged J2000 while upstream interprets AzEl/xel-el. Do not fit silently or claim real-data pointing recovery. Inspector and Docker recipe uncommitted; rawdata and downloaded upstream source kept ignored under outputs. Next: document reader barrier, checkpoint verified implementation, advance larger structural scaling and real-data convention validation.

- Beam-selection and common-prior campaigns archived and documented. Rich beam selection (192 fits) brings four truth families to mean held-out residual~1.042 and mean maxflux-ratio errors0.014–0.033%; one-width chromatic fit instead has~1.10% bias despite lower residual than fixed beam. Enumerating candidates is not cheaper and no superiority over always-rich joint fit established. Two-candidate96fit baseline retained. Common-prior72fit sweep: trueconstant(+30,-30)arcsec, jointflux + matchedkatbeam gives relative0.74–1.03arcsec, common0.17–0.37arcsec, test~1.01–1.02 for priors0.1/0.5/3arcmin. Restricted gain/sky/spline model and constant truth are not unrestricted Gaussian gauge. Full checks running. Continue after checkpoint; do not treat commit as terminal.

- Active continuation: user explicitly asks not to stop at commits. Separate train/validation/test beam-model selection campaign implemented (12 seeds, four truth families). Two-candidate baseline exposes lower residual yet worse flux ratios for chromatic width error. Expanded beam callback/solver to three physical parameters (log width, chromatic log-width slope at1.3GHz per0.4GHz, log-axis ratio), with independent optional priors/zero-fixed coordinates. Rich four-candidate campaign completed192 fits; derivative/noiseless tests passed. This is ordinary model-selection baseline, not novel. Results/docs pending archive.
- Gate6 continuation in progress: optional common pointing spline with zero-centred knot prior, explicitly separated from zero-mean relative offsets; physical total returned in offsets_arcmin. Requires zero_mean_pointing and fit_pointing. Prior sweep0.1/0.5/3arcmin running on matched katbeam, gains and fluxes jointly fitted. New common-mode tests/full verification pending. Do not claim prior-independent recovery from this restricted model.

- Checkpoint verified: release build, 11 Rust tests and 68 Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks passed. New tests cover SVD propagation against analytic linear covariance, rejection of singular precision, frozen-parameter uncertainty, joint width autodiff and noiseless recovery.

- Gate5 pilot: optional local Gauss–Newton uncertainty from SVD of full residual+prior Jacobian; marginalized pointing/flux/flux-ratio/beam-width std. Rank-deficient precision rejected, noise not rescaled. Twelve independent noise seeds at fixed truth71 give correct-beam pointing coverage96.0%, flux-ratio35/36; fixed1% wrong width pointing85.6%, ratio0/36. Coordinates/ratios correlated, one truth only: no precise coverage guarantee.
- Added shared beam log-width inference through tabulated callback, optional prior0.03. Same wrong-width noise pilot restores pointing coverage96.0%, flux-ratio34/36 and mean held-out residual1.030, recovered multipliers1.009765–1.010264. Known-family control, not novel or arbitrary-beam robustness. Gate7 contiguous time-gap control implemented, three zero-common joint test residuals1.0108/1.0136/0.9897. Archive/doc `uncertainty-coverage.md`. Gates5/7 only pilot; gate6 common-prior sweep still pending; gates8–10 unchanged. Full checks running including new derivative/recovery/uncertainty tests.

- User clarified novelty must mean better calibration/imaging quality or comparable quality with less runtime/resources than state of the art. Persisted in AGENTS.md and `development-roadmap.md`. Toy wins alone are insufficient.
- First passes of gates 1–4: 96 stress fits across width mismatch, independent fitted channel gains, out-of-family ripple and missing source. Report/archive `robustness-stress.md` and `results/robustness-stress.json`. Width +1% leaves 1.09–1.46 arcsec pointing but biases flux ratios 0.53–0.76%, held-out residual 2.38–2.57. Ripple 6 arcsec/90 min yields ~4.32 arcsec errors. Missing 20mJy source yields 12.57–12.88 arcsec errors, residual160–165. All convergence flags true; convergence is not correctness.
- Added optional `gain_per_channel=True` in JAX solver; independent spline coefficients at each observed frequency, gain cube shape(time,frequency,antenna) and frequency labels returned. Default achromatic shape unchanged. Channel-dependent noiseless recovery controls added. Full checks running. Remaining within gates1–4: heterogeneous beams/squint, smooth spectral gain truth, jumps and extended/spectral sky errors. Gates5–10 not completed; no measured-data drift fit or state-of-the-art advantage claimed.

- Verification for this checkpoint: release build, 11 Rust tests, 63 Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks passed. Held-out campaign completed all 24 fits successfully and results archived with fixture/beam provenance.

- Public 892 KB SARAO pointing-history downloaded into ignored outputs; CC BY-NC 4.0 provenance in `pointing-history.md`. Safe NPZ inspection finds 2x64x881 array, 2019–2022 timestamps, missing values, five duplicate timestamps and 53.8% exact adjacent antenna repeats. Coordinate/assembly/freshness conventions unresolved, so no empirical temporal covariance or six-hour interpolation claimed. Inspector script saves local summary/hash. Raw data not committed.
- Held-out benchmark implemented with six whole withheld times (2016 train / 672 test complex rows) and exact frozen-pointing gain/sky-only baseline. Three seeds, 24 fits: zero physical mean joint test clean RMS 0.220–0.247 mJy versus baseline 2.566–2.724; whitened test residual 1.011–1.023 versus 4.329–4.773. Nonzero shared physical pointing still fails adequacy (31.4–32.4). Matched beam and spline assumptions; synthetic trajectories, not historical data. Added gain-only recovery test; full checks running. No claim of real-data validation or resolved common-mode ambiguity.

- Joint nonlinear smooth achromatic gains implemented in `solve_pointing` via optional `gain_prior_sigma=(logamp_sigma, phase_sigma)`, same spline knots, antenna-zero phase reference, proper knot priors. Existing spectral/mode paths retain standardized nuisance priors. Noiseless anchored-flux test recovers pointing, gains and sky; four invalid-prior tests added. Three-seed/18-fit katbeam campaign archived in `results/joint-gain-pointing.json`: zero physical mean + joint flux gives 0.575–0.888 arcsec relative RMSE, wrong fixed sky 6.51–6.90. Nonzero common offset still mismatched (residual mean square 31.7–32.8); gain model is restricted achromatic, not the free-channel Gaussian gauge. Absolute flux scale remains prior-dependent in campaign. Held-out/gain-only/beam-error tests still pending.

- Zero-mean recovery campaign: `examples/relative_pointing.py`, three seeds, six cases each, full toy rows and scalar katbeam H. Known unit gains/exact beam. Zero physical mean: joint flux recovery 0.63–0.88 arcsec versus 5.67–6.22 arcsec with fixed ±2% wrong sky. Physical (+30,-30) arcsec common offset: joint flux relative error 3.48–3.98 arcsec but whitened residual mean square ~35.6, exposing restricted-model mismatch. All fits converge, numerical zero mean maintained. Archived results and `research/relative-pointing.md`; next joint nonlinear gains, not a claim against the gauge convention. Full checks: 11 Rust and 57 Python tests passed before campaign addition; rerun underway for checkpoint.

- Oleg recommends imposing zero mean per-antenna pointing rather than trying to recover the nearly degenerate shared offset. Implemented opt-in `zero_mean_pointing=True` in the smooth solver using an orthonormal antenna contrast basis at every knot. Linear spline interpolation preserves the constraint at all times; two coordinates per knot are removed, not softly penalized. Existing default retained for reproducibility. Added known-sky noiseless relative-recovery tests, including mode selection. This is a conventional identifiability constraint, not a novelty claim; unknown physical common pointing can still cause mismatch under restricted sky/gain models. Joint gain/sky nonlinear validation remains pending.
- Structured audit implemented in the working tree: Rust column-pivoted Householder QR with checked Python C-ABI wrapper eliminates time-local gains and differential offsets; a reusable compressed design preserves information for sky/common-mode audits and external flux priors. Native katbeam H benchmark: dense median 2.005 s, blocked Rust 0.177 s, blocked NumPy 0.160 s (three warmed runs each). Maximum information-matrix difference from dense approximately 2.6e-11. Speedup comes from blocking; Rust is not faster than NumPy here. Dense nuisance matrix 5376x1934 becomes local 224x78 blocks and a 432x64 retained design. These sizes are not peak-memory measurements. Benchmark artifact: ignored `outputs/blocked-benchmark/results.json`; reproduction: `examples/blocked_benchmark.py`. Local nuisance smoothness cannot be imposed after independent elimination.

- Extended session started2026-09-11 09:32:54UTC, targeting approximately two hours of development (to11:32:54UTC). First checkpoint: public PyPI katbeam0.1 installed (7.9KB wheel). Runtime L-band table900–1650MHz differs from current GitHub; pinned/hash provenance. Implemented stable differentiable cosine taper, table validation/no extrapolation, H/V scalar adapters and custom predictor callbacks in smooth solver/audit. 14 ablations show native measurement-informed bounds~8arcsec; freezing axis ratio gives~100–120arcsec; native-width Gaussian~8–9arcsec; fixed-shape Gaussian, circular profile and no rotation remain degenerate. Report `research/katbeam-pointing.md`, script/archive. Beam known exactly; not measured visibility calibration. Next: structured audit computation, beam-parameter uncertainty, joint nonlinear recovery.

- Implemented local external-flux information budget: optional positive-definite correlated log-flux covariance in `sky_locked_information`, with standalone data, externally conditioned data, external-prior and total information matrices. Generalized fractions compare standalone data to total, not posterior-variance fractions. `examples/information_budget.py` runs eight controlled cases. Gaussian with independent1% flux errors yields local σ[6.269,6.731]arcsec but zero standalone data fraction; 5% gives[31.341,33.642]. Quartic.1 with1% gives[5.907,6.297] and0.75–1.34% data-only fraction. A common5% flux-scale error changes neither; channel-correlated priors tighten constraints via spectral knowledge. Report `research/information-budget.md`, archived matrices/covariance definitions. No measured-beam validation or nonlinear recovery claimed.

- Removed the separate review brief and its links at the user's request; the main scientific note remains.
- Review package prepared: expanded formal derivation/prior-art boundaries in `research/gaussian-gauge.md`, and `research/sharing-draft.md` (not sent). Added 21-point gauge sweep with fixed noisy data: maximum prediction difference1.35e-15 Jy; chi-squared5424.231020291 varies7.01e-11. Reproducible SVG in `research/figures/gauge-orbit.svg`, visually inspected via local raster rendering. Results now record source/fixture/binary SHA-256 plus runtime versions. Additional regression checks composition, noisy likelihood and failure of collinear anchors. Analytic heterogeneous-metric corollary included but explicitly not simulated. Literature comparison includes Pointing SelfCal, RIME ambiguities, BIRO, identifiability work, blind ptychography and measured MeerKAT beams; novelty remains unconfirmed. No message sent to professor.

- Important correction to earlier lead: freeing the 46 remaining common temporal modes restores both Gaussian null directions. Derived exact finite gauge h(t)=Q^-1 R(t)a, accompanied by source/channel flux and antenna/time/channel gain transformations. Seed61 finite test with nonzero smooth differential offsets and complex gains: 34.95 arcsec pointing difference, max visibility difference9.31e-16 Jy for ratio1.1. Implemented `rangtoy.gauge`; report `research/gaussian-gauge.md` supersedes unrestricted interpretation of beam-rotation results.
- Generalized local audit now supports common temporal complement, synthetic quartic log-beam shape and exactly fixed source/channel flux anchors. Full eight-antenna coverage with all gain/differential/common nuisances: Gaussian ellipse rank0; quartic .01 rank2 with local bounds561/586 arcsec, quartic .1 bounds57.7/60.0 arcsec. Circular beam remains rank0 at zero pointing. Central flux anchor alone rank0; central+one off-axis rank1; central+two non-collinear off-axis rank2 (perfect-flux assumption). Reproducible `examples/gaussian_gauge.py`; archive `research/results/gaussian-gauge.json`. Measured beams and nonlinear joint recovery remain pending; no confirmed novelty claim.

- Frequency-dependent gain/differential-pointing audit implemented and run: `examples/gain_observability.py`, archived `research/results/gain-observability.json`. New Rust `--pointing-full-reference` exports all 2688 rows for the same eight antennas (not full MeerKAT). With 1536 unconstrained real antenna/time/channel gain columns plus 336 zero-mean per-time pointing columns and 16 channel-flux columns, the rotating ratio-1.1 model retains both shared modes: local bounds [1.107, 1.066] arcsec. Thinned 538-row fixture loses both modes under the same nuisance assumptions. Complete circular control still degenerate. Other common temporal modes and beam shape remain fixed; nonlinear joint nuisance recovery still pending. Tests verify full/thinned consistency, all baseline coverage, and both rank controls.

- Gain-nuisance extension of the local symmetry audit: optional constant or per-time complex antenna gains, shared across frequency, projected jointly with free source/channel amplitudes. Both shared pointing modes survive ratio-1.1 rotating-beam audit; local coordinate bounds change from [2.068, 1.916] to [2.549, 2.405] arcsec with 384 gain columns. Not a nonlinear gain/pointing recovery result. Regression covers nested information loss and preservation of circular-beam ambiguity. Reproduction: `examples/observability.py` (seven cases). Public SARAO L-band metrics download returned HTTP 502; measured-beam validation remains pending.

- New concrete physical lead: exact sky-locked common-pointing/sky degeneracy for identical circular beams and unconstrained source/channel amplitudes. Measured pilot error energy is 99.9% in this two-dimensional shared trajectory. Implemented `rangtoy.observability`, local sky-prior-free audit, and nonlinear variable-projection solver; see `research/beam-rotation.md`. Generic mode truncation remains a negative accuracy result.
- Controlled 20-noise-realization shared-mode test: circular-beam fits refused; correct rotating ratio-1.1 beam recovers 1.787 arcsec RMS; wrong fixed ratio1.08 gives 51.929 arcsec; jointly fitting ratio from circular initialization restores 1.859 arcsec. Sixteen source/channel fluxes free, no spectral prior. Other pointing and DI gains fixed. Not a confirmed first-in-literature contribution or general telescope result.
- Exact finite gauge, local rank controls, nonlinear recovery, and shape recovery tests pass. Reports `research/beam-rotation.md`, `research/spectral-pointing.md`; combined summaries under `research/results/symmetry-and-spectral-campaigns.json`. JAX-only new paths preserve Rust baseline.

- Work toward a defensible contribution: optional spectral-index priors and prior-whitened, sky-marginalized pointing-mode truncation are implemented. Expanded `examples/sky_uncertainty.py`; new `examples/mode_selection.py` gives both full/selected solvers identical five-value smoothing grids with separate train/validation/test times.
- Spectral mismatch (alpha ±.1, flux ±2%, 20 seeds, 1 mJy noise): flux-only joint fit gives 68.51 arcsec pointing error despite improved residuals; jointly fitting spectra gives 4.132 arcsec. At 10 mJy, fixed-smoothing selection keeps 56/96 modes and improves 19.27→18.13 arcsec. Equal-budget validation tuning removes pointing advantage: full 18.5009 vs selected 18.4975 arcsec, selected mean 44.8/96 modes. Do not claim a new accuracy improvement.
- Current runs: `outputs/spectral-20`, `outputs/spectral-noisy-20`, `outputs/mode-cv-20`; three-seed physical decomposition in `outputs/common-mode-pilot` shows flux-only spectral-error failure is mostly array-common (68.79 arcsec common versus 4.79 differential). Investigating sky-locked/parallactic-frame ambiguity, not yet a validated novelty claim.
- Additional close precedents reviewed: Sob et al. 2021 solution interval selection, Tasse 2014 nonlinear Kalman calibration, Fisher/score compression and low-rank methods. Absence of exact search matches does not establish novelty.

- Added optional per-component Gaussian flux priors to smooth-pointing inference; zero sigma fixes a component, None preserves fixed-sky behavior. Returns fitted fluxes; prior-normalized additive corrections are differentiated jointly with spline coefficients.
- Three 20-seed campaigns (180 converged fits, including duplicate paired controls): 2% source-flux errors cause 30.237 arcsec fixed-sky pointing RMSE; 5% joint flux priors recover 2.475 arcsec vs 2.402 correct-sky control. Held-out RMS 3.682 → 1.067 mJy/component. Overconfident 0.01% priors leave 28.187 arcsec error. Matched-sky joint fit costs a small increase to 2.475 arcsec.
- Results and reproduction: `research/sky-uncertainty.md`, `research/results/sky-uncertainty.json`, `examples/sky_uncertainty.py`. Fixed source layout/sign pattern, exact central flux anchor and correct spectra/beam remain limitations. No new-algorithm claim.

- Converted all 18 display equations across four research documents to GitHub-supported fenced math blocks; equations unchanged. Documented the formatting convention in CONTRIBUTING.md.

- User/professor focus: pointing-error solutions; explicitly requested component-list conversion, DFT prediction, JAX automatic differentiation and smoothly time-varying per-antenna offsets. Implemented optional `rangtoy.pointing` with natural cubic spline trajectories, integrated-curvature regularization and SciPy least squares using JAX Jacobians.
- Public PyPI explicitly required by user; isolated `.venv` installed JAX/JAXlib 0.11.1, NumPy 2.5.3, SciPy 1.18.1, pytest 9.1.1 and Ruff 0.16.7. Do not use the Spotify registry. Rules saved in AGENTS.md.
- Rust `--pointing-reference` exports deterministic prediction/analytic-derivative fixtures; JAX comparisons, finite differences, spline controls and noiseless recovery passed (7 new tests).
- Initial smooth-pointing example (seed 7, noise 1 mJy/component, six knots, smoothness .01): 2.005 arcsec trajectory RMSE, held-out residual RMS 2.635 → .950 mJy/component. Sinusoidal truth differs from spline fit; sky/beam remain exactly known. Full details in `research/pointing-solutions.md`.
- Saved smooth-pointing numerical summary and dependency-free SVG trajectory figure under `research/results` and `research/figures`. Full local check passed with 9 Rust and 15 Python tests, including JAX, plus Clippy and both format/lint checks.

- Public repository created and verified at `https://github.com/gijzelaerr/rang`; initial public commit `2587480`. Both author and committer use `gijsmolenaar@gmail.com`; this identity is configured locally and required by AGENTS.md.
- Presentation revised: result-led README, contributor guide, clear implementation status and linked reproducibility material. Current contribution assessment is `research/novelty.md`.
- Targeted prior-art review adds robust ellipsoidal beamforming and partially constrained CMB component separation as strong objections to broad novelty. The sharper candidate uses separate response-distortion and model-error sensitivity budgets for physical calibration selection; specified, not implemented or demonstrated.
- Next discriminating work: complete-estimator derivatives and uncertain bright-source/beam perturbations with matched joint-inference baselines. No novelty claim is warranted by current results.

- Added shared log-beam-width fitting (17 physical parameters), analytic derivative test, and end-to-end width-mismatch recovery test. JSON keeps pointing arrays at 16 elements and reports fitted width separately.
- Twenty paired seeds 1–20: 2% width mismatch gives fixed-width joint flux 34.269 mJy versus width-fitting 20.124 mJy (truth 20). Corresponding injection response is 99.748% versus 99.990%; held-out RMS 11.706 versus 9.976 mJy. Matched-width flux 20.030 versus 20.081 mJy. Adaptive protection still gives no added benefit.
- Professor-facing discussion note: `research/first-results.md`; machine-readable campaign summary in `research/results/beam-width-campaign.json`. Raw runs and inspected plots in ignored `outputs/campaign-{matched,width}`.
- BIRO (Lochner et al. 2015, including Smirnov) directly precedes joint flux/pointing/beamwidth inference. Explicitly cited; no novelty claimed.
- Full release build, 9 Rust tests, 8 Python tests, Clippy, Ruff and both format checks passed after implementation.
- User authorized pushing and supplied `https://github.com/gijzelaerr/rang`. Both Git HTTPS and authenticated GitHub CLI report repository not found. Asked asynchronously for creation/visibility permission or access correction; do not create without that choice. Earlier approval classification issue was resolved enough to run the explicit supplied-URL checks; current problem is repository availability.

## Earlier checkpoints

- Request: review recent radio calibration/imaging and related fields, then identify a plausible new mathematical method, including non-coplanar geometry and 3D propagation.
- Repository initially contained no implementation or research documents; existing `.gitignore` was preserved.
- Completed a targeted primary-source literature investigation. Findings and a detailed candidate method are in `calibration-research-2026-09-11.md`.
- Current user scope: MeerKAT only. Active specification is `meerkat-scope.md`. The original report remains background and is marked superseded for experiment scope.
- User implementation conventions: Rust for computational kernels; Python for astronomer-facing interfaces and pipeline scripting. Commit solely under the user's identity without agent signatures or co-author trailers. Persisted in the root `AGENTS.md`.
- Initial working choice: MeerKAT L-band Stokes-I continuum, physical pointing and small beam corrections selected using sky-uncertainty-adjusted information and a local bound on science-signal distortion. L-band is an agent-selected starting point, not a user-imposed band restriction.
- Closest precedents: Albert tomography; BayesCal; resolve; Mouri Sardarabadi/Koopmans identifiability and suppression; Yatawatta/Leahy influence-based tuning; IDG-CAL 2026.
- Relevant latest result: Russeeawon et al. June 2026 clock/TEC initialization, including Smirnov, incorporated into QuartiCal.
- Status: runnable Rust/Python toy implemented. Rust has no external crate dependencies; Python invokes a JSON executable and plots with Matplotlib. No telescope downloads, commits or external publication.
- Additional close precedents: pointing selfcal, MeerKAT L-band beam measurements/holography, EIDOS and the December 2025 MeerKAT visibility-plane mosaicing framework.
- Toy: eight rounded published MeerKAT core positions, flat heights, Gaussian 13.5 m beam, 24 time samples, four L-band frequencies, full w phase, 16 constant antenna-frame pointing parameters, four known bright sources and one uncertain extended component. Geometry provenance/verification limitation is explicit in `data/README.md`.
- Initial matched-width result (seeds 7, 11, 19; true source 20 mJy): pointing-only recovers 12.05 mJy; joint/protected 19.79 mJy; known-pointing 19.89 mJy. All 16 modes survive the default budget; no evidence of added benefit from adaptive protection.
- Stress result: 2% beam-width mismatch biases joint/protected flux to 34.03 mJy while the finite injection response stays near one. Distinguish signal-response preservation from absolute accuracy.
- Strict budget (1e-6, seed 7) underfits and recovers 27.78 mJy instead of 20 mJy. A shifted source outside the fitted template shows 7.62% finite norm distortion despite a near-unit response projection. Both failure cases are documented.
- Controls: zero-error base fit exact; analytic derivatives, geometry, linear algebra and noiseless recovery tested. Coarse source quadrature initially biased even known-pointing recovery; resolved by adequate sampling and covered by a finer-grid convergence test.
- Main entry point: `python3 examples/toy.py --seeds 7 11 19 --output outputs/demo`. Artifacts in ignored `outputs/`; reproducible commands/results documented in `examples/README.md`.
- Verification: 8 Rust tests and 7 Python tests passed; release build, Clippy with warnings denied, Rust formatting and Python Ruff lint/format passed. PNG visually inspected. Final state is uncommitted per current workflow.
- Next research step: replace the idealized beam with measured beam information, include bright-source uncertainty and evaluate whether any adaptive selection benefit survives a matched joint-inference comparison. Acquire verified full-array coordinates before instrument-specific claims. Keep the w-term; introduce ionospheric complexity only as supported.
