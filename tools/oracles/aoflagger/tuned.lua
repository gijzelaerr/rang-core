--[[
 A-FLAG tuned strategy (research/a-flag-aoflagger.md, section 2.2): one
 Tricolour `sum_threshold` step reproduced as closely as the AOFlagger 3.5 Lua
 API allows. Same input, output and parameter file as tricolour-firstpass.lua.

 Differences from the mapped strategy, each towards Tricolour:
 - high_pass_filter variance = the 4-pass box cascade's effective variance
   4((2r+1)^2 - 1)/12 with Tricolour's r = floor(0.5 sqrt(12 sigma^2/4 + 1)),
   on Tricolour's support 8r+1;
 - flagged samples are set to 0 and stay in the sums, as `_average_freq`
   zeroes them (plain `sumthreshold`, not `_masked`);
 - Tricolour's order: spectrum, then the time pass alone, then the frequency
   pass alone with the spectrum and time flags in the noise-estimate mask;
 - no dilation (Tricolour's box smearing and fraction cuts have no Lua
   counterpart).
 What remains different (not expressible): lengths 1..256 and rho 4/3; one
 global noise estimate per baseline instead of per channel / per chunk; the
 background rejection loop; mean instead of median spectrum; kernel shape.
]]

aoflagger.require_min_version("3.5")

local SENS_PER_SIGMA = 0.2441

local function box_cascade(sigma)
  local r = math.floor(0.5 * math.sqrt(12.0 * sigma * sigma / 4.0 + 1.0))
  return 8 * r + 1, 4.0 * ((2 * r + 1) ^ 2 - 1) / 12.0
end

function execute(input)
  local P = dofile(os.getenv("RANG_AFLAG_PARAMS"))
  local sens = SENS_PER_SIGMA * P.outlier_nsigma
  local kx, vx = box_cascade(P.spike_width_time)
  local ky, vy = box_cascade(P.spike_width_freq)
  if vx <= 0 then vx = 1e-6 end
  if vy <= 0 then vy = 1e-6 end

  local zero = input - input -- zero image (the driver feeds finite values)
  local iter = input:copy()
  local result = nil
  for _ = 1, P.num_major_iterations do
    local work = iter:copy()
    work:set_masked_visibilities(zero) -- flagged samples are 0, as _average_freq

    -- Spectrum.
    local spec = aoflagger.downsample(work, P.ntime, 1, true)
    aoflagger.high_pass_filter(spec, 1, ky, 1.0, vy)
    aoflagger.sumthreshold(spec, sens, sens, false, true)
    local spec_full = work:copy()
    aoflagger.upsample_mask(spec, spec_full, P.ntime, 1)
    work:join_mask(spec_full)

    -- 2-D background with the input and spectrum flags masked.
    local resid = work:copy()
    aoflagger.high_pass_filter(resid, kx, ky, vx, vy)

    -- Time pass alone, then the frequency pass with the time flags in the
    -- noise-estimate mask.
    local tdet = resid:copy()
    aoflagger.sumthreshold(tdet, sens, sens, true, false)
    local fdet = resid:copy()
    fdet:join_mask(tdet)
    aoflagger.sumthreshold(fdet, sens, sens, false, true)

    local det = tdet:copy()
    det:join_mask(fdet)
    det:join_mask(spec_full)
    result = det
    iter:join_mask(det)
  end
  input:set_mask(result)
end
