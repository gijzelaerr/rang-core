--[[
 A-FLAG hybrid kernel test (research/a-flag-aoflagger.md, section 2.3).

 Input: an image of Tricolour's residual, normalised by Tricolour's own chi_1
 per column or chunk (examples/oracle_aoflagger.py builds it from the
 Tricolour dump); the input mask marks the `missing` samples (H1: padding
 only; H2: padding and Tricolour's input flags of the pass).

 With every sample of the data mask flagged, WinsorizedMode sees no samples
 and returns 0, so the sensitivity is used as the absolute factor (A3, an
 implementation detail of ThresholdConfig::ExecuteWithMissing in 3.5).
 With sens = 1/6 the length-L threshold on the window mean is
 1.5^log2(L) / L in units of Tricolour's chi_1. One direction per call:
 RANG_AFLAG_PARAMS names a table with `x` and `y` booleans.
 Output mask: the detections only.
]]

aoflagger.require_min_version("3.5")

function execute(input)
  local P = dofile(os.getenv("RANG_AFLAG_PARAMS"))
  local missing = input:copy()
  local data = input:copy()
  data:clear_mask()
  data:invert_mask()
  aoflagger.sumthreshold_masked(data, missing, 1.0 / 6.0, 1.0 / 6.0, P.x, P.y)
  input:set_mask(data)
end
