"""note_merge2.py : section 12 of research/g9-stokes.md (merge of main a2450aa: G5 multiscale and
C5 self-calibration) and its tool-timings rows."""

W = "/home/gijsm/Worktrees/rang/fp-g9-stokes/"
p = W + "research/g9-stokes.md"
s = open(p).read().rstrip("\n") + "\n"
s += """
## 12. Merge of main `a2450aa` (G5 multiscale, C5 self-calibration), 2026-11-09 (measured)

Main `a2450aa` (which includes `f3ab57d`, G5's merge) merged into `fp-g9-stokes`
([resolve_g5.py](results/g9-stokes-scripts/resolve_g5.py),
[selfcal_refusal.py](results/g9-stokes-scripts/selfcal_refusal.py)). Conflicts resolved
additively: gemclean's usage text keeps both sections; `parse_args` keeps G9's and G5's checks;
`core_config` keeps G9's `pol` parsing and G5's multiscale-option refusals (the G5 and G9 refusals
are gone on both sides); `gemclean_arguments` passes both sets of options; CHANGELOG and
tool-timings keep both sides.

**`-multiscale` with several polarisations: refused, a follow-up.** radler's multiscale joins
polarisations through the same linked image set, so on paper it is G5's joined-channel path with
one coefficient per (channel, polarisation) entry. But G5's port and its oracle cases are Stokes I
only, and supporting it would need its own comparison against WSClean (multiscale with joined
polarisations, per-scale components in every polarisation), which this merge does not have. So
gemclean refuses `-multiscale` with more than one polarisation (one non-I polarisation takes G5's
path unchanged), and `rang-core` refuses `image.multiscale` with several polarisations.

**C5:** self-calibration images through `image.*` and predicts `<name>-model.fits`, a Stokes I
model; `rang-core` refuses the selfcal stage when `image.pol` is not `I` (path `image.pol`, a
follow-up). The E2 expected-refusal sets after the merge: E2-A `{G4}` (main's), E2-B empty.

Checks ([merge_check2.sh](results/g9-stokes-scripts/merge_check2.sh), outputs
`/mnt/d/rang/outputs/g9-20261109-06`), builds and runs under the heavy lock:

- **Criterion A against main `a2450aa`** (gemclean built from it, sha256 `4e73ca72…7405958a`;
  merged binary `b41690d8…5dc302be`), `-no-update-model-required`: D1 C0, C0 `-single`, C1, C3, C4,
  **all 100 FITS files identical**, and `-pol I` identical to main's C0.
- **IQUV smoke test:** H1p Q2 (IQUV joined) 17 of 17 FITS files identical to the frozen binary's
  H1p-Q2. `-pol IQUV -multiscale` is refused (exit 2) before the MS is read.
- check-all: only `test_every_note_is_in_the_research_index` fails (1060 passed, 68 skipped).
"""
open(p, "w").write(s)
t = W + "research/tool-timings.md"
s = open(t).read().rstrip("\n") + "\n"
s += (
    "| 2026-11-09 | G9 merge of main a2450aa: check-all | worktree | see "
    "g9-20261109-checkall-4.time | – | only `test_every_note_is_in_the_research_index` fails |\n"
    "| 2026-11-09 | G9 merge check 2 (main a2450aa build, merged build, criterion A, one smoke run) "
    "| D1, H1p | builds about 2.5 min each; runs as before | 2.11-6.86 GB | heavy lock; all identical |\n"
)
open(t, "w").write(s)
