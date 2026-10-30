--[[
 A-FLAG mapped strategy (research/a-flag-aoflagger.md, section 2.2): one
 Tricolour `sum_threshold` step of CARACal's first-pass (and mild) strategy,
 translated onto the AOFlagger 3.5 Lua API in AOFlagger's own idiom.

 Input: one real image per baseline (polarisation I, amplitude): the core's
 polarised intensity, width = time, height = channel; the input mask holds
 the running window flags before the step. Output mask: the step's detections
 of the last major iteration (the driver ORs them with the input flags and
 with the NaN cells, as Tricolour's executor and `_get_flags_impl` do).

 Per-stage parameters are read from the Lua table file named by the
 environment variable RANG_AFLAG_PARAMS (written by examples/oracle_aoflagger.py):
   ntime, outlier_nsigma, spike_width_time, spike_width_freq, num_major_iterations

 Mapping (every place the two algorithms differ is listed in the protocol):
 - outlier_nsigma -> sumthreshold sensitivity 0.2441 * n, the Gaussian
   calibration of AOFlagger's winsorized-mode noise estimate against
   Tricolour's 1.4826 * MAD (frozen in section 1 before any control data).
 - windows_time / windows_freq / rho -> AOFlagger's fixed lengths 1..256
   with effective rho 4/3 (not settable from Lua).
 - spike_width_time / _freq -> high_pass_filter with variance spike_width^2
   (the Lua arguments are variances, A4) on Tricolour's kernel support 8r+1.
 - background_iterations / background_reject -> not expressible; AOFlagger's
   idiom instead recomputes the high-pass with the flags so far in each major
   iteration.
 - time-median spectrum -> masked time-mean spectrum (downsample), 1-D
   high-pass, sumthreshold_masked along frequency, broadcast in time.
 - input flags -> `missing` (sumthreshold_masked), AOFlagger's documented way.
 - time_extend / freq_extend -> scale_invariant_rank_operator_masked with
   generic-default's eta = 0.2 per major iteration; flag_all_*_frac -> none.
]]

aoflagger.require_min_version("3.5")

local SENS_PER_SIGMA = 0.2441

local function support(sigma)
  local r = math.floor(0.5 * math.sqrt(12.0 * sigma * sigma / 4.0 + 1.0))
  return 8 * r + 1
end

function execute(input)
  local P = dofile(os.getenv("RANG_AFLAG_PARAMS"))
  local sens = SENS_PER_SIGMA * P.outlier_nsigma
  local kx, ky = support(P.spike_width_time), support(P.spike_width_freq)
  local vx, vy = P.spike_width_time ^ 2, P.spike_width_freq ^ 2

  local original = input:copy() -- input flags, used as `missing`
  local iter = input:copy() -- running flags of the major iterations
  local result = nil
  for _ = 1, P.num_major_iterations do
    -- Spectrum: masked time-mean, 1-D background, SumThreshold along frequency.
    local spec = aoflagger.downsample(iter, P.ntime, 1, true)
    local spec_missing = spec:copy()
    aoflagger.high_pass_filter(spec, 1, ky, 1.0, vy)
    aoflagger.sumthreshold_masked(spec, spec_missing, sens, sens, false, true)
    local spec_full = iter:copy()
    aoflagger.upsample_mask(spec, spec_full, P.ntime, 1)

    -- 2-D background and SumThreshold in both directions (interleaved).
    local resid = iter:copy()
    resid:join_mask(spec_full)
    aoflagger.high_pass_filter(resid, kx, ky, vx, vy)
    aoflagger.sumthreshold_masked(resid, original, sens, sens, true, true)
    resid:join_mask(spec_full)

    -- Dilation (AOFlagger's scale-invariant rank operator).
    aoflagger.scale_invariant_rank_operator_masked(resid, original, 0.2, 0.2)

    result = resid
    iter:join_mask(resid)
  end
  input:set_mask(result)
end
