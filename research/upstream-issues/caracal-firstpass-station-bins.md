# CARACal: first-pass strategy empties station-bins on pre-flagged calibrator data

Repository: caracal-pipeline/caracal. Status: **not filed: reproduced, but indistinguishable
from intended RFI excision; no defect shown.** Checked 2026-10-30 (task U2). Different from
[caracal-firstpass-intermediate-flags.md](caracal-firstpass-intermediate-flags.md), which was
about the intermediate flag state inside one run; this is about the final output removing
every usable sample of solver bins.

Origin: [../luno-array-campaign.md](../luno-array-campaign.md) (on main after the L1 merge):
on 60 % pre-flagged LUNO data the first pass flagged 762,924 new cells and every training
sample of stations 4 and 5 in gain frequency bin 9, so the solver lost those gains.

- Reproduction: Tricolour 0.2.1 (PyPI, Numba 0.60.0, Python 3.12) with
  `mk_rfi_flagging_calibrator_fields_firstpass.yaml` from CARACal 1.2.1 (unchanged on
  `master` 8f7bb363), CARACal's arguments (`-fs polarisation -dc DATA -wb numpy -fn
  J1939-6342`), on scan 9 of `outer_scans.zip`: (a) native flags (51.5 % of cross samples), (b)
  native flags widened channel by channel to 60.7 % (as a wider static mask would). Counted
  station x (2 dumps x 32 channels) bins with at least one usable cross sample before and none
  after (`guard/bins.py`, `guard/specific.py`).
- (a) cross flags 51.5 -> 67.7 %, 55,757 new cells; 357 of 2,186 usable station-bins lost
  (median 152 usable samples before, up to 192); 318 of the 357 are bins lost by all four
  stations at once (124 channels newly flagged on every cross row), 39 are station-specific.
  (b) 60.7 -> 71.9 %, 38,694 new cells; 383 of 2,148 lost, 328 by all stations, 55
  station-specific. At 1 x 1 intervals: 31,977 and 21,699 of about 1e5 usable bins lost.
- Why not filed: the losses are mostly whole channels and dumps flagged on every baseline,
  which is what the strategy is for; without RFI ground truth for scan 9 there is no evidence
  that good data was removed. A "minimum unflagged fraction per station/channel block" guard
  would by construction keep RFI the flagger found, and solvers already flag empty bins.
  The LUNO consequence (unavailable held-out losses) came from rang's split-before-flagging
  design. A documentation note was considered and not proposed without a demonstrated harm.
- Cost: Tricolour 514.9 s for (a) with a cold Numba cache on a load-50 host (run under
  `script` to avoid the 300 s ProgressBar wait, tricolour #110), 12.7 s for (b) warm;
  0.44-0.76 GB RSS.
