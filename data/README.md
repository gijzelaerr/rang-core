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
