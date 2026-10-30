-- Absolute-threshold probe: with every sample flagged in the data mask,
-- WinsorizedMode sees no samples and returns 0, so the factor is the
-- sensitivity itself. Threshold of the length-1 operation = 6 * sens.
function execute(input)
  local missing = input:copy()           -- input flags (the missing mask)
  local data = input:copy()
  data:clear_mask()
  data:invert_mask()                     -- all flagged
  local sens = tonumber(os.getenv("RANG_SENS") or "1")
  aoflagger.sumthreshold_masked(data, missing, sens, sens, true, true)
  input:set_mask(data)
end
