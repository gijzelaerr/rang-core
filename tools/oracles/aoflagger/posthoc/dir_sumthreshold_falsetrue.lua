function execute(input)
  local missing = input:copy()
  local data = input:copy()
  local all_flagged = input - input
  all_flagged:flag_zeros()
  data:set_mask(all_flagged)
  aoflagger.sumthreshold(data, 1.0/6.0, 1.0/6.0, false, true)
  input:set_mask(data)
end
