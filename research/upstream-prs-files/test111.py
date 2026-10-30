

def test_sum_threshold_flagger_integer_parameters():
  """Integer values of float parameters must not compile another kernel specialisation (#111)"""
  rs = np.random.RandomState(seed=1)
  vis = np.abs(rs.standard_normal((2, 2, 32, 64))).astype(np.float32)
  flags = np.zeros(vis.shape, np.bool_)
  int_kw = dict(
    outlier_nsigma=10,
    background_reject=2,
    spike_width_time=2,
    spike_width_freq=10,
    flag_all_time_frac=1,
    flag_all_freq_frac=1,
    rho=1,
  )
  float_kw = {k: float(v) for k, v in int_kw.items()}

  expected = flagging.sum_threshold_flagger(vis, flags, num_major_iterations=1, **float_kw)
  nsignatures = len(flagging._get_flags_impl.signatures)
  out_flags = flagging.sum_threshold_flagger(vis, flags, num_major_iterations=1, **int_kw)
  assert len(flagging._get_flags_impl.signatures) == nsignatures
  np.testing.assert_array_equal(out_flags, expected)
