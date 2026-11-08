"""note_merge.py : add section 11 (the merge of main 3defaae) to research/g9-stokes.md and
the merge's tool-timings rows."""

W = "/home/gijsm/Worktrees/rang/fp-g9-stokes/"
p = W + "research/g9-stokes.md"
s = open(p).read().rstrip("\n") + "\n"
s = s.replace(
    "- **Merge with W6/G6 (`fp-g6-predict`).** Expected textual conflicts, all additive:",
    "- **Merge with W6/G6 (`fp-g6-predict`)**, done on this branch on 2026-11-08 (section 11).\n"
    "  The conflicts were, as expected, all additive:",
    1,
)
s += """
## 11. Merge of main `3defaae` (G6 and W6), 2026-11-08 (measured)

Main `3defaae` (G6: MODEL_DATA after imaging and `-predict`; W6: `-scans`, `-unit-weights`,
WSClean's WEIGHT fallback) merged into `fp-g9-stokes`. Conflicts resolved additively:
`input::Selection` and its default keep `polarization`, `scans` and `unit_weights`; `read_ms` keeps
W6's `row_mask`, weight source and fallback and G9's correlation indices and cell; `bin/gemclean.rs`
keeps both sets of `Args`, flags and the `Selection` literal, and G9's `run_polarizations` and G6's
`write_model` / `predict_only` (interleaved by git around their shared report lines) whole, one
after the other; CHANGELOG and tool-timings keep both sides. Semantic edits:

- G6's model writing is refused for polarisations other than Stokes I: gemclean refuses `-predict`
  and the model update after imaging (on by default, as WSClean's) unless
  `-no-update-model-required` when `-pol` is not `I`, and `rang-core` refuses `image.write_model`
  with `image.pol` other than `I` (path `image.write_model`, no task: a follow-up of this note).
  `rang-core image` already passes `-no-update-model-required`, so E2-B's image stage runs.
- E2-B's expected refusal set (`test_the_acceptance_configurations_parse_and_wait_for_their_tasks`)
  is now empty: W6 removed W4, G9 removed G9.
- `run_polarizations` builds each polarisation's `Selection` from the merged one, so `-scans` and
  `-unit-weights` reach every polarisation.

Checks ([merge_check.sh](results/g9-stokes-scripts/merge_check.sh), outputs
`/mnt/d/rang/outputs/g9-20261108-05`), every build and run under the heavy lock:

- **Criterion A against main `3defaae`** (gemclean built from it, sha256 `cebcf148…a728873d`;
  merged binary `6935a229…44eaa58e`), both with `-no-update-model-required` so that G3's D1.ms is
  not written: D1 C0, C0 `-single`, C1, C3, C4, **all 100 FITS files identical**, and `-pol I`
  identical to main's C0.
- **Smoke tests against the frozen binary's held-out output** (H1p, `-no-update-model-required`):
  Q2 (IQUV joined) 17 of 17 FITS files identical to the frozen H1p-Q2; Q1 with `-scans 1` (H1p's
  one scan) 17 of 17 identical to the frozen H1p-Q1. `-pol IQUV` without
  `-no-update-model-required` is refused (exit 2) before the MS is read.
- check-all: only `test_every_note_is_in_the_research_index` fails (1049 passed, 68 skipped).
"""
open(p, "w").write(s)

t = W + "research/tool-timings.md"
s = open(t).read().rstrip("\n") + "\n"
s += (
    "| 2026-11-08 | G9 merge of main 3defaae: check-all | worktree | 12:36 with lock wait | 1.83 GB "
    "| only `test_every_note_is_in_the_research_index` fails |\n"
    "| 2026-11-08 | G9 merge check (main 3defaae build, merged build, criterion A, two smoke runs) "
    "| D1, H1p | builds about 2.5 min each; runs as before | 2.10-6.86 GB | heavy lock for every "
    "build and run; all identical |\n"
)
open(t, "w").write(s)
