# E5 packaging, licence and changelog review (read-only)

Checkout `<worktree>`, main `3eab67c` (2026-11-11). Read-only: nothing
was edited, committed or built beyond `maturin sdist` (3.5 s) into the scratch folder
`<scratch>\e5-pkg`.
"Verified" means that I ran the command named. "Derived" means that I read it from configuration but did not
observe it in a built artefact.

Counts: **release-blocking 7** (PK-01 to PK-07), **should-fix 10** (PK-08 to PK-17), **later 8** (PK-18 to PK-25).

## Context

- `origin/main` and GitHub `main` are at `c2fe7cc`. Local `3eab67c` is ahead by two docs-only commits
  (`git diff --stat c2fe7cc 3eab67c`: `research/README.md`, `research/v6-vlbi-scope.md`). The latest
  `wheels` run 43004680641 on `c2fe7cc` is green in every job: 5 wheels, sdist, 10 test cells. `release` and
  `publish` were skipped because the push was not a tag. The last three failures were on 2026-11-06 (verified
  with `gh run list`/`gh run view`).
- PyPI has 0.1.0 only: 5 abi3 wheels plus the sdist, with `License-Expression GPL-3.0-or-later`. The GitHub
  release is v0.1.0 (verified through the PyPI JSON and `gh release list`).
- The finish-plan prerequisites of E5 are not met yet. E2 is running. E3 (against CARACal) and E4 (tutorial,
  CI end-to-end job) are not done (`research/finish-plan.md:115-117`, `research/STATE.md:12`). This is
  therefore a pre-review, and PK-04 cannot be closed until they land.

## 1. Version agreement: everything is 0.1.0. The bump list for 0.2.0

All of these are at 0.1.0 (verified with grep). Each needs `0.1.0` → `0.2.0`:

| File:line | Field |
| --- | --- |
| `pyproject.toml:7` | `[project] version` (the one source) |
| `Cargo.toml:3` | `rang-sim` |
| `core/Cargo.toml:3` | `rang-core` (also gives `gemclean -version`: `env!("CARGO_PKG_VERSION")`, `core/src/gemclean/cli.rs:1119`, and the `version` field in gemclean reports at cli.rs:1435, 2232, 2960, 3106) |
| `core/py/Cargo.toml:3` | `rang-core-py` |
| `Cargo.lock:7` | rang-sim |
| `core/Cargo.lock:578, 589` | rang-core, rang-sim |
| `core/py/Cargo.lock:682, 693, 702` | rang-core, rang-core-py, rang-sim (refresh with `cargo metadata --offline --format-version 1 >/dev/null` in `.`, `core/`, `core/py/`, as CONTRIBUTING.md:80-82 says) |
| `CITATION.cff:11` | `version:` (not covered by any test, see PK-11) |
| `docs/installation.md:113` | the comment `# rang-core 0.1.0` (not tested, see PK-11) |
| `CHANGELOG.md:10` | `## Unreleased` becomes `## 0.2.0 (<date>)`; keep an empty `## Unreleased` (the test needs one) |

These follow automatically: `rang.__version__` (importlib.metadata, else pyproject), `docs/conf.py:27-32`
(`release` from metadata or pyproject), and `rang-core --version`. `tests/test_w4_5_release.py:56-77` checks
pyproject against the three manifests, the three locks, `rang.__version__` and the installed metadata. It
also checks docs/conf.py (line 80), `--version` (line 101) and that CHANGELOG has `## <version>` (line 106).
`tests/test_g8_gemclean.py:89-110` checks `gemclean -version` against `core/Cargo.toml`. 13 passed, 1
skipped: the comrak rendering test (verified with `pytest tests/test_w4_5_release.py`).
`examples/casacure_rs/Cargo.toml:3` and `formal/lakefile.toml:2` are separate projects and stay as they are.

The release workflow checks tag == version, in both the `release` and the `publish` job, before any upload.
It compares the tag with every wheel and sdist file name and with `pyproject.toml` (release job only), and
expects exactly 5 wheels and 1 sdist (`.github/workflows/wheels.yml:231-256, 308-328`; verified by reading).

## 2. sdist (verified: `maturin sdist`, extracted, listed)

`rang_core-0.1.0.tar.gz`: **1.86 MB, 375 entries**. W4-R14 found 1,010 entries and 5.4 MB, so the sdist is
much smaller now. It contains:

- the three crates and their locks, `src/`, `core/src` (81 files), `core/py`
- `python/rang` (115 entries, with `data/` holding the two Tricolour masks, `TRICOLOUR-LICENSE`, its README
  and `casacore_observatories.json`)
- `data/` (README plus four `.itrf.txt`, including `meerkat.itrf.txt`)
- `LICENSE`, `README.md`, `CHANGELOG.md`, `CITATION.cff`, `.gitattributes`, `pyproject.toml`, `PKG-INFO`
- `tests/` (every `test_*.py`, `conftest.py`, `tests/data` goldens of 127 kB and 2 w2 YAMLs)
- `tools/wheel/` (9 files), plus `tools/a1_casa.sh`, `tools/a1_checks.sh`, `tools/gain_hash_gate.py` and
  `tools/heavy_lock.py`

It holds no `research/`, `history/`, `outputs/`, `docs/`, `notebooks/`, `formal/`, `.github/` or `.cargo/`.
The `_core.pyd` in the checkout is gitignored and not packed. The largest file is
`4k_lband_meerkat.staticmask` at 590 kB. A grep for `gijsm`, `C:\Users`, GitHub, PyPI and AWS token patterns
and private keys found nothing. PKG-INFO metadata is correct for 0.1.0 (classifiers, dependencies, markers).
CI builds a wheel from the sdist and imports it (`wheels.yml:122-130`, green).

## Findings

### PK-01: release-blocking. README and docs say gemclean is not in the wheels

- **Where:** `README.md:25-27`, `docs/index.md:38-40`.
- **What is wrong:** both say gemclean "is not in the wheels" and give a `cargo build ... --bin gemclean`
  command. Since G8 (5a24fc7), gemclean is a console script in every wheel: `pyproject.toml` `[project.scripts]
  gemclean = "rang.gemclean:main"`, and CI runs `gemclean --version` from the wheel (`wheels.yml:130`, plus
  the test cells). The README is the PyPI project page.
- **Fix:** replace the sentence with "`gemclean` is installed with the wheel (the console script runs
  GeMClean inside `rang._core`); a standalone binary builds with `cargo build ... --profile gemclean --bin
  gemclean`", in both files.
- **Small and unambiguous:** yes. Verified by grep.

### PK-02: release-blocking. The README command table understates the commands

- **Where:** `README.md:89-95`.
- **What is wrong:** the row says `flag`, `calibrate`, `image`, `run` "solve (`complex` only so far)". It omits
  `apply` and `selfcal`. Since C2e, C6w and E0, `calibrate` runs K, G, B, A, F and Gpol, KCROSS, Xf, Df
  (`python/rang/core_config.py:61-66` `CASA_TERMS + POL_TERMS`). `selfcal` exists since C5. The "What it is"
  bullets (README.md:21-34) and docs/index.md:41-44 likewise list only flag, calibrate, image and run.
- **Fix:** the row becomes "`flag`, `calibrate`, `apply`, `selfcal`, `image`, `run`: Tricolour flagging; CARACal's
  cross-calibration K, G, B, A, F and polarisation terms; apply with parallactic angle; self-calibration rounds;
  GeMClean imaging; resume". Mirror it in docs/index.md.
- **Small and unambiguous:** yes. Verified by grep.

### PK-03: release-blocking. The Unreleased entries state superseded behaviour, and they become the release notes

- **Where:** `CHANGELOG.md:10-388`; `wheels.yml:259-279` copies the version section verbatim into the GitHub
  release.
- **What is wrong:** the section is a chronological log of 294 commits (238 non-merge, 56 merges since
  v0.1.0; `git log v0.1.0..HEAD`). Several entries describe states that later entries in the same section
  undo, so as 0.2.0 notes they are false:
  - :71 says `image.gemclean: auto` "finds `core/target/<profile>/gemclean.exe` on Windows". :28 says that
    search "is gone", and `python/rang/core_pipeline.py:1893` confirms it.
  - :175 says `extendflags: true` "(not ported, no owner)" is a configuration error. :102-112 (E0) say it runs.
  - :198-199 say `refant: auto` is "refused as not ported". E0 (:102) says it runs.
  - :225-228 say the K, G, B, A, F terms are "not chunked yet ... refused". W3b (:89) says they are chunked.
  - :239-243 say `image` is refused when `data.scans` leaves out a scan ("gemclean has no scan selection"),
    and that `data.weights: uniform` for imaging "is still refused". W6 (:152-157) says both are accepted.
  - :283-285 say applying a complex term to another field and polarised models are refused, "naming C2a and
    C7a". C7a (:209) supersedes the polarised models.
  - :325 says polarised `manual` models are "refused until C7a". C7a is done.
  - :330-333 say the rest of CARACal's chain "is refused with the task that adds it". Most of it is now added.
  - :369-370 say KCROSS, Xf and the parallactic angle are "refused until their steps". C6 and C6w added them.
- **Fix:** rewrite the section into a 0.2.0 summary grouped as Breaking/Changed, New, Fixed, Research and
  Known limits. State the end state per feature and drop the superseded intermediate refusals. Keep the
  detailed log under a link (for example `research/STATE.md`). Then check every remaining "refused" sentence
  against `rang-core config check`.
- **Small and unambiguous:** no (editorial). Each line was verified by reading the later superseding entry.

### PK-04: release-blocking. No Known limits statement

- **Where:** `CHANGELOG.md:10` (the Unreleased section); `README.md:11-19` (Status block).
- **What is wrong:** the finish plan requires the release to state the following (`research/finish-plan.md:
  139-141`, "E3 can come out badly ... stated in the release"; E2-N "open" at :115). Unreleased states none of
  these as release limits:
  - native data (E2-N) untested: "native" appears once, in an unrelated sentence;
  - the E2 and E3 outcomes: no E2 entry, and E3 appears 0 times;
  - E1 "no gate met as frozen": only in a "Research" bullet at :63-67;
  - the selfcal model-absorption limit: only inside the C5b bullet at :56-57;
  - the unexplained 40-60× thermal floor: "floor" appears 0 times;
  - the provisional C6 defaults (:177) and the parallactic-angle convention.

  The README status ("a tested research demonstrator, not an operational calibrator") and the Research table
  also predate E2 and E3.
- **Fix:** add `### Known limits` to the 0.2.0 section listing each item above with its report link, filled
  from E2 and E3 when they land. Update the README status block to match.
- **Small and unambiguous:** no (it depends on E2 and E3). Verified with counted greps over the extracted
  Unreleased text.

### PK-05: release-blocking (if the owner treats the coordinates as copyrightable). GPL-2.0-only simms files in the sdist, compiled into the library

- **Where:** `data/meerkat.itrf.txt` and `data/{vla-c,wsrt,kat7}.itrf.txt` (shipped in the sdist);
  `core/src/gemclean/sim.rs:41` (`include_str!("../../../data/meerkat.itrf.txt")`, inside an unconditional
  `pub mod sim`, `core/src/gemclean.rs:59`); `docs/licence.md:22` lists simms as "GPL-2.0".
- **What is wrong:** simms declares **GPL-2.0-only**. Its `pyproject.toml` at the pinned commit `e715505`
  has `license = {text = "GPL-2.0-only"}`. At `ad6d0a4`, `setup.py` says `license="GPL2"` (verified with
  `gh api`). docs/licence.md:8-9 itself says "GPL-2.0-only code cannot be combined with GPL-3 code", yet it
  lists simms without "only". The sdist redistributes the four files under a package whose licence
  expression is GPL-3.0-or-later. The crate compiles them in. `sim::antennas` is used only by `simulate`,
  which is called from tests and core/examples. The shipped cdylib therefore probably drops the bytes, but I
  did not check this, because downloading a CI wheel needs permission. sim.rs did not exist at v0.1.0
  (`git ls-tree v0.1.0 core/src/gemclean/` is empty), so this exposure is new in 0.2.0.
- **Fix (owner decision):**
  - (a) Record a decision that ITRF antenna coordinates are uncopyrightable facts and correct
    docs/licence.md:22 to "GPL-2.0-only; factual coordinates, used as data".
  - Or (b) gate `sim::antennas` and `sim::simulate` behind `#[cfg(any(test, feature = "sim"))]` and restore
    `{ path = "data/**/*", format = "sdist" }` (also update `test_sdist_excludes_the_research_tree`, which
    asserts data/ stays in).
  - Or (c) take MeerKAT positions from a permissive source (katpoint/katconfig antenna descriptions or an
    observation's ANTENNA table).
  - In every case, drop the three unused `.itrf` files from the sdist: only core/examples (excluded) use them.
- **Small and unambiguous:** no.

### PK-06: release-blocking. The wheels carry no MIT or BSD notices except Tricolour's

- **Where:** `pyproject.toml:11` (`license-files = ["LICENSE"]`).
- **What is wrong:** compiled ports ship in `rang._core` without their notices:
  - QuartiCal's MIT notice (Copyright (c) 2022 Jonathan Simon Kenyon) is in `core/src/solve.rs`, `diag.rs`,
    `cal/delay.rs` and `cal/delay_offset.rs`.
  - codex-africanus's BSD-3 notice is in `core/src/predict.rs`.
  - Tricolour's BSD-3 notice is in `core/src/sumthreshold.rs`.

  These notices exist only in `.rs` source comments, and the wheel has no `.rs` files. MIT requires the
  notice in "all copies or substantial portions". BSD-3 clause 2 requires it "in the documentation and/or
  other materials" of a binary distribution. Only `rang/data/TRICOLOUR-LICENSE` ships. Its copyright line
  happens to equal africanus's but is labelled as Tricolour's.
- **Evidence:** derived from `pyproject.toml` and the sdist listing, not from a built wheel. W4's wheel listing
  (`research/w4-review.md:411-413`) shows only LICENSE, the Tricolour licence and the SBOM.
- **Fix:** add `THIRD-PARTY-NOTICES.md` (QuartiCal MIT full text; africanus and Tricolour BSD-3; WSClean
  GPL-3.0 and ducc0 GPL-2.0-or-later attributions) and set `license-files = ["LICENSE",
  "THIRD-PARTY-NOTICES.md", "python/rang/data/TRICOLOUR-LICENSE"]`. Optionally assert it in
  `test_pyproject_metadata`.
- **Small and unambiguous:** yes.

### PK-07: release-blocking. The README and the licence page say ported code keeps its upstream notices, but the GPL ports do not

- **Where:** `README.md:145`; `docs/licence.md:10`; `core/src/grid.rs:1-11`, `core/src/weights.rs:1-8`,
  `core/src/wgridder.rs:1-12`.
- **What is wrong:** the MIT and BSD ports quote their notices verbatim. The GPL ports only name the
  upstream: "André Offringa and contributors, GPL-3.0" and "Martin Reinecke (Max-Planck-Society;
  GPL-2.0-or-later)". They carry no upstream `Copyright` line (verified with `grep -n -i copyright` on the
  three files). grid.rs also has no rang copyright line. GPL §4 and §5 ask to keep intact the upstream
  copyright notices of a covered work and to mark modifications. As written, the README sentence is false
  for these three files.
- **Fix:** add the upstream copyright lines from WSClean 3.6's `wstackinggridder.cpp` and ducc0 0.42.0's
  `wgridder_impl.h` headers verbatim, plus "modified: translated to Rust by ...", to grid.rs, weights.rs and
  wgridder.rs. Alternatively, soften README.md:145 to "Ported code names its upstream".
- **Small and unambiguous:** yes (copying the upstream header lines).

### PK-08: should-fix. The licence table is incomplete

- **Where:** `docs/licence.md:14-23`.
- **What is wrong:** the table is missing:
  - codex-africanus 0.4.4 (`core/src/predict.rs`, BSD-3);
  - katdal 0.23 test helpers adapted in `python/rang/meerkat.py:440-444` (BSD-3, NRF/SARAO);
  - CARACal 8f7bb363 (GPL-2.0: its pyproject says `license = "GPL-2.0"`, ambiguous between only and
    or-later; verified with `gh api`), whose `get_refant` the module docstring of
    `python/rang/cal_refant.py:1-16` says it follows "operation by operation";
  - msutils `flag_stats`/`wgs84_to_ecef` (same docstring; licence not checked, the repo 404s on the license
    API);
  - CASA `FlagAgentExtension` (`core/src/flag_extend.rs:1-7`), fluxscale and applycal semantics, and the
    casacore 3.8.1 sources read for AipsIO (`core/src/aipsio.rs:7-11` says nothing is copied, LGPL);
  - casacore-data 20250826 (`python/rang/data/casacore_observatories.json`).

  The table says the licences are "as the reports record it", but each upstream's exact licence is supposed
  to be checked before porting.
- **Fix:** add these rows. For CARACal and msutils, state whether code was translated or only behaviour was
  reimplemented. If code was translated from GPL-2.0-only sources, see PK-05.
- **Small and unambiguous:** yes for the rows. The CARACal and msutils classification needs the owner.

### PK-09: should-fix. The provenance of casacore_observatories.json is undocumented in the package

- **Where:** `python/rang/data/README.md`.
- **What is wrong:** it documents only the Tricolour masks. `casacore_observatories.json` (10 kB, shipped in
  the wheel) carries its source string only inside the JSON, and its licence nowhere
  (`research/e0-refant-extend.md:96`).
- **Fix:** add a section on its source (casacore-data 20250826-160001-5 via `me.observatory()` in
  rang-o-casa 6.7.6.14), its SHA-256 and its licence.
- **Small and unambiguous:** yes.

### PK-10: should-fix. The release test does not run in CI, and publish can precede a failed release job

- **Where:** `wheels.yml:208-210, 285-287`; `tools/wheel/test.py:70-72`.
- **What is wrong:**
  - `tests/test_w4_5_release.py` runs only in the local full check. The CI wheel subset is
    core_backends, pointing_sim, p7, p12, t1, w4_3 and g8, and no workflow runs it. At tag time CI checks
    only file names and pyproject against the tag.
  - `publish` and `release` each need only `[wheel, sdist, test]` and run in parallel. A missing or empty
    `## 0.2.0` section fails `release` (`wheels.yml:267-270`) after PyPI has already accepted the upload,
    which cannot be undone.
- **Fix:** set `publish: needs: [wheel, sdist, test, release]`. Add a light step to the release job that runs
  `python -m pytest -q tests/test_w4_5_release.py -k "versions_agree or changelog or citation"` from the
  checkout (it needs the installed wheel for `rang.__version__`; the sdist job's venv would do).
- **Small and unambiguous:** yes (the needs line). Verified by reading.

### PK-11: should-fix. CITATION.cff and installation.md are outside the version guard

- **Where:** `CITATION.cff:11`; `docs/installation.md:113`; `tests/test_w4_5_release.py:56-77`;
  `CONTRIBUTING.md:79-86`.
- **What is wrong:** `CITATION.cff` `version:` is not in `test_versions_agree`, the release steps in
  CONTRIBUTING do not name it, and it has no `date-released`. A 0.2.0 bump that follows CONTRIBUTING leaves
  CITATION at 0.1.0. installation.md:113 hard-codes `# rang-core 0.1.0`.
- **Fix:**
  - Add `assert re.search(rf"^version: {re.escape(version)}$", _text("CITATION.cff"), re.M)` to
    test_versions_agree, and add `date-released: <date>` (bumped in the release commit).
  - Change installation.md:113 to `# rang-core <version>`, or test it.
  - Name CITATION.cff in CONTRIBUTING.md:80.
- **Small and unambiguous:** yes.

### PK-12: should-fix. The README says the wheel carries every kernel, but the GPU gridder is not in the wheels

- **Where:** `README.md:24` ("w-stacking gridder (CPU and GPU)"), `README.md:57-58` ("carries every kernel"),
  `README.md:113`.
- **What is wrong:** wheels are built without the `gpu` feature: `wheels.yml:106` has `--release --locked`,
  and `[tool.maturin]` has no `features`, while `core/py/Cargo.toml:19-21` puts `gpu` behind a feature. A
  `pip install` user has no GPU path. docs/installation.md says nothing about GPU (verified with grep).
- **Fix:** add to README.md:58 "(the `wgpu` GPU gridder needs a source build with `maturin develop
  --release --features gpu`)", and add the same to docs/installation.md.
- **Small and unambiguous:** yes.

### PK-13: should-fix. Breaking changes are scattered, not summarised

- **Where:** `CHANGELOG.md` Unreleased.
- **What is wrong:** each breaking change is mentioned inline, but there is no summary. They are:
  - the research stages moved under `rang-core research` (:340);
  - the root crate, binary and environment variables renamed with no aliases, and receipts v4 (:375-378;
    that line names the old identifiers, which contain a word the owner bans; not quoted here);
  - K default `delay_and_offset` (:288);
  - gemclean 1e-4 single precision by default (:20);
  - every restored image's BMAJ, BMIN and BPA change (:28-34);
  - `image.gemclean: auto` no longer searches PATH or core/target (:26-29);
  - four stage-hash changes needing `--force`: image and selfcal (G7, :25), selfcal (C5b, :52), calibrate
    (E0, :111-112).
- **Fix:** add `### Breaking and rerun-needed` at the top of 0.2.0 with these eight bullets. This is part of
  PK-03's rewrite.
- **Small and unambiguous:** yes.

### PK-14: should-fix. The `pypi` environment has no protection

- **Where:** GitHub environment `pypi`, used at `wheels.yml:289-290`.
- **What is wrong:** `gh api repos/gijzelaerr/rang-core/environments` shows `protection_rules: []` and
  `deployment_branch_policy: null`. There are no rulesets and no tag protection. Any `v*` tag pushed by anyone
  with write access publishes to PyPI without review. Contributors are now invited (AGENTS.md: PRs), and
  trusted publishing trusts the environment name only.
- **Fix:** in the repository settings, give `pypi` a required reviewer (the owner) and a deployment tag
  policy `v*`. Optionally add a tag ruleset that restricts who can create `v*` tags. This is an owner action.
- **Small and unambiguous:** yes (a settings change).

### PK-15: should-fix. CONTRIBUTING misstates what the sdist contains

- **Where:** `CONTRIBUTING.md:90-92`; `pyproject.toml:84-87` comment.
- **What is wrong:** both say the sdist carries "only the crates, `python/`, `tests/` and `tools/wheel/`". The
  verified sdist also carries `data/` (needed for the build since G8), `CITATION.cff`, `.gitattributes` and
  `tools/a1_casa.sh`, `tools/a1_checks.sh`, `tools/gain_hash_gate.py`, `tools/heavy_lock.py`.
- **Fix:** exclude the four dev-only `tools/*` files (`{ path = "tools/a1_*.sh", format = "sdist" }` and the
  same for the two `.py` files), then say "the crates, `data/`, `python/`, `tests/`, `tools/wheel/`, README,
  CHANGELOG, CITATION and LICENSE".
- **Small and unambiguous:** yes.

### PK-16: should-fix. The `recipes` extra cannot install on Python 3.14

- **Where:** `pyproject.toml:52`.
- **What is wrong:** `recipes = ["stimela==2.1.4"]`, and stimela 2.1.4 has `Requires-Python <3.14,>=3.9`
  (verified with the PyPI JSON). `pip install 'rang-core[recipes]'` on CPython 3.14, a classifier the
  package declares, fails to resolve. README.md:65 only hints at it with "(Python 3.13)".
- **Fix:** `recipes = ["stimela==2.1.4; python_version < '3.14'"]`, and say in the README extras table
  "needs Python ≤ 3.13".
- **Small and unambiguous:** yes.

### PK-17: should-fix. The version regex allows pre-releases

- **Where:** `tests/test_w4_5_release.py:58`.
- **What is wrong:** `r"\d+\.\d+\.\d+([ab]\d+|rc\d+)?"` accepts a1 and rc versions, but the owner rule
  (2026-11-11) is no alpha or rc releases ever.
- **Fix:** `r"\d+\.\d+\.\d+"`.
- **Small and unambiguous:** yes.

### PK-18: later. There are no SPDX headers and no header policy

- **Where:** every source file.
- **What is wrong:** none of the source files carries `SPDX-License-Identifier`. Files without a GPL notice
  (verified with `grep -L` on "Licensed under the GNU General Public|GNU General Public License|part of
  Rang (GPL-3.0-or-later)"):
  - `python/rang`: 110 of 110
  - `core/src`: 28 of 81
  - `core/py/src`: 0 of 12
  - `src`: 7 of 7
  - `tools`: 73 of 73

  No policy exists: SPDX and "header" appear only incidentally in research/wheel.md:414 and
  ecosystem-survey.md:31, and nowhere in CONTRIBUTING.md or AGENTS.md. The GPL does not require per-file
  headers.
- **Fix:** adopt one line, `# SPDX-License-Identifier: GPL-3.0-or-later` (Python) and `//` the same (Rust),
  except files that quote an upstream notice. Add a ruff/check-all test. Write the policy in CONTRIBUTING.
- **Small and unambiguous:** no (mechanical but touches 300 files).

### PK-19: later. The `meerkat` extra needs a C compiler and has no cp314 wheel

- **Where:** `pyproject.toml:56-57`.
- **What is wrong:** `katsdptelstate[rdb]` pulls python-lzf and rdbtools, which are sdist-only, and cityhash,
  which has no cp314 wheel (verified with the PyPI JSON). This is stated only in a pyproject comment, not in
  the README extras table or docs/installation.md.
- **Fix:** add to the extras table "needs a C compiler; not on 3.14 without one".
- **Small and unambiguous:** yes.

### PK-20: later. The Development Status classifier

- **Where:** `pyproject.toml:16`.
- **What is wrong:** `Development Status :: 3 - Alpha` is unchanged. The finish line calls 0.2.0 "a working
  toolchain", so `4 - Beta` may fit. This is an owner choice. Note that "Alpha" here is a classifier, not a
  pre-release version.
- **Fix:** the owner decides.
- **Small and unambiguous:** no.

### PK-21: later. The PyPI page's links point at the moving `main`

- **Where:** `README.md:1-157`.
- **What is wrong:** about 45 links and the logo `src` point at `.../blob/main/...` or `raw.../main/...`.
  On PyPI the 0.2.0 page will drift as main moves, and reports may be renamed. Today every linked research
  file exists (verified with a loop). All eight pythonic.nl and raw image URLs return 200 (verified with curl).
- **Fix:** optionally pin the links to `v0.2.0` in the release commit, or accept the drift.
- **Small and unambiguous:** no.

### PK-22: later. The Rust dependency licences are not shipped as text

- **Where:** wheel and sdist.
- **What is wrong:** 37 locked crates are MIT/Apache-2.0, BSD-2-Clause and Unicode-3.0, all
  GPL-3-compatible (verified with `cargo metadata --locked --offline`). Their notices are present only
  through maturin's SBOM.
- **Fix:** optionally generate a `cargo about` file into THIRD-PARTY-NOTICES (PK-06).
- **Small and unambiguous:** no.

### PK-23: later. The sdist ships tests that cannot run from it

- **Where:** sdist `tests/`.
- **What is wrong:** all 60-odd `tests/test_*.py` ship, but most read `research/` and skip or fail from an
  sdist. This is intended (`pyproject.toml:84-86`), but costs about 0.5 MB.
- **Fix:** none needed; or include only the wheel subset listed in `tools/wheel/test.py:70-72`.
- **Small and unambiguous:** no.

### PK-24: later. The flagger weights: nothing bundled (confirmation)

- **Where:** `core/src/f3flag.rs`, `core/src/cnnflag.rs`, `python/rang/f*flag.py`.
- **What is wrong:** nothing. There are no embedded weight arrays (a grep for large `const`/`static` f32
  arrays found none), and the CHANGELOG at :141 says "weights are run outputs, not shipped". The open item
  "shipping LUNO-derived weights" (finish-plan.md section 6) needs a licence note only if weights are ever
  added.
- **Fix:** none.
- **Small and unambiguous:** n/a.

### PK-25: later. The local main is unpushed

- **Where:** local `main` at `3eab67c`; `origin/main` at `c2fe7cc`.
- **What is wrong:** two docs-only commits are unpushed. CI green is verified on `c2fe7cc`, not on the
  reviewed commit.
- **Fix:** push, and confirm `wheels` is green on the commit that will be tagged (finish-plan E6).
- **Small and unambiguous:** yes.

## Dependencies and metadata (no finding)

- Runtime dependencies are `numpy>=1.26` and `pyyaml>=6`. They are minimal, unbounded above, and have
  cp314 wheels.
- The casacure pin is 3.8.35, while 3.8.41 is the latest release. The pin is intentional (oracle), and its
  marker matches its wheels.
- jax, scipy and numpy latest require Python ≥ 3.12, but older releases resolve on 3.10 and 3.11. The lower
  bounds are fine.
- The classifiers are 3.10-3.14, which agrees with abi3-py310 (`core/py/Cargo.toml:16`) and with the test
  cells (3.10 and 3.14). The URLs return 200.
- `License-Expression` is correct. There is no `License ::` classifier, as PEP 639 requires.
- LICENSE is the GPLv3 text. GitHub detects `gpl-3.0`. All three Cargo.toml say `license =
  "GPL-3.0-or-later"`. The README, docs/licence.md and CITATION all say GPL-3.0-or-later.
