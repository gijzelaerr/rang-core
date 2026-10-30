"""Rows-as-lanes for the frequency axis of _box_gaussian_filter and _sum_threshold (run from a clone root)."""
p = "src/tricolour/core/kernels/flagging.py"
s = open(p).read()

old = """  if r[1] > 0:
    for i in range(data.shape[0]):
      _box_gaussian_filter1d(data[i], r[1], out[i], passes)
    need_copy = False
"""
new = """  if r[1] > 0:
    # Filter the transpose in blocks of columns, as for axis 0, so that the
    # inner loops run across rows instead of one row at a time.
    data_t = np.ascontiguousarray(data.T)
    out_t = np.empty_like(data_t)
    step = 256
    for i in range(0, data_t.shape[1], step):
      sub = slice(i, min(i + step, data_t.shape[1]))
      _box_gaussian_filter1d(data_t[:, sub], r[1], out_t[:, sub], passes)
    out[:] = out_t.T
    need_copy = False
"""
assert s.count(old) == 1
s = s.replace(old, new)

old = """  elif axis == 1:
    for i in range(input_data.shape[0]):
      _sum_threshold1d(input_data[i], input_flags[i], output_flags[i], windows, outlier_nsigma, rho, chunks)
"""
new = """  elif axis == 1 and input_data.ndim == 2:
    # Work on the transpose in blocks of columns, as for axis 0, so that the
    # inner loops run across rows instead of one row at a time.
    data_t = np.ascontiguousarray(input_data.T)
    flags_t = np.ascontiguousarray(input_flags.T)
    output_t = np.empty(data_t.shape, np.bool_)
    step = 256
    for i in range(0, data_t.shape[1], step):
      sub = slice(i, min(i + step, data_t.shape[1]))
      _sum_threshold1d(data_t[:, sub], flags_t[:, sub], output_t[:, sub], windows, outlier_nsigma, rho, chunks)
    output_flags[:] = output_t.T
  elif axis == 1:
    for i in range(input_data.shape[0]):
      _sum_threshold1d(input_data[i], input_flags[i], output_flags[i], windows, outlier_nsigma, rho, chunks)
"""
assert s.count(old) == 1
s = s.replace(old, new)
open(p, "w").write(s)
