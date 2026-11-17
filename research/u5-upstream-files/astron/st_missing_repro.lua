function execute(input)
  local missing = input:copy()   -- the flags passed to run() mark the missing samples
  local data = input:copy()
  aoflagger.sumthreshold_masked(data, missing, 1.0, 1.0, true, false)
  input:set_mask(data)
end
