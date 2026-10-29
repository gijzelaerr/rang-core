# Static masks copied from Tricolour 0.2.1

`4k_lband_meerkat.staticmask` (SHA256 `96969417441917454186ddcf5fe2fbc4e9cc0aa464f8d072c917749164108c33`)
and `4k_uhfband_meerkat.staticmask` (SHA256 `2d862fbe61e7cf4b7799fb9cf7ceaff81860a26d70eb770816dfb2a3e8ddc1bb`)
are byte-for-byte copies of `tricolour/data/` in the Tricolour 0.2.1 wheel
(`tricolour-0.2.1-py3-none-any.whl`, SHA256
`7dd8dfcf8058bdc7351540d4d6248664169bab1debf8791234e9fa8846f1c63b`), the
version the archived CARACAL controls ran. They are NumPy `.npy` files with a
structured dtype `[("mask", bool), ("chans", float64)]` of shape `(2, 32768)`;
the mask is row 0 of `mask` and the channel centre frequencies in Hz are row 1
of `chans`, as `tricolour/mask.py` reads them. `TRICOLOUR-LICENSE` is the
licence file distributed with that wheel (BSD-3-Clause); see
`research/core-d-tricolour.md` section 1 for the licence decision.
