function execute(input)
  local missing = input:copy()
  local data = input:copy()
  local all_flagged = input - input
  all_flagged:flag_zeros()
  data:set_mask(all_flagged)
  local sens = tonumber(os.getenv("RANG_SENS") or "1")
  aoflagger.sumthreshold_masked(data, missing, sens, sens, true, true)
  input:set_mask(data)
end
