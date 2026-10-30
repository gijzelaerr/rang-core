# DDFacet: Hogbom diverges to inf on a point source with more than one facet

Repository: saopicc/DDFacet. Status: **filed 2026-10-30, https://github.com/saopicc/DDFacet/issues/77.
No PR** (cause not found within the one-hour time box). Task U3,
[../upstream-saopicc.md](../upstream-saopicc.md). Origin: the stalled Hogbom run in
[ddfacet-feasibility.md](../ddfacet-feasibility.md) (overflow at `ClassModelMachineHogbom.py:184`),
which the brief allowed filing only if it reproduced on synthetic data within an hour: it did, in
the first 2-minute run.

- **Versions.** DDFacet 1.0.0.0 = `master` 2fe05ab4; Python 3.12.15; NumPy 2.3.2.
- **Reproduction** (`research/upstream-saopicc-files/hogbom_run.sh`, `hogbom_synth.py`): copy of
  `outputs/luno-solve-20261029-02/work.ms` (4 antennas, 192 rows, 2048 channels, field 1) with
  `DATA` = 1 Jy point source at the phase centre (XX = YY = 1); the study's command (512 px at
  8″, Briggs 0.5, 3×3 facets, Hogbom, 3 major cycles, peak factor 0.05, NCPU 4).
- **Observed.**

  | Run | Facets | uv | Major cycle 0 | Wall / peak RSS |
  |---|---|---|---|---|
  | `point-s1` | 3×3 | 74 m | 20,000 iterations, peak `inf`, overflow at :184, model `nan`; 368 components, largest ±inf | 101.7 s / 8.9 GB |
  | `long30` | 3×3 | UVW ×30 (2.2 km) | 20,000 iterations, peak 8.26e15 Jy | 104.2 s / 9.0 GB |
  | `nf1` | 1 | 74 m | converges: residual peak 0.047 Jy, then 0.0022 Jy | 273.1 s / 21.5 GB |

  Dirty peak 1.000 Jy in all runs, at the centre pixel (262, 262) in the two 3×3 runs (checked
  in `img.dirty.fits`). The divergence follows the
  facet count, not the compact-array PSF (the study's suspicion), so the study's "stall" was this
  divergence followed by degridding an `inf`/`nan` model.
- **Expected.** Removal of the point source for any facet count.
- **Cause (not established).** The facet-dependent step is `PSFServer.setLocation`/`GivePSF`
  (`giveFacetID2`, polygon test on l, m) choosing the facet PSF that `SubStep` subtracts; a PSF
  mismatched to the component position would explain exponential growth. Not verified; the
  issue says so. Also suggested: a divergence stop like WSCMS's `MinorDivergenceFactor`.
- **Duplicates checked.** saopicc/DDFacet and cyriltasse/DDFacet (`hogbom`, `diverg`, `facets`):
  cyriltasse#674 (Hogbom stalls at a residual floor) and #608 (channel indexing) differ.
- **Not run.** A v0.9.1 comparison (0.9.1 does not install on GCC 15, see
  [killms-ddfacet-app-api.md](killms-ddfacet-app-api.md)); HMP/SSD on the synthetic MS.
- **Note for rang.** Peak RSS 8.9-21.5 GB for a 37 MB MS (the study's 8.9 GB HMP peak recurs);
  DF0/DF5 oracle runs should use one facet or check Hogbom output for `nan`.
