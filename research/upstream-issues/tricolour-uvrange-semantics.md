# Tricolour 0.5.0: `apply_static_mask` `uvrange` now means |uvw|, where 0.2.x used 0.5·|Δp|²

Repository: ratt-ru/tricolour (with caracal-pipeline/caracal for the strategies). Status:
**not filed; text for the coordinator (list or file after the user's say).** Found by task
RV1 ([../rv1-revalidate.md](../rv1-revalidate.md)) on 2026-10-30, reading `0.5.0-dev`
`367ff54` against 0.2.1 and reproduced with both versions on a synthetic case
(`outputs/rv1-20261030-logs/uvrange_demo.py`, `uvrange-demo.log`). It is a behaviour change
of a release still to come, not a regression in a released version. The 0.5.0 rule looks
like the intended one, so this asks for a release note and a CARACal check rather than a code
change.

<!-- issue-title: 0.5.0: apply_static_mask's uvrange selects |uvw| <= hi, where 0.2.x selected 0.5*|dp|^2 <= hi^2 (a sqrt(2) wider range); worth a release note -->
<!-- issue-body -->
**What changed**
In 0.2.1 (`tricolour/flagging.py`, `apply_static_mask`) a baseline is selected for the static
mask when `d2 = 0.5 * sum((antspos[a1] - antspos[a2])**2)` lies in `[lo**2, hi**2]`. That is
`|Δp| <= sqrt(2) * hi`, so CARACal's `uvrange: "0~550"` (in `mk_rfi_flagging_calibrator_fields_firstpass.yaml`
and `mk_rfi_flagging_target_fields_firstpass.yaml`) masks baselines up to about 778 m. On
`0.5.0-dev` (`src/tricolour/core/kernels/flagging.py`, from at least `367ff54`) the selection
is per baseline and time on `sqrt(sum(uvw**2)) in [lo, hi]`, so the same strategy masks
baselines up to 550 m. Because |uvw| equals the baseline length, that is exactly the
`sqrt(2)` factor.

**To reproduce**
Three baselines of 300, 700 and 900 m, one time, the shipped `4k_lband_meerkat` mask on
4096 L-band channels, `apply_static_mask(..., accumulation_mode="or", uvrange="0~550")`:

| Version | 300 m | 700 m | 900 m |
| --- | ---: | ---: | ---: |
| 0.2.1 (PyPI; NumPy 2.0.2, Numba 0.60.0, Python 3.12) | 1700 channels masked | 1700 | 0 |
| 0.5.0-dev `367ff54` (NumPy 2.5.4, Numba 0.68.1, Python 3.13) | 1700 | 0 | 0 |

On the full MeerKAT array (56 antennas, positions from a public L-band calibrator store),
165 of 1540 cross baselines lie between 550 and 778 m: 629 are masked under the 0.2.x rule
and 464 under 0.5.0's.

**Expected**
The 0.5.0 behaviour matches the documented meaning ("uvrange (only accepts meters) in CASA
style"). Users who upgrade will see fewer static-mask flags on 550–778 m baselines with
unchanged strategy files. A line in the 0.5.0 release notes, and a check by the CARACal
maintainers that 550 m (and not the effective 778 m) is what the first-pass strategies
intend, would avoid surprises.

**Context**
Everything else we compared was identical. Tricolour 0.5.0-dev `367ff54` reproduced 0.2.1
on four archived CARACal first-pass and mild-strategy runs (140 rows × 4096 channels, four
stations, baselines below 75 m, so the uvrange change cannot act there). That held flag for
flag, in every strategy step, in the polarised intensity bit for bit, and in the end-to-end
`tricolour` CLI.
<!-- /issue-body -->
