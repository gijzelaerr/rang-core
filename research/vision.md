# ra-ng: the project's direction

Set by the owner on 2026-11-11. Status: **direction agreed; everything below
that is not already on `main` is proposed.** The finish plan
([finish-plan.md](finish-plan.md)) stays the next milestone, because its parity
gates are what makes "science grade" a claim that can be checked.

## 1. What ra-ng is for

**ra-ng** is the project name. `rang-core` is its first package (the Rust core,
the extension `rang._core` and the command line); later packages split off it.
The aim is to be the home for agentic radio astronomy: open an agent (Claude or
any other) in this repository and work from there, whether you are

| Who | What they do here | Exists | Proposed |
| --- | --- | --- | --- |
| A beginner | ask questions and learn radio astronomy from notebooks | notebooks 01-07 (they teach rang's chain and experiments) | an introductory track: interferometry, visibilities, the MeerKAT array, calibration, imaging, time-domain basics; E4's MS-to-image tutorial at its centre |
| An astronomer | make science-grade images and time series | `rang-core run`, GeMClean, full polarisation (gated by v0.2.0) | task procedures for agents (image my MS, calibrate a track); time-series products (section 3) |
| An algorithm scientist | improve the code with an agent and contribute it back | oracles, frozen tolerances, the novelty rule, the heavy lock | the written contribution path (section 5); research skills (section 6) |

The science goals stay: higher calibration and imaging quality at comparable
cost, or comparable quality at materially lower cost, against the state of the
art, with negative results recorded. Making the software faster, leaner and
easier to use, and bringing in the best current research, serves those goals.

## 2. Telescopes

- **MeerKAT first** (L band; UHF and S band later), as in
  [meerkat-scope.md](meerkat-scope.md).
- **LOFAR in mind** (the owner knows people at ASTRON): much lower
  frequencies, so ionosphere, direction-dependent effects, station beams and
  much larger data. Keep telescope specifics behind the existing boundary
  (`python/rang/meerkat.py`, the W4 refusals for unsupported data); do not
  generalise until a second telescope's data and oracle are in hand.
- **VLBI later, not now** (owner asked 2026-11-11; EHT, Obit): shares the
  measurement equation, flagging, the formats layer and regularised imaging, but
  needs fringe fitting, a priori amplitude calibration and closure-quantity
  imaging on very sparse uv coverage. Possible first pieces, each with an oracle:
  fringe fitting (CASA `fringefit`, AIPS FRING) and closure imaging (eht-imaging,
  SMILI). Obit's MeerKAT wideband imaging (MFImage) is a candidate oracle for the
  MeerKAT work now.

## 3. Time series

New scope: **pulsars and transients (FRBs, GRBs)**. Nothing in the
finish plan covers it. Likely parts, all proposed: image-plane light curves and
dynamic spectra from interferometric data; beamformed (filterbank) data with
dedispersion, single-pulse search and folding, with PRESTO, DSPSR or Heimdall as
oracles. A scoping note picks the first product and its oracle
before anything is built.

## 4. Speed and platforms

Rust for kernels, Python for interfaces and orchestration (as `AGENTS.md`
already says). Use GPU acceleration where it pays, but stay cross-platform:
every GPU path has a CPU path that gives the same result within a written
tolerance, and the five wheel platforms keep working without a GPU.

## 5. Contributions

- The owner commits to `main` directly.
- Everyone else, people and their agents, contributes through pull requests
  that pass CI. A change that claims a scientific or performance gain brings its
  proposal note, frozen tolerance, oracle and measurement, as the research notes
  here do.

## 6. Research and improvement skills (proposed)

The record so far (gain-TV flagging, pointing, F2, F3) is that ideas promising on
paper were null or failed their own test, so skills propose and measure; they do
not merge on their own.

- **Literature digest:** a dated digest of new papers and releases relevant to
  ra-ng, and proposal notes, each with a tolerance and an oracle written before
  anything is built.
- **Improve:** takes one proposal the owner approved, works on a branch with the
  full checks, the heavy lock and the novelty rule, and ends in a PR.
- **Budget:** the weekly API limit stopped work once (2026-10-31). Cadence
  (owner, 2026-11-11): one digest a week; improvements only on request.

## 7. Order

Everything runs in parallel except CPU- or GPU-heavy tasks, which take turns
through `tools/heavy_lock.py`. E2 was halted at the owner's request and
resumed on the owner's word on 2026-11-11; E2 to E6 form the heavy queue. The light tasks below run alongside.

| ID | Task | Done when | Heavy | Files |
| --- | --- | --- | --- | --- |
| V1 | Time-series scoping note | A note names the first product (pulsar, FRB or GRB), its data, its oracle and the tolerances to freeze | no | `research/` only |
| V2 | Contribution path and agent front door | `CONTRIBUTING.md` and `docs/contributing.md` give the PR route; `AGENTS.md` separates owner-only rules (git identity, registry) from contributor rules; first task procedures in the repo with thin `.claude/skills/` wrappers | no | `AGENTS.md`, `CONTRIBUTING.md`, `docs/contributing.md`, `.claude/` |
| V3 | Introductory notebook track, outline | An outline of the beginner track and how it joins E4's tutorial and notebooks 01-07 | no | `research/` (outline only; notebooks after E4) |
| V4 | Research skills (digest, improve) | A weekly literature digest (owner: weekly, 2026-11-11) runs on a schedule and writes a dated digest and proposal notes; the improve skill acts only on a proposal the owner approved | no | `.claude/skills/`, `research/digests/` (after V2) |
| V5 | Obit as a second imaging oracle | Obit (MFImage) installed in WSL; a note compares GeMClean, WSClean and MFImage on S1 and the pilot at tolerances written first: flux, spectral index, rms, time, memory | yes | `research/`, `tools/` |
| V6 | VLBI scoping note (EHT, EVN with MeerKAT) | A note picks the first piece (fringe fitting against CASA `fringefit`/AIPS FRING, or closure imaging against eht-imaging/SMILI), its public data and its tolerances; owner decides whether and when it starts, after LOFAR | no | `research/` only |
| V7 | LOFAR scoping note (LOFAR and LOFAR 2.0) | A note picks the first piece (DI ionospheric solve against DP3 DDECal, or the station beam against EveryBeam), its public data and its tolerances, and lists what to ask ASTRON; owner decides whether and when it starts | no | `research/` only |
