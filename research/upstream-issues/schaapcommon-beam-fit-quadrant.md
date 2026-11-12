Target: https://git.astron.nl/RD/schaapcommon/-/issues (issue with the patch inline, not an MR; the anonymous API lists no schaapcommon issues at all, so if issues are disabled there, post at https://gitlab.com/aroffringa/wsclean/-/issues instead)
Status: ready to post
Reproduced on: schaapcommon master 35f91f8039d5d5d0cd73ddbb75af03898d185f05 (the commit WSClean master 486d0f5 pins), built against GSL 2.x and run with the snippet below; the same loops are in b553fd2 (the schaapcommon pinned by WSClean v3.7) and in every version back to d4a30343 (2022) and WSClean 3.0's math/gaussianfitter.cpp
Duplicates checked: schaapcommon issues and MRs ("gaussian", "fit", "quadrant", "unsigned", "size_t"; nearest MR !188 fit without negatives, !154 clean-up); WSClean issues/MRs ("beam fit", "fitted beam", "gaussian fit", "quadrant"; nearest issue #176 "Master Branch failing to fit synth beam", MR !668 "Fix beam fitting box size"; neither is this)
Title: Fit2DGaussianCentred fits only the x >= 0, y >= 0 quadrant of its box (unsigned pixel offsets)
---
`FittingCentered`, `FittingDerivativeCentered`, `FittingCircularCentered` and
`FittingDerivativeCircularCentered` in `src/fitters/gaussianfitter.cc` (at 35f91f8: lines 105-108,
128-131, 156-159, 189-192) loop with `size_t yi, xi` and compute

```cpp
const int y_mid = height / 2;
const double y = (yi - y_mid) * scale;   // size_t - int -> size_t
```

For `yi < y_mid` the difference wraps to about 1.8e19, the model is 0 there, and the residual is
the constant `-image`. Those pixels contribute nothing to the gradient, so only the quadrant
`x >= 0, y >= 0` of the fitting box shapes the result. This is the restoring-beam fit in WSClean
(`math/imageoperations.cpp`, `FitBeamSize`), for both the elliptical and the `-circular-beam` fit.

Reproduction: an elliptical Gaussian (8 x 5 px FWHM, PA 30 deg) in a 64 x 64 image, fitted
three times: unchanged; with the three other quadrants set to 0; with them set to a 0.5 plateau.

```cpp
#include <cmath>
#include <cstdio>
#include <vector>
#include "schaapcommon/fitters/gaussianfitter.h"
int main() {
  const size_t n = 64;
  const double k = 2.0 * std::sqrt(2.0 * std::log(2.0)), pa = 30.0 * M_PI / 180.0;
  const double smaj = 8.0 / k, smin = 5.0 / k;
  std::vector<float> a(n * n), b(n * n), c(n * n);
  for (size_t yi = 0; yi != n; ++yi)
    for (size_t xi = 0; xi != n; ++xi) {
      const double x = double(xi) - double(n / 2), y = double(yi) - double(n / 2);
      const double u = -x * std::sin(pa) + y * std::cos(pa), v = x * std::cos(pa) + y * std::sin(pa);
      const double g = std::exp(-0.5 * (u * u / (smaj * smaj) + v * v / (smin * smin)));
      const size_t i = yi * n + xi;
      const bool q = x >= 0 && y >= 0;
      a[i] = g; b[i] = q ? g : 0.0f; c[i] = q ? g : 0.5f;
    }
  for (auto* img : {&a, &b, &c}) {
    const auto e = schaapcommon::fitters::Fit2DGaussianCentred(img->data(), false, n, n, 6.0, 10.0, false);
    std::printf("major %.6f  minor %.6f  pa %.6f deg\n", e.major, e.minor, e.position_angle * 180.0 / M_PI);
  }
}
```

master 35f91f8:

```
major 8.000000  minor 5.000000  pa 30.000000 deg
major 8.000000  minor 5.000000  pa 30.000000 deg
major 8.000000  minor 5.000000  pa 30.000000 deg
```

with the patch below:

```
major 8.000000  minor 5.000000  pa 30.000001 deg
major 4.000470  minor 1.841248  pa 150.762652 deg
major 65.403911  minor 26.807338  pa 44.988163 deg
```

Effect on real PSFs (MeerKAT L-band, WSClean 3.7 defaults, the 10-beam box): the whole-box
least-squares fit gives 13.58" x 9.47" where WSClean writes 13.88" x 8.34", and 16.97" x 9.41"
where WSClean writes 16.86" x 9.62". A numpy fit restricted to the same quadrant reproduces
WSClean's header beam to 3e-7.

Second, smaller defect: the analytic Jacobian has the wrong sign on the beta terms. With
`G = exp(-x^2/(2 sx^2) + beta x y/(sx sy) - y^2/(2 sy^2))`,
`dG/dsx = (x^2/sx^3 - beta x y/(sx^2 sy)) G`; lines 166-167 have `+beta`. lmsder still
converged to the same minimum in the cases we tried. The same sign error is in `dsx`, `dsy`, `dx`, `dy` of
`FittingDerivativeWithAmplitude` and `FittingDerivativeWithAmplitudeAndFloor` (there is a TODO
about the signs at line 267); those loops already use `int`.

Suggested fix (centred functions only):

```diff
--- a/src/fitters/gaussianfitter.cc
+++ b/src/fitters/gaussianfitter.cc
@@ -102,9 +102,9 @@
-  for (size_t yi = 0; yi != height; ++yi) {
+  for (int yi = 0; yi != int(height); ++yi) {
     const double y = (yi - y_mid) * scale;
-    for (size_t xi = 0; xi != width; ++xi) {
+    for (int xi = 0; xi != int(width); ++xi) {
       const double x = (xi - x_mid) * scale;
(same change at lines 128/130, 156/158 and 189/191)
@@ -164,8 +164,8 @@
-        const double dsx = (beta * x * y / (sx * sx * sy) + x * x / (sx * sx * sx)) * exp_term;
-        const double dsy = (beta * x * y / (sy * sy * sx) + y * y / (sy * sy * sy)) * exp_term;
+        const double dsx = (-beta * x * y / (sx * sx * sy) + x * x / (sx * sx * sx)) * exp_term;
+        const double dsy = (-beta * x * y / (sy * sy * sx) + y * y / (sy * sy * sy)) * exp_term;
```

Fixing this changes every fitted restoring beam (BMAJ/BMIN/BPA) WSClean writes, by 1-14 % per
axis in the two cases above, so it probably wants a changelog line.
