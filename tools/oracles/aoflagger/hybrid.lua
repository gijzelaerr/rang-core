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
 1.5^log2(L) / L in units of Tricolour's chi_1. Output mask: the detections.

 Post-hoc fixes (2026-10-31, run -10; the frozen run -04 is void):
 1. The frozen version set the all-flagged mask with clear_mask() +
    invert_mask(). In 3.5 clear_mask removes the mask (SetNoMask) and
    invert_mask only inverts existing masks, so the noise estimate was not
    disabled. A zero image with flag_zeros() gives the all-flagged mask.
 2. In 3.5.0, Functions::sumthreshold_masked (lua/functionswrapper.cpp)
    reads its direction flags from Lua arguments 4 and 5 instead of 5 and 6:
    the horizontal (x) pass always runs (argument 4 is a number, which is
    true in Lua) and the vertical pass follows the x_direction argument.
    The driver therefore lays every pass out along x, and RANG_AFLAG_PARAMS
    selects `vertical` only for width-1 images, where the horizontal pass is
    a plain L = 1 threshold and the vertical pass is the masked
    (VerticalStacked) SumThreshold.
]]

aoflagger.require_min_version("3.5")

function execute(input)
  local P = dofile(os.getenv("RANG_AFLAG_PARAMS"))
  local missing = input:copy()
  local data = input:copy()
  local all_flagged = input - input
  all_flagged:flag_zeros()
  data:set_mask(all_flagged)
  -- 3.5.0 argument handling: (…, a, b) runs horizontal always, vertical = a.
  aoflagger.sumthreshold_masked(data, missing, 1.0 / 6.0, 1.0 / 6.0, P.vertical, false)
  input:set_mask(data)
end
