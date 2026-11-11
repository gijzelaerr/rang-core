# E4: from a Measurement Set to an image (tutorial, command reference, CI)

Task E4 of [finish-plan.md](finish-plan.md): "A reader goes from MS to image
following the docs alone", and "CI runs a small end-to-end job on all five
wheels". Started early, 2026-11-11, before E2 has results. The E2 numbers
are placeholders (section 4). Branch `claude/focused-snyder-580a11` from main
`3eab67c`.

**Status:** implemented and measured: locally on Windows x86_64, and in CI
on all five wheels (section 5). Every check passed. This is
documentation and a regression check. It makes no scientific claim and no
novelty claim.

## 1. What was built

| Piece | Where |
| --- | --- |
| The tutorial notebook, rendered by the docs workflow | `notebooks/00-ms-to-image.ipynb`, linked from `docs/tutorials/index.md` ("Start here"), `docs/index.md` and `README.md` |
| The configuration and flagging strategy the tutorial and CI share | `examples/ms-to-image/config.yaml`, `strategy.yaml` |
| The end-to-end check, runnable locally | `tools/e2e/run.py OUT_DIR [--installed]` |
| The CI job: five platforms, Python 3.14, the wheel plus its `imaging` extra, no cargo | job `e2e` in `.github/workflows/wheels.yml` (`needs: wheel`) |
| Command reference: a `gemclean -h` section and a link to the tutorial | `docs/gen_cli.py` writes `docs/cli.md` |
| A1's generator under a wheel install | `examples/a1_simtruth.py` (section 6) |

**Data:** A1 small ([a1-simtruth.md](a1-simtruth.md)): 16 antennas, 64
channels, 104 integrations, 12,480 rows, 41 MB, written from the registered
seeds in about 4 s. This follows V3's proposal (`research/v3-intro-track.md`
section 4, on branch `claude/musing-dewdney-667f5d`) that E4 and the intro
notebooks I5-I7 share one MS. The public fixture has four antennas and one
field, so it cannot run a calibrator-to-target chain.

**Chain:** `rang-core run` with flag (the Tricolour port), calibrate
(setjy; K, G, B on J1939−6342; Gsec and F on SIM-GCAL), apply (K, G, B to
the flux calibrator; K, B and F from the nearest gain-calibrator scan to the
gain calibrator and the target), and image (GeMClean, 1024² × 3″, Briggs 0,
`write_model: true`). Then one `gemclean` call by hand on DATA. The polcal
section and selfcal are described but not run.

## 2. What the tutorial shows

The notebook explains each configuration section and shows each output:

- the run directory and `state.json`;
- resume (a second `run` skips every stage);
- the flag versions (`rang_original`, `rang_<stage>_<UTC>`) and a restore
  of `rang_original` on a copy;
- FLAG against A1's RFI mask;
- the K table against the true delays;
- MODEL_DATA (the setjy model on the flux calibrator, the CLEAN model on
  the target);
- CORRECTED_DATA against DATA on the flux calibrator;
- the FITS files and the six brightest components against the truth;
- residual against thermal noise;
- `gemclean` on uncalibrated DATA;
- the receipt.

It also shows two refusals with exit 2: circular feeds (`flag`, and the MS
is unchanged) and `pol: IQUV` with `write_model` (`config check`). The
results are printed by cells. The prose quotes only A1's design values
(sizes, σ, field layout) and the flagging numbers of section 3.

## 3. Measured (one local run; Windows x86_64, 2 threads, 2026-11-11)

Run with the main checkout's extension (built after the last Rust commit
`6e940b9`) and this branch's Python. The scratch run directories were
deleted afterwards.

| Quantity | Value |
| --- | --- |
| A1 small generation | 2.9-4.0 s |
| `rang-core run`: flag, calibrate, apply, image | 2.0, 1.7, 1.3-1.9, 3.5-3.8 s; 9.7-11.7 s wall |
| `tools/e2e/run.py`, whole | 16.5 s |
| Notebook under papermill | 24.9-30.1 s |
| Flagged fraction, whole MS | 0.364 |
| Recall of A1's RFI mask (`any` / `above_5sigma`) | 0.902 / 0.977; false flags on clean cells 0.290 / 0.330 |
| K against the true delays (relative to m000) | median 0.061 ns, max 0.146 ns (true \|τ\| 1-10 ns) |
| Brightest target component, 0.500 Jy point | 0.4957 Jy/beam peak (−0.9 %) |
| Next three points (0.190, 0.172, 0.162 Jy) | 0.180, 0.167, 0.161 Jy/beam |
| Restoring beam | 29.0″ × 4.97″, PA 34°, at 1284 MHz |
| Residual rms | 0.70 mJy/beam: 18× the natural-weighting thermal estimate (0.039 mJy/beam). A1's S term (10.5° rms phase, 1.0 % amplitude on the target only) and Briggs 0 weighting both raise it; the two are not separated |
| The same image from uncalibrated DATA | residual rms 1.82 mJy/beam; brightest point not recovered (0.002 Jy/beam) |

**Flagging is not a result here.** Nine strategies and CARACal's were run
on A1 small. The script is
[results/e4-tutorial/flag_variants.py](results/e4-tutorial/flag_variants.py)
and the numbers are in
[flag_variants.json](results/e4-tutorial/flag_variants.json). The static
mask on every baseline flags 57.8 % of the cells by itself (recall 0.985),
and 61.3 % with SumThreshold added. On channels of 13.4 MHz the mask covers
most of the band. CARACal's calibrator first pass flags 31.4 % (recall
0.758 / 0.959). It applies the mask on every baseline, then again up to
550 m. Without the mask, SumThreshold at 4.5-6σ recalls 1.4-5.5 % of the
mask cells, about its false-flag rate of 1.2-3.4 %. At the tutorial's 5σ
that is 3.3 %. A uvcontsub step before it flags 39.5 % with recall 0.44:
no better than chance. The tutorial applies the mask on baselines up to
1 km only, unlike CARACal's 550 m, and flags 36.4 %. It was chosen on this
one MS, so it is tuned to it. The tutorial and the strategy file both say
so.

**CI bounds** (`tools/e2e/run.py` BOUNDS) were chosen after this one run.
They are wide enough to allow for other platforms' arithmetic:

| Quantity | Bound |
| --- | --- |
| Flagged fraction | 0.30-0.43 |
| Brightest peak | 0.475-0.525 Jy |
| Residual rms | 0.5-1.0 mJy |
| BMAJ | 26-32″ |
| BMIN | 4.5-5.5″ |
| Largest MODEL_DATA amplitude on the target | 0.05-5 Jy |

The job also checks:

- every stage `done`;
- the four flag versions, MODEL_DATA, CORRECTED_DATA (finite on the
  unflagged target cells);
- the five CASA tables, the five FITS files and the receipt's schema;
- the circular-feed refusal (exit 2, words, FLAG, DATA and the flag
  versions unchanged);
- with `--installed`, that `rang` is imported from the wheel, not from the
  checkout.

## 4. Placeholders for E2

The tutorial's section 6, "On a real MeerKAT observation", is marked as a
placeholder. It will quote four things from E2: wall time per stage and
the machine, the flagged fraction against CARACal's, the tables against
CASA's and CARACal's, and image rms, dynamic range and fluxes against
CARACal and WSClean. Nothing there is filled in yet.

## 5. CI runs (branch `claude/focused-snyder-580a11`, commit `5417157`)

`wheels.yml` does not run on branch pushes, so it was dispatched with
`gh workflow run wheels.yml --ref claude/focused-snyder-580a11`: run
[43017536385](https://github.com/gijzelaerr/rang-core/actions/runs/43017536385).
Every job passed: the 5 wheels, the sdist, the 10 `test` cells and the 5
`e2e` cells. `release` and `publish` were skipped. The push's `docs` run
[43017518270](https://github.com/gijzelaerr/rang-core/actions/runs/43017518270)
also passed. It executed notebook 00 in 16.7 s, the CLI page check passed,
and `sphinx-build -W` passed.

`e2e` cells, from their `e2e.json` artifacts. 36 checks each, all passed,
and `rang` was imported from the installed wheel in every cell:

| Platform | Job wall | generate | `run` | flagged | peak (Jy/beam) | residual rms (mJy) | beam (″) | MODEL_DATA max (Jy) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| linux-x86_64 | 40 s | 3.8 s | 8.3 s | 0.3638 | 0.4957 | 0.705 | 29.00 × 4.97 | 1.629 |
| linux-aarch64 | 33 s | 3.0 s | 10.2 s | 0.3638 | 0.4957 | 0.705 | 29.00 × 4.97 | 1.629 |
| macos-arm64 | 49 s | 4.8 s | 16.4 s | 0.3638 | 0.4957 | 0.705 | 29.00 × 4.97 | 1.629 |
| macos-x86_64 | 128 s | 13.6 s | 54.6 s | 0.3638 | 0.4957 | 0.705 | 29.00 × 4.97 | 1.630 |
| windows-x86_64 | 51 s | 4.6 s | 11.0 s | 0.3638 | 0.4957 | 0.705 | 29.00 × 4.97 | 1.630 |

The numbers agree across platforms to the digits shown. The next commit changed only comments in
`strategy.yaml`, the notebook's prose, a research script and this note.
None of them changes what `e2e` runs, so this run stands for that commit
too. Only the
MODEL_DATA maximum differs, in its fourth digit. Each cell finishes within
the 5-minute aim, the slowest being macos-x86_64 at 128 s. The bounds of
section 3 are much wider than the spread seen, so they could be tightened
later.

## 6. Found on the way

- **A1 under a wheel install.** `rang.simtruth` looks for
  `data/meerkat.itrf.txt` two directories above its own file, which is the
  repository root only in a source checkout. Under a wheel,
  `examples/a1_simtruth.py generate` failed with FileNotFoundError (tested
  with the package copied outside the checkout). The generator now points
  `simtruth.ITRF` at its own checkout's table when the package's is
  missing, in the parent and in spawned workers. Shipping the table as
  package data is V3's owner decision 4 and is not done here.
- **Strategy YAML in flow style.** A strategy entry written as
  `- {name: x, task: y}` fails in `core_flag.parse_strategy`
  (`encode_steps`) with `KeyError: 'task'` and no message naming the file.
  This is a follow-up, not fixed here.
- **Landing pages were stale.** README and `docs/index.md` still said
  GeMClean is not in the wheels (it is since G8), and the README command
  table said calibrate is "`complex` only so far". Both are corrected.

## 7. For the coordinator

1. At merge, run the full `python -m rang.check` (left to the coordinator:
   the heavy lock was held by E2).
2. Owner decision: should `release` and `publish` in `wheels.yml` also
   `need` the `e2e` job? Today only `wheel`, `sdist` and `test` gate a
   release.
3. Owner decision (V3 4): ship `meerkat.itrf.txt` as package data so A1 can
   be written from a plain `pip install`.
4. Fill section 4 of this note and the tutorial's section 6 from E2's
   archive when E2 lands; E5 reviews the result.
