Target: https://gitlab.com/aroffringa/aoflagger/-/issues
Status: ready to post (low priority; documentation, one small behaviour question)
Reproduced on: read in source at master 811f8e09261f04e97a4802a23635eee125fbf4b7 and v3.5.0 f4ee4cf; (2) also run on AOFlagger 3.5.0
Duplicates checked: AOFlagger issues/MRs ("high_pass_filter", "sigma", issues for "invert_mask"; none found; "clear_mask" and MRs for "invert_mask" not run, gitlab.com API rate limit; nearest MR !122 "Fix error in sumthreshold Lua documentation")
Title: Lua docs: high/low_pass_filter take sigma squared; invert_mask after clear_mask does nothing
---
1. `doc/source/lua_functions.rst` documents `high_pass_filter(data, xsize, ysize, xsigma, ysigma)`
   and `low_pass_filter(...)` with "xsigma: Gaussian width in time direction". The values go to
   `HighPassFilter::SetHKernelSigmaSq` / `SetVKernelSigmaSq` (`lua/functions.cpp:207-235`) and the
   kernel is `exp(-0.5 x^2 / sigmaSquared)` (`util/rng.cpp:84-86`), so they are variances in
   samples^2: the shipped `low_pass_filter(resized_data, 21, 31, 2.5, 5.0)` is a Gaussian of sigma
   1.58 x 2.24 samples, not 2.5 x 5. Changing the code would change every strategy, so we suggest
   only renaming the parameters in the docs (`xsigma2`, `ysigma2`, "squared Gaussian width, in
   samples^2").

2. `Data:clear_mask()` is documented as "Unflags all visibilities (sets all flags to false)"
   (`doc/source/lua_class_data.rst:70-73`) but calls `SetNoMask()` (`lua/data.h:83`).
   `Data:invert_mask()` then loops over `MaskCount()`, which is 0 (`lua/datawrapper.cpp:278-287`),
   so `data:clear_mask(); data:invert_mask()` leaves the data unflagged rather than fully flagged,
   without an error. Other functions treat "no mask" as all-false. Either `invert_mask` could
   create an all-true mask when there is none, or the docs could note that a cleared mask cannot be
   inverted (`flag_zeros()` on a zero image is a working "flag everything").
