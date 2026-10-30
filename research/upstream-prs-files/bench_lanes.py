"""Time sum_threshold_flagger on synthetic windows; the tricolour on sys.path decides the variant.

usage: python -I bench_lanes.py <label> <repeats> <out.npz>
"""
import json
import sys
import time

import numpy as np
import numba

import tricolour
from tricolour.core.kernels import flagging

label, repeats, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]

# background_flags step of the 0.5.0-dev default strategy (floats written as floats)
KW = dict(
  outlier_nsigma=10.0, windows_time=[1, 2, 4, 8], windows_freq=[1, 2, 4, 8], background_reject=2.0,
  background_iterations=5, spike_width_time=12.5, spike_width_freq=10.0, time_extend=3, freq_extend=3,
  freq_chunks=10, average_freq=1, flag_all_time_frac=0.6, flag_all_freq_frac=0.8, rho=1.3,
  num_major_iterations=1,
)
SHAPES = {"64x4096": (4, 1, 64, 4096), "32x2048": (8, 1, 32, 2048), "256x1024": (2, 1, 256, 1024)}

rs = np.random.RandomState(42)
results = {"label": label, "file": flagging.__file__, "numba": numba.__version__, "times": {}}
flags_out = {}
for name, shape in SHAPES.items():
  nbl, ncorr, ntime, nchan = shape
  freq = np.linspace(0, 1, nchan)
  vis = (1.0 + 0.3 * np.sin(6 * freq))[None, None, None, :] + 0.05 * rs.standard_normal(shape)
  vis[:, :, :, nchan // 7 : nchan // 7 + 40] += 2.0  # broadband RFI block
  vis[:, :, ntime // 3, :] += 1.0  # bad dump
  vis[:, :, :, nchan // 2] += 0.5  # narrow channel
  vis = np.abs(vis).astype(np.float32)
  flags = np.zeros(shape, np.bool_)
  flags[:, :, :, :nchan // 64] = True
  flagging.sum_threshold_flagger(vis, flags, **KW)  # warm up (and compile)
  times = []
  for _ in range(repeats):
    t0 = time.perf_counter()
    f = flagging.sum_threshold_flagger(vis, flags, **KW)
    times.append(time.perf_counter() - t0)
  results["times"][name] = times
  flags_out[name] = f
np.savez_compressed(out, **flags_out)
print(json.dumps(results))
