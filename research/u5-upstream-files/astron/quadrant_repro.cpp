// Fit2DGaussianCentred sees only the x>=0, y>=0 quadrant of its box.
// Build: g++ -O2 -std=c++17 -I schaapcommon/include/schaapcommon/fitters -I schaapcommon/include
//        -I aocommon/include quadrant_repro.cpp schaapcommon/src/fitters/gaussianfitter.cc -lgsl -lgslcblas
#include <cmath>
#include <cstdio>
#include <vector>
#include "schaapcommon/fitters/gaussianfitter.h"

int main() {
  const size_t n = 64;
  const double fwhm_maj = 8.0, fwhm_min = 5.0, pa = 30.0 * M_PI / 180.0;
  const double k = 2.0 * std::sqrt(2.0 * std::log(2.0));
  const double smaj = fwhm_maj / k, smin = fwhm_min / k;
  std::vector<float> a(n * n), b(n * n), c(n * n);
  for (size_t yi = 0; yi != n; ++yi)
    for (size_t xi = 0; xi != n; ++xi) {
      const double x = double(xi) - double(n / 2), y = double(yi) - double(n / 2);
      // major axis along PA measured from +y towards -x (any convention will do here)
      const double u = -x * std::sin(pa) + y * std::cos(pa);
      const double v = x * std::cos(pa) + y * std::sin(pa);
      const double g = std::exp(-0.5 * (u * u / (smaj * smaj) + v * v / (smin * smin)));
      const size_t i = yi * n + xi;
      a[i] = g;                                   // the Gaussian everywhere
      b[i] = (x >= 0 && y >= 0) ? g : 0.0f;       // only the x>=0, y>=0 quadrant kept
      c[i] = (x >= 0 && y >= 0) ? g : 0.5f;       // other quadrants a 0.5 plateau
    }
  for (auto* img : {&a, &b, &c}) {
    const auto e = schaapcommon::fitters::Fit2DGaussianCentred(img->data(), false, n, n, 6.0,
                                                                10.0, false);
    std::printf("major %.6f  minor %.6f  pa %.6f deg\n", e.major, e.minor,
                e.position_angle * 180.0 / M_PI);
  }
}
