

def test_frequency_axis_matches_per_row():
  """The frequency-axis paths, which work on the transpose in column blocks,
  must give the same bits as filtering and thresholding each row on its own."""
  rs = np.random.RandomState(seed=7)
  data = np.abs(rs.standard_normal((300, 700))).astype(np.float32)
  data[:, 350:360] += 4.0
  flags = rs.uniform(size=data.shape) < 0.05

  out = np.empty_like(data)
  flagging._box_gaussian_filter(data, np.array([0.0, 10.0]), out)
  r = int(0.5 * np.sqrt(12.0 * 10.0**2 / 4 + 1))
  expected = np.empty_like(data)
  for i in range(data.shape[0]):
    flagging._box_gaussian_filter1d(data[i], r, expected[i], 4)
  np.testing.assert_array_equal(out, expected)

  windows = np.array([1, 2, 4, 8])
  chunks = np.array([0, 300, 700])
  out_flags = flagging._sum_threshold(data, flags, 1, windows, 4.5, 1.3, chunks)
  expected_flags = np.empty_like(flags)
  for i in range(data.shape[0]):
    flagging._sum_threshold1d(data[i], flags[i], expected_flags[i], windows, 4.5, 1.3, chunks)
  np.testing.assert_array_equal(out_flags, expected_flags)
