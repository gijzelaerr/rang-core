# FS2: Perley-Butler 2017 and 2013 against CASA `setjy`, with CASA's own tables

Protocol frozen 2026-11-02 on branch `fs2-casarundata` (from `6beec0a`), before
any table was fetched or read. Task FS2 of the big plan; the open item of
[fs1-flux-standards.md](fs1-flux-standards.md) ("Oracle pending"). The owner
approved the download on 2026-11-02.
Status at freeze: proposed; only directory listings of the source were seen.

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
