# Licence and acknowledgements

## Software

rang-core is free software under the GNU General Public License, version 3
or (at your option) any later version; see {gh}`LICENSE`. The GPL was chosen
on 2026-10-29 so that GPL-3 radio-astronomy tools such as WSClean and
AOFlagger can be ported into the core. GPL-2.0-only code cannot be combined
with GPL-3 code, so each upstream's exact licence is checked before it is
ported, and ported code keeps its upstream copyright notices.

| Ported or bundled | Upstream licence, as the reports record it |
| --- | --- |
| QuartiCal 0.2.7 `complex` solver | MIT; the ported file keeps its notice ({gh}`research/core-phase2.md`) |
| Tricolour 0.2.1 strategies and static masks | BSD-3-Clause, on the strength of its `LICENSE` file; the masks ship with `TRICOLOUR-LICENSE` ({gh}`research/core-d-tricolour.md`) |
| WSClean 3.6 weights and w-stacking gridder | GPL-3.0 ({gh}`research/core-c-gridder.md`) |
| ducc0 0.42.0 wgridder | GPL-2.0-or-later ({gh}`research/df1-wgridder.md`) |
| SARAO/SKA pointing-offset fit (ska-sdp-wflow-pointing-offset) | BSD-3-Clause ({gh}`research/b1-beam-pointing.md`) |
| codex-africanus 0.4.4 WSClean-format component predict (`core/src/predict.rs`) | BSD-3-Clause; the translated file keeps its notice, as does {gh}`THIRD-PARTY-NOTICES.txt` |
| katdal 0.23 test helpers, adapted for the synthetic MVF writer (`python/rang/meerkat.py`) | BSD-3-Clause, National Research Foundation (SARAO) |
| CASA (casa6) calibration and flagging C++: `SolvableVisCal.cc`, `SolveDataBuffer.cc`, `StandardVisCal.cc`, `DJones.cc`, `XJones.cc`, `KJones.cc`, `Calibrater.cc`, `VisCal.cc`, `Jones.cc`, `VisEquation.cc`, `CTPatchedInterp.cc`, `RIorAParray.cc`, `FlagAgentExtension.cc`, read in the mirror `dic-case-studies/casa6` at `9269a52` and followed in the K, G, B, F, polarisation and apply ports (`core/src/cal/`, `rang.cal_*`, `rang.applycal`, `rang.formats.caltable`) and in `core/src/flag_extend.rs` | GPL-2.0-or-later (`Calibrater.cc`), LGPL-2.0-or-later or LGPL-2.1-or-later (`FlagAgentExtension.cc`), each file's own header; Associated Universities, Inc. (and ESO for `FlagAgentExtension.cc`). The LGPL lets a copy be put under the GPL, so all are compatible with GPL-3.0-or-later; each derived file names CASA and the notices are in {gh}`THIRD-PARTY-NOTICES.txt` (checked 2026-11-12, E5 final) |
| MeerKAT ITRF positions from simms | Facts, not code: see below ({gh}`data/README.md`) |

Crystalball is GPL-2.0-only and is not ported.

Behaviour reimplemented from upstream source and documentation, with no
code copied (owner decision E5-33, 2026-11-11,
{gh}`research/e5-prereview.md`):

| Reimplemented | Upstream and its licence |
| --- | --- |
| CARACal 8f7bb363 `manage_antennas.get_refant` (`refant: auto`, `python/rang/cal_refant.py`) | CARACal, GPL-2.0 (its `pyproject.toml` does not say whether only or or-later); follow-up: ask the CARACal authors to confirm GPL-2.0-or-later |
| msutils 1.2.0 `flag_stats.save_statistics` and `wgs84_to_ecef`, as `get_refant` uses them (`python/rang/cal_refant.py`) | msutils; licence not checked (its repository reports none) |
| CASA's ported sources | Listed with the ported code above: the calibration and flag-extension ports read CASA's C++ source, so they are translations, not reimplementations of documented behaviour |
| casacore 3.8.1 AipsIO and table formats (`core/src/aipsio.rs`, the table writer) | casacore, LGPL-2.1-or-later; the formats were read in its sources, nothing is copied |

The observatory positions in `python/rang/data/casacore_observatories.json`
come from casacore-data 20250826 ({ghdir}`python/rang/data`); like the
antenna tables below they are positions, not code.

The antenna coordinate tables in `data/*.itrf.txt` are copied from simms
(GPL-2.0-only). They hold measured antenna positions (ITRF X, Y, Z, dish
diameter, name, mount) and no code; positions of physical antennas are facts,
which copyright does not cover, so they carry no simms licence obligation and
ship under rang-core's GPL-3.0-or-later with their source recorded in
{gh}`data/README.md`. Only `meerkat.itrf.txt` ships in the sdist, because
GeMClean's simulator compiles it in; the VLA, WSRT and KAT-7 tables feed the
research examples only and stay in the repository (owner decision E5-11,
2026-11-11, {gh}`research/e5-prereview.md`). A byte copy of
`meerkat.itrf.txt` is package data (`python/rang/data/`), so the A1
simulation (`rang.simtruth`, `python -m rang.simtruth_ms`) runs from a wheel
(V3's owner decision 4, {gh}`research/v3-intro-track.md`).

## Data

No raw visibilities or beam maps are committed or redistributed. Fetched
data stay in ignored `outputs/` or in a cache directory the user names.

- **MeerKAT data (SARAO).** The LUNO calibrator observation is used with the
  observer's permission (Ben Hugo, 2026-10-29), recorded as a user decision
  in {gh}`research/big-plan.md`; publications cite the SARAO data usage
  acknowledgement, recorded in {gh}`research/flagging-verdict.md` as:

  > The MeerKAT telescope is operated by the South African Radio Astronomy
  > Observatory, which is a facility of the National Research Foundation, an
  > agency of the Department of Science and Innovation.

  The report notes this wording is to be checked against SARAO's data policy
  before publication.
- **MeerKAT L-band holography beams** (de Villiers 2023, AJ 165, 78; data DOI
  10.48479/wdb0-h061): licence **CC BY-NC 4.0**. rang reads them by HTTP
  range for non-commercial research and never redistributes them; a
  commercial use of products derived from them would need SARAO's permission
  ({gh}`research/b1-beam-pointing.md`).
- **ESO137 target field** (RATT public bucket): licence **CC BY 4.0**, cite
  Ramatsoku et al. (2020) ({gh}`research/b1-beam-pointing.md`).
- **The tutorial fixture** `outer_scans.zip` is a public test file of the SKA
  repository ska-sdp-wflow-pointing-offset (Git LFS), downloaded on demand
  and verified by SHA256, never bundled
  ({gh}`research/measurement-set-inspection.md`).
- **Antenna positions.** The simulation's eight core positions are transcribed from
  Jonas & the MeerKAT Team, PoS(MeerKAT2016)001 ({gh}`data/README.md`).

## Logo

The interferogram mark and the `rang-core` wordmark are the project's own
({ghdir}`docs/logo`).
