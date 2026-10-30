# Geometry provenance

The toy uses eight rounded horizontal positions from Table 1 of *The MeerKAT Radio Telescope*, Jonas & the MeerKAT Team, PoS(MeerKAT2016)001:

https://pos.sissa.it/277/001/pdf

| Antenna | Published X (m) | Published Y (m) |
| --- | ---: | ---: |
| m000 | -8 | 27 |
| m004 | -124 | -19 |
| m008 | -93 | -302 |
| m012 | 140 | -135 |
| m016 | 288 | 49 |
| m020 | 97 | -66 |
| m024 | -351 | 386 |
| m028 | -51 | 148 |

These values were transcribed from the indexed table text on 2026-09-11. The publisher PDF download returned HTTP 403 during this session, so the transcription has not been checked against a rendered table. The toy treats X/Y as east/north, takes latitude -30.713 degrees and sets heights to zero. This is an approximate published core layout, **not verified current three-dimensional survey geometry**. Obtain coordinates from a MeerKAT observation or authoritative antenna descriptions before making instrument-specific accuracy claims.

The code projects these baseline vectors into uvw and retains the full w(n-1) phase. This accounts for the curved sky for the assumed geometry; it does not restore omitted terrain or survey information.

No telescope observations, measured holography beams or external datasets are bundled. The 13.5 m Gaussian beam is an explicitly idealized response, not EIDOS, katbeam or a measured MeerKAT beam.

## MeerKAT 64-antenna ITRF positions (`meerkat.itrf.txt`)

Added 2026-10-30 for the CLEAN theory measurements
(`research/clean-theory.md`, `core/examples/clean_theory.rs`). Copied
verbatim from the simms repository (radio-astro/simms, GPL-2.0),
`simms/observatories/meerkat.itrf.txt`, last changed in commit
`ad6d0a4acfd4f4622be22f9f88e42f3a21a86a73` of 2018-01-02; columns are ITRF
X, Y, Z in metres, dish diameter, name, mount. A 2018 mailing-list note calls
these positions out of date, and they are not checked against a MeerKAT
observation's ANTENNA table. They give a realistic uv coverage and PSF for
algorithm studies, not survey-grade geometry.

## VLA (C configuration), WSRT and KAT-7 ITRF positions

Added 2026-10-30 for the CLEAN phase-transition study
(`research/clean-phase-transition.md`,
`core/examples/clean_phase_transition.rs`). All three come from the same
simms repository, which has moved from `radio-astro/simms` to
`ratt-ru/simms` (GPL-2.0; the GitHub API redirects the old name). They were
downloaded on 2026-10-30 from the `master` branch at commit
`e715505bd483252a404f552ff07e9d01f0939ff4` (2026-03-20) as
`https://raw.githubusercontent.com/ratt-ru/simms/master/simms/observatories/<file>`.
Columns are ITRF X, Y, Z in metres, dish diameter, name, mount, as in
`meerkat.itrf.txt`.

| File here | simms file | Antennas | Longest baseline | Last change to the simms file | SHA-256 of the copy |
| --- | --- | ---: | ---: | --- | --- |
| `vla-c.itrf.txt` | `vlac.itrf.txt` | 27 | 3.39 km | `3e239f53041e958d25b213d41d56d7565e9b0729`, 2015-06-13 | `c9bc5d85…b4388a7` |
| `wsrt.itrf.txt` | `wsrt.itrf.txt` | 14 | 2.70 km | `3f85ccc1bcf8838f4751e046802c54406dc352d2`, 2016-02-02 | `6042f799…ffb5488` |
| `kat7.itrf.txt` | `kat-7.itrf.txt` | 7 | 0.18 km | `3f85ccc1bcf8838f4751e046802c54406dc352d2`, 2016-02-02 | `74588620…682c24e` |

`wsrt.itrf.txt` and `kat7.itrf.txt` are byte-identical copies;
`vla-c.itrf.txt` drops the one header line (`#X Y Z dish_diam station
mount`) of the simms file and is otherwise identical. The VLA table is one
fixed C-configuration pad set; the WSRT table is one fixed setting of the
movable dishes (RT0-RT9 at 144 m spacing, RTA-RTD beyond), not any
particular observation's; KAT-7 was decommissioned in 2016. None of these
was checked against an observation's ANTENNA table. Like the MeerKAT file,
they are realistic layouts for algorithm studies and **not survey-grade
geometry**.
