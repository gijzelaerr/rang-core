# FS2: Perley-Butler 2017 and 2013 against CASA `setjy`, with CASA's own tables

Protocol frozen 2026-11-02 on branch `fs2-casarundata` (from `6beec0a`), before
any table was fetched or read. Task FS2 of the big plan; the open item of
[fs1-flux-standards.md](fs1-flux-standards.md) ("Oracle pending"). The owner
approved the download on 2026-11-02.
Status at freeze: proposed; only directory listings of the source were seen.

**Status now: measured** ([results](#measured-results-2026-11-02)). PB2017: 4 of 20
sources equal `setjy` and are regular (3C123, 3C286, 3C295, Hercules A); 16 stay
opt-in because CASA's table is not the paper's Table 5. No transcription error.
PB2013: measured, not in the core.

## Why

FS1 verified PB2010, Baars, SR2016 and `manual` against `setjy` and left
PB2017 paper-transcribed and opt-in, because its coefficient table is not in
the oracle image. PB2013 has no table in the image either and **is not in the
core at all** (FS1 item 7: "not ported unless its table and paper text become
available"). FS2 supplies the tables to the oracle and answers both.

## Source (listings only, before the fetch)

`casarundata` is not on PyPI (404). `casaconfig` fetches it from
`https://go.nrao.edu/casarundata`, which redirects to
`https://casa.nrao.edu/download/casaconfig/data/`.

| Source | What | Size |
| --- | --- | --- |
| `rsync://casa-rsync.nrao.edu/casa-data/nrao/VLA/standards/PerleyButler2017Coeffs` | `table.{dat,f0,info,lock}` | 59,899 bytes |
| same, `PerleyButler2013Coeffs` | `table.{dat,f0,info,lock}` | 19,975 bytes |
| `casarundata-2026.10.27-1.tar.gz` (with a published `.md5`) | streamed, only those two tables extracted | 336 MB of network, about 80 KB on disk |

The tables need nothing else (four plain files each). The rsync tree has no
version label and is dated 2021-10-08, so:

1. **Primary:** rsync with `-r --no-motd` (no symlinks) into a fresh
   `/mnt/d/rang/data/casarundata-standards/rsync-20261102/`.
2. **Version:** stream the newest named release once through `md5sum` and
   `tar -xz` restricted to the two tables, into a fresh sibling
   `release-2026.10.27-1/`; check the md5 against the published file and that
   both trees are byte-identical. If they differ, the release is the oracle
   and the difference is a finding.

The download is untrusted data: nothing in it is executed, and it is never
committed. Per-file URL, version, size and SHA-256 go in the results JSON.

## Oracle

`rang-o-casa:6.7.6.14`, `--network none`, the tables mounted read-only at
`/tables`, `examples/oracle_setjy.py /run --fs2 --tables /tables` into a fresh
`outputs/fs2-20261102-NN`. CASA finds the tables through its working directory
(FS1 probe). `--dump-tables` first records the column names, types, keywords
and row counts, opened read-only by a script kept outside the tables directory.
If casacore cannot open them on the read-only mount (a lock), the tables are
copied into the container's tmpfs and used from there; that is a recorded
post-hoc change, not a change of oracle.

- **Primary arm (FS1's frozen grid and sources).** `sample_ghz()` (85
  single-channel SPWs, 0.05-50 GHz), the 1001-channel 0.8-1.8 GHz SPW, the 18
  `FIELDS` names, epoch 2020-01-01; `setjy(field, standard, scalebychan=True,
  usescratch=True)` for `Perley-Butler 2017` and `Perley-Butler 2013`.
- **Control.** `Perley-Butler 2010` on the same MS: its array hashes must equal
  FS1's run `outputs/fs1-20261030-01` (the mount changes nothing).
- **Secondary arm, declared here.** The PB2017 sources FS1's list lacks, at
  their J2000 positions, same grid: J0133-3629; FORNAX_A, FORNAXA; J0444-2809;
  PICTOR_A, PICTORA; TAURUS_A, TAURUSA, 3C144; HYDRA_A, HYDRAA, 3C218; VIRGO_A,
  VIRGOA, 3C274; HERCULES_A, HERCULESA, 3C348; 3C353; CYGNUS_A, CYGNUSA, 3C405;
  CASSIOPEIA_A, CASSIOPEIAA, 3C461. A source no listed name reaches is "not
  oracled" and keeps its opt-in.
- **Epoch and frame arm** (FS1 ran this for PB2010 only). Single-channel SPWs,
  3C48, 3C138, 3C147, 3C286, 3C295, 3C380, both standards: TOPO at 2000-01-01,
  2010-01-01, 2020-01-01, and LSRK at 2020-01-01. FS1's `setjy` default
  `interpolation` is kept.

## Criterion (the same as FS1's, per recognised source)

Stated as FS1 froze it:

1. **Doubles:** `flux(source, nu, standard)` equals `setjy`'s `fluxd` to
   **1e-6 relative** at every single-channel SPW inside the model's range.
2. **Float32 MODEL_DATA:** the port's per-channel I rounded to float32 equals
   CASA's MODEL_DATA I to within **one float32 ulp**, with Q = U = V = 0 where
   CASA writes zeros.

FS1 measured ≤ 1.6e-14 and 0 ulps for SR2016 and PB2010, and those are reported
beside the pass/fail here; the pass itself is criteria 1 and 2, as frozen. Also
recorded: FS1's criterion 5 (out of range, `extrapolate=True`, unknown names
refused) and 6 (Rust = Python to 1e-13).

## Decision rules, frozen

- **A mismatch is recorded as frozen.** The table's coefficients are then
  compared with the FS1 transcription of the paper's Table 5 (and the paper if
  they disagree). Outcomes:
  - **Transcription error** (a digit in the core differs from Table 5, and the
    table agrees with Table 5): fix the core, labelled post-hoc, and re-measure.
  - **CASA's table differs from Table 5** while the core agrees with the paper:
    not a transcription error. The core stays; the difference is a finding and
    the question goes to the coordinator.
  - **Storage difference** (the table holds float32 or more digits of the same
    decimals): not a transcription error. As FS1 did with `_f32`, the core may
    store what CASA stores; a labelled representation fix, then re-measure.
  - **Model difference** (epoch or MJD terms, `fluxd` moving between epochs, or
    a different functional form): not a transcription error. The source stays
    opt-in and the question goes to the coordinator; nothing is tuned.
- **The opt-in.** FS1's rule: "Until then PB2017 is opt-in only", and the
  `verified` field is "equal to CASA setjy within the FS1 acceptance". So a
  source becomes regular (no `unverified_ok`) only if it passes criteria 1 and 2
  in the primary or secondary arm and shows no epoch dependence in the epoch
  arm. `verified` is per source; a source that does not pass keeps the opt-in
  and the coordinator gets the partial result.
- **PB2013.** The core has none, and FS1 requires the paper text as well as the
  table. Porting from the table and checking against `setjy` on that same table
  would prove nothing. So: `setjy`'s values are measured and archived; `flux`
  keeps refusing "Perley-Butler 2013" as an unknown standard; porting it is a
  question for the coordinator. Its verdict is "measured, not in the core".
- **1934-638 under PB2017/PB2013.** FS1 left open what `setjy` does (not
  rejected by name; the paper omits it). This run records it. The port's refusal
  stays unless the table holds the source, which is then a finding.

## Files

`examples/oracle_setjy.py` (additive `--fs2`, `--dump-tables`),
`examples/check_fluxstd.py` (additive `--fs2`), `tests/test_fluxstd.py`,
`research/results/fs2-casarundata.json` (derived numbers only), this report;
`python/rang/fluxstd.py` and `core/src/fluxstd.rs` only as the rules above allow.

## Measured results (2026-11-02)

Everything below is after the freeze. Oracle: `rang-o-casa:6.7.6.14`
(`sha256:24822b4038c5…`), casatools 6.7.6-14, `--network none`.
Archive: [results/fs2-casarundata.json](results/fs2-casarundata.json) (derived
numbers only: `setjy`'s values, comparisons, hashes; no table).

**The download.** Release `casarundata-2026.10.27-1`: 352,724,572 bytes
streamed once and not kept, md5 `9095d076…` equal to the published `.md5`,
sha256 `e372fef1…`. The rsync tree is byte-identical to that release's two
tables, 79,874 bytes per tree. Per file (both trees):

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `PerleyButler2013Coeffs/table.dat` | 4,270 | `19a44f2c63ccdf512c9afcd9dac149f12d3fa2ebe5a2597ba029045120f6b663` |
| `PerleyButler2013Coeffs/table.f0` | 15,360 | `a694c8a47679c69416821277946dbc782716c8fb3532d1d9848f4df8f1ddfc09` |
| `PerleyButler2013Coeffs/table.info` | 20 | `2e6837789cd3ba36bb60a9871db174b4d14842bd7953249d117ccc2cc6f0a271` |
| `PerleyButler2013Coeffs/table.lock` | 325 | `0d68529c4619f6bfbdcad5426ad139bafd4fb9b3e7f7759cc9351d0d60ecbb81` |
| `PerleyButler2017Coeffs/table.dat` | 16,034 | `2a2caa17837101b697393fb4e5cc1a30ae6d9966e2f746720f3ac662826b58f2` |
| `PerleyButler2017Coeffs/table.f0` | 43,520 | `f4b8a2c38c0f34b5bc1440aff23478b8bd3d7c203230af6b17cd7c443d8e3fdc` |
| `PerleyButler2017Coeffs/table.info` | 20 | `2e6837789cd3ba36bb60a9871db174b4d14842bd7953249d117ccc2cc6f0a271` |
| `PerleyButler2017Coeffs/table.lock` | 325 | `4aa58e6cbf114c4e3f7d9ab365a4b4e5805496c4f31855295b0fb5c1fa508bee` |

Tables: "Perley-Butler 2017 coefficients", revision 1.0, dated 17/07/25, 18
epoch rows (1983.4 to 2017.0); "Perely-Butler 2013 coefficients" (sic),
revision 1.0, dated 13/05/14, 17 rows (1983.4 to 2012.0); float32 coefficient
columns. Read as data in the container only; nothing in the download was run.
The NRAO rsync server's banner reserves its computing facilities for authorised
personnel, so a repeat should use the release, which comes from the HTTPS tree
`casaconfig` itself uses and has the same bytes.

**Verdicts.**

- **PB2017: partial.** 3C123, 3C286, 3C295 and Hercules A equal `setjy` and are
  now regular. The other sixteen keep the opt-in. The core equals the paper's
  Table 5 for all twenty (arXiv v1, read again here): **no transcription error**.
  The sixteen differ because CASA's table is not Table 5.
- **PB2013: measured, not in the core.** `setjy` equals its own table (the
  check below); its seven sources are archived; `flux` still refuses the standard.
- **Control:** PB2010's 36 arrays have the hashes of FS1's run 01: mounting the
  tables changes nothing.

Per PB2017 source. "Table" is CASA's last row against Table 5; "as frozen" is
Table 5's decimals in double against `setjy` (maximum relative in the model's
range / maximum float32 ulps on 0.8-1.8 GHz); "L band" is the same relative
difference on 0.856-1.712 GHz; "port" is the module now. Criteria: 1e-6 and 1 ulp.

| Source | Table against Table 5 | Largest coefficient difference | As frozen | L band | Port | Result |
| --- | --- | ---: | --- | ---: | --- | --- |
| J0133-3629 | more digits | 0.0002 | 3.9e-04 / 465 | 2.8e-05 | 3.9e-04 / 465 | opt-in |
| 3C48 | **epoch rows** | 0.0000 | 1.6e-07 / 1 | 6.9e-08 | 1.6e-07 / 1 | opt-in |
| Fornax A | more digits | 0.0005 | 1.8e-03 / 1.67e+04 | 1.2e-03 | 1.8e-03 / 1.67e+04 | opt-in |
| 3C123 | same decimals | 0.0000 | 5.6e-08 / 1 | 4.8e-08 | 5.7e-08 / 0 | **equal, regular** |
| J0444-2809 | more digits | 0.0004 | 2.2e-04 / 2.02e+03 | 1.5e-04 | 2.2e-04 / 2.02e+03 | opt-in |
| 3C138 | **epoch rows** | 0.0003 | 2.2e-03 / 541 | 2.6e-05 | 2.2e-03 / 541 | opt-in |
| Pictor A | more digits | 0.0001 | 1.1e-04 / 217 | 1.1e-05 | 1.1e-04 / 217 | opt-in |
| Taurus A | more digits | 0.0004 | 1.8e-03 / 3.02e+03 | 2.0e-04 | 1.8e-03 / 3.02e+03 | opt-in |
| 3C147 | **epoch rows** | 0.0004 | 9.0e-03 / 390 | 3.2e-05 | 9.0e-03 / 390 | opt-in |
| 3C196 | more digits | 0.0004 | 2.7e-03 / 722 | 4.6e-05 | 2.7e-03 / 722 | opt-in |
| Hydra A | more digits | 0.0005 | 4.5e-03 / 453 | 3.7e-05 | 4.5e-03 / 453 | opt-in |
| Virgo A | more digits | 0.0003 | 1.2e-03 / 510 | 3.4e-05 | 1.2e-03 / 510 | opt-in |
| 3C286 | same decimals | 0.0000 | 1.5e-07 / 2 | 1.4e-07 | 5.5e-08 / 0 | **equal, regular** |
| 3C295 | same decimals | 0.0000 | 2.0e-07 / 2 | 1.3e-07 | 5.2e-08 / 0 | **equal, regular** |
| Hercules A | same decimals | 0.0000 | 1.3e-07 / 1 | 5.8e-08 | 4.8e-08 / 0 | **equal, regular** |
| 3C353 | **different value** | 0.0412 | 3.2e-02 / 1.93e+04 | 1.0e-03 | 3.2e-02 / 1.93e+04 | opt-in |
| 3C380 | more digits **range 0.05-4 GHz** | 0.0034 | 1.1e-01 / 298 | 1.7e-05 | 1.1e-01 / 298 | opt-in |
| Cygnus A | more digits | 0.0005 | 1.4e-03 / 432 | 3.5e-05 | 1.4e-03 / 432 | opt-in |
| 3C444 | more digits | 0.0003 | 3.7e-04 / 1.55e+03 | 9.5e-05 | 3.7e-04 / 1.55e+03 | opt-in |
| Cassiopeia A | more digits | 0.0005 | 5.0e-04 / 768 | 4.7e-05 | 5.0e-04 / 768 | opt-in |

**What the mismatches are, by the frozen rules.**

- **Storage (3C123, 3C286, 3C295, Hercules A).** The table holds float32 of
  Table 5's decimals. In double the decimals passed criterion 1 (≤ 2.0e-7) and
  failed criterion 2 for 3C286 and 3C295 (2 ulps). The rule allows storing what
  CASA stores: `_f32` for these four, the digits unchanged (**labelled
  representation fix**). The port then gives 0 ulps on all 1001 channels.
- **More digits (twelve sources).** CASA's table carries a fourth decimal where
  Table 5 prints three (or two); each value rounds to the printed one. Not a
  transcription error; the core keeps the paper's values. On L band the effect
  is at most 2e-4 where the source's range covers it (Taurus A; Fornax A's
  range stops at 0.5 GHz). In range it reaches 4.5e-3 (Hydra A), because the
  rounded terms grow at the range ends.
- **3C353: a different value.** Table 5 prints a3 = −0.032 ± 0.0005; CASA's
  table has −0.0732 ± 0.0047. The core has the printed value, so this is not a
  transcription error, and it moves 3C353 by up to 3.2 % in range and 0.1 % on
  L band. Which is
  right is open: the ApJS version of record was not in hand, only arXiv v1.
- **3C380: a different range.** Table 5 gives 0.05-50 GHz, CASA's table 0.05-4
  GHz. The paper's text (section 7.8) calls the source variable and useful only
  at low frequencies. It also has more digits, up to 11 % in the paper's range.
- **Epoch rows (3C48, 3C138, 3C147).** `setjy` takes the nearest row (the
  `interpolation='nearest'` default; the epoch arm's values equal that row):
  relative to 2020, 3C48 moves 7.8%, 3C138 33.0% and 3C147 47.8% at 2000 or 2010. The last
  row (2017.0) is what Table 5 prints for 3C48, and rounds to it for the other
  two. A model difference: the core has no epoch argument, so they stay opt-in.
  3C286, 3C295, 3C380, 3C123 and Hercules A do not move at all; no source moves
  in LSRK. On 2017 and later data 3C48 passes both criteria, but no other epoch does.

**What else `setjy` does on the table path.**

- `fluxd` is float32 here (it was double on FS1's compiled path), so doubles
  cannot agree better than 5.7e-8; rounded to float32 the table's polynomial
  equals `fluxd` and MODEL_DATA at 0 ulps for every recognised field of both
  standards. Post-hoc: the check's frozen-in-code threshold of 1e-13 was wrong for
  this path and now asks for float32 equality. FS1's 1e-6 and 1 ulp are unchanged.
- **Out of range** it logs WARN and evaluates the polynomial anyway (FS1's
  compiled standards do not warn). The port still refuses unless `extrapolate=True`.
- **1934-638 (FS1's open item):** in neither table. `setjy` logs SEVERE "does
  not appears to be in" and returns `{}` without raising, under all three names.
  J0408-6545 is "not recognized" (1 Jy). So for MeerKAT's two primaries PB2017
  and PB2013 give nothing; 3C286 is the MeerKAT-relevant source verified here.
- **Names:** `FORNAX_A` and `3C144`-style names are recognised; the unspaced
  `FORNAXA` forms give 1 Jy and SEVERE. The module's names are unchanged
  ("Hercules A"), so it refuses `3C348`; that is safe and left as is.
- **Stokes:** Q = U = V = 0 for every recognised field, which closes FS1's
  "unverified for PB2017".
- **PB2013 against PB2017:** 3C286 at 1.4 GHz is 0.49 % higher under PB2013
  (from the two tables' polynomials). PB2013 has 3C48, 3C138, 3C147, 3C286,
  3C123, 3C295 and 3C196 under FS1's names, with the same epoch-row sources;
  3C380 and 3C444 are not in it.

## Post-hoc steps, labelled

1. The arXiv PDF of Perley & Butler (v1, 2,311,277 bytes, sha256 `975c2018…`) was
   fetched to compare, as the frozen rule says, into
   `paper-arxiv-1609.05940/` beside the tables. Its size was not stated first.
2. Run `outputs/fs2-20261102-02`: the epoch arm on 3C295, 3C123 and HERCULES_A.
   3C123 and Hercules A had passed but the frozen arm did not include them, and the
   rule needs them flat. 3C295 repeats a failure in run 01: one call (PB2013, LSRK)
   logged `FilebufIO::readBlock - incorrect number of bytes read` on the table
   mounted from `/mnt/d`, and returned no value. It did not recur in run 02; the
   likely cause is the Windows-drive mount, not checked further. That is 1 of 152
   logged calls in run 01, and no verdict rests on it (PB2013 is not in the core).
3. The representation fix above. The check prints both the as-frozen and the
   current numbers (`as_frozen_*` in the archive).
4. In the check, not in the protocol: Fornax A and Cassiopeia A first classified as
   "differs" from a double rounding at a tie (2.2175, −0.0705); the rule now tests
   half a printed unit. That leaves 3C353 alone in that class.

The rule for the opt-in was applied per source, as frozen. `core/src/fluxstd.rs` is
unchanged. The published ApJS table and the PB2013 paper text were not read.

## Open, for the coordinator

- Should the sixteen follow CASA's digits (as the compiled standards do) or stay
  on the printed Table 5? The core stays on the paper until that is decided.
- Should the core gain an epoch argument for 3C48, 3C138 and 3C147, and which rule
  (CASA's nearest row)?
- Port PB2013? FS1 asks for the paper text as well as the table.
- 3C353's a3 and 3C380's range: check the ApJS version of record.

## Reproduce

Tables under `/mnt/d/rang/data/casarundata-standards/` (see Source); from the
worktree, with `$T` that directory's `rsync-20261102`, `$RUN` a fresh run directory:

```bash
docker run --rm --user $(id -u):$(id -g) --network none --tmpfs /tmp -e HOME=/tmp \
  -v $PWD/examples:/code:ro -v $RUN:/run -v $T:/tables:ro -w /run rang-o-casa:6.7.6.14 \
  /opt/casa/bin/python -I /code/oracle_setjy.py /run --dump-tables --tables /tables
#   ... /run --fs2 --tables /tables                                   # run 01
#   ... /run --fs2-epoch 3C295,3C123,HERCULES_A --tables /tables      # run 02, post-hoc
python examples/check_fluxstd.py --fs2 outputs/fs2-20261102-01 outputs/fs2-20261102-02 \
  outputs/fs1-20261030-01 /mnt/d/rang/data/casarundata-standards \
  research/results/fs2-casarundata.json
```

The tests read only the committed archive, so they need neither tables nor Docker.

## Tool runs

| Date | Tool | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-11-02 | `rsync` | the two tables | 10.9 s | – | 79,874 bytes |
| 2026-11-02 | `curl` into selective `tar` | `casarundata-2026.10.27-1.tar.gz` | 129 s | – | 352,724,572 bytes streamed, 8 files kept |
| 2026-11-02 | `oracle_setjy.py --dump-tables` (docker) | `fs2-20261102-01` | 2.4 s | 30 MB (client) | |
| 2026-11-02 | `oracle_setjy.py --fs2` (docker) | `fs2-20261102-01` | 781.6 s (control 40 s, PB2017 81 s, PB2013 67 s, secondary 157 s, epoch arm 408 s) | 293 MB (container) | |
| 2026-11-02 | `oracle_setjy.py --fs2-epoch` (docker) | `fs2-20261102-02` | 171.3 s | 31 MB (client) | post-hoc |
| 2026-11-02 | `uv venv` + `uv pip install` | worktree, public PyPI | 165 s | – | Python 3.14 |
| 2026-11-02 | `check_fluxstd.py --fs2` | runs 01, 02, FS1 run 01 | 0.3 s | 49 MB | |
| 2026-11-02 | `bash tools/check-all.sh`, before the final commit | branch at `ea46706` + the FS2 files (log `outputs/fs2-20261102-check-all.log`) | 528.0 s (pytest 828 passed, 20 skipped in 200.6 s) | 1.99 GB | PASS |
