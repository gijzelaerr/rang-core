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
| MeerKAT ITRF positions from simms | GPL-2.0 ({gh}`data/README.md`) |

Crystalball is GPL-2.0-only and is not ported.

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
- **Antenna positions.** The toy's eight core positions are transcribed from
  Jonas & the MeerKAT Team, PoS(MeerKAT2016)001 ({gh}`data/README.md`).

## Logo

The interferogram mark and the `rang-core` wordmark are the project's own
({ghdir}`docs/logo`).
