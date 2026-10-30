# CARACal: first-pass Tricolour strategy drops and rebuilds flags on pre-flagged data

Repository: caracal-pipeline/caracal (not under ratt-ru). Status: **not filed: behaves as
designed.** Checked 2026-10-30.

- Observation ([core-k-luno-campaign.md](../core-k-luno-campaign.md)): on a 2048-channel
  sub-band that is already 70 % flagged, `mk_rfi_flagging_calibrator_fields_firstpass.yaml`
  (CARACal 8f7bb363) runs `uvcontsub_flagger` with `or_original_from_cycle: 1`, which discards
  the running flags (39 %), then static masks and SumThreshold rebuild them (66 %) and
  `combine_with_input_flags` restores the input; 166 new cells in all.
- Why not filed: `or_original_from_cycle: 1` is documented in Tricolour's `uvcontsub_flagger`
  docstring ("1 therefore discard starting flags") and the final combine step restores the
  input flags, so the output is as intended. The intermediate fraction only matters to someone
  reading per-step logs. Tricolour and rang's port agree flag for flag
  ([core-d-tricolour.md](../core-d-tricolour.md)).
- Organisation: CARACal lives under `caracal-pipeline`, not `ratt-ru`; any future CARACal
  report needs the user's confirmation that it counts as RATT software.
