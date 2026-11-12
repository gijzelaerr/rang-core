Target: https://gitlab.com/aroffringa/wsclean/-/issues
Status: ready to post
Reproduced on: read in source at WSClean master 486d0f5f2277818bd8082b5e7eb8b3f762b14bc3 (`gridding/msprovidercollection.cpp:28`) and v3.7 (`:27`); v3.4 used `vInL` (`gridding/msgridderbase.cpp:252`), so it changed in v3.5. Not observable on our test sets: on a MeerKAT MS imaged at 64^2 to 2048 x 128 px of 4", WSClean 3.7 logs the same w range and max uvw (the grid covers all baselines there)
Duplicates checked: WSClean issues/MRs ("CalculateMsLimits"; "w range" (8 issues, 6 MRs, none about the bounds test), "maximum uvw" (0), "MsLimits" (only !717) rerun 2026-11-12; nearest MR !717 "PAN-211 Move MS data initialisation", the v3.5 refactor that moved this code)
Title: CalculateMsLimits tests the y (v) bound with u
---
`gridding/msprovidercollection.cpp` (master 486d0f5):

```cpp
27  const double x = u * pixel_size_x * image_width;
28  const double y = u * pixel_size_y * image_height;   // should be v
29  const double imaging_weight = image_weights->GetWeight(u, v);
```

Up to v3.4 the same test was in `MSGridderBase` with `y = vInL * PixelSizeY() * ImageHeight()`.

With `y` computed from `u`, the "is this sample on the uv grid" test becomes
`|u| < 1/(2 dl_x)` and `|u| < 1/(2 dl_y)`; `|v|` is never checked. Samples whose `|v|` lies beyond
the grid therefore still count towards `max_w`, `min_w`, `max_baseline_uvw` and
`max_baseline_in_m`. Those feed the gridders' w range and `theoretical_beam_size_ = 1 / MaxBaseline()`
(`gridding/msgridder.cpp:26`), which also sets the restoring-beam fitting box. It only matters
when the pixel scale undersamples the longest v baselines (or when `pixel_size_x != pixel_size_y`,
e.g. via `-predict` from a FITS image), so most runs are unaffected.

Fix: `const double y = v * pixel_size_y * image_height;`
