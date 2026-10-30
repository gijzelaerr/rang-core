# Imaging: weighting, gridding and the replay

## Imaging weights

`rang.core_weights` ports WSClean 3.6's natural, uniform and Briggs
weighting: a weight grid of the padded image size over half the uv plane,
WSClean's rank filter (3.0 over 16 cells) and nearest-cell lookup, plus its
Stokes I formation from XX and YY. On all 19 oracle runs the weights are
bit-identical to the ones WSClean stored ({gh}`research/core-b-weighting.md`).
The defaults are rang's imaging settings: 512 pixels of 8 arcsec, padding
1.2. Briggs robustness trades sensitivity (natural, robust 2) against
resolution and sidelobes (uniform, robust −2); tutorial 4 sweeps it.

## Gridding

Two gridders turn weighted visibilities into a dirty image and its PSF.

**W-stacking** (`rang.core_grid`) ports WSClean 3.6-1's `WStackingGridder`
inversion path with its Measurement Set reader conventions. It matches
WSClean's dirty images and PSFs to at most 6.1e-7 of the peak on all fifteen
archived jobs, once WSClean's default image padding is modelled
({gh}`research/core-c-gridder.md`).

**The exact wgridder** (`rang.core_wgridder`) ports ducc0 0.42.0's wgridder
(Arras et al. 2021): `vis2dirty` and `dirty2vis`, f32 and f64, the
exponential-of-semicircle kernel and w-planes, with the kernel chosen by
ducc0's cost model for one thread so results are bit-identical at any thread
count. It agrees with ducc0 to 1e-12 to 1e-14 of the peak away from the
field edge and is adjoint to 4e-13. The 19 % difference between the
w-stacking image and a direct Fourier transform turned out to be aliasing of
WSClean's Kaiser–Bessel kernel at padding 1.2, not a defect
({gh}`research/df1-wgridder.md`). After DF2a it runs at ducc0's speed on
whole-array inputs ({gh}`research/df2-wgridder-speed.md`).

Both use the direct Fourier transform's sign and axis conventions documented
in the module docstrings, and `fits_image`/`write_fits` give WSClean's FITS
orientation.

## The imaging replay

`rang.core_imaging` reruns the fifteen archived dirty inversions of the
imaging track with the core's weights, w-stacking gridder and Measurement Set
reader instead of WSClean, and recomputes the archived template fits,
response fractions and closures with the unedited audit algebra. Pixels
agree within 6.1e-7 of the peak and template fluxes within 1.4e-7
({gh}`research/core-i-imaging-replay.md`). `rang-core imaging replay` runs it.

## Deconvolution

rang has no production deconvolver. The CLEAN study
({doc}`../research/index`) implements Högbom and Clark iterations in
`core/src/clean.rs` to measure what can and cannot be proven about them.
